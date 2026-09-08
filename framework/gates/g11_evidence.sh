#!/usr/bin/env bash
# G11 -- Evidence provenance.
#
# Judges the claim ledger, not the code: every conclusion an agent reports should rest on a
# claim recorded with reproducible provenance. This gate refuses completion while any
# latest-per-id claim record is invalid -- a claim without provenance is a failure, not a
# caveated pass.
#
# Exit: 0 claims valid | 1 invalid claims listed | 2 BLOCKED | 4 NOT_APPLICABLE (no claims)
GATE_NAME="g11_evidence"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- claim ledger unreadable"; persist blocked "no python3"; exit $BLOCKED; }

# Windows python prints CRLF through interop pipes; $( ) strips the \n but keeps
# the stray CR, which makes [ -eq ] reject digits as garbage. Never read dirty bytes.
raw=$(python3 framework/claims/ledger.py analyse 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

# No claims recorded -- nothing to judge. NOT_APPLICABLE is not a pass, and it is not
# persisted: there is no verdict to record.
if [ "$rc" -eq 3 ]; then
  log "NOT_APPLICABLE  no claims recorded -- nothing to judge"
  exit $NOT_APPLICABLE
fi

# Validate before judging: an unparsable report must never read as a clean ledger.
printf '%s' "$out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert d.get('status') in ('ok', 'invalid')" 2>/dev/null || {
  log "BLOCKED  unparsable claim ledger output -- refusing to read as valid"
  echo "$out"
  persist blocked "unparsable claim ledger output"
  exit $BLOCKED
}

status=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status'))" | tr -d '\r')
invalid_count=$(printf '%s' "$out" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('invalid', [])))" | tr -d '\r')
claims=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('claims', 0))" | tr -d '\r')

if [ "$status" = "ok" ] && [ "$invalid_count" -eq 0 ]; then
  persist pass "$claims claim(s) valid with provenance"
  pass "claim ledger valid: $claims claim(s), provenance present"
fi

log "FAIL  $invalid_count invalid claim(s) in ledger:"
invalid_lines=$(printf '%s' "$out" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for inv in d.get('invalid', []):
    print('%s  status=%s  classification=%s  problems=%s' % (
        inv.get('claim_id'), inv.get('status'), inv.get('classification'),
        ','.join(inv.get('problems', []))))
" 2>/dev/null)
while IFS= read -r line; do
  [ -n "$line" ] && log "FAIL  $line"
done <<EOF
$invalid_lines
EOF

persist fail "$invalid_count invalid claim(s)"
fail "claim ledger invalid: $invalid_count claim(s) lack provenance"