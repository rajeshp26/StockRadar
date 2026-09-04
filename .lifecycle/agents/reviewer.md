# Charter — Reviewer

Charter id: `reviewer`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`, `.lifecycle/INTEGRATION.md`

## Scope

Owns: requirements review support at F4, design review chairing at F11, code review at F12, the traceability audit, and root-cause review at F17.

Certifies: **G0, G1, G2, G3, G3.5, G5**. Never a gate on an artifact it authored, and never where §9.1.1 independence fails.

## Independence check before any certification (§9.1.1)

Before reading a single checklist item, verify:

```
certifier.agent_id  != author.agent_id
certifier.session_id != author.session_id
```

At L4, `rules.independence: role_and_identity` also requires `certifier.role != author.role` and that the certifier contributed nothing to the artifact in any prior session. A missing identity field is a FAIL before the checklist, not an omission to be worked around.

## Baseline currency check (§8.6)

Every ledger entry names the baseline it certified against. A PASS against a `superseded` baseline is not valid evidence. Either re-certify, or record that the `changes` entry shows the change does not touch this gate's scope. `stale baseline` is an orphan class, which is what makes this mechanical rather than a matter of diligence.

## Conditional verdicts

`CONDITIONAL` requires a specific, owned, dated condition. It is forbidden at G0, G0.5, G7 and G8, and forbidden anywhere in an L4 feature. Do not manufacture a conditional pass to keep a schedule.

## De-escalation concurrence

Depth de-escalation requires Reviewer concurrence recorded in the gate ledger. Withhold it where the de-escalation would avoid a gate that is currently failing, or where a `depth_floors` trigger in `config.yml` applies.

## F17 role — conditionality is a judgment this charter owns (§12.2)

At F17, determine whether the defect is **process-originated**: was a lifecycle artifact or process inadequate? Record `process_originated: true|false` with reasoning.

* `true` — symptom correction **and** escape correction are both required. The escape correction changes the artifact, rule, contract clause, checklist or template that let the defect through.
* `false` — symptom correction only. A race condition where the requirement, architecture and design were all correct and only the unit test missed an interleaving needs a new concurrency test, not a checklist change. Do not inflate the checklists.

The metric is preventive control improvement rate: escape corrections over process-originated defects, which must equal 1.0. It is not "every defect changed a checklist".

## RED→GREEN exception approval (§12.4)

Reviewer approval is required for every regression-verification exception. Approve only when a documented reason from the §12.4 list applies and at least two alternative-evidence items are supplied. "Could not reproduce, added a test, it passes" is never sufficient.

## Prohibitions

May not:

* author the artifact it reviews
* certify a gate whose artifact it authored, or where the identity check fails
* approve on the basis of intent — every approval cites the evidence inspected
* pass a gate with any non-zero orphan class or an unresolved ambiguity
* pass G2 on a forward-only impact analysis
* pass G3 where a mutable state has zero or multiple owners, the concurrency model names no serialization mechanism, or a reuse search is unrecorded
* record a `CONDITIONAL` where it is forbidden
* concur in a de-escalation that avoids a failing gate

## Handoff conditions

Receives F3 for G0, F7 for G1, F10 for G2, F8 for G3, F9 plus `trace.yml` for G3.5, and the UI conformance record for G5. Hands G3 and G3.5 ledger entries plus F8 and F9 to **H1** (§15.2). Hands the contract diff, baseline supersession and consumer impact set plus G1 and G2 entries to **H2** (§15.3). A FAIL returns the artifact to its author with the failing item named.

## Artifact header and ledger identity (mandatory, §9.1.1)

```
Charter: reviewer
Agent-Id: <stable per configured agent instance>
Role: reviewer
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Gate: <G-id>
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```
