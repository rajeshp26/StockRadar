#!/usr/bin/env bash
# G5 — frontend stack conformance. Referenced by impact_to_gates for component and wider.
GATE_NAME=g5-stack
source "$(dirname "$0")/_lib.sh"

# No frontend in the repo at all => nothing to conform to. This is a genuine
# not-applicable, not a vacuous pass: there is no artefact of this class to judge.
if [ ! -d src/frontend ] && [ ! -f package.json ]; then
  not_applicable "no frontend present (no src/frontend, no package.json)" \
    '{"checked":["src/frontend","package.json"],"found":false}'
fi

out="$(python3 framework/frontend/stack_check.py 2>&1)"; rc=$?
echo "$out"
case "$rc" in
  0) persist pass "frontend stack conformant"; pass "frontend stack conformant" ;;
  4) not_applicable "no frontend application present — nothing to conform to" \
       '{"stack_check_exit":4,"checked":"framework/frontend/stack_check.py"}' ;;
  2) persist blocked "stack check could not run: $out"
     log "BLOCKED  stack check could not evaluate — treat as unverified, not conformant"
     exit 2 ;;
  *) persist fail "frontend stack violations"; fail "frontend stack violations (see above)" ;;
esac
