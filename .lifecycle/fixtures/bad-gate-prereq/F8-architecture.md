# F8 — Architecture (abbreviated, one page per Rule D2)

Feature: FEAT-2026-001
Depth: L2 — abbreviated. No alternatives record required at this depth.

```yaml
author: { agent_id: arch-4c19, role: architect, session_id: s-2026-08-26-b, timestamp: 2026-08-26T14:00:00-04:00 }
charter: .lifecycle/agents/architect.md
```

## 1. Structure and dependency direction

```
CMP-01 hmi ──IPC──▶ CMP-02 audio_service ──in-process──▶ CMP-05 persistence
                          │
                          └── applies to zone gain AFTER arbitration
```

Dependencies are acyclic. CMP-05 knows nothing of CMP-02's policy; CMP-01 holds no offset state of its own.

## 2. Failure boundaries and degradation

| Boundary | Failure | Degradation |
|---|---|---|
| CMP-01 → CMP-02 | IPC timeout at 800 ms | HMI reverts the control to the last known value and surfaces a retry affordance |
| CMP-02 → CMP-05 | repository unavailable | STORAGE_UNAVAILABLE returned; applied value unchanged (AC-001-4) |
| CMP-02 → zone gain | apply failure | APPLY_FAILED; stored value authoritative at next reapply (AC-001-11) |

## 3. Concurrency model (§6.6) — mandatory F8 artifact

State under concurrent mutation: `activeZoneOffset[zoneId]`.

| Item | Decision |
|---|---|
| Ownership | CMP-02, sole writer |
| Consistency model | single-writer sequential consistency within CMP-02 |
| Serialization mechanism | per-zone command queue inside CMP-02; writes for one zone are serialized, different zones proceed in parallel |
| Conflict resolution | driver precedence, then arrival order within the queue |
| Deterministic winner | yes — `requesterRole == driver` wins; ties broken by queue arrival sequence, which is total per zone |
| Ordering | per-zone FIFO after the precedence rule is applied |
| Atomicity | store-then-apply; a failed apply does not report Applied |
| Race prevention | no shared mutable offset outside CMP-02; CMP-01 holds a render copy only |
| Reentrancy | queue handler is non-reentrant; a nested setZoneOffset is rejected with APPLY_FAILED |
| Thread safety | single dispatch thread per zone queue; repository calls made off that thread with the result posted back |

A non-deterministic winner would fail G3. This is the finding MSF-2 forced into the design.

## 4. Reuse search (§6.7) — hard G3 check

```yaml
existing_mechanism:
  searched: true
  scope: "settings orchestration, persistence, per-seat scoping, event publication"
  candidates:
    - "seat-scoped settings repository writer (existing)"
    - "per-zone command queue in the source-select path (existing)"
    - "settings change event publisher (existing)"
  selected: ["seat-scoped repository writer", "per-zone command queue", "settings change event publisher"]
  new_mechanisms_introduced: none
  reason: "all three needs are met by existing project mechanisms; a bespoke queue or event channel would duplicate them"
```

## 5. Persistence and schema

One new column on the existing seat-scoped settings table, nullable, defaulting to 0 dB. Migration is additive; rollback leaves the column present but unread by the prior build, which is what AC-001-12 verifies in both directions.

## 6. Design models used (§6.10)

Component diagram and one state machine. No class diagram: no design question here requires one. "No diagram without a design question it answers."
