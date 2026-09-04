# F5 — Test Analysis

Feature: FEAT-2026-001
Baseline: BL-REQ-002

```yaml
author: { agent_id: ver-2e88, role: verifier, session_id: s-2026-08-25-c, timestamp: 2026-08-25T17:30:00-04:00 }
charter: .lifecycle/agents/verifier.md
```

## 1. Techniques applied

Equivalence partitioning, boundary value analysis, state-transition coverage, decision table, error guessing, interruption/resumption, timeout and retry, concurrency, persistence across restart/reboot/upgrade/downgrade/rollback, configuration and variant sweep, connectivity variants (n/a — no network path), performance, observability. Security and accessibility recorded as not applicable with reason: no new data class, no new UI element beyond an existing slider pattern.

## 2. Test conditions

| id | Condition | Technique | Derived from | AC-derivable |
|---|---|---|---|---|
| TC-1 | Offset applied to target zone only | equivalence | AC-001-1 | yes |
| TC-2 | Audible level change on the target zone | domain | AC-001-1 | yes |
| TC-3 | Offset at +max and −max exact | boundary | AC-001-7 | yes |
| TC-4 | Offset one step beyond range rejected | boundary | AC-001-8 | yes |
| TC-5 | Repository unavailable → current value retained | error_guessing | AC-001-4 | yes |
| TC-6 | Concurrent writes → one deterministic winner | concurrency | AC-001-9 | yes |
| TC-7 | Loser receives supersede notification | concurrency | AC-001-9 | yes |
| TC-8 | Reapply precedes first output on the zone | state_transition | AC-001-11 | yes |
| TC-9 | Upgrade defaults offset to 0 dB, preserves others | state_transition | AC-001-12 | yes |
| TC-10 | Rollback leaves prior settings readable | state_transition | AC-001-12 | yes |
| TC-11 | Alert and chime level unchanged under max offset | domain | AC-001-7 | yes |
| TC-12 | ZONE_NOT_PRESENT on a variant without the endpoint | equivalence | AC-001-5 | yes |
| TC-13 | Rejected writes log reason code and requested value | observability | NFR-4 | yes |
| TC-14 | HMI-commit-to-audible ≤ 200 ms p95 | performance | NFR-1 | yes |
| TC-15 | Repository write ≤ 50 ms p95 | performance | NFR-2 | yes |
| TC-16 | First-output delta ≤ 120 ms with a stored offset | performance | NFR-3 | yes |
| TC-17 | **Power loss between repository commit and zone apply leaves no divergence between stored and applied value** | error_guessing | independent | **no** |
| TC-18 | **Rapid repeated writes coalesce without transient audible stepping** | error_guessing | independent | **no** |
| TC-19 | **Offset survives a repository compaction or vacuum cycle** | error_guessing | independent | **no** |
| TC-20 | **Seat isolation holds when both zones are written in the same arbitration window** | pairwise | independent | **no** |
| TC-21 | **Offset applied while the zone is muted becomes correct on unmute, not doubled** | state_transition | independent | **no** |

TC-17 through TC-21 are not derivable from any AC. Five conditions, which satisfies the G0.5 item requiring at least one — the detectable signature that transcription did not occur.

## 3. Missing-scenario findings raised to F3 (§5.5)

| id | Finding | Status |
|---|---|---|
| MSF-1 | TC-21 has no requirement: behaviour of an offset applied while muted is unspecified | closed — AC-001-7 clarified that offset composes with mute rather than replacing it |
| MSF-2 | AC-001-9 said "last write wins", which is not deterministic across IPC | closed — F3 amended, BL-REQ-001 superseded by BL-REQ-002 |
| MSF-3 | TC-17 divergence between stored and applied value unspecified | closed — AC-001-11 extended: reapply is authoritative over any partially applied value |

Open findings: **0**. F5 re-derived against BL-REQ-002 after the amendments. G0.5 may now be certified.

## 4. Selected coverage set (§8.5)

Per `config.yml` L2 defaults plus one addition: `requirement`, `acceptance_criteria`, `scenario`, `interface_contract`, `error_path`, `regression`, and `risk_coverage` added voluntarily because five scenarios sit in the `high` band.

| Metric | Threshold |
|---|---|
| requirement coverage | 100% |
| acceptance-criteria coverage | 100% |
| scenario coverage | 100% of non-deferred |
| interface/contract coverage | 100% of IFC-1 operations |
| error-path coverage | 100% of declared error codes |
| regression coverage | 100% of F10 impacted paths |
| risk coverage | 100% of `high` and `critical` scenarios have an F15 case |

## 5. Environment matrix

| Surface | Cases |
|---|---|
| host_unit | UT-1 … UT-9 |
| service_harness | IT-1 … IT-6 |
| bench_hu | ST-1 … ST-8 (real audio path; audible assertions live here) |
| vehicle | none at L2; ST-4 is repeated on vehicle if bench cannot reproduce the alert path |

## 6. Risk-earned depth check

| Band | Scenarios | F15 case present |
|---|---|---|
| high | SCN-1, 3, 4, 5, 6, 7, 11, 12, 13 | yes, all nine |
| medium | SCN-2, 8, 10, 15 | positive + negative present |
| low | SCN-9, 14 | one nominal case each |
| critical | none | — |
