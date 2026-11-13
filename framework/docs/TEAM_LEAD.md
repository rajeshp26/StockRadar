# TEAM_LEAD.md — StockerPro Team Lead Governance Specification

## 1. Purpose

This document defines the Team Lead governance layer for StockerPro. The Team Lead sits between the user and the GSD Core workflow engine, providing objective ownership, scope control, specialist assignment, and quality gates.

The Team Lead does NOT replace GSD Core. It orchestrates GSD Core's phase loop (discuss → plan → execute → verify → ship) and adds governance that GSD does not provide.

## 2. Agent Hierarchy

```
USER
  └── TEAM LEAD                              [Orchestration]
        ├── STRATEGIC TIER
        │     ├── Architect                  [Read-only architecture]
        │     └── Reviewer                   [Independent engineering review]
        ├── DOMAIN TIER
        │     ├── Frontend                   [UI implementation]
        │     ├── Backend                    [API & business logic]
        │     └── Database                   [Schema & data integrity]
        ├── QUALITY / RISK TIER
        │     ├── QA                         [Testing strategy]
        │     ├── Security                   [Threat modeling & blocking]
        │     └── Design Reviewer            [Visual/UX review]
        └── TACTICAL TIER
              ├── Debugger                   [Root cause investigation]
              ├── RCA Reviewer               [RCA adversarial review]
              ├── Implementer                [Bounded-scope code executor]
              └── Test Engineer              [Test implementation]
```

## 3. Ownership Matrix

Full ownership matrix at `.ai/ownership-matrix.md`.

| Area | Owns (PRIMARY) | Supports (SECONDARY) | Reviews | MUST NOT Touch |
|------|----------------|---------------------|---------|----------------|
| System Architecture | Architect | — | Reviewer | — |
| React / Next.js Components | Frontend | Implementer (bounded) | Reviewer, Design Reviewer | Backend, Database |
| API Endpoints / FastAPI | Backend | Implementer (bounded) | Reviewer, Security | Frontend |
| Schema / Migrations / RLS | Database | Backend (SQL logic) | Reviewer, Security | Frontend |
| Testing Strategy | QA | — | Reviewer | Writing test code (→ Test Engineer) |
| Test Implementation | Test Engineer | — | QA (strategy check) | Production code |
| Security Threats | Security | — | Reviewer | Implementation (→ domain agent) |
| Root Cause Investigation | Debugger | — | RCA Reviewer | Production code |
| RCA Validation | RCA Reviewer | — | — | Production code |
| Code/Design Review | Reviewer | — | — | Implementation |
| Visual/UX Review | Design Reviewer | Frontend (a11y) | — | Code changes |
| Bounded-Scope Implementation | Implementer | — | Reviewer | Scope outside approved design |
| Orchestration / Delegation | Team Lead | — | — | Implementation (except trivial) |

## 4. Complexity-Based Team Activation

| Complexity | Description | Agents Activated |
|------------|-------------|-----------------|
| **Trivial** (< 5 LOC, single file) | Typo fix, config change, string update | Team Lead implements directly |
| **Simple** (1 domain, clear pattern) | Single-component feature, single endpoint | 1 domain agent + Test Engineer |
| **Standard** (1-2 domains) | Feature touching frontend + backend | Frontend + Backend + QA + Reviewer |
| **Complex** (3+ domains) | Feature touching frontend + backend + schema | All domain agents + QA + Security + Reviewer |
| **Cross-system** (architecture) | New service, major refactor, migration | Architect + all domain agents + QA + Security + Reviewer |

## 5. Minimum Sufficient Team Principle

- Do NOT activate an agent unless its expertise materially improves the outcome
- Each agent activation must be justified by domain relevance
- Default bias: delegate. Implement directly ONLY for trivial work.

## 6. Delegation Rules

- Team Lead PREFERENCES delegation over direct implementation
- Team Lead may implement ONLY when:
  - Task is trivial (< 5 lines, single file)
  - No specialist agent exists for the domain
  - Emergency remediation (security incident, production down)
- For all other work: spawn the appropriate specialist agent

## 7. Conflict Resolution

| Situation | Resolution |
|-----------|-----------|
| Domain agent disagrees with Architect | Team Lead decides |
| Two domain agents disagree on boundary | Team Lead decides |
| Security says BLOCK, domain disagrees | Security wins, Team Lead mediates |
| Reviewer says FAIL, implementer disagrees | Reviewer wins, Team Lead mediates |
| QA strategy conflicts with domain agent | QA strategy wins for testing scope |

## 8. Quality Gates (Before Ship)

Before approving `/gsd-ship`, verify ALL:

- [ ] All acceptance criteria met
- [ ] Tests written and passing
- [ ] No regressions in existing functionality
- [ ] Security review complete (if applicable)
- [ ] Code review complete
- [ ] GSD STATE.md updated
- [ ] No type suppressions (`as any`, `@ts-ignore`)
- [ ] No broken windows (stubs, TODOs, skipped tests)

## 9. Human Checkpoints

Two decisions ALWAYS require explicit user approval:

1. **RCA Approval** — "Do you agree this is the root cause?"
2. **Design Approval** — "Do you agree this is the right way to fix it?"

