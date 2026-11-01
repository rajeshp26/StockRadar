# Skill Routing Matrix

Central registry mapping conditions to required skills and responsible agents.
Every delegation must consult this matrix before selecting skills.

## Routing table

| Condition | Required Skill | Agent | When to activate |
|---|---|---|---|
| New feature or enhancement | `requirements-authoring` | Team Lead / Architect | Any new user-facing behavior |
| Planning or decomposing any non-trivial change | `task-breakdown` | Planner / Team Lead | Before writing a plan, acceptance criteria or task list |
| Proving a feature or fix works (integration, end-to-end, real data) | `system-test-authoring` | Verifier | Any criterion tagged integration, e2e, browser or data-invariant; before any 'it works' claim |
| Architecture change | `software-architecture-design` | Architect | New boundaries, new components, cross-component flow |
| Unknown technical behavior | `technical-validation` | Researcher / Architect | Material assumption before design |
| API endpoint change | `api-design` | Architect | New or modified HTTP endpoints |
| API contract change | `contract-authoring` | Architect / Implementer | OpenAPI schema changes |
| Database/schema change | `database-schema-design` | Architect | Table/column/index modifications |
| Unit tests required | `unit-test-authoring` | Implementer | Any business logic verification |
| Test design technique, coverage claim, risk-based regression scope, defect report, test plan or work-product review, ISTQB exam prep | `istqb-testing` | Verifier / Implementer / Reviewer | Choosing a technique or stating coverage, selecting regression scope, writing a defect report, planning or reporting testing, reviewing a work product |
| Performance impact | `performance-testing` | Verifier | Latency, throughput, memory, concurrency |
| Security concern | `security-audit` | security-auditor | Threat modeling, vulnerability assessment |
| Design direction for a UI surface is undecided (2-3 comparable mockups before a plan) | `gsd-sketch` + `frontend-react` + `apple-ui` | ui-designer | Before a screen/layout direction enters a plan; the human approval selects the variant |
| UI surface introduces or changes a pattern/system (screen, form, table, navigation, feedback surface, overlay, motion) | `designmotion-design` + `apple-ui` | Implementer / Reviewer | State coverage, feedback timing, failure modes, component-system choice; `apple-ui` still wins on finance tokens, motion values and data-viz |
| Design craft reference outside the finance design system (CSS effect, named UX law, animation recipe, library comparison) | `design/skills/` corpus (advisory): `ania-kubow-design` for CSS, `uiux-design-foundations` for principles | any role, on demand | Read-only craft reference, never mandatory and never evidence (AGENTS.md > agent definition > skill content) |
| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |
| Backend logic change | `backend-python` | Implementer | Endpoints, business logic, persistence |
| Visible behavior change | `browser-verification` | Verifier | Playwright specs, visual validation |
| Code review | `gsd-code-review` | Reviewer | Phase completion, PR review |
| Defect escape | `retrospective` | Implementer | Post-fix framework gap analysis |
| Failing test during implementation (TEST_FAILED signal) | `gsd-debug` | Implementer | Before any retry, assertion edit, or timeout raise: reproduce the failure, read it, hypothesise, test |
| Ambiguity/uncertainty/multiple interpretations, or writing/reviewing/refactoring code | `karpathy-guidelines` | Team Lead / Implementer / Architect / Reviewer | When assumptions exist, clarity is needed, a simpler approach may be better, or a change should stay surgical and avoid overcomplication |

## UI design precedence

Load the union: a finance UI task loads `apple-ui` + `frontend-react`, plus
`designmotion-design` when the surface's behaviour is new or under review. Precedence
resolves conflicts only; it never suppresses loading.

- `apple-ui` wins on finance visual tokens, motion values and data visualization.
- `designmotion-design` wins on interaction behaviour (state coverage, feedback timing,
  failure modes, component-system choice) where `apple-ui` is silent.
- If both specify the same thing, `apple-ui` wins and the plan records the conflict.
- `design/skills/` (imported craft corpus) is advisory: load it on demand, never as a rule
  and never as evidence (AGENTS.md > agent definition > skill content).
- `frontend-react` is the implementation stack and does not by itself decide design; it
  pairs with `apple-ui` for finance surfaces.

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
- [ ] `istqb-testing` when choosing a test technique, stating coverage, or writing a defect report
- [ ] `gsd-debug` reasoning loop before editing assertions, raising timeouts, or retrying a failing test
- [ ] `designmotion-design` when a UI surface introduces or changes a pattern/system
- [ ] Do not skip required skills

### Reviewer
- [ ] Verify implementation matches architecture
- [ ] Verify contract compliance
- [ ] Verify required skills were actually used
- [ ] Verify test adequacy via `unit-test-authoring` standards
- [ ] `istqb-testing` when judging test adequacy by technique and coverage, not by pass count

### Verifier
- [ ] `performance-testing` when performance is material
- [ ] `browser-verification` for visible behavior
- [ ] `istqb-testing` when choosing a test technique or stating a coverage claim
- [ ] Load applicable evidence classes per requirement shape
