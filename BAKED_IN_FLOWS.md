# Baked-In Integration Flows

## 1. SkillSpec Contract Registration (BAKED-IN)
Trigger: task-register with skill_spec in JSON payload

Flow:
1. Agent calls gsd_state.py task-register
2. register_task() detects skill_spec (baked-in)
3. Instantiate SkillSpec, validate with SkillAdapter.validate_skill_for_enforcement()
4. If invalid -> ValueError
5. Normalize via SkillAdapter.skill_to_task_contract()
6. Merge and mark _skill_spec_normalized
7. Write to .planning/tasks/

Example:
python framework/adapters/gsd_state.py task-register --id T-01 --json "{\"skill_spec\":{\"name\":\"support.answer.v1\",\"persona\":\"helpful\",\"model\":\"claude-4\",\"risk\":\"low\",\"eval_set\":\"qa\"}}"

## 2. Gateways (Available)
ToolGateway, ModelGateway, Guardrails, HumanGateway, EvaluationGateway, MemoryGateway, Handoffs, RAG - import from framework.gateways

## 3. Patterns (Available)
chaining, routing, parallel, reflection, react, planning, errors, learning, prioritization from framework.patterns

## 4. Loops (Available)
TaskLoop, MetaLoop, CognitiveAgent from framework.loops

Status: SkillSpec normalization is baked-in. Others available for use. All 240 tests pass.
