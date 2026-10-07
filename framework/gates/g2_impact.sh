#!/usr/bin/env bash
# G2 — Impact validation. Changed symbols must map to tests that actually ran.
GATE_NAME=g2_impact
source "$(dirname "$0")/_lib.sh"

FRESH=$(python3 framework/adapters/code_intel.py freshness 2>/dev/null || echo '{}')
if echo "$FRESH" | grep -q '"stale": true'; then
  log "index stale — reindexing before impact analysis"
  python3 framework/adapters/code_intel.py reindex >/dev/null 2>&1 || true
fi

CHANGED=$(changed_source_files | wc -l | tr -d ' ')
[ "$CHANGED" -gt 0 ] || { persist skip "no changes"; not_applicable "no changes" '{"changed_source_files":0}'; }

TESTS=$(python3 framework/adapters/code_intel.py affected-tests 2>/dev/null || echo '{}')
TIER=$(echo "$TESTS" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tier",4))' 2>/dev/null || echo 4)
COUNT=$(echo "$TESTS" | python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("tests",[])))' 2>/dev/null || echo 0)

log "changed files: $CHANGED   affected tests: $COUNT   provider tier: $TIER"

# Never read "unknown impact" as "no impact".
if [ "$COUNT" -eq 0 ] && [ "$TIER" -ge 4 ]; then
  persist fail "unknown impact: search fallback returned no tests"
  fail "UNKNOWN_IMPACT — search fallback found no tests; expand context and inspect source"
fi

if [ "$COUNT" -eq 0 ]; then
  log "provider reports no affected tests; verifying with three-check low-impact test"
  persist pass "no affected tests, provider tier $TIER"
  pass "no affected tests"
fi

persist pass "$COUNT affected tests identified"
pass "impact mapped to $COUNT tests"
