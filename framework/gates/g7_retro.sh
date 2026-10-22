#!/usr/bin/env bash
# G7 — Retrospective completeness.
#
# Runs when a defect was found AFTER the implementation that introduced it was accepted:
# a failing test on previously-green code, a review rejection, a reopened task, a production
# defect. Its job is NOT to judge the code — G1-G6 do that. Its job is to prove the framework
# learned something specific from the escape.
#
# It fails when a retrospective is missing, when its recommendation is unfalsifiable prose
# instead of a named fix target, or when the same gap has recurred.
#
# Exit: 0 complete | 1 incomplete or recurrence | 2 BLOCKED | 4 NOT_APPLICABLE (no defect)
GATE_NAME="g7_retro"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

RETRO_DIR="$STATE_ROOT/retro"
TASK="${RETRO_TASK_ID:-}"

have python3 || { log "BLOCKED  python3 unavailable — cannot evaluate retrospective"; persist blocked "no python3"; exit $BLOCKED; }
python3 -c "import yaml" 2>/dev/null || { log "BLOCKED  pyyaml unavailable — containment map unreadable"; persist blocked "no pyyaml"; exit $BLOCKED; }

# ── Is a retrospective owed at all? ──
# Owed when a trigger marker exists. The Team Lead writes one on TEST_FAILED against
# previously-green code, REVIEW_REJECTED, a reopened task, or a reported production defect.
TRIGGER="$RETRO_DIR/triggers"
if [ ! -d "$TRIGGER" ] || [ -z "$(ls -A "$TRIGGER" 2>/dev/null)" ]; then
  log "NOT_APPLICABLE  no defect-escape trigger recorded — nothing to retrospect"
  exit $NOT_APPLICABLE
fi

open_triggers=$(ls -1 "$TRIGGER" 2>/dev/null | wc -l | tr -d ' ')
log "open triggers: $open_triggers"

missing=0
bad=0
for t in "$TRIGGER"/*; do
  [ -f "$t" ] || continue
  tid=$(basename "$t" .yaml); tid=${tid%.yml}; tid=${tid%.json}
  # A trigger is discharged by a ledger entry for that task.
  if ! python3 - "$tid" <<'PY'
import json, subprocess, sys
tid = sys.argv[1]
r = subprocess.run(["python3", "framework/retro/ledger.py", "path"],
                   capture_output=True, text=True)
from pathlib import Path
p = Path(r.stdout.strip()) if r.returncode == 0 else None
if not p or not p.exists():
    sys.exit(1)
for line in p.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        continue
    if str(e.get("task_id")) == tid and e.get("type") != "human_correction":
        # A human correction is an observation, not a retrospective: it carries no
        # counterfactual and no fix, so it must never discharge a defect trigger.
        sys.exit(0)
sys.exit(1)
PY
  then
    log "FAIL  no retrospective recorded for escaped defect in task $tid"
    missing=$((missing+1))
  fi
done

# ── Ledger consistency: recurrence and unverified fixes ──
led_out=$(python3 framework/retro/ledger.py analyse 2>&1)
led_rc=$?
if [ "$led_rc" -eq 3 ]; then
  log "FAIL  triggers exist but ledger is empty — a defect escaped with no retrospective"
  persist fail "ledger empty with $open_triggers open trigger(s)"
  exit 1
fi

# Windows python prints CRLF through interop pipes; $( ) strips the \n but keeps
# the stray CR, so [ -gt ] rejects "1\r" as garbage and reads false — every
# recurrence (including human-correction recurrence, the Gap 5 escalation path)
# would then silently pass. Strip before numeric use, exactly as g8 does.
recur=$(printf '%s' "$led_out" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(0); raise SystemExit
print(len(d.get('recurring_signatures',[])))" 2>/dev/null || echo 0)
recur=$(printf '%s' "$recur" | tr -d '\r')
unver=$(printf '%s' "$led_out" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(0); raise SystemExit
print(len(d.get('unverified_fixes',[])))" 2>/dev/null || echo 0)
unver=$(printf '%s' "$unver" | tr -d '\r')

if [ "$recur" -gt 0 ]; then
  log "FAIL  $recur recurring gap signature(s) — a previous fix did not close the gap"
  printf '%s' "$led_out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d.get('recurring_signatures',[]):
    print('  x%d  %s' % (r['occurrences'], r['signature']))
    for h in r.get('history',[]):
        if 'what' in h and h.get('what') is not None:
            print('        %s  corrected: %s' % (h.get('task_id'), h.get('what')))
        else:
            print('        %s  fix=%s landed=%s' % (h.get('task_id'), h.get('fix_target'), h.get('fix_landed')))
" 2>/dev/null
  bad=$((bad+1))
fi

if [ "$unver" -gt 0 ]; then
  log "FAIL  $unver fix(es) claimed as landed with no verifying command"
  bad=$((bad+1))
fi

if [ "$missing" -gt 0 ] || [ "$bad" -gt 0 ]; then
  persist fail "missing=$missing recurrence_or_unverified=$bad"
  fail "retrospective incomplete: $missing missing, $bad consistency failure(s)"
fi

persist pass "$open_triggers trigger(s) discharged; ledger consistent"
pass "retrospectives complete for $open_triggers escaped defect(s); no recurrence"
