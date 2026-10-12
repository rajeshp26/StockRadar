---
name: software-architecture-design
description: Design software architecture for features touching multiple components, introducing new boundaries, or changing data flow. Use when the task requires system design decisions before implementation. Covers repo-first discovery, constraint analysis, alternatives, trade-offs, contracts, and risk assessment.
---

# Software Architecture Design

Architecture is a decision with consequences. Every design choice must be justified against the existing codebase, not derived from generic patterns.

## Mandatory sequence

```
Requirement
    ↓
System understanding (codebase-first)
    ↓
Existing architecture discovery
    ↓
Constraints (technical + business)
    ↓
Unknowns / assumptions
    ↓
Validation / POC if required (load technical-validation skill)
    ↓
Architecture alternatives
    ↓
Trade-off analysis
    ↓
Architecture decision
    ↓
Affected components
    ↓
Contracts required
    ↓
Data model changes
    ↓
Risks
    ↓
Validation criteria
```

## Rule: repo-first, not generic-first

Before proposing any architecture, the Architect MUST:

1. **Inspect the existing codebase** using codegraph, lsp, and grep
2. **Discover existing patterns** — how does this repo solve similar problems?
3. **Map existing components** — what already exists that can be reused or extended?
4. **Understand existing data flow** — how does data move today?
5. **Identify existing contracts** — what API shapes are already defined?

Generic architecture disconnected from the actual codebase is a finding, not a design.

## Required output

```yaml
architecture:
  requirement_id: REQ-XXX
  existing_patterns_reused:
    - component: [what exists]
      how: [how it is reused or extended]
  new_components_required:
    - component: [what is new]
      purpose: [why it is needed]
  modified_components:
    - component: [what changes]
      change: [what specifically changes]
  interfaces:
    - type: [api | internal | event | database]
      description: [what it does]
      consumers: [who uses it]
  data_flow:
    description: [how data moves through the system]
    affected_paths: [file paths]
  constraints:
    - [technical constraint]
    - [business constraint]
  unknowns:
    - question: [what is uncertain]
      resolution: [repo evidence | docs | experiment | POC | accepted assumption]
  risks:
    - risk: [what could go wrong]
      severity: [low | medium | high | critical]
      mitigation: [how to reduce]
  decisions:
    - id: D-XXX
      decision: [what was decided]
      rationale: [why this over alternatives]
      alternatives_rejected:
        - option: [rejected option]
          reason: [why rejected]
  contracts_required:
    - contract_id: [API contract ID]
      change_type: [new | modify]
  data_model_changes:
    - entity: [what entity changes]
      change: [add | modify | remove]
  validation_criteria:
    - [how to prove the architecture works]
```

## Design checklist (mandatory before finishing)

Before completing, verify every item:

- [ ] Existing codebase inspected with tools (not memory)
- [ ] Existing patterns identified and documented
- [ ] New vs modified components explicitly separated
- [ ] Interfaces defined with consumers
- [ ] Data flow traced through existing paths
- [ ] Constraints documented (not assumed)
- [ ] Unknowns resolved or escalated
- [ ] Risks identified with mitigations
- [ ] Alternatives considered and rejected with reasons
- [ ] Contracts required identified
- [ ] Data model changes specified
- [ ] Validation criteria defined

## When to escalate

Escalate to Team Lead when:
- Architecture requires a new boundary not covered by existing patterns
- Multiple equally valid approaches exist with no clear winner
- Material assumptions remain unresolved after validation attempt
- Contract change is incompatible with existing consumers

## Integration with other skills

- Load `technical-validation` when unknowns require resolution before design
- Load `api-design` when new or modified API endpoints are required
- Load `database-schema-design` when data model changes are needed
- Load `contract-authoring` after architecture decisions are finalized
- Load `performance-testing` when architecture introduces latency/throughput concerns

## Architecture findings (evidence-backed, before design)

Architecture work is incomplete if it only describes the system. Before proposing
changes, record a findings pass over the EXISTING architecture. Every finding
needs evidence (file+line or a test), impact, severity, confidence, and a
smallest safe correction. Reject style-only or hypothetical findings.

| Type | Meaning |
| --- | --- |
| architecture_debt | works today, makes future changes harder |
| boundary_violation | responsibility crosses a declared boundary |
| convention_drift | implementation diverges from the repo's dominant pattern |
| flow_conflict | multiple sources of truth, bypassed layers, circular or dead flows |

```yaml
architecture_findings:
  - type: [architecture_debt | boundary_violation | convention_drift | flow_conflict]
    severity: [low | medium | high]
    confidence: [low | medium | high]
    evidence: [file path and line, or a test that demonstrates it]
    impact: [what it breaks or slows down]
    smallest_safe_correction: [minimal change that removes the finding]
```

Routing: a confirmed finding becomes a claim-ledger entry, then a planner task if
actionable, and the reviewer verifies the correction. Do not create a separate
debt-register subsystem.

## Source code is authoritative, graphs are navigation

Graph/codegraph output accelerates navigation; direct source inspection wins
when they conflict. Never record "graph says X" as an architecture finding. The
chain is: graph suggests X -> inspect source -> confirm or reject -> claim.