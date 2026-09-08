#!/usr/bin/env bash
# G12 -- Provider health pre-flight.
#
# Refuses task delegation to a model/provider that has NOT passed a lightweight
# invocation health check during the current execution context. First dispatch in
# a window is the probe; its outcome is recorded, and a blocking outcome (quota
# exhaustion, auth failure, model unavailable, provider timeout/network) refuses
# the NEXT dispatch. A model absent from `opencode models` is MODEL_UNAVAILABLE.
#
# This gate exists because the framework previously delegated first and learned
# about provider health from dead workers: spawns against a credit-walled
# OpenRouter account died at SPAWN, and the liveness layer misread each spawn as a
# stall. Health is a provider-boundary question and a pre-flight one.
#
# Exit: 0 provider healthy (dispatch allowed) | 1 unhealthy (blocking class named,
#       refuse dispatch) | 2 BLOCKED (cannot verify: no python3, no resolve
#       engine, inventory unreadable -- never a pass) | 4 NOT_APPLICABLE (no
#       model resolved; nothing to dispatch)
GATE_NAME="g12_provider"
. "$(dirname "$0")/_lib.sh"

NOT_APPLICABLE=4
BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable -- provider health unreadable"; persist blocked "no python3"; exit $BLOCKED; }

raw=$(python3 framework/providers/healthcheck.py check 2>&1)
rc=$?
out=$(printf '%s' "$raw" | tr -d '\r')

# NOT_APPLICABLE -- no models resolved. Never persisted: no verdict exists.
if [ "$rc" -eq 4 ]; then
  log "NOT_APPLICABLE  no model resolved -- nothing to dispatch"
  exit $NOT_APPLICABLE
fi

# Validate before judging: an unparsable report must never read as a clean verdict.
printf '%s' "$out" | python3 -c "import sys, json; d=json.load(sys.stdin); assert d.get('status') in ('pass', 'fail', 'blocked')" 2>/dev/null || {
  log "BLOCKED  unparsable provider health output -- refusing to read as pass"
  echo "$out"
  persist blocked "unparsable provider health output"
  exit $BLOCKED
}

# healthcheck.py already exits 0 pass | 1 fail | 2 blocked; map to gate verdicts.
status=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status'))" | tr -d '\r')
case "$status" in
  pass)
    persist pass "provider healthy: all $(printf '%s' "$out" | python3 -c "import sys, json; print(len(json.load(sys.stdin)['models']))" | tr -d '\r') resolved model(s) in inventory, no blocking failure in window"
    pass "provider pre-flight: healthy -- dispatch allowed"
    ;;
  blocked)
    reason=$(printf '%s' "$out" | python3 -c "import sys, json; print(json.load(sys.stdin).get('reason',''))" | tr -d '\r')
    log "BLOCKED  cannot verify provider health: $reason"
    persist blocked "cannot verify provider health: $reason"
    exit $BLOCKED
    ;;
  fail)
    log "FAIL  provider unhealthy -- dispatch refused:"
    printf '%s' "$out" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in d.get('problems', []):
    print('%s  model=%s  in_inventory=%s  %s' % (p.get('agent'), p.get('model'), p.get('in_inventory'), p.get('problem','')))
" 2>/dev/null | while IFS= read -r line; do
      [ -n "$line" ] && log "FAIL  $line"
    done
    persist fail "provider unhealthy: $(printf '%s' "$out" | python3 -c "import sys, json; print('; '.join(p.get('problem','')[:120] for p in json.load(sys.stdin).get('problems',[])))" | tr -d '\r')"
    fail "provider pre-flight: unhealthy -- NO TASK DISPATCH"
    ;;
esac