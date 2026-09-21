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

# Single classification pass: one interpreter, one parse. The raw report is echoed
# verbatim on the FAIL path so named claim ids stay visible to the caller
# (validate.py asserts on them).
verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
rc = int(sys.argv[1])
if rc == 3:
    print('NOT_APPLICABLE|no claims recorded -- nothing to judge')
    sys.exit(0)
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|unparsable claim ledger output -- refusing to read as valid')
    sys.exit(0)
status = d.get('status')
invalid = d.get('invalid') or []
if status == 'ok' and not invalid:
    print('PASS|%s' % d.get('claims', 0))
    sys.exit(0)
lines = ['%d invalid claim(s) in ledger:' % len(invalid)]
for inv in invalid:
    lines.append('%s  status=%s  classification=%s  problems=%s' % (
        inv.get('claim_id'), inv.get('status'), inv.get('classification'),
        ','.join(inv.get('problems', []))))
print('FAIL|' + chr(10).join(lines))
" "$rc")

case "${verdict%%|*}" in
  PASS)
    n=${verdict#*|}
    persist pass "$n claim(s) valid with provenance"
    pass "claim ledger valid: $n claim(s), provenance present"
    ;;
  NOT_APPLICABLE)
    log "NOT_APPLICABLE  ${verdict#*|}"
    exit $NOT_APPLICABLE
    ;;
  FAIL)
    printf '%s\n' "$out"
    tail=${verdict#*|}
    first=${tail%%$'\n'*}; first=${first%% *}
    while IFS= read -r line; do
      [ -n "$line" ] && log "FAIL  $line"
    done <<EOF
$tail
EOF
    persist fail "$first invalid claim(s)"
    fail "claim ledger invalid: $first claim(s) lack provenance"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    printf '%s\n' "$out"
    persist blocked "unparsable claim ledger output"
    exit $BLOCKED
    ;;
esac