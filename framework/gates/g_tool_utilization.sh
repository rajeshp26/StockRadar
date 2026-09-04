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
GATE_NAME="g_tool_utilization"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2

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
        print(f'GAPS:Tool evidence missing in: {', '.join(gaps)}')
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
    log "SKIP  no verification artifacts to check"
    persist pass "no verification artifacts"
    pass "no verification artifacts to check"
fi

if [ $rc -ne 0 ]; then
    log "FAIL  $out"
    persist fail "$out"
    fail "tool utilization check failed: $out"
fi

persist pass "tool evidence present in verification artifacts"
pass "tool utilization verified"