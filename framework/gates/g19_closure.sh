#!/usr/bin/env bash
# G19 -- Verification closure.
#
# Judges the verification matrix, not the diff: every acceptance criterion the plan declares
# must be closed by a FRESH, BOUND artifact from the gate its evidence class routed to, or by
# an explicit human waiver. `pending`, `fail` and `unverifiable` all refuse completion.
#
# WHY THIS GATE EXISTS
# ====================
# `AC-n` was minted by the plan lint and then dropped. Nothing downstream could answer "did
# AC-3 pass?", so a plan could declare `AC-1 [e2e] "portfolio renders four real periods"` and
# the only gate that ran (g6) drove a mocked scaffold spec and exited 0. The run was green and
# the requirement was untouched. This gate makes the requirement the unit of completion.
#
# Input: CLOSURE_MATRIX=<path>  or CLOSURE_PLAN=<plan.md>  or SYSTEM_PLAN / ENTRY_PLAN, or the
#        pointer written by `matrix.py emit` at <state_root>/verification/current.json.
# Exit: 0 every criterion pass or human-waived | 1 at least one criterion not closed |
#       2 BLOCKED (matrix/plan unreadable, python3 absent) | 3 UNVERIFIABLE (the matrix drifted
#       from the plan, or the pointer names a matrix that no longer exists) | 4 NOT_APPLICABLE
#       (no plan and no matrix given, or the plan declares no criteria)
GATE_NAME="g19_closure"
. "$(dirname "$0")/_lib.sh"

PASS=0
FAIL=1
BLOCKED=2
UNVERIFIABLE=3
NOT_APPLICABLE=4

have python3 || { log "BLOCKED  python3 unavailable -- closure unreadable"; persist blocked "no python3"; exit $BLOCKED; }

if [ ! -f framework/verifier/matrix.py ]; then
  persist blocked "framework/verifier/matrix.py missing"
  log "BLOCKED  framework/verifier/matrix.py missing -- cannot judge closure"
  exit $BLOCKED
fi

matrix="${CLOSURE_MATRIX:-}"
plan="${CLOSURE_PLAN:-${SYSTEM_PLAN:-${ENTRY_PLAN:-}}}"

if [ -z "$plan" ] && [ -n "${SYSTEM_TASK:-${ENTRY_TASK:-}}" ]; then
  task="${SYSTEM_TASK:-$ENTRY_TASK}"
  plan="$(python3 framework/adapters/gsd_state.py plan-path --task "$task" 2>/dev/null | tr -d '\r' || true)"
  plan="${plan//\\//}"
  case "$plan" in
    NOT_FOUND*) plan="" ;;
  esac
fi

args=()
[ -n "$matrix" ] && args+=(--matrix "$matrix")
[ -n "$plan" ] && args+=(--plan "$plan")
[ "${CLOSURE_STRICT:-0}" = "1" ] && args+=(--strict)
[ "${CLOSURE_ORPHANS:-0}" = "1" ] && args+=(--orphans)

out="$(python3 framework/verifier/matrix.py check "${args[@]}" 2>&1)"; rc=$?
out="$(printf '%s' "$out" | tr -d '\r')"

case "$rc" in
  "$PASS")
    persist pass "$out"
    pass "verification closure: $out" ;;
  "$FAIL")
    persist fail "$out"
    fail "verification closure refused: every acceptance criterion needs a passing, bound artifact or a human waiver"$'\n'"$out" ;;
  "$UNVERIFIABLE")
    persist unverifiable "$out"
    log "UNVERIFIABLE  $out"
    gate_result unverifiable 3
    exit $UNVERIFIABLE ;;
  "$NOT_APPLICABLE")
    persist not_applicable "$out"
    not_applicable "no criteria to close" \
      '{"checked":"framework/verifier/matrix.py check","plan":"'"${plan:-none}"'"}' ;;
  *)
    persist blocked "closure check exit $rc: $out"
    log "BLOCKED  closure check exit $rc: $out"
    exit $BLOCKED ;;
esac
