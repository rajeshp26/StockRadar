#!/usr/bin/env bash
# G17 -- System-test evidence (DID-017).
#
# Judges whether every real-stack acceptance criterion (integration | e2e | browser |
# data-invariant) in the plan has a FRESH, PASSING, UNTAMPERED black-box system-test result
# produced by framework/testing/run_system_tests.py: frozen suite byte-identical, real stack
# reached, no skips, JUnit and log hashes intact, code unchanged since the run, and a red-phase
# run proving the suite can fail. An agent cannot hand-write this evidence.
#
# Input: SYSTEM_PLAN=<plan.md>  (or SYSTEM_TASK=<task id>, resolved through the state adapter)
# Exit: 0 pass | 1 fail | 2 BLOCKED (python3/plan/policy unreadable) | 3 UNVERIFIABLE (the stack
#       was unreachable; never a pass) | 4 NOT_APPLICABLE (no plan given, or the plan has no
#       real-stack criteria)
GATE_NAME="g17_system_tests"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2
UNVERIFIABLE=3

have python3 || { log "BLOCKED  python3 unavailable"; persist blocked "no python3"; exit $BLOCKED; }

plan="${SYSTEM_PLAN:-}"
if [ -z "$plan" ] && [ -n "${SYSTEM_TASK:-}" ]; then
  plan="$(python3 framework/adapters/gsd_state.py plan-path --task "$SYSTEM_TASK" 2>/dev/null | tr -d '\r')"
fi
if [ -z "$plan" ]; then
  log "NOT_APPLICABLE  no plan given (set SYSTEM_PLAN or SYSTEM_TASK); ASK completion is guarded separately"
  gate_result not_applicable 4
  exit $NOT_APPLICABLE
fi
if [ ! -f "$plan" ]; then
  log "BLOCKED  plan not readable: $plan"
  persist blocked "plan not readable"
  exit $BLOCKED
fi

out="$(python3 framework/testing/run_system_tests.py verify --plan "$plan" 2>&1)"; rc=$?
out="$(printf '%s' "$out" | tr -d '\r')"
case "$rc" in
  0) persist pass "$out"; pass "system-test evidence verified: $out" ;;
  1) persist fail "$out"; fail "system-test evidence missing or invalid: $out" ;;
  3) persist unverifiable "$out"; log "UNVERIFIABLE  $out"; gate_result unverifiable 3; exit $UNVERIFIABLE ;;
  4) log "NOT_APPLICABLE  $out"; persist not_applicable "$out"; gate_result not_applicable 4; exit $NOT_APPLICABLE ;;
  *) persist blocked "harness exit $rc: $out"; log "BLOCKED  harness exit $rc: $out"; exit $BLOCKED ;;
esac
