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
skip() { log "SKIP  $*"; exit 0; }
pass() { log "PASS  $*"; exit 0; }
fail() { log "FAIL  $*"; exit 1; }

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
