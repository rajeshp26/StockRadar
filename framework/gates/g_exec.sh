#!/usr/bin/env bash
# G-EXEC -- Execution-integrity gate.
#
# Judges the control plane's execution behaviour against the adversarial E/G matrix
# (framework/adapters/failure_injection.py): a worker that deviates from its declared
# contract -- wrong budgets, out-of-order lifecycle events, THINKING while paused,
# leaked supervision state -- earns exit 1 here, because an observability framework
# that cannot detect its own control-plane drift under adversarial injection has no
# integrity to report.
#
# This gate exists because the framework previously claimed execution fidelity on the
# strength of the adapter's own unit tests. Injection is the independent check that the
# claim holds under deviation, not just under the happy path. The matrix is
# self-cleaning: residue left in the task store after a run is itself a deviation.
#
# Exit: 0 matrix 38/38 checks pass | 1 deviations listed | 2 BLOCKED (python3/state
#       root unreadable -- never a pass) | 4 NOT_APPLICABLE (matrix module absent)
GATE_NAME="g_exec"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- matrix unreadable"; persist blocked "no python3"; exit $BLOCKED; }

[ -f framework/adapters/failure_injection.py ] || {
  log "NOT_APPLICABLE  failure_injection.py absent -- no matrix to judge"
  exit $NOT_APPLICABLE
}

raw=$(python3 framework/adapters/failure_injection.py 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

if [ "$rc" -eq 0 ]; then
  persist pass "failure-injection matrix 38/38 checks green"
  pass "execution integrity: failure-injection matrix 38/38 checks green"
fi

log "FAIL  failure-injection matrix reported deviations (exit $rc):"
printf '%s\n' "$out" | while IFS= read -r line; do
  [ -n "$line" ] && log "FAIL  $line"
done
persist fail "failure-injection matrix deviations (exit $rc)"
fail "execution integrity: failure-injection matrix deviations listed above"
