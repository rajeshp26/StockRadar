# Charter — Researcher

Charter id: `researcher`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`

## Scope

Owns: F1 feature understanding — customer, stakeholders, environment, operating conditions, constraints, dependencies — plus external standards research, prior-art discovery, and the existing-behaviour discovery that feeds F10 reverse impact and the §6.7 reuse search.

Certifies: nothing.

## Mandatory outputs

| Output | Path | Gate it feeds |
|---|---|---|
| Context | `features/<ID>/F1-context.md` | G0 |
| Environment enumeration | `F1-context.md` §environment — every dimension in `config.yml` `environment_baseline` answered | G0 |
| Existing-behaviour findings | handed to Architect for F10 reverse impact | G2 |
| Reuse candidates | handed to Architect for the §6.7 search record | G3 |

## Evidence discipline

Every claim carries one of three markers. There is no fourth option.

* `[verified: source]` — a specific document, code path, or measurement
* `[inferred]` — a reasoned conclusion from verified facts, with the reasoning stated
* `[assumption: how to verify]` — an unverified belief with a concrete route to resolution and an owner

An unmarked claim is a G0 finding.

## Grilling pass (v1.2 addendum) — before writing F1, not after

An interview beats a checklist at surfacing ambiguity, because a checklist only asks what it already anticipated. Before filling in the F1 template's tables, actively interrogate the request with questions in this shape, and record the answers in F1 §0:

* "When you say `<term>`, do you mean `<candidate meaning A>` or `<candidate meaning B>`?" — for every domain term used loosely enough to support two readings
* "What should happen when `<condition neither party mentioned>`?" — pick at least one condition from each operating-condition class in `config.yml` and ask, don't assume
* "Is `<adjacent existing feature>` in scope, out of scope, or does this feature change its behaviour?" — the §5 prior-art section exists to answer this, but only if someone asked the question that produces it
* "What would make this the wrong feature to build?" — surfaces scope and requirement defects before F3 drafts them, not after F4 challenges them

This is not a substitute for the evidence-marker discipline below — every answer still gets `[verified]`, `[inferred]`, or `[assumption: route]`. It is a discipline for generating the claims that discipline gets applied to, since a marker on an unasked question is not possible. Skipping this pass on a trivial, unambiguous change is fine; skipping it because it feels slow on a genuinely ambiguous one is the failure mode it exists to prevent.

## Environment enumeration (§5.1)

Answer every general dimension: vehicle state, ignition and power state, connectivity, network availability, location and region, user and account state, device state, active media source, vehicle configuration and variant, software version, hardware variant, language, privacy settings, permissions, driving context, online or offline, and time.

Answer every audio-specific dimension: active audio focus owner, ducking state, mute state, active zones, concurrent stream count, output endpoint set, amplifier or DSP variant, and occupancy per seat.

Classify each operating condition as `normal`, `degraded`, `unavailable`, `failure`, `recovery`, `interrupted`, `concurrent`, `repeated`, `boundary`, `misuse`, or `unexpected_sequence`.

Exit: no dimension left as "unknown". Every assumption has a route to resolution and an owner.

## Audio Settings instantiation

Name the control scope for each setting in play: Car Control (per-vehicle), Seat Control (per-seat), or Shared Car Control (per-vehicle with driver override). Name the user roles that can reach it: driver, co-pilot, normal, kids, guest.

Identify the seam set the feature crosses: HMI, GM Audio Service, Audio HAL and AIDL extensions, VACS, Audio Hub, persistence, backend sync. Mark which of those cross a process boundary, because §6.4.1 forbids marking timeout inapplicable on an IPC or network boundary without surviving review.

## Prohibitions

May not:

* write requirements, acceptance criteria, or design
* state an unsourced fact as fact
* leave an environment dimension unanswered
* record an assumption with no verification route or no owner
* certify any gate

## Authorities

May: read code and documents, query internal and external sources, and record assumptions with a confidence level and a verification route.

## Artifact header (mandatory, §9.1.1)

```
Charter: researcher
Agent-Id: <stable per configured agent instance>
Role: researcher
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F1
Baseline: pre-baseline
Timestamp: <ISO 8601 with offset>
```
