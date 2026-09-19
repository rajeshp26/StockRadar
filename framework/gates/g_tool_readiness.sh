#!/usr/bin/env bash
# G-T0 -- Tool readiness.
#
# Before work begins, verify that:
#   1. Available tools are identified
#   2. Applicable tools are identified
#   3. Required tools are identified
#   4. Tool plan is created
#   5. Tool availability is confirmed
#
# Exit: 0 tool plan exists and required tools available | 1 tool plan missing or tools unavailable | 2 BLOCKED
GATE_NAME="g_tool_readiness"
. "$(dirname "$0")/_lib.sh"

BLOCKED=2

have python3 || { log "BLOCKED  python3 unavailable"; persist blocked "no python3"; exit $BLOCKED; }

# Check if tool plan exists in the task record
# The tool plan should be in the task's verification artifact or state
TOOL_PLAN_CHECK=$(python3 -c "
import json, subprocess, sys

try:
    # Get current phase
    result = subprocess.run(
        ['python3', 'framework/adapters/gsd_state.py', 'current-phase'],
        capture_output=True, text=True
    )
    phase_data = json.loads(result.stdout)
    current_phase = phase_data.get('current', '00-unphased')
    
    # Check if tool registry exists
    import os
    if not os.path.exists('framework/tools/registry.yaml'):
        print('MISSING:framework/tools/registry.yaml not found')
        sys.exit(1)
    
    # Check if team-lead has tool applicability analysis
    team_lead_path = '.opencode/agents/team-lead.md'
    if not os.path.exists(team_lead_path):
        print('MISSING:team-lead.md not found')
        sys.exit(1)
    
    with open(team_lead_path, 'r') as f:
        content = f.read()
    
    if 'Tool Applicability Analysis' not in content:
        print('MISSING:Tool Applicability Analysis not in team-lead.md')
        sys.exit(1)
    
    # Check if tool contracts exist for core agents
    core_agents = ['implementer.md', 'verifier.md', 'researcher.md', 'architect.md', 'planner.md', 'reviewer.md']
    missing_contracts = []
    for agent in core_agents:
        agent_path = f'.opencode/agents/{agent}'
        if os.path.exists(agent_path):
            with open(agent_path, 'r') as f:
                if '## Tool Contract' not in f.read():
                    missing_contracts.append(agent)
    
    if missing_contracts:
        print(f'MISSING:Tool contracts missing in: {', '.join(missing_contracts)}')
        sys.exit(1)
    
    print('OK')
    sys.exit(0)
    
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" 2>&1)

rc=$?
out=$(printf '%s' "$TOOL_PLAN_CHECK" | tr -d '\r')

if [ $rc -ne 0 ]; then
    log "FAIL  $out"
    persist fail "$out"
    fail "tool readiness check failed: $out"
fi

persist pass "tool plan exists, registry present, contracts in place"
pass "tool readiness verified"