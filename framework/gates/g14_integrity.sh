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

# Single classification pass; raw report echoed verbatim on the FAIL path so the
# E-codes and claim ids validate.py asserts on stay visible.
verdict=$(printf '%s' "$out" | python3 -c "
import json, sys
rc = int(sys.argv[1])
if rc == 3:
    print('NOT_APPLICABLE|no claims recorded -- nothing to check integrity')
    sys.exit(0)
try:
    d = json.load(sys.stdin)
except Exception:
    print('BLOCKED|unparsable integrity report -- refusing to judge')
    sys.exit(0)
status = d.get('status')
violations = d.get('violations') or []
if status == 'ok' and not violations:
    print('PASS|%s' % d.get('claims', 0))
    sys.exit(0)
lines = ['%d evidence integrity violation(s) across %s claim(s):' % (
    len(violations), d.get('claims', 0))]
for v in violations:
    lines.append('%s  %s  %s' % (v.get('claim_id'), v.get('check'), v.get('message')))
print('FAIL|' + chr(10).join(lines))
" "$rc")

case "${verdict%%|*}" in
  PASS)
    n=${verdict#*|}
    persist pass "$n claim(s) passed evidence integrity E1-E8"
    pass "evidence integrity: $n claim(s), all E-checks pass"
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
    persist fail "$first evidence integrity violation(s)"
    fail "evidence integrity: $first violation(s) found"
    ;;
  BLOCKED)
    log "BLOCKED  ${verdict#*|}"
    printf '%s\n' "$out"
    persist blocked "unparsable integrity report"
    exit $BLOCKED
    ;;
esac