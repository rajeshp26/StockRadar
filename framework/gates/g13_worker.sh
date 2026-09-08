#!/usr/bin/env bash
# G13 -- Worker observability.
#
# Judges the task event stream, not the contract file: a registered task whose worker
# has gone silent past its budgets, failed without resolution, or left an unreadable
# event stream is a supervision debt that pretending otherwise does not pay. This gate
# refuses completion while any worker escalates (health STALLED/OVERDUE/FAILED, or a
# BROKEN stream); the recovery route is reported WITH the task, never abstracted away.
# WARNING (silent past the progress timeout, probe-and-continue) is healthy here.
#
# This gate exists because a delegated task's contract and its lifecycle events are
# the executable record of a worker's liveness, execution phase, and progress; the
# framework previously had no gate that refused to treat an overdue worker as done.
#
# Exit: 0 all workers healthy or terminal | 1 unhealthy worker(s) listed |
#       2 BLOCKED (adapter unusable -- never a pass) | 4 NOT_APPLICABLE (no tasks)
GATE_NAME="g13_worker"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- task state unreadable"; persist blocked "no python3"; exit $BLOCKED; }

raw=$(python3 framework/adapters/gsd_state.py task-summary 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

# NOT_APPLICABLE -- nothing registered. Never persisted: no verdict exists.
status=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null | tr -d '\r')
if [ "$rc" -ne 0 ] && [ -z "$status" ]; then
  log "BLOCKED  task-summary failed -- state root unreadable"
  echo "$out"
  persist blocked "task-summary failed"
  exit $BLOCKED
fi

# Validate before judging: an unparsable summary must never read as a clean ledger.
show=$(printf '%s' "$out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert d.get('status') in ('ok', 'unhealthy', 'empty'); assert isinstance(d.get('unhealthy'), list); print(d.get('status'))" 2>/dev/null | tr -d '\r')
if [ -z "$show" ]; then
  log "BLOCKED  unparsable task summary -- refusing to read as valid"
  echo "$out"
  persist blocked "unparsable task summary"
  exit $BLOCKED
fi

[ "$show" = "empty" ] && {
  log "NOT_APPLICABLE  no tasks registered -- nothing to observe"
  exit $NOT_APPLICABLE
}

registered=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('registered', 0))" | tr -d '\r')

if [ "$show" = "ok" ]; then
  persist pass "$registered task(s) healthy, no escalation owed"
  pass "worker observability: $registered task(s) healthy"
fi

log "FAIL  $registered task(s) registered; unhealthy worker(s) need escalation:"
printf '%s' "$out" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for u in d.get('unhealthy', []):
    fc = ('  failure_class=%s' % u.get('failure_class')) if u.get('failure_class') else ''
    print('%s  agent=%s  state=%s  health=%s  level=%s%s' % (
        u.get('task_id'), u.get('agent'), u.get('state'), u.get('health'),
        u.get('recovery_level'), fc))
    action = u.get('recovery_action') or ''
    if action:
        print('    -> %s' % action)
" 2>/dev/null | while IFS= read -r line; do
      [ -n "$line" ] && log "FAIL  $line"
    done
persist fail "$(printf '%s' "$out" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('unhealthy', [])))" | tr -d '\r') unhealthy worker(s) out of $registered"
fail "worker observability: unhealthy worker(s) require supervision before completion"