#!/usr/bin/env bash
# G18 -- security-audit artifact integrity, and completion refusal on open findings.
#
# Judges a completed security-audit run's artifacts, not prose:
#   - findings.json          validated by the skill's own validate-findings.cjs
#   - coverage-ledger.json   validated by the skill's own validate-coverage-ledger.cjs
# Then refuses completion while a CONFIRMED high/critical finding is unresolved -- the
# same enforcement shape G7 applies to retrospectives and G8 to blockers.
#
# The run directory is named by AUDIT_RUN_DIR (or $1); the validators are the vendored
# copies under framework/opencode/skills/security-audit/.
#
# Exit: 0 artifacts valid and no open confirmed high/critical finding | 1 invalid
#       artifacts, or an open confirmed high/critical finding | 2 BLOCKED (run dir or
#       required artifact missing/unreadable) | 3 UNVERIFIABLE (validators absent, or no
#       interpreter could judge -- the validators need O_NOFOLLOW, so a Windows node.exe
#       cannot judge any input and must not read as pass OR fail; the sandbox container
#       supplies a POSIX node when the host has none) | 4 NOT_APPLICABLE (no audit run)
GATE_NAME="g18_security_audit"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2
UNVERIFIABLE=3
NOT_APPLICABLE=4
SKILL_DIR="${AUDIT_SKILL_DIR:-framework/opencode/skills/security-audit}"
RUN_DIR="${AUDIT_RUN_DIR:-${1:-}}"

if [ -z "$RUN_DIR" ]; then
  not_applicable "no audit run directory (set AUDIT_RUN_DIR) -- nothing to judge" \
    '{"audit_run_dir": null}'
fi
if [ ! -d "$RUN_DIR" ]; then
  precondition_missing "audit run directory not found: $RUN_DIR" \
    "{\"audit_run_dir\": \"$RUN_DIR\"}"
fi

