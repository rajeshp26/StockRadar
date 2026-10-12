---
name: technical-validation
description: Prevent agents from turning assumptions into implementation decisions without sufficient evidence. Cross-cutting skill for resolving unknowns through an evidence hierarchy: repo inspection → documentation → experiment → POC → explicit assumption. Use whenever a material assumption affects architecture, API, database, performance, security, or correctness.
---

# Technical Validation

An assumption that materially affects architecture, implementation, API, database design, performance, security, or correctness MUST NOT silently become a design decision.

## Evidence hierarchy (always follow this order)

```
Claim / Assumption
       ↓
Can repository evidence answer it?
       │
       ├── YES → inspect repository (codegraph, lsp, grep, read)
       │
       └── NO
            ↓
       Can documentation answer it?
            │
            ├── YES → research (context7, websearch, github_search)
            │
            └── NO
                 ↓
             Can an experiment answer it?
                 │
                 ├── YES → perform experiment (minimal code, isolated test)
                 │
                 └── NO
                      ↓
                 Can a POC answer it?
                      │
                      ├── YES → perform POC (throwaway implementation)
                      │
                      └── NO → explicitly document assumption as accepted risk
```

## Critical rule

**Never skip a level.** If repository evidence could answer the question, do not research external docs. If docs could answer it, do not build an experiment. Each level is more expensive than the previous.

## Validation record

Every material assumption MUST produce a validation record:

```yaml
validation:
  question: [what is uncertain]
  evidence_level: [repo | docs | experiment | poc | assumption]
  investigation:
    method: [how it was investigated]
    tools_used: [which tools were used]
    result: [what was found]
  conclusion: [answer derived from evidence]
  remaining_uncertainty: [what is still unknown]
  decision_enabled: [what decision this validation unblocks]
  assumption_if_unresolved: [explicit statement if assumption accepted]
```

## What counts as material

A material assumption is one where, if wrong, any of the following would change:

- Architecture decision
- API contract
- Data model
- Performance characteristics
- Security posture
- Correctness guarantee

Immaterial assumptions (naming conventions, formatting preferences, file organization within a component) may be documented but do not require validation.

## Validation triggers

Load this skill when any of the following are true:

- Unknown system behavior relevant to the design
- External library or API behavior assumed but not verified
- Performance characteristic assumed but not measured
- Security property assumed but not tested
- Data compatibility assumed but not confirmed
- Integration behavior assumed but not verified
- Concurrency behavior assumed but not tested

## Experiment design

When an experiment is the appropriate validation level:

1. **Minimal scope** — test only the uncertain behavior
2. **Isolated** — do not modify production code for an experiment
3. **Disposable** — experiment artifacts are not committed
4. **Reproducible** — another agent can repeat it
5. **Conclusive** — the experiment must be able to prove or disprove the assumption

## POC design

When a POC is required:

1. **Throwaway** — POC code is not merged
2. **Scoped** — POC answers a specific question, not "will this whole thing work"
3. **Time-boxed** — if POC takes longer than proportionate to the risk, escalate
4. **Documented** — findings feed back into architecture decisions

## Assumption acceptance

When no validation method can resolve the assumption:

1. Explicitly state the assumption
2. State why it cannot be validated
3. State the impact if wrong
4. Record it as an accepted risk with an approver
5. Plan re-validation when the information becomes available

## Integration with other skills

- Feeds into `software-architecture-design` — unknowns must be resolved before architecture is finalized
- Feeds into `api-design` — API behavior assumptions must be validated
- Feeds into `database-schema-design` — data compatibility assumptions must be validated
- Feeds into `performance-testing` — performance assumptions must be measured
