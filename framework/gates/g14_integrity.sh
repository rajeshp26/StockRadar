#!/usr/bin/env bash
# G14 -- Evidence integrity.
#
# Judges whether evidence is authentic: it exists (E2), belongs to the task (E3),
# was actually produced with a receipt present (E5/E6), has no open reviewer
# suspicion or unfinished review blocking a VERIFIED claim (E7), and has not been
# reused verbatim across tasks (E8). Record-structure integrity (E1/E3/E4/E5)
# shares the ledger's own validate_record codes.
#
# Distinct from G11 (record validity): a fabricated or borrowed claim can be
# perfectly well-formed, and G14 exists to catch that class.
#
# Data source: `python3 framework/claims/ledger.py integrity` (latest claim per id).
# Exit: 0 all claims pass E1-E8 | 1 violations listed | 2 BLOCKED | 4 NOT_APPLICABLE (no claims)

GATE_NAME="g14_integrity"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

if ! have python3; then
  log "BLOCKED  python3 unavailable -- integrity check unreadable"
  persist blocked "no python3"
  exit $BLOCKED
fi

raw=$(python3 framework/claims/ledger.py integrity 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

if [ "$rc" -eq 3 ]; then
  log "NOT_APPLICABLE  no claims recorded -- nothing to check integrity"
  exit $NOT_APPLICABLE
fi

printf '%s' "$out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert isinstance(d, dict) and d.get('status') in ('ok', 'violations')" 2>/dev/null || {
  log "BLOCKED  unparsable integrity report -- refusing to judge"
  echo "$out"
  persist blocked "unparsable integrity report"
  exit $BLOCKED
}

status=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status'))" | tr -d '\r')
violations=$(printf '%s' "$out" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('violations', [])))" | tr -d '\r')
claims=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('claims', 0))" | tr -d '\r')

if [ "$status" = "ok" ] && [ "$violations" -eq 0 ]; then
  persist pass "$claims claim(s) passed evidence integrity E1-E8"
  pass "evidence integrity: $claims claim(s), all E-checks pass"
fi

log "FAIL  $violations evidence integrity violation(s) across $claims claim(s):"
lines=$(printf '%s' "$out" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for v in d.get('violations', []):
    print('%s  %s  %s' % (v.get('claim_id'), v.get('check'), v.get('message')))
" 2>/dev/null)
while IFS= read -r line; do
  [ -n "$line" ] && log "FAIL  $line"
done <<EOF
$lines
EOF

persist fail "$violations evidence integrity violation(s)"
fail "evidence integrity: $violations violation(s) found"
