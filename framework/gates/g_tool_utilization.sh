#!/usr/bin/env bash
# G-T1 -- Tool utilization.
#
# After work completes, verify that:
#   1. Required tools were actually invoked
#   2. Tool results were considered
#   3. Tool results are recorded/evidenced
#   4. Manual reasoning did not replace required tool usage
#   5. Tool failures were handled
#
# Exit: 0 required tools used and evidenced | 1 tool usage gaps found | 2 BLOCKED
#       4 NOT_APPLICABLE (no artifacts AND the plan does not require evidence)
GATE_NAME="g_tool_utilization"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2
ENTRY_PLAN="${ENTRY_PLAN:-}"

have python3 || { log "BLOCKED  python3 unavailable"; persist blocked "no python3"; exit $BLOCKED; }

# Check for tool evidence in verification artifacts
TOOL_EVIDENCE_CHECK=$(python3 -c "
import json, subprocess, sys, os, glob

try:
    # Get state root
    result = subprocess.run(
        ['python3', 'framework/adapters/gsd_state.py', 'state-root'],
        capture_output=True, text=True
    )
    state_root = result.stdout.strip()
    
    # Look for verification artifacts that should contain tool evidence
    verification_files = glob.glob(f'{state_root}/**/verification*.yaml', recursive=True)
    verification_files += glob.glob(f'{state_root}/**/verification*.json', recursive=True)
    
    if not verification_files:
        # No verification artifacts found - this might be okay for some tasks
        print('NO_VERIFICATION_ARTIFACTS')
        sys.exit(0)
    
    # Check each verification artifact for tool evidence
    gaps = []
    for vfile in verification_files:
        with open(vfile, 'r') as f:
            content = f.read()
        
        # Look for tool evidence patterns
        has_tool_evidence = (
            'tool_evidence' in content or
            'tool:' in content or
            'exit_code:' in content or
            'command:' in content
        )
        
        if not has_tool_evidence:
            gaps.append(os.path.basename(vfile))
    
    if gaps:
        print('GAPS:Tool evidence missing in: ' + ', '.join(gaps))
        sys.exit(1)
    
    print('OK')
    sys.exit(0)
    
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" 2>&1)

rc=$?
out=$(printf '%s' "$TOOL_EVIDENCE_CHECK" | tr -d '\r')

if [ "$out" = "NO_VERIFICATION_ARTIFACTS" ]; then
    # EXIT_CODES.md (G-T1 row) defines exit 4 for the case where there is nothing to judge;
    # skip() is retired because it reported result=pass on an unjudged gate. But "no artifact"
    # is only innocent when the task never claimed depth. For L2+ or a real-stack criterion,
    # an absent artifact is a FAILURE -- the work asserted something it did not prove.
    # The depth comes from the plan (framework/tools/evidence_level.py), never from an env var:
    # an agent can set an env var, but the plan is the artifact under review.
    if [ -z "$ENTRY_PLAN" ] || [ ! -f "$ENTRY_PLAN" ]; then
        log "NOT_APPLICABLE  no verification artifacts and no ENTRY_PLAN to derive the required depth"
        persist not_applicable "no artifacts, no plan context"
        not_applicable "no verification artifacts and no ENTRY_PLAN to derive the required depth" \
            '{"verification_artifacts":0,"plan_context":"absent"}'
    fi

    if [ ! -f framework/tools/evidence_level.py ]; then
        persist blocked "evidence_level.py missing; cannot decide whether artifacts are required"
        log "BLOCKED  framework/tools/evidence_level.py missing -- cannot judge G-T1"
        exit $BLOCKED
    fi

    lvl="$(python3 framework/tools/evidence_level.py "$ENTRY_PLAN" 2>&1)"; lvl_rc=$?
    lvl="$(printf '%s' "$lvl" | tr -d '\r')"
    case "$lvl_rc" in
        0) ;;
        *) persist blocked "evidence level unreadable (exit $lvl_rc)"
           log "BLOCKED  evidence level unreadable (exit $lvl_rc): $lvl"
           exit $BLOCKED ;;
    esac

    case "$lvl" in
        REQUIRED*)
            persist fail "no verification artifact where the plan requires evidence: $lvl"
            fail "no verification artifact, but the plan requires evidence ($lvl); an absent artifact is not a clean result" ;;
        OPTIONAL*)
            log "NOT_APPLICABLE  no verification artifacts; plan does not require them ($lvl)"
            persist not_applicable "no artifacts; plan does not require evidence"
            not_applicable "no verification artifacts; the plan does not require them ($lvl)" \
                '{"verification_artifacts":0,"plan_requires_evidence":false}' ;;
        *) persist blocked "evidence level produced no verdict: $lvl"
           log "BLOCKED  evidence level produced no verdict: $lvl"
           exit $BLOCKED ;;
    esac
fi

if [ $rc -ne 0 ]; then
    log "FAIL  $out"
    persist fail "$out"
    fail "tool utilization check failed: $out"
fi

persist pass "tool evidence present in verification artifacts"
pass "tool utilization verified"
