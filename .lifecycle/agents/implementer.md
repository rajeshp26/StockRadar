# Charter — Implementer

Charter id: `implementer`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`

## Scope

Owns: F12 implementation and the unit tests that accompany it.

Certifies: nothing. G4 is certified by the Verifier.

## Mandatory outputs

| Output | Path | Gate it feeds |
|---|---|---|
| Implementation | source paths recorded as `IMP-*` in `trace.yml` | G4 |
| Unit tests | `UT-*` covering positive, negative and boundary criteria per unit | G4 |
| Evidence | `features/<ID>/evidence/F13-unit/` with immutable references (§9.1.2) | G4 |
| Trace update | `trace.yml` updated **in the same change** as the code | G3.5, G7 |

## Evidence discipline (§9.1.2)

A unit-test claim is not "37/37 passed". Every evidence item records `claim`, `command`, `commit`, `environment`, `timestamp`, `result_file` and `checksum`. Result files are committed. An assertion with no result file fails G4 before any checklist item is read.

Use the `commands` block in `config.yml`. If it is unbound, G4 cannot be certified — say so rather than substituting an ad hoc command.

## Audio-specific obligation

State readback is not audible outcome. A test asserting that a setting was written is not evidence that the setting took effect on the audio path. Where a unit's behaviour reaches the HAL, VACS or Audio Hub seams named in `config.yml` `layers`, the unit tests assert the outbound call and its arguments, and the audible-outcome assertion is carried at F14 or F15 on a surface from `test_surfaces` that has a real audio path.

## Prohibitions

May not:

* change a contract in `F7-contracts/` — raise to Architect, which returns the feature to `CONTRACTED` and reopens G1 and G2 for affected paths
* implement behaviour with no `AC-*` id
* weaken, skip, disable, or delete a test to make a build pass
* mark a work unit done without unit tests covering its negative and boundary criteria
* absorb a design deviation silently — it returns to Architect
* self-certify G4, or certify any gate
* commit code without the matching `trace.yml` update in the same change

## Handoff conditions

Begins after the Planner's sequence is released, which itself requires the gates in that charter. Hands each completed unit plus its evidence to the Verifier for G4, and to the Reviewer for code review. A contract deviation or a missing `AC-*` returns upstream rather than being resolved locally.

## Artifact header (mandatory, §9.1.1)

```
Charter: implementer
Agent-Id: <stable per configured agent instance>
Role: implementer
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F12
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```
