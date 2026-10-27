# Integration Usage Guide: How Each Feature Works

## Overview
The integration is baked-in - SkillSpec adapter auto-loads in gsd_state.py, all patterns/gateways/loops are available under framework/. Existing gates unchanged.

## 1. SkillSpec Contracts (Auto-available)
**Location:** `framework/skill_contracts/skill_spec.py`  
**Trigger:** Auto-loaded via `framework/adapters/gsd_state.py` (baked-in)  
**When used:** Define agents as typed contracts, validated before execution

**How it works:**
1. Import SkillSpec/ToolSpec from skill_contracts
2. Define skill with name (domain.role.version), persona, model, tools, risk, eval_set
3. Call .validate() - checks name, persona, model, risk in {low,medium,high}, temperature 0-2, max_iterations>=1, eval_set present, tools <=10, no duplicate tool names
4. Use SkillAdapter.skill_to_task_contract() to convert to task format
5. Task supervision uses it automatically

**Expected outcome:** Clean validated contracts, bridges to existing task system.

**Example:**
```python
from skill_contracts.skill_spec import SkillSpec, ToolSpec
from adapters.skill_adapter import SkillAdapter
s = SkillSpec(name='support.answer.v1', persona='helpful', model='claude-4', tools=[ToolSpec(name='search',description='search')], risk='low', eval_set='qa')
print(s.validate())  # []
tc = SkillAdapter.skill_to_task_contract(s)
```

## 2. Gateways
**Location:** `framework/gateways/`

| Gateway | Trigger | How it works | Expected outcome |
|---------|---------|--------------|-----------------|
| ToolGateway | Tool execution | Validates schema, checks policy, retries on transient errors, classifies errors | Safe controlled tool execution |
| ModelGateway | LLM calls | Routes to appropriate model, fallbacks, reasoning modes | Optimized routing with resilience |
| Guardrails | Before actions | Validates args, identity, policy | Blocks invalid/unsafe actions |
| HumanGateway | High-risk actions (risk=high) | Escalates to human approval | Human-in-loop for consequential actions |
| EvaluationGateway | After outputs | Grounding checks, rubric evaluation | Quality validation |
| MemoryGateway | Memory ops | Stores/retrieves with scopes | Structured memory |
| Handoffs (A2A) | Agent-to-agent | Agent cards, typed tasks/messages/artifacts | Structured delegation |
| RAG | Knowledge retrieval | Retrieval with grounding | Grounded answers |

## 3. Patterns
**Location:** `framework/patterns/`

| Pattern | Trigger | How it works | Expected outcome |
|---------|---------|--------------|-----------------|
| chaining.run_chain | Sequential multi-step | Execute steps in order, pass outputs forward | Predictable pipeline |
| routing.Router | Unclear intent | Classify and dispatch to handler | Route to specialist |
| parallel | Independent subtasks | Run concurrently, aggregate results | Faster execution |
| reflection.Reflector | Need critique/revision | Generate -> critique -> revise until threshold | Higher quality output |
| react | Tool use needed | Think -> act (tool) -> observe loop | Tool-using agent behavior |
| planning | Complex goal | Decompose into plan, execute steps | Structured execution |
| errors | Failures | Classify error, retry/fallback/degrade/escalate | Resilient handling |
| learning | Repeated tasks | Learn with gated promotion | Improvement over time |
| prioritization | Multiple tasks | Score and order | Optimal scheduling |

## 4. Loops
**Location:** `framework/loops/`

| Loop | Trigger | How it works | Expected outcome |
|---------|---------|--------------|-----------------|
| TaskLoop | Task execution | SPAL: Sense->Plan->Act->Learn with termination gates (iterations/budget/goal/stagnation) | Bounded autonomous execution |
| MetaLoop | Multi-agent/supervision | Re-plan/re-route/stop agents based on progress | Adaptive coordination |
| CognitiveAgent | Metacognitive needs | Self-monitor, detect stagnation, pivot strategy | Smarter recovery from stuck states |

## 5. Adapters & MCP
**Adapters:** `framework/adapters/skill_adapter.py` bridges SkillSpec<->task contracts (auto-used)  
**MCP Registry:** `framework/mcp/registry.json` central source of truth for servers  
**Utilities:** `llm.py` (StubLLM + LLM protocol), `context.py` (budgeted assembly), `tracing.py` (spans)

## Quick Test
```python
import sys
sys.path.insert(0, 'framework')
from skill_contracts.skill_spec import SkillSpec, ToolSpec
from adapters.skill_adapter import SkillAdapter
s = SkillSpec(name='test.agent.v1', persona='test', model='stub', eval_set='basic')
assert s.validate()==[]
assert 'agent' in SkillAdapter.skill_to_task_contract(s)
```
