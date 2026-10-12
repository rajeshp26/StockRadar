# Skill Routing Matrix

Central registry mapping conditions to required skills and responsible agents.
Every delegation must consult this matrix before selecting skills.

## Routing table

| Condition | Required Skill | Agent | When to activate |
|---|---|---|---|
| New feature or enhancement | `requirements-authoring` | Team Lead / Architect | Any new user-facing behavior |
| Architecture change | `software-architecture-design` | Architect | New boundaries, new components, cross-component flow |
| Unknown technical behavior | `technical-validation` | Researcher / Architect | Material assumption before design |
| API endpoint change | `api-design` | Architect | New or modified HTTP endpoints |
| API contract change | `contract-authoring` | Architect / Implementer | OpenAPI schema changes |
| Database/schema change | `database-schema-design` | Architect | Table/column/index modifications |
| Unit tests required | `unit-test-authoring` | Implementer | Any business logic verification |
| Performance impact | `performance-testing` | Verifier | Latency, throughput, memory, concurrency |
| Security concern | `security-research` | Researcher | Threat modeling, vulnerability assessment |
| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |
| Backend logic change | `backend-python` | Implementer | Endpoints, business logic, persistence |
| Visible behavior change | `browser-verification` | Verifier | Playwright specs, visual validation |
| Code review | `gsd-code-review` | Reviewer | Phase completion, PR review |
| Defect escape | `retrospective` | Implementer | Post-fix framework gap analysis |
| Ambiguity/uncertainty/multiple interpretations, or writing/reviewing/refactoring code | `karpathy-guidelines` | Team Lead / Implementer / Architect / Reviewer | When assumptions exist, clarity is needed, a simpler approach may be better, or a change should stay surgical and avoid overcomplication |

## Skill dependency chain

```
requirements-authoring
    â†“
technical-validation (if unknowns exist)
    â†“
software-architecture-design
    â†“
    â”œâ”€â”€ api-design (if API changes)
    â”‚       â†“
    â”‚   contract-authoring
    â”‚       â†“
    â”‚   implementer
    â”‚
    â”œâ”€â”€ database-schema-design (if data changes)
    â”‚       â†“
    â”‚   implementer
    â”‚
    â””â”€â”€ implementer
            â†“
        unit-test-authoring (if business logic)
            â†“
        reviewer
            â†“
        verifier
            â†“
        performance-testing (if performance-sensitive)
            â†“
        browser-verification (if visible behavior)
```

## Mandatory skill checks by agent

### Team Lead
- [ ] `requirements-authoring` for all feature requests
- [ ] Consult routing matrix for every delegation
- [ ] Record required skills in Tool Plan

### Architect
- [ ] `software-architecture-design` for all L3/L4 tasks
- [ ] `technical-validation` for any material unknown
- [ ] `api-design` before `contract-authoring`
- [ ] `database-schema-design` for data model changes

### Planner
- [ ] Verify required skills listed in each task
- [ ] Ensure architect outputs (architecture + contracts + data design) are consumed
- [ ] Do not redesign architecture

### Implementer
- [ ] Load ALL skills specified by Team Lead / Planner
- [ ] `unit-test-authoring` for business logic
- [ ] Do not skip required skills

### Reviewer
- [ ] Verify implementation matches architecture
- [ ] Verify contract compliance
- [ ] Verify required skills were actually used
- [ ] Verify test adequacy via `unit-test-authoring` standards

### Verifier
- [ ] `performance-testing` when performance is material
- [ ] `browser-verification` for visible behavior
- [ ] Load applicable evidence classes per requirement shape
