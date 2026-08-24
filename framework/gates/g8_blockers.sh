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

log "FAIL  $count open blocker(s) -- completion refused until resolved:"
python3 framework/adapters/gsd_state.py list-blockers --text
persist fail "$count open blocker(s)"
fail "completion refused: $count open blocker(s) require resolution"