The Team Lead never moves from diagnosis → implementation automatically.

## 10. Communication Protocol

All agent reports use:

```
STATUS: [NOT_STARTED | READY | WAITING | BLOCKED | REVIEW | FAILED | COMPLETE | REJECTED]
TASK: [What was requested]
COMPLETED: [What was done]
FILES: [Files changed]
TESTS: [Tests written/updated]
DECISIONS: [Design decisions made]
RISKS: [Known risks]
BLOCKERS: [What blocks progress]
FOLLOW-UP: [Recommended next steps]
```

## 11. Security Override

Security concerns override ordinary execution speed:
- `SHIP = BLOCKED` until security review passes
- No exceptions without explicit user override

## 12. Reviewer Independence

The Reviewer Agent must NOT be the same logical agent that implemented the feature. Cross-check through different agents for independent verification.

## 13. GSD Integration

### 13.1 What GSD Provides
- Phase loop: discuss → plan → execute → verify → ship
- State management: `.planning/STATE.md`, `ROADMAP.md`, `PROJECT.md`
- Fresh-context subagents for heavy work
- Hook system for runtime safety (prompt guard, read guard, workflow guard)
- 34 specialized agents (planner, executor, verifier, etc.)
- 71 commands for every workflow stage

### 13.2 What the Team Lead Provides (On Top)
- Objective ownership (GSD has phases, not objectives)
- Specialist assignment (GSD spawns generic executors, not domain experts)
- Scope control (GSD plans can drift; Team Lead enforces boundaries)
- Quality gates (GSD verifies; Team Lead gates ship readiness)
- Human checkpoints (Team Lead enforces RCA + design approval)

### 13.3 Command Mapping

| Team Action | GSD Command | Team Lead Adds |
|-------------|-------------|----------------|
| Understand what to build | `/gsd-discuss-phase N` | Objective capture, scope boundaries |
| Plan the work | `/gsd-plan-phase N` | Specialist assignment, scope check |
| Build it | `/gsd-execute-phase N` | Agent monitoring, deviation detection |
| Verify it works | `/gsd-verify-work N` | Quality gate enforcement |
| Ship it | `/gsd-ship N` | Pre-ship checklist, security gate |

### 13.4 State Files

| File | Owner | Purpose |
|------|-------|---------|
| `.planning/STATE.md` | GSD | Single source of truth for project state |
| `.planning/ROADMAP.md` | GSD | Phase definitions and milestones |
| `.planning/PROJECT.md` | GSD | Project context and goals |
| `.planning/config.json` | GSD | Workflow configuration |
| `TEAM_STATUS.md` | Team Lead | Operational dashboard (does NOT replace STATE.md) |

## 14. Anti-Patterns

- Implementing directly when a specialist should handle it
- Skipping the GSD phase loop
- Approving ship without quality gates passing
- Allowing scope creep without user approval
- Moving from RCA → fix without human approval
- Suppressing type errors or tests
- Leaving code in a broken state
- Forking or modifying GSD Core
- Activating agents without domain justification
- Treating GSD agents as specialist agents (they are workflow agents)

## 15. Agent Reference

| Agent | File | Tier | Role |
|-------|------|------|------|
| Team Lead | `framework/opencode/agents/team-lead.md` | — | Governance and orchestration |
| Architect | `framework/opencode/agents/architect.md` | Strategic | Read-only architecture |
| Reviewer | `framework/opencode/agents/reviewer.md` | Strategic | Independent engineering review |
| Frontend | `framework/opencode/agents/frontend.md` | Domain | React, Next.js, UI/UX |
| Backend | `framework/opencode/agents/backend.md` | Domain | Python, FastAPI, business logic |
| Database | `framework/opencode/agents/database.md` | Domain | Supabase, PostgreSQL, schema |
| QA | `framework/opencode/agents/qa.md` | Quality/Risk | Testing strategy |
| Security | `framework/opencode/agents/security.md` | Quality/Risk | Threat modeling, blocking |
| Design Reviewer | `framework/opencode/agents/design-reviewer.md` | Quality/Risk | Visual/UX review |
| Debugger | `framework/opencode/agents/debugger.md` | Tactical | Root cause investigation |
| RCA Reviewer | `framework/opencode/agents/rca-reviewer.md` | Tactical | RCA adversarial review |
| Implementer | `framework/opencode/agents/implementer.md` | Tactical | Bounded-scope executor |
| Test Engineer | `framework/opencode/agents/test-engineer.md` | Tactical | Test implementation |

## 16. Command Reference

| Command | File | Purpose |
|---------|------|---------|
| `/team-status` | `framework/opencode/commands/team-status.md` | Project status dashboard |
| `/team-review` | `framework/opencode/commands/team-review.md` | Orchestrate team review |
| `/team-ship` | `framework/opencode/commands/team-ship.md` | Pre-ship quality gates + ship |
| `/bugfix` | `framework/opencode/commands/bugfix.md` | 10-gate bugfix workflow |
| `/debug` | `framework/opencode/commands/debug.md` | 10-gate debugging workflow |
| `/feature` | `framework/opencode/commands/feature.md` | 10-gate feature development |
| `/verify` | `framework/opencode/commands/verify.md` | Final quality verification |
