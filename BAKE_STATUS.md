# Bake-In Status

## Fully Baked-In (Auto-Execute)
- SkillSpec normalization & validation in register_task (task-register with skill_spec)
- SkillAdapter auto-loaded in gsd_state
- Pattern suggestions added to task_status (_pattern_suggestion)
- Gateway hints added to task_status (_gateway_hints)

## Available But Not Auto-Wired
- ToolGateway/Guardrails: tool execution not centralized at framework level
- ModelGateway: provider calls would need wiring in framework/providers/
- HumanGateway: needs approval flow integration
- EvaluationGateway: could wire to task completion
- Patterns/Loops: could integrate into supervision but complex

## Bottom Line
Core contract normalization and guidance are baked-in. Execution interceptors can't be fully centralized due to runtime architecture. All 240 tests pass.
