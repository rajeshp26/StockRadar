#!/usr/bin/env bash
# G8 -- Blocker escalation hygiene.
#
# A non-complete stop (CONTEXT_INSUFFICIENT, BLOCKED, UNKNOWN_IMPACT, ...) must land as a
# record in <state_root>/blockers.yaml the moment it happens -- not vanish into a quiet
# agent. This gate refuses completion while any open blocker exists, the same way G7
# refuses completion on an incomplete retrospective.
#
# Exit: 0 no open blockers | 1 open blockers listed | 2 BLOCKED
GATE_NAME="g8_blockers"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- blocker state unreadable"; persist blocked "no python3"; exit $BLOCKED; }
python3 -c "import yaml" 2>/dev/null || { log "BLOCKED  pyyaml unavailable -- blocker state unreadable"; persist blocked "no pyyaml"; exit $BLOCKED; }

# Windows python prints CRLF through interop pipes; $( ) strips the \n but keeps
# the stray CR, which makes [ -eq ] reject digits as garbage. Never read dirty bytes.
raw=$(python3 framework/adapters/gsd_state.py list-blockers 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')
if [ $rc -ne 0 ]; then
  log "BLOCKED  gsd_state list-blockers failed rc=$rc"
  echo "$out"
  persist blocked "list-blockers rc=$rc"
  exit $BLOCKED
fi

# Validate before counting: an unparsable listing must never read as zero. The
# capture above is CR-stripped for the same reason: a stray CR must never turn a
# valid count into an unreadable one.
printf '%s' "$out" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null || {
  log "BLOCKED  unparsable blocker listing -- refusing to read as zero"
  echo "$out"
  persist blocked "unparsable blocker listing"
  exit $BLOCKED
}
# The length itself comes back from Windows python through an interop pipe -- CRLF
# again. Strip before numeric use or [ -eq ] sees garbage and a clean tree reads FAIL.
count=$(printf '%s' "$out" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" | tr -d '\r')

if [ "$count" -eq 0 ]; then
  persist pass "no open blockers"
  pass "no open blockers"
fi

# --- retry budgets (framework/retry_policy.yaml) ---------------------------------
# The budgets were data nothing read: a blocker could sit past test_failure: 2
# forever and every gate still said only "one open blocker", so the documented
# on_exhaustion (escalate_to_human) never fired. The blockers store is the only
# per-task retry counter that exists (telemetry TEST_FAILED events carry no
# task_id), so this gate is where the comparison happens. An unreadable budget
# report is BLOCKED -- never read as "nothing exhausted".
rb_raw=$(python3 framework/adapters/gsd_state.py retry-budget 2>&1)
rb_rc=$?
rb_out=$(printf '%s' "$rb_raw" | tr -d '\r')
if [ $rb_rc -ne 0 ]; then
  log "BLOCKED  gsd_state retry-budget failed rc=$rb_rc"
  echo "$rb_out"
  persist blocked "retry-budget rc=$rb_rc"
  exit $BLOCKED
fi
printf '%s' "$rb_out" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null || {
  log "BLOCKED  unparsable retry-budget report -- refusing to read as zero"
  echo "$rb_out"
  persist blocked "unparsable retry-budget report"
  exit $BLOCKED
}
exh=$(printf '%s' "$rb_out" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('exhausted', [])))" | tr -d '\r')
if [ "${exh:-0}" -gt 0 ] 2>/dev/null; then
  # The escalation name is policy data, not a constant: print the value the
  # report actually carries so retry_policy.yaml stays the single source of it.
  onx=$(printf '%s' "$rb_out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('on_exhaustion') or 'unset')" | tr -d '\r')
  log "FAIL  ${exh} open blocker(s) past retry budget -- on_exhaustion: ${onx}:"
  printf '%s' "$rb_out" | python3 -c "import sys, json; [print('  %s  %s  retries=%s budget=%s' % (e.get('id'), e.get('signal'), e.get('retries'), e.get('budget'))) for e in json.load(sys.stdin).get('exhausted', [])]"
fi

log "FAIL  $count open blocker(s) -- completion refused until resolved:"
python3 framework/adapters/gsd_state.py list-blockers --text
persist fail "$count open blocker(s)"
fail "completion refused: $count open blocker(s) require resolution"
