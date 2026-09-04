# F6 — Decomposition

Feature: FEAT-2026-001

```yaml
author: { agent_id: arch-4c19, role: architect, session_id: s-2026-08-26-b, timestamp: 2026-08-26T09:15:00-04:00 }
charter: .lifecycle/agents/architect.md
```

## 1. Chain

`UC → capability → responsibility → component → interface → contract → unit`

| Component | Layer | Single cohesive responsibility (§6.2) |
|---|---|---|
| CMP-01 | hmi | Render the rear zone offset control and commit user intent |
| CMP-02 | audio_service | Own the zone offset value, arbitrate writes, apply to zone gain |
| CMP-05 | persistence | Store and retrieve seat-scoped setting values |

Cohesion test per §6.2: CMP-02 holds three operations — validate, arbitrate, apply — which belong to one responsibility boundary, ownership of the offset value. Retained rather than split; the cohesion justification is recorded here rather than counting operations.

## 2. Allocation

| UC | Components |
|---|---|
| UC-001 | CMP-01, CMP-02, CMP-05 |
| UC-002 | CMP-01, CMP-02, CMP-05 |

No unallocated use case. No component allocated to zero use cases.

## 3. Interaction mechanisms (§6.3)

```
Request/response (IPC):
  CMP-01 → IFC-1.setZoneOffset(zoneId, offsetDb, requesterRole)
        → CMP-02 validate → arbitrate → CMP-05.write(seat, key, value)
        ← Applied | OFFSET_OUT_OF_RANGE | ZONE_NOT_PRESENT
          | STORAGE_UNAVAILABLE | SUPERSEDED

State exposure:
  CMP-02 exposes activeZoneOffset[zoneId] — read-only to CMP-01

Event:
  CMP-02 ──publishes EVT-1 ZoneOffsetChanged──▶ CMP-01 (HMI refresh)
```

Mid-sequence failure: if `CMP-05.write` succeeds and the zone-gain apply then fails, CMP-02 does not report Applied. It reports STORAGE_UNAVAILABLE only for write failure; an apply failure raises APPLY_FAILED and the stored value is reconciled at next reapply, which is what AC-001-11 makes authoritative.

## 4. Ownership register (§6.5) — mandatory at L2+

| State | Owner | Readers | Writers | Persistence | Sync | Control scope |
|---|---|---|---|---|---|---|
| `activeZoneOffset[zoneId]` | CMP-02 | CMP-01, CMP-02 | **CMP-02 only** | CMP-05 | EVT-1 | seat |

Exactly one authoritative owner. Two owners would be a G3 failure and an orphan state per §8.4.
