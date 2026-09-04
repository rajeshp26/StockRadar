# F2 — Scenario Model, risk-ranked

```
Charter: researcher            # or architect where the project assigns F2 there
Agent-Id: <...>
Role: <...>
Session-Id: <...>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F2
Baseline: pre-baseline
Timestamp: <ISO 8601 with offset>
```

Spec: §5.2, §5.2.1, §5.2.2. Scenarios are generated from the matrix, not from imagination.

## 1. Journeys

| Id | Customer | Journey | Discovers | Learns | Invokes | Recovers | Abandons |
|---|---|---|---|---|---|---|---|
| JRN-1 | CUS-1 | | | | | | |

## 2. Use cases

| Id | Use case | Journeys |
|---|---|---|
| UC-001 | | JRN-1 |

Every `UC-*` traces to at least one `JRN-*`.

## 3. Selection technique — not a Cartesian product (§5.2.1)

State which techniques generated the scenario set. Thousands of mechanically expanded combinations is a failure mode, not thoroughness.

- [ ] equivalence partitioning — partitions named below
- [ ] boundary analysis
- [ ] pairwise / combinatorial selection
- [ ] state-transition coverage
- [ ] risk-based selection
- [ ] domain-specific mandatory combinations

Named partitions, where equivalence is asserted:

| Partition | Members treated as equivalent | Why |
|---|---|---|
| | | |

Unreachable combinations, listed once:

| Combination | Why unreachable |
|---|---|

## 4. Scenario matrix

Dimensions to sweep, all mandatory at L3+:

| Dimension | Values in scope |
|---|---|
| Customer | |
| Surface / environment | |
| Primary state | |
| Connectivity | |
| User state | |
| Device | |
| Configuration | |
| Trigger | |
| Class | |

Coverage rule: each dimension appears in at least one scenario, and every applicable `class` value has at least one scenario.

## 5. Scenarios with risk scores (§5.2.2)

`priority = likelihood × impact × (6 − detectability)`. Bands: low 1–20, medium 21–45, high 46–80, critical 81–125.

| Id | Scenario | Class | Technique | L | I | D | Priority | Band | Earns |
|---|---|---|---|---|---|---|---|---|---|
| SCN-1 | | | | | | | | | |

What each band earns:

* **low** — one case at F13 or F14
* **medium** — case at F14
* **high** — case at F15; no deferral without Reviewer concurrence
* **critical** — case at F15 **and** F16; no deferral at all

A `SCN-*` with no risk score is an `orphan risk` (§8.4). So is a `high`/`critical` scenario with no F15 case.

Scores are reviewed at F4 by an identity other than this artifact's author.

## 6. Deferrals

| Scenario | Deferred | Reason | Owner |
|---|---|---|---|

An `SCN-*` with no `AC-*` and no recorded deferral is an `orphan scenario`.

## 7. Audio Settings instantiation

- [ ] Focus scenarios cover acquire, **loss** and **regain**
- [ ] Ducking scenarios cover onset, release, and duck during an active user change
- [ ] Per-seat scenarios assert isolation from other seats
- [ ] `shared_vehicle` scenarios cover simultaneous driver and co-pilot writes
- [ ] Persistence scenarios sweep **read and write** across restart, reboot, upgrade, downgrade, rollback
- [ ] Backend sync scenarios cover offline write, reconnect merge, conflicting device-versus-backend modification
- [ ] At least one scenario targets audible outcome on a real audio path
- [ ] Concurrent stream and multi-zone scenarios present where in scope

## 8. Exit criteria

- [ ] Every `UC-*` traces to at least one `JRN-*`
- [ ] Every applicable class has at least one `SCN-*`
- [ ] Every `SCN-*` carries `likelihood`, `impact`, `detectability`, priority and band
- [ ] Every `SCN-*` records the technique that produced it
- [ ] Unexpected-action, environment-change and dependency-failure questions answered per use case
