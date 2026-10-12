# Retrospective intelligence

A defect that reaches production is two failures: the defect, and the framework that passed it.
Fixing only the first guarantees the second recurs.

## When a retrospective is owed

Whenever a defect is found **after the change that introduced it was accepted**:

| Signal | Meaning |
| --- | --- |
| `TEST_FAILED_ON_PREVIOUSLY_GREEN` | a passing test broke |
| `REVIEW_REJECTED` | review caught what earlier checkpoints did not |
| `INTEGRATION_FAILED` | components correct alone, wrong together |
| `TASK_REOPENED` | completion criteria were satisfied and the work was still wrong |
| `PRODUCTION_DEFECT` | every checkpoint passed it |
| `GATE_FAILED_AFTER_ACCEPTANCE` | a gate that should have run earlier caught it late |

A retrospective is **not** owed when a checkpoint catches a defect at the first place it could
have been caught. That is the framework working. Recording a retrospective there produces
paperwork and trains everyone to ignore the ledger.

## The escape path is computed, not argued

`framework/retro/escape_path.py` takes where the defect was injected, where it was caught, and
the task's original classification, and returns the checkpoints it passed through. That set is
the framework's failure and it is arithmetic. An agent cannot reason its way out of it, and
cannot inflate it either.

## Routing gap versus containment miss

This distinction determines where the fix goes, and getting it backwards is the most common
way a retrospective wastes effort.

A **routing gap** means the checkpoint would have caught the defect but never ran — the impact
class or requirement shape did not activate it. The check is fine. Fix the routing.

A **containment miss** means the checkpoint ran and missed it. Fix the check.

Routing gaps take precedence. Activating an existing gate is cheaper and more reliable than
making an active gate smarter, and it usually closes a whole class rather than one instance.

## Recommendations must be falsifiable

A recommendation names one target from the closed list in
`framework/retro/containment_map.yaml`, each of which is a file plus a check that proves the
change landed. `none_human_judgement` with a stated reason is a valid outcome — some defects
need domain knowledge no static check can express without unacceptable false positives.

Unfalsifiable recommendations are rejected: be more careful, add more tests, improve the
process, communicate better. None can fail, so none can be verified, so none changes
behaviour.

## A claimed fix needs an exit code

`fix_verified_by` is a command and its result. The Definition-of-Done rule applies here without
modification: a fix that exists but was never demonstrated is a claim, not evidence.

## Recurrence outranks any individual retrospective

The ledger matches structural signatures, not prose, so rewording cannot hide a repeat. Second
occurrence escalates to a human with zero retries. At that point the framework has shown it
cannot close the gap by itself, and filing a third variant of the same fix is the failure
mode this rule exists to prevent.

## Where a lesson goes

A retrospective produces a lesson. Where it lands decides whether anything changes. The analyser
reports `destination.tier`. Land the lesson at the tier it names — never lower for convenience.

| Tier | Enforcement | When |
|---|---|---|
| `executable_check` | gate exit code | a gate or routing table can assert it |
| `declared_rule` | gate reads the declaration | expressible in `architecture_rules.yaml` or a skill rule |
| `design_checklist` | recorded disposition | **architecture only** — judgement at design time, no artefact to check |
| `agent_instruction` | none | non-architecture phase; prefer a check |
| `unmapped_combination` | — | the map has no row; adding the row is the fix |
| `accepted` | ledger note | prevention costs more than recurrence |

Three things this ranking exists to prevent.

**A checklist item that should be a check.** "Domain must not import transport" is a declared
boundary G3 enforces. Writing it as a checklist question replaces an exit code with a claim.

**A checklist for implementation, review, or testing.** Those lessons resolve to gates and skill
rules. The checklist tier is reachable only from `injected_at: architecture`, because that is the
one phase whose output is a decision with no artefact behind it.

**An unmapped gap recorded as accepted risk.** Different conclusions. Accepted means a change
would not pay for itself. Unmapped means the map has no row for this pair. Conflating them turns
a missing row into a decision, and the row never gets added.