# The container backend binds these at their own absolute paths, so resolve them once.
_abs() { case "$1" in /*) printf '%s' "$1" ;; *) printf '%s/%s' "$PWD" "$1" ;; esac; }
RUN_DIR="$(_abs "$RUN_DIR")"
SKILL_DIR="$(_abs "$SKILL_DIR")"

FINDINGS="$RUN_DIR/findings.json"
LEDGER="$RUN_DIR/coverage-ledger.json"
[ -f "$FINDINGS" ] || precondition_missing "findings.json missing in audit run" \
  "{\"audit_run_dir\": \"$RUN_DIR\", \"missing\": \"findings.json\"}"
[ -f "$LEDGER" ] || precondition_missing "coverage-ledger.json missing in audit run" \
  "{\"audit_run_dir\": \"$RUN_DIR\", \"missing\": \"coverage-ledger.json\"}"

V_FIND="$SKILL_DIR/validate-findings.cjs"
V_LEDGER="$SKILL_DIR/validate-coverage-ledger.cjs"
[ -f "$V_FIND" ] || capability_missing "validators not installed at $SKILL_DIR (apply the plane bundle)" \
  "{\"skill_dir\": \"$SKILL_DIR\"}"
[ -f "$V_LEDGER" ] || capability_missing "ledger validator not installed at $SKILL_DIR" \
  "{\"skill_dir\": \"$SKILL_DIR\"}"

# Interpreter candidates, in order. The validators refuse to read input unless the OS
# enforces no-follow + nonblocking opens (a deliberate anti-symlink/anti-FIFO control).
# Windows node lacks O_NOFOLLOW, so a node.exe interop run reports "input protection is
# unavailable" for EVERY input -- including a valid one. That is an unverifiable
# interpreter, NOT an invalid artifact: it must not decide, and we fall through to the
# next candidate. A genuine schema rejection maps to exit 1. Never confuse the two.
POSIX_UNAVAILABLE="no-follow and nonblocking input protection is unavailable"

# A Windows node.exe cannot read a /mnt/c path; translate when interop is in use.
_native_path() { # <interp> <path>
  case "$1" in
    *.exe)
      if have wslpath; then wslpath -w "$2" 2>/dev/null || printf '%s' "$2"; else printf '%s' "$2"; fi
      ;;
    *) printf '%s' "$2" ;;
  esac
}

_run_native() { # <interp> <validator> <artifact>
  "$1" "$(_native_path "$1" "$2")" "$(_native_path "$1" "$3")" </dev/null 2>&1
}

# The container candidate runs the validator inside the sandbox image, which supplies a
# POSIX node (with O_NOFOLLOW) when the host has none. `run` fails closed: when the
# container is not enforceable here it prints an {"ok": false, ...} report and exits 3,
# which is "could not judge", so the caller falls through rather than reading a verdict.
_run_container() { # <validator> <artifact>
  local out rc
  out="$(python3 framework/adapters/sandbox.py run --backend container \
           --target "$RUN_DIR" --extra-ro "$SKILL_DIR" -- node "$1" "$2" </dev/null 2>&1)"; rc=$?
  case "$out" in
    '{"ok": false'*) return 3 ;;
  esac
  printf '%s' "$out"
  return "$rc"
}

_candidates() {
  local c
  for c in node node.exe; do have "$c" && printf 'native:%s\n' "$c"; done
  if [ "${SANDBOX_ALLOW_CONTAINER:-1}" != "0" ] && have python3; then
    printf 'container\n'
  fi
  return 0
}

validate() { # <validator> <artifact> ; echoes output ; 0 valid | 1 rejected | 3 unjudgeable
  local cand out="" rc=0
  local -a cands=()
  # Read every candidate up front. A child that consumes stdin must not be able to swallow
  # the rest of the list -- a Windows node.exe under WSL interop does exactly that, which
  # silently dropped the container fallback.
  mapfile -t cands < <(_candidates)
  for cand in "${cands[@]}"; do
    [ -n "$cand" ] || continue
    case "$cand" in
      native:*) out="$(_run_native "${cand#native:}" "$1" "$2")"; rc=$? ;;
      container) out="$(_run_container "$1" "$2")"; rc=$? ;;
      *) continue ;;
    esac
    if [ "$rc" = 0 ]; then printf '%s' "$out"; return 0; fi
    # rc=3 means this candidate could not judge (unjudgeable interpreter, or the container
    # was not enforceable here) -- never a verdict, so try the next one.
    if [ "$rc" = 3 ]; then continue; fi
    case "$out" in *"$POSIX_UNAVAILABLE"*) continue ;; esac
    # A genuine rejection (or a hard error) decides; do not paper over it.
    printf '%s' "$out"
    return 1
  done
  printf '%s' "$out"
  return 3
}

check_artifact() { # <validator> <artifact> <label>
  local out vrc
  out="$(validate "$1" "$2")"; vrc=$?
  case "$vrc" in
    0) return 0 ;;
    3)
      log "UNVERIFIABLE  $3: no interpreter candidate could judge (native node lacks POSIX protection; container unavailable)"
      persist blocked "validator unjudgeable ($3)"
      capability_missing "cannot validate $3: no POSIX-capable interpreter (native node and sandbox container both unavailable)" \
        "{\"artifact\": \"$3\", \"required\": \"linux node with O_NOFOLLOW, or the container backend (build framework/container/Dockerfile)\"}"
      ;;
    *)
      log "FAIL  $3 failed validation:"
      printf '%s\n' "$out" | sed 's/^/  /' | while IFS= read -r l; do [ -n "$l" ] && log "FAIL  $l"; done
      persist fail "$3 invalid"
      fail "audit artifacts invalid: $3"
      ;;
  esac
}

check_artifact "$V_FIND" "$FINDINGS" "findings.json"
check_artifact "$V_LEDGER" "$LEDGER" "coverage-ledger.json"

# An open confirmed high/critical finding is a blocker. (Overall severity is the
# schema's own field: severity.overall_severity.)
blocking="$(python3 - "$FINDINGS" <<'PY' 2>/dev/null || true
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
for f in data if isinstance(data, list) else []:
    sev = (f.get("severity") or {}).get("overall_severity")
    if f.get("verdict") == "confirmed" and sev in ("high", "critical"):
        print("%s\t%s\t%s" % (sev, f.get("fingerprint", "?"), f.get("title", "")))
PY
)"

if [ -n "$blocking" ]; then
  log "FAIL  open confirmed high/critical finding(s) -- completion refused:"
  printf '%s\n' "$blocking" | while IFS="$(printf '\t')" read -r sev fp title; do
    [ -n "$sev" ] && log "FAIL  $sev  $fp  $title"
  done
  n="$(printf '%s\n' "$blocking" | grep -c . || true)"
  persist fail "$n open confirmed high/critical finding(s)"
  fail "unresolved confirmed high/critical security finding(s): $n"
fi

persist pass "audit artifacts valid; no open confirmed high/critical finding"
pass "audit artifacts valid; no open confirmed high/critical finding"
