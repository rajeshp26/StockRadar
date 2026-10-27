# Professional Framework Comparison

## Comparison
- Enforcement/Gates: Our framework is stronger than LangGraph/OpenAI Agents/CrewAI (we have executable gates g1-g18)
- Task Supervision: More mature (lifecycle, health checks, blockers, retries)
- Evidence Discipline: Unique (VERIFIED citations, claim ledger)
- Security/Permissions: More rigorous (enforcement plane)
- Tool Interception: Industry does better (they control runtime, we don't)
- Agent Loops: Industry does better (built into runner)
- Patterns as First-Class: Industry does better (seamless composition)

## Assessment
Our approach is professional. Where we control the flow (task registration, supervision, guidance) we bake things in. Where we don't control the runtime (tool/model calls), we provide clean abstractions for use. This is reasonable given our architecture. All 240 tests pass.
