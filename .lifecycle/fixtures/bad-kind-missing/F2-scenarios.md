# F2 — Scenario Model

Feature: FEAT-2026-001
Depth: L2

```yaml
author: { agent_id: res-9b41, role: researcher, session_id: s-2026-08-24-b, timestamp: 2026-08-24T15:05:00-04:00 }
charter: .lifecycle/agents/researcher.md
```

## 1. Journeys

| id | Customer | Journey |
|---|---|---|
| JRN-1 | CUS-1 | discovers the rear offset control, sets it, and hears the change persist across a drive cycle |
| JRN-2 | CUS-2 | inspects rear offsets and resets one to default |

## 2. Use cases

| id | Use case | Journeys |
|---|---|---|
| UC-001 | Rear occupant sets a volume offset for their zone | JRN-1 |
| UC-002 | Driver resets a rear zone offset to default | JRN-2 |

## 3. Selection method (§5.2.1)

Combinations are **not** Cartesian-expanded. Selected by: equivalence partitioning on offset value, boundary analysis at ±limit, pairwise interaction across `{zone set × power state × repository state}`, state-transition coverage on the write path, risk-based selection per §5.2.2, and one domain-mandatory combination (offset × alert playback).

Unreachable combinations, recorded once: offset write on a variant with no rear zone endpoint is unreachable through the HMI because the control is not rendered; it remains reachable through the service API, so SCN-9 tests the API path only.

## 4. Scenario matrix

| id | Title | Class | Technique | L | I | D | Score | Band |
|---|---|---|---|---|---|---|---|---|
| SCN-1 | Rear occupant sets offset, value applied and audible | normal | equivalence | 5 | 3 | 4 | 30 | medium |
| SCN-2 | Offset at +max and −max | boundary | boundary | 3 | 3 | 3 | 27 | medium |
| SCN-3 | Offset persists across accessory-off and power cycle | persistence | state_transition | 4 | 4 | 3 | 48 | high |
| SCN-4 | Repository unavailable at write | failure | state_transition | 3 | 4 | 2 | 48 | high |
| SCN-5 | Repository returns after outage; pending write reconciled | recovery | state_transition | 2 | 4 | 2 | 32 | medium |
| SCN-6 | Rear occupant and driver write the same zone simultaneously | concurrent | pairwise | 2 | 4 | 1 | 40 | medium |
| SCN-7 | Offset must not change alert or chime level | safety | domain_mandatory | 2 | 5 | 2 | 40 | medium |
| SCN-8 | Rapid repeated slider changes coalesce | repeated | equivalence | 4 | 2 | 3 | 24 | medium |
| SCN-9 | Offset write on a variant with no rear zone | negative | pairwise | 2 | 3 | 4 | 12 | low |
| SCN-10 | Power loss mid-write leaves no partial value | interrupted | state_transition | 2 | 4 | 1 | 40 | medium |
| SCN-11 | Upgrade from a build with no offset column | upgrade | state_transition | 3 | 3 | 2 | 36 | medium |
| SCN-12 | Downgrade and rollback discard the offset cleanly | rollback | state_transition | 2 | 4 | 2 | 32 | medium |
| SCN-13 | Seat isolation: rear change does not alter front value | normal | pairwise | 4 | 4 | 3 | 48 | high |
| SCN-14 | Driver resets rear offset to default | alternate | equivalence | 3 | 2 | 4 | 12 | low |
| SCN-15 | Offset set below the audible floor, misuse of the control | misuse | boundary | 2 | 4 | 3 | 24 | medium |

Class coverage: normal, alternate, negative, failure, recovery, boundary, concurrent, persistence, upgrade, rollback, safety, repeated, interrupted, misuse all present. `performance` is discharged by NFR-1/NFR-2 conditions rather than a distinct SCN, recorded here as a deliberate choice.

No dimension is discharged only by a `low` scenario. SCN-9 and SCN-14 are the only `low` bands and neither is the sole scenario for its dimension.

## 5. Persistence sweep rule

Every persistence dimension is swept in **both** directions — read and write — per the G0 checklist item inherited from DEF-031 in v1.0. SCN-3 covers read-after-restore; SCN-4 and SCN-10 cover the write path; SCN-11 and SCN-12 cover schema transitions in both directions.

## 6. Exit (§5.2)

Every UC traces to a JRN; every applicable class has a scenario; every SCN is risk-scored; the unexpected-input, environment-change and dependency-failure question is answered for both use cases.
