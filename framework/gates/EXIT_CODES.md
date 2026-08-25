# Gate Exit Code Contract — AUTHORITATIVE

Machine-checked by `framework/validate.py`. If a document disagrees with this table, the
document is wrong. Generated claims about gate behaviour must cite this file.

| Gate | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| G1 contract   | valid, types in sync, tests green | validation failed / CONTRACT_CHANGE | BLOCKED (python3 absent) | — | — |
| G2 impact     | impact mapped to N tests | UNKNOWN_IMPACT | — | — | — |
| G3 architecture | boundaries respected | boundary violation | BLOCKED (pyyaml absent) | — | — |
| G4 executable | N checks green | ≥1 check failed | — | — | — |
| G5 stack      | conformant | violations found | BLOCKED (cannot evaluate) | — | NOT_APPLICABLE (no frontend) |
| G6 browser    | specs ran and passed | specs ran and failed | **NEVER EMITTED** | UNVERIFIABLE | — |
| G7 retro      | retros complete, no recurrence | incomplete or recurrence | BLOCKED (python3/pyyaml absent) | — | NOT_APPLICABLE (no escape trigger) |
| G8 blockers  | no open blockers | open blockers listed | BLOCKED (python3/pyyaml absent) | — | — |
| G9 scope      | within declared scope (or SKIP: no plan / no changes) | undeclared files listed | — | — | — |

## G6 emits ONLY 0, 1, 3

G6 has no exit 2. Any table offering "2 = BLOCKED (no driver/config)" for G6 is a bug, and a
dangerous one: it creates a second code for the condition exit 3 exists to name. A reader who
sees BLOCKED alongside UNVERIFIABLE will treat one of them as ignorable. Missing driver,
missing config, and missing specs all return **3**.

## G7 exit 4 is not a pass

Exit 4 from G7 means no defect-escape trigger was recorded, so there was nothing to retrospect.
That is the normal case for a clean task. It is not evidence that the framework is learning —
only that nothing escaped this time. Do not report it as a passed retrospective.

## G8 blocks completion on open blockers

A non-complete stop (CONTEXT_INSUFFICIENT, BLOCKED, UNKNOWN_IMPACT, ...) recorded in
<state_root>/blockers.yaml stays open until explicitly resolved. While any open record
exists, G8 returns exit 1 and completion is refused -- the same enforcement shape G7
applies to retrospectives. Exit 0 means zero open records; exit 2 means the store could
not be read (python3/pyyaml absent or unparsable state), which is never read as zero.

## G9 skips are not silent passes

G9 judges changed source files against the plan's declared files_or_components. With no plan
context or no source changes it logs SKIP and exits 0 -- that is "nothing was judged", not
"scope respected". A skip must be reported as skipped, never counted as a passed check.

## Exit 3 is the most important code in the framework

Exit 3 means "we could not look." It is never read as "it looks right."

On exit 3 you may NOT claim the requirement is verified, and you may NOT claim it is
violated. Record it as `unverifiable` and name what is missing.

## Universal rules

| Rule | Meaning |
|---|---|
| Never pass vacuously | zero checks executed is FAIL, never pass (G4) |
| Missing tool is never a pass | substitute it, or report BLOCKED / UNVERIFIABLE |
| SKIP ≠ PASS | skip means no artefact of that class exists to judge |
| CONTRACT_CHANGE outranks test failure | a schema change causes test failure by definition; route the cause to Architect, not the symptom to Implementer |
| UNKNOWN_IMPACT is not "no impact" | zero tests found at tier 4 escalates |

## Non-zero codes are not interchangeable

BLOCKED (2) means the gate could not evaluate — a toolchain problem. UNVERIFIABLE (3) means
the gate evaluated its preconditions correctly and found no way to produce evidence — a
capability problem. NOT_APPLICABLE (4) means there is nothing of this class to judge. Only
FAIL (1) is a verdict about the code.
