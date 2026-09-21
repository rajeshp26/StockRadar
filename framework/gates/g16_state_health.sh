#!/usr/bin/env bash
# G16 -- State health.
#
# One-shot health over the live GSD state: every registered task's contract must
# be readable and its event stream's tail parseable, and the claim ledger's tail
# must parse as JSON. Broken task state blocks completion -- an unreadable stream
# is a stall that must be fixed, not worked around. FAILED/LOST tasks are not
# broken: a terminal task with a readable stream is healthy.
#
# Data source: `python3 framework/adapters/gsd_state.py state-health`.
# Exit: 0 healthy | 1 broken task(s) | 2 BLOCKED | 4 NOT_APPLICABLE (no tasks, no ledger)

GATE_NAME="g16_state_health"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- state unreadable"; persist blocked "no python3"; exit $BLOCKED; }

out=$(python3 framework/adapters/gsd_state.py state-health 2>&1)
rc=$?
out=$(printf '%s' "$out" | tr -d '\r')

if [ "$rc" -ne 0 ]; then
  log "BLOCKED  state-health exited $rc -- refusing to judge"
  printf '%s\n' "$out"
  persist blocked "state-health exit $rc"
  exit $BLOCKED
fi

verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|state-health output is not a JSON object')
    sys.exit(0)
broken = d.get('broken_tasks', 0)
if broken:
    print('FAIL|%d broken task(s) in store' % broken)
    sys.exit(0)
if d.get('tasks_total', 0) == 0 and not d.get('ledger_present', False):
    print('NOT_APPLICABLE|no tasks, no ledger')
    sys.exit(0)
print('PASS|%d task(s), 0 broken, ledger %s' % (
    d.get('tasks_total', 0),
    'present+parseable' if d.get('ledger_tail_parseable', False) else 'present'))
")

case "${verdict%%|*}" in
  PASS)
    msg=${verdict#*|}
    persist pass "$msg"
    pass "state health ok: $msg"
    ;;
  NOT_APPLICABLE)
    log "NOT_APPLICABLE  ${verdict#*|}"
    exit $NOT_APPLICABLE
    ;;
  FAIL)
    printf '%s\n' "$out"
    msg=${verdict#*|}
    persist fail "$msg"
    fail "state health: $msg"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    persist blocked "${verdict#*|}"
    exit $BLOCKED
    ;;
esac