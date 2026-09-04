# F5 — Test Analysis

```
Charter: verifier
Agent-Id: <...>
Role: verifier
Session-Id: <...>              # MUST differ from the F3 author's session
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F5
Baseline: <BL-id being analysed against>
Timestamp: <ISO 8601 with offset>
```

Spec: §5.5. Derived from requirements, the risk-ranked matrix and **independent analysis** — explicitly not by one-to-one transcription of acceptance criteria.

## 1. The F5 → F3 loop (blocking, §5.5)

- [ ] **Step 1** — `TC-*` derived, including conditions the requirements do not mention
- [ ] **Step 2** — every condition with no corresponding requirement raised as a missing-scenario finding
- [ ] **Step 3** — F3 amended and F5 re-derived against the amended baseline
- [ ] **Step 4** — zero findings open

### Missing-scenario findings

| Id | Condition with no requirement | Raised | Status | Resolving AC |
|---|---|---|---|---|

**Open count must be zero before G0.5 may pass.** There is no `CONDITIONAL` path around this.

## 2. Independence signature

| Metric | Value |
|---|---|
| `TC-*` total | |
| `TC-*` not derivable from any `AC-*` | |

The second number must be **≥ 1**. Zero is the detectable signature of transcription and fails G0.5.

## 3. Test conditions with technique attribution

Every `TC-*` records which technique produced it.

| Id | Condition | Technique | Covers | Risk band | Level | Surface |
|---|---|---|---|---|---|---|
| TC-1 | | equivalence / boundary / state_transition / decision_table / error_guessing / interruption / timeout_retry / concurrency / persistence / variant / connectivity / performance / security / usability / accessibility / observability | AC-… / NFR-… / IFC-… | | F13/F14/F15/F16 | |

## 4. Technique block — applied or not applicable with a reason

At L1 this block is scoped "as applicable".

| Technique | Applied | `TC-*` produced | If not applicable, why |
|---|---|---|---|
| equivalence partitioning | | | |
| boundary value analysis | | | |
| state-transition coverage | | | |
| decision tables | | | |
| error guessing | | | |
| interruption and resumption | | | |
| timeout and retry | | | |
| concurrency | | | |
| persistence across restart/reboot/upgrade/downgrade/rollback | | | |
| configuration and platform variants | | | |
| connectivity variants | | | |
| performance | | | |
| security | | | |
| usability | | | |
| accessibility | | | |
| observability | | | |

## 5. Risk-earned depth (§5.2.2)

| Band | Count | Earns | Cases present |
|---|---|---|---|
| low | | one case at F13 or F14 | |
| medium | | case at F14 | |
| high | | case at F15 | |
| critical | | case at F15 **and** F16 | |

- [ ] Every `high` scenario has an F15 case, or a deferral with Reviewer concurrence
- [ ] Every `critical` scenario has F15 and F16 cases, with no deferral

## 6. Environment matrix

Surfaces from `config.yml` `test_surfaces`.

| Case | host_unit | service_harness | hal_vacs_loop | bench_hu | vehicle | backend_stage |
|---|---|---|---|---|---|---|

## 7. Selected coverage set and thresholds (§8.5)

Chosen from `config.yml` `coverage_menu`. At L3+, `risk_coverage` is mandatory.

| Metric | Threshold | Rationale |
|---|---|---|

Do not state or demand "100% test coverage" (§8.5).

## 8. Regression selection from F10

Populated when F10 hands over the impacted-path list.

| Impacted path | Dependents | Selected regression cases |
|---|---|---|

Every impacted path needs at least one selected case, or it is an `orphan impact`.

## 9. Audio Settings instantiation

- [ ] Conditions exist per audio-specific environment dimension
- [ ] Focus loss and regain conditions present
- [ ] Ducking onset, release and duck-during-user-change present
- [ ] Per-seat isolation condition present
- [ ] `shared_vehicle` simultaneous-write condition present
- [ ] Backend offline write, reconnect merge and conflict conditions present
- [ ] Persistence swept read **and** write
- [ ] **At least one audible-outcome condition on `bench_hu` or `vehicle`**, distinct from state readback
