#!/usr/bin/env bash
# G-SANDBOX -- sandbox readiness pre-flight.
#
# Refuses target-controlled execution unless the host can enforce the security-audit
# skill's sandbox contract. Two backends satisfy it: an OS-enforced sandbox via
# unprivileged user namespaces (bubblewrap), or an OCI container (--network=none,
# --read-only, --cap-drop=ALL, no-new-privileges). Either way: no external network, an
# empty allowlisted environment, read-only target and toolchain, and a single writable
# scratch dir. It wraps `python3 framework/adapters/sandbox.py probe`, which measures --
# it does not assume.
#
# This is a pre-flight gate in the G12/G-ENTRY shape: it is the capability check that
# gates execution, not a report about it.
#
# Exit: 0 enforceable -- execution permitted | 1 an isolation control FAILED when
#       attempted (isolation broken; refuse) | 3 a required capability is MISSING
#       (neither bubblewrap/user-namespaces nor a usable container) -- refuse and stay
#       source-only | 2 BLOCKED (python3 or the probe is unreadable -- never a pass) | 4
#       NOT_APPLICABLE (SANDBOX_EXEC_REQUIRED=0: no execution in this run)
GATE_NAME="g_sandbox"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2
UNVERIFIABLE=3
NOT_APPLICABLE=4

if [ "${SANDBOX_EXEC_REQUIRED:-1}" = "0" ]; then
  not_applicable "execution not required for this run (SANDBOX_EXEC_REQUIRED=0)" \
    '{"sandbox_exec_required": false}'
fi

have python3 || { log "BLOCKED  python3 unavailable -- sandbox capability unreadable"; persist blocked "no python3"; exit $BLOCKED; }

BACKEND="${SANDBOX_BACKEND:-auto}"
out="$(python3 framework/adapters/sandbox.py probe --backend "$BACKEND" --json 2>&1)"
rc=$?
chosen="$(printf '%s' "$out" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("backend") or "?")
except Exception: print("?")' 2>/dev/null || echo '?')"
log "probe exit=$rc backend=$chosen"

# Validate before judging: an unparsable probe must never read as enforceable.
printf '%s' "$out" | python3 -c 'import sys,json;json.load(sys.stdin)' >/dev/null 2>&1 || {
  log "BLOCKED  unparsable sandbox probe output -- refusing to read as pass"
  printf '%s\n' "$out" >&2
  persist blocked "unparsable sandbox probe output"
  exit $BLOCKED
}

ev="$(printf '%s' "$out" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(json.dumps({"missing":d.get("missing",[]),"violations":d.get("violations",[]),"unjudged":d.get("unjudged",[])}))')"
unv="$(printf '%s' "$out" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d.get("unjudged",[])))')"

case "$rc" in
  0)
    persist pass "sandbox enforceable via $chosen"
    pass "sandbox pre-flight: enforceable via $chosen -- target execution permitted"
    ;;
  1)
    log "FAIL  isolation control(s) failed when attempted -- execution refused:"
    printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for n in d.get('violations',[]):
    c=d['checks'][n]
    print('  %s: %s' % (n, c.get('detail','')))
" 2>/dev/null | while IFS= read -r line; do [ -n "$line" ] && log "FAIL  $line"; done
    persist fail "sandbox isolation violation: $ev"
    fail "sandbox pre-flight: ISOLATION VIOLATED -- NO TARGET EXECUTION"
    ;;
  *)
    [ "$unv" -gt 0 ] && log "NOTE  $unv required check(s) unjudged"
    log "MISSING  required sandbox capability absent -- execution refused (stay source-only):"
    printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for n in d.get('missing',[])+d.get('unjudged',[]):
    c=d['checks'].get(n,{})
    print('  %s: %s' % (n, c.get('detail','')))
" 2>/dev/null | while IFS= read -r line; do [ -n "$line" ] && log "MISSING  $line"; done
    persist blocked "sandbox capability missing: $ev"
    capability_missing "sandbox capability missing -- execution refused" "$ev"
    ;;
esac
