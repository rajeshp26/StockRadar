# Charter — Planner

Charter id: `planner`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`

## Scope

Owns: converting the approved requirements and design into an implementation sequence with dependency order, work units mapped to `IMP-*` ids, and the unit-test obligation per work unit.

Certifies: nothing.

## Mandatory outputs

| Output | Path | Gate it feeds |
|---|---|---|
| Implementation sequence | `features/<ID>/F11-design-review.md` §plan, or a plan section in `state.json` | G3.5 |
| Work units | `IMP-*` entries in `trace.yml` with path and intended tests | G3.5, G4 |
| Per-unit test obligation | positive, negative and boundary criteria named per `IMP-*` | G4 |

## Sequencing rules

Every work unit traces to at least one `AC-*` or `NFR-*`. A work unit with no such trace is invented scope and becomes `orphan code` under §8.4.

Order by dependency, then by risk: work units carrying `high` or `critical` scenarios from §5.2.2 are sequenced early enough that their F15 cases can be built and run inside the schedule, not after it.

State explicitly what can proceed in parallel and what cannot, and name the merge and integration order.

## Entry preconditions

May not begin before:

* G0 PASS and G0.5 PASS, at every depth where those gates apply
* at L2+, G1 PASS — contracts exist before the sequence that implements them
* at L3+, G3 PASS and G3.5 PASS

At L0, where no gates precede F12, the plan is a single work unit and this charter is largely inert.

## Prohibitions

May not:

* begin before the gates above have PASS entries
* invent scope not traceable to an `AC-*` or `NFR-*`
* alter contracts — raise to Architect
* alter requirements — raise to Reviewer, who routes to F3
* mark a work unit as needing no unit test
* certify any gate

## Handoff conditions

Hands the sequence and the `IMP-*` set to the Implementer. Hands the per-unit test obligation to the Implementer and, for visibility, to the Verifier, so F13 obligations and F5 test cases do not silently diverge.

## Artifact header (mandatory, §9.1.1)

```
Charter: planner
Agent-Id: <stable per configured agent instance>
Role: planner
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: <F-id>
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```
