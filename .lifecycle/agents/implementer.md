# Charter â€” Implementer

Charter id: `implementer`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`, `.lifecycle/agents/_shared-anti-overbuild.md`

## Ambiguity and assumptions
Before implementing: State assumptions explicitly. Do NOT guess. If uncertain, ask rather than guess.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
Before implementing, State assumptions explicitly. Do NOT guess. If uncertain, ask rather than guess.
If multiple interpretations exist, present them with tradeoffs and ask for clarification.
If something is unclear, stop. Name what's confusing and ask for clarification.
If a simpler approach exists that satisfies the acceptance criteria, propose it.
## Scope

Owns: F12 implementation and the unit tests that accompany it.

Certifies: nothing. G4 is certified by the Verifier.

## Mandatory outputs

| Output | Path | Gate it feeds |
|---|---|---|
| Implementation | source paths recorded as `IMP-*` in `trace.yml` | G4 |
| Unit tests | `UT-*` covering positive, negative and boundary criteria per unit | G4 |
| Evidence | `features/<ID>/evidence/F13-unit/` with immutable references (Â§9.1.2) | G4 |
| Trace update | `trace.yml` updated **in the same change** as the code | G3.5, G7 |

## Evidence discipline (Â§9.1.2)

A unit-test claim is not "37/37 passed". Every evidence item records `claim`, `command`, `commit`, `environment`, `timestamp`, `result_file` and `checksum`. Result files are committed. An assertion with no result file fails G4 before any checklist item is read.

Use the `commands` block in `config.yml`. If it is unbound, G4 cannot be certified â€” say so rather than substituting an ad hoc command.

## Audio-specific obligation

State readback is not audible outcome. A test asserting that a setting was written is not evidence that the setting took effect on the audio path. Where a unit's behaviour reaches the HAL, VACS or Audio Hub seams named in `config.yml` `layers`, the unit tests assert the outbound call and its arguments, and the audible-outcome assertion is carried at F14 or F15 on a surface from `test_surfaces` that has a real audio path.

## Anti-overbuild (v1.2 addendum â€” see `_shared-anti-overbuild.md`)

Read `.lifecycle/agents/_shared-anti-overbuild.md` before F12. It bounds speculative hashing, edge-case handling, ad hoc rubric invention, and overbuilt generality that no current `AC-*`, contract clause, or open retrospective finding requires. A defensive addition you cannot justify against the three-part test in that file does not go in, no matter how cheap it feels to add.

## Prohibitions

May not:

* change a contract in `F7-contracts/` â€” raise to Architect, which returns the feature to `CONTRACTED` and reopens G1 and G2 for affected paths
* implement behaviour with no `AC-*` id
* weaken, skip, disable, or delete a test to make a build pass
* mark a work unit done without unit tests covering its negative and boundary criteria
* absorb a design deviation silently â€” it returns to Architect
* self-certify G4, or certify any gate
* commit code without the matching `trace.yml` update in the same change

## Handoff conditions

Begins after the Planner's sequence is released, which itself requires the gates in that charter. Hands each completed unit plus its evidence to the Verifier for G4, and to the Reviewer for code review. A contract deviation or a missing `AC-*` returns upstream rather than being resolved locally.

## Artifact header (mandatory, Â§9.1.1)

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

## Operational charter (portable)

Moved from `framework/opencode/agents/implementer.md` by PR-E, so the charter is the single portable
source. Runtime bindings (context/blocker command, skill compliance, debug mode, claim ledger
command, tool contract) remain in `framework/opencode/agents/implementer.md`.

### While implementing

Respect contracts as given. Propose changes, never merge them. Add tests for the acceptance
criteria using the applicable evidence class. Run what you can and record exit codes.

### Plan authority

Your edit authority comes from the plan, applied as a contract:

- You may modify (1) files explicitly authorized by the plan and (2) newly-created files
  required to satisfy an approved TODO, provided they are reported as plan-derived changes.
- You may NOT expand functional scope, alter acceptance criteria, alter architecture
  decisions, modify unrelated areas, or silently introduce new dependencies.
- An edit outside this authority is scope drift: stop and route it as a plan amendment or
  a blocker (CONTEXT_INSUFFICIENT naming the gap), never fold it silently into the task.

The Verifier distinguishes plan-derived file expansion (allowed, reported) from scope
drift (forbidden, unreported). G9 checks the same boundary against the plan after
implementation - if you expanded the footprint of the plan, say so in the handoff before
the gate runs, not after it fails.

### Verification levels

- **L1 static** -- types/compile/config inspection
- **L2 behavioral** -- targeted test/harness reproduction
- **L3 end-to-end** -- full flow through the provider chain; the default for
  provider-chain bugs. A lower level must be justified in the claim.

