# F9 — Detailed Design (abbreviated, one page per Rule D2)

Feature: FEAT-2026-001

```yaml
author: { agent_id: arch-4c19, role: architect, session_id: s-2026-08-26-b, timestamp: 2026-08-26T16:20:00-04:00 }
charter: .lifecycle/agents/architect.md
```

## 1. Design elements

| id | Component | Satisfies | Contracts | Units |
|---|---|---|---|---|
| DES-1 | CMP-02 | AC-001-1, AC-001-4, AC-001-5, AC-001-8, AC-001-9, AC-001-11, AC-001-12, AC-002-1, NFR-1, NFR-2, NFR-3, NFR-4 | IFC-1, EVT-1 | IMP-1, IMP-2 |
| DES-2 | CMP-01 | AC-001-1, AC-002-1 | IFC-1, EVT-1 | IMP-3 |
| DES-3 | CMP-05 | AC-001-4, AC-001-12 | — | IMP-4 |

## 2. State machine (§6.9) — required because behaviour is temporal

```
IDLE ──setZoneOffset──▶ VALIDATING
VALIDATING ──invalid──▶ IDLE            (OFFSET_OUT_OF_RANGE)
VALIDATING ──no zone──▶ IDLE            (ZONE_NOT_PRESENT)
VALIDATING ──valid────▶ ARBITRATING
ARBITRATING ──lost────▶ IDLE            (SUPERSEDED, loser notified)
ARBITRATING ──won─────▶ STORING
STORING ──repo error──▶ IDLE            (STORAGE_UNAVAILABLE, applied value unchanged)
STORING ──stored──────▶ APPLYING
APPLYING ──apply fail─▶ RECONCILE_PENDING (APPLY_FAILED)
APPLYING ──applied────▶ IDLE            (EVT-1 published)
RECONCILE_PENDING ──reapply──▶ APPLYING (stored value authoritative)
POWER_ON ──stored value present──▶ APPLYING (before first zone output, AC-001-11)
```

Every error transition is present, which is what §6.9 requires rather than a happy-path diagram.

## 3. Error propagation

Repository errors are mapped, not leaked: any repository exception becomes STORAGE_UNAVAILABLE at the IFC-1 boundary, with the underlying reason logged per NFR-4. CMP-01 never sees a persistence-layer error type.

## 4. Threading and lifecycle

One dispatch thread per zone queue, owned by CMP-02 for the life of the service. Repository I/O is off-thread with results posted back to the owning queue, so the single-writer invariant holds without a lock on the offset value itself.

## 5. Patterns (§6.8)

None introduced. The existing command-queue mechanism is reused, so no pattern justification block is required. Adding a Strategy here for a single arbitration rule would be a snowflake.
