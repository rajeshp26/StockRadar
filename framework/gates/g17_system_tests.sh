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

have python3 || { log "BLOCKED  python3 unavailable"; persist blocked "no python3"; \
  precondition_missing "python3 unavailable; the system-test harness cannot run" '{"python3":null}'; }

plan="${SYSTEM_PLAN:-}"
if [ -z "$plan" ] && [ -n "${SYSTEM_TASK:-}" ]; then
  plan="$(python3 framework/adapters/gsd_state.py plan-path --task "$SYSTEM_TASK" 2>/dev/null | tr -d '\r')"
fi
if [ -z "$plan" ]; then
  not_applicable "no plan given (set SYSTEM_PLAN or SYSTEM_TASK); ASK completion is guarded separately" \
    '{"plan":null}'
fi
if [ ! -f "$plan" ]; then
  persist blocked "plan not readable"
  precondition_missing "plan not readable: $plan" "{\"plan\":\"$plan\"}"
fi

out="$(python3 framework/testing/run_system_tests.py verify --plan "$plan" 2>&1)"; rc=$?
out="$(printf '%s' "$out" | tr -d '\r')"
case "$rc" in
  0) persist pass "$out"
     # Bind the file the harness judged. `matrix.py check` requires a real-stack row to carry an
     # artifact hash for EVERY routed gate, and g17's evidence IS the green result document --
     # without it the criterion would read as "a gate said pass", which is the claim this whole
     # change exists to replace. The path is the harness's own convention (run_system_tests.py
     # `paths()`); verify() has already confirmed the file exists and is untampered.
     gate_artifact "${plan%.md}.system-tests.green.result.json"
     pass "system-test evidence verified: $out" ;;
  1) persist fail "$out"; fail "system-test evidence missing or invalid: $out" ;;
  3) persist unverifiable "$out"
     unverifiable "harness could not judge: $out" '{"harness_exit":3}' ;;
  4) persist not_applicable "$out"
     not_applicable "$out" '{"harness_exit":4}' ;;
  *) persist blocked "harness exit $rc: $out"
     precondition_missing "harness exit $rc: $out" "{\"harness_exit\":$rc}" ;;
esac
