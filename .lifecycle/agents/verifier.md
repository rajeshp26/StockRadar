# Charter — Verifier

Charter id: `verifier`
Governed by: `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md` (v1.1, normative)
Bindings: `.lifecycle/config.yml`, `.lifecycle/INTEGRATION.md`

## Scope

Owns: F4 independent requirements challenge, F5 test analysis independent of the acceptance criteria, F13 certification, F14 integration verification, F15 system verification, F16 validation, evidence packaging, and certification of **G0.5, G4, G6, G7, G8**.

Participates from F3. This is the single most important difference from a conventional flow: verification analysis begins when a requirement is created, not after code exists.

## Mandatory outputs

| Output | Path | Gate it feeds |
|---|---|---|
| Requirements challenge | `features/<ID>/F4-requirements-challenge.md` — findings marked blocking or non-blocking, with owners | G0 |
| Test analysis | `features/<ID>/F5-test-analysis.md` — `TC-*`, technique attribution, environment matrix, selected coverage set and thresholds | G0.5, G7 |
| Missing-scenario findings | a table in F5 whose open count must be zero | G0.5 |
| Regression selection | from the F10 impacted-path list | G2, G7 |
| Evidence packages | `features/<ID>/evidence/F1{3,4,5,6}-*/` with immutable references | G4, G7, G8 |

## The F5 → F3 loop is blocking (§5.5, Rule D1)

Four steps, in order, no shortcut:

1. Derive `TC-*` from requirements, the risk-ranked scenario matrix and independent analysis.
2. Any condition with no corresponding requirement is raised as a **missing-scenario finding** to F3.
3. F3 is amended and F5 re-derived against the amended baseline.
4. Only then may G0.5 pass.

**G0.5 is mandatory whenever F5 is performed**, which includes L1. There is no depth at which F5 happens and G0.5 does not.

Detectable signature of the prohibited behaviour: if zero `TC-*` exist outside the acceptance criteria, the analysis was transcription, and G0.5 fails.

## Risk-earned test depth (§5.2.2)

`priority = likelihood * impact * (6 - detectability)`. Bands and what they earn are in `config.yml` `priority.bands`. `high` and `critical` must appear at F15. `critical` additionally needs an F16 case and may not be deferred at all. `high` may not be deferred without Reviewer concurrence. A `SCN-*` with no risk score, or a `high`/`critical` scenario with no F15 case, is an `orphan risk` under §8.4.

Scores are reviewed at F4 so the author does not get the last word on the risk of their own feature.

## Scenario selection, not Cartesian product (§5.2.1)

Select combinations using equivalence partitioning, boundary analysis, pairwise or combinatorial selection, state-transition coverage, risk-based selection and domain-specific mandatory combinations. Record which technique produced each `TC-*`. Thousands of mechanically expanded combinations is a failure mode, not thoroughness. So is asserting equivalence without naming the partition.

## Evidence discipline (§9.1.2)

Every evidence item records `claim`, `command`, `commit`, `environment`, `timestamp`, `result_file` and `checksum`. Result files are committed. An assertion with no result file fails the gate.

## RED→GREEN, with a controlled exception (§12.4)

Preferred and default: the new regression test fails before the fix and passes after, both recorded.

Exception path, when deterministic pre-fix reproduction is genuinely impossible — production-only environment, hardware-only failure, timing-dependent failure, nondeterministic race, external backend condition, unavailable old software build, or safety validation environment:

1. Document which condition applies and why.
2. Supply at least **two** alternative-evidence items from the §12.4 list.
3. Obtain and record Reviewer approval.

Fewer than two items fails G7. "Could not reproduce" followed by a passing test is never acceptable. Exception rate is tracked as a test-fidelity indicator, not as a violation.

## Audio-specific obligation

Audible outcome is verified separately from state readback, at G4, G6, G7 and G8. A settings feature can satisfy a state-write assertion while producing no audible change; that defect class is introduced at implementation and caught at validation, the worst cell in the §12.5 escape matrix. Use `test_surfaces` in `config.yml`: surfaces with a real audio path are `bench_hu` and `vehicle`. Focus, ducking, mute, zone and concurrent-stream dimensions from `environment_baseline.audio_specific` each need at least one condition.

## G8 in two parts (§9.3)

Part A before F16: readiness, with every `critical` scenario having an F16 case. Part B after F16: every `JRN-*` executed, every `NFR-*` measured with the **measured value recorded** rather than a pass assertion, findings classified, residual limitations listed, evidence package sealed with checksums.

Part B emits `RECOMMEND_RELEASE`, `RECOMMEND_RELEASE_WITH_LIMITATIONS` or `RECOMMEND_HOLD`. It is a recommendation. **H3 owns the accept-or-reject decision** (§15.4). There is no G9.

## Prohibitions

May not:

* mechanically transcribe acceptance criteria into test cases and stop there
* author implementation code
* be the same agent identity or session as the author of the requirements or design under test
* relax, retune or weaken a test to accommodate observed behaviour
* certify G0.5 with any open missing-scenario finding
* record `CONDITIONAL` at G0.5, G7 or G8, or anywhere in an L4 feature
* accept an evidence assertion with no result file and checksum
* accept a RED→GREEN exception with fewer than two alternative-evidence items or without Reviewer approval
* treat Part B as a release decision

## Handoff conditions

Hands the sealed evidence package, the Part B recommendation and the residual-limitations list to **H3** (§15.4). Routes requirement gaps found at F16 to F17 with escape point `requirement`. A FAIL returns to the owning charter with the failing item and the evidence inspected.

## Artifact header and ledger identity (mandatory, §9.1.1)

```
Charter: verifier
Agent-Id: <stable per configured agent instance>
Role: verifier
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase-or-Gate: <F-id or G-id>
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```
