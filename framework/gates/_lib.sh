#!/usr/bin/env bash
# Gates require bash (export -f, [[ ]], PIPESTATUS). Refuse clearly rather than
# misbehaving under sh, where a bad substitution can look like a gate verdict.
if [ -z "${BASH_VERSION:-}" ]; then
  echo "BLOCKED: framework gates require bash. Run: bash $0" >&2
  exit 2
fi

# Shared gate helpers. Every gate is a command with an exit code.
# The model interprets results; it does not decide whether a gate passed.
set -uo pipefail
GATE_NAME="${GATE_NAME:-gate}"
STATE_ROOT="$(python3 framework/adapters/gsd_state.py state-root 2>/dev/null || echo .planning)"
# Normalise to a cwd-relative path so it can be compared against changed_files() output.
case "$STATE_ROOT" in
  "$PWD"/*) STATE_ROOT="${STATE_ROOT#"$PWD"/}" ;;
  "$PWD")   STATE_ROOT="." ;;
esac

log()  { printf '[%s] %s\n' "$GATE_NAME" "$*"; }

# ─── Canonical [gate] protocol (P0-3) ─────────────────────────────────────────
# Every gate verdict is emitted on the canonical line so the telemetry plugin
# parses it from output text without filename heuristics:
#   [gate] <id> result=<pass|fail|unverifiable> exit=<code> ms=<ms>
# Disposal (an earlier condition prevented reaching the gate):
#   [gate] <id> result=not_reached
# The line is the protocol; the plugin's classifier additionally requires a
# matched launch (GATE_EXECUTION_STARTED) before any EXECUTED_* state.

# Gate start moment, captured at source time. GNU date +%s%N; anything that is
# not pure digits (macOS %N, missing date) falls back to 0 → ms reports 0.
GATE_START_MS="$(date +%s%N 2>/dev/null || true)"
case "$GATE_START_MS" in
  ''|*[!0-9]*) GATE_START_MS=0 ;;
esac

# Short gate id: g8_blockers → g8, g5-stack → g5, g_tool_utilization stays.
gate_id() {
  case "$GATE_NAME" in
    g[0-9]*) printf '%s\n' "${GATE_NAME%%[-_]*}" ;;
    *)       printf '%s\n' "$GATE_NAME" ;;
  esac
}

# Milliseconds since the gate started (0 when the clock is unavailable).
gate_elapsed_ms() {
  local now
  now="$(date +%s%N 2>/dev/null || true)"
  case "$now" in
    ''|*[!0-9]*) now=0 ;;
  esac
  if [ "$GATE_START_MS" = "0" ] || [ "$now" = "0" ]; then
    printf '0\n'
  else
    printf '%s\n' "$(( (now - GATE_START_MS) / 1000000 ))"
  fi
}

# Emit the canonical result line. result ∈ pass|fail|unverifiable.
gate_result() {
  local result="$1" exit_code="${2:-0}"
  printf '[gate] %s result=%s exit=%s ms=%s\n' "$(gate_id)" "$result" "$exit_code" "$(gate_elapsed_ms)"
}

# Emit the explicit NOT_REACHED disposal line (never inferred from absence).
gate_not_reached() {
  printf '[gate] %s result=not_reached\n' "$(gate_id)"
}

# Verdicts emit the canonical line alongside the human log line. skip() is a
# NON-FAILING verdict (exit 0, result=pass) — the gate was not applicable, not
# failed; the human SKIP line preserves the distinction for readers.
skip() { log "SKIP  $*"; gate_result pass 0; exit 0; }
pass() { log "PASS  $*"; gate_result pass 0; exit 0; }
fail() { log "FAIL  $*"; gate_result fail 1; exit 1; }

# Persist immediately — OpenCode prunes tool output.
persist() {
  local status="$1"; shift
  python3 framework/adapters/gsd_state.py write-verification \
    --phase "$(python3 -c 'import json,subprocess;print(json.loads(subprocess.run(["python3","framework/adapters/gsd_state.py","current-phase"],capture_output=True,text=True).stdout).get("current") or "00-unphased")' 2>/dev/null || echo 00-unphased)" \
    --json "gate: $GATE_NAME
status: $status
detail: $*
at: $(date -u +%FT%TZ)" >/dev/null 2>&1 || true
}

have() { command -v "$1" >/dev/null 2>&1; }

# Changed files = tracked modifications PLUS untracked additions.
# `git diff HEAD` alone misses new files, which silently turns gates into no-ops.
# Paths are emitted RELATIVE TO CWD, not to the git root. When the project lives in a
# subdirectory of a larger repo (monorepos, vendored trees), git reports repo-relative paths
# which never match project-relative dirs like ".planning/contracts" — silently turning every
# path-matching gate into a no-op that passes.
changed_files() {
  { git diff --name-only --relative HEAD 2>/dev/null
    git ls-files --others --exclude-standard --directory --no-empty-directory 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
  } | sed '/^$/d' | sort -u
}

# SOURCE changes only. Gates write their own verdicts into project state via persist(), so
# raw changed_files() reports gate output as a code change — the gate then analyses its own
# footprint, finds no tests for it, and reports UNKNOWN_IMPACT on a clean tree. Impact
# analysis must look at source, not at framework bookkeeping.
changed_source_files() {
  { git diff --name-only --relative HEAD 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
  } | sed '/^$/d' | sort -u | grep -v -E "^($STATE_ROOT/|\.opencode/|framework/telemetry/)" || true
}
export -f changed_source_files 2>/dev/null || true
export -f changed_files 2>/dev/null || true
