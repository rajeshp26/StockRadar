# DEF-<nnn>

```
Charter: reviewer              # F17 root-cause review is Reviewer-owned
Agent-Id: <...>
Role: reviewer
Session-Id: <...>
Feature: <FEATURE-ID>
Phase: F17
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```

Schema: `.lifecycle/schema/defect.schema.json`
Spec: §12. A defect is evidence that the engineering system allowed an error to be created and then failed to catch it.

## Summary

<one sentence, observable>

## Reproduction

```yaml
deterministic: true|false
steps:
  - ...
```

## Escape and detection

```yaml
introduced_at: requirement | acceptance_criterion | scenario | architecture |
               interface_contract | detailed_design | implementation |
               environment_configuration
detected_at:   unit | integration | system | validation | production
escape_path:   [...]
```

## Root cause

Why it was **possible**, not just what is wrong.

## Classification (§12.2)

```yaml
process_originated: true|false
```

Reasoning: <was a lifecycle artifact or process inadequate?>

This single field decides what follows. `true` requires both corrections below. `false` requires symptom correction only — and the absence of a checklist change is then **correct**, not a finding. Do not inflate the checklists.

## Symptom correction

Always required. Fix the software so the defect no longer exists.

```yaml
description: ...
elements_changed: [...]
tests_added: [...]
```

## Escape correction

Required **only when `process_originated: true`**. Fix the artifact or process that let it through.

```yaml
artifact_or_process_changed: [requirement | acceptance_criterion | scenario |
                              matrix_dimension | design_rule | pattern_constraint |
                              contract_clause | test_case | checklist_item | template]
description: ...
reentry_phase: <F-id>          # exit from DEFECT_LOOP re-enters here
gates_reopened: [...]
```

Delete this section entirely when `process_originated: false`.

## Regression verification (§12.4)

### Preferred — RED→GREEN

```yaml
mode: red_green
test: <ST-/IT-/UT- id>
red_evidence: <evidence item: failing before the fix>
green_evidence: <evidence item: passing after the fix>
```

### Exception — only when deterministic pre-fix reproduction is impossible

```yaml
mode: exception
test: <id>
exception:
  condition: production_only_environment | hardware_only_failure |
             timing_dependent_failure | nondeterministic_race |
             external_backend_condition | unavailable_old_build |
             safety_validation_environment
  why: ...
  alternative_evidence:        # at least TWO; fewer than two fails G7
    - ...
    - ...
  reviewer_approval:
    agent_id: ...
    role: reviewer
    session_id: ...
    timestamp: ...
```

"Could not reproduce" followed by a passing test is never acceptable.

## Disposition

```yaml
disposition: fixed | deferred | accepted_limitation | not_a_defect | duplicate
disposition_rationale: ...
```

## Worked contrast (§12.2)

| Case | Requirement | Design | process_originated | Symptom correction | Escape correction |
|---|---|---|---|---|---|
| Scenario never modelled — storage unavailable on restore | inadequate | — | **true** | new AC, design error path, tests | F2 matrix rule: sweep persistence both directions; G0 checklist item |
| Race condition, unit test missed an interleaving | correct | correct | **false** | new concurrency test | **none required** |
| Contract omitted a timeout at an IPC seam | correct | inadequate | **true** | timeout added, tests | G1 checklist item on boundary-versus-timeout |
