# F3 — Requirements

Feature: FEAT-2026-001
Depth: L2
Baseline: BL-REQ-001 (created at G0, superseded by BL-REQ-002 — see §change log)

```yaml
author: { agent_id: arch-4c19, role: architect, session_id: s-2026-08-25-a, timestamp: 2026-08-25T10:00:00-04:00 }
charter: .lifecycle/agents/architect.md
note: "Requirements authored under the Architect charter is NOT permitted (§4.3). This feature ran with a dedicated requirements author; see below."
```

Correction: per §4.3 the Architect may not author requirements. The authoring identity is:

```yaml
author: { agent_id: res-9b41, role: researcher, session_id: s-2026-08-24-b, timestamp: 2026-08-25T10:00:00-04:00 }
reviewed_by: { agent_id: rev-7f2a, role: reviewer, session_id: s-2026-08-26-a }
```

## 1. Functional

```
US-001  As a rear-seat occupant
        I want to set a volume offset for my zone
        so that my zone is balanced to my preference without changing other seats.

AC-001-1  Given the vehicle has a rear zone endpoint
          When the rear occupant sets a zone offset to a supported value
          Then the offset shall be applied to that zone only
          And the applied offset shall be reported as active
          And the resulting level change shall be audible on that zone.
```

```
US-002  As the driver
        I want to reset a rear zone offset
        so that I can return the vehicle to a known state.

AC-002-1  Given a non-zero rear offset is stored
          When the driver resets that zone
          Then the offset shall return to 0 dB
          And the change shall be audible on that zone.
```

## 2. Negative

```
AC-001-4  Given the settings repository is unavailable
          When a zone offset write is requested
          Then the system shall retain the current applied offset
          And shall report the write as failed
          And shall not present the requested value as active.
```

```
AC-001-5  Given the vehicle variant has no rear zone endpoint
          When a zone offset write is requested through the service interface
          Then the system shall reject the request with ZONE_NOT_PRESENT
          And shall not alter any other zone.
```

## 3. Boundary

```
AC-001-7  Given a requested offset at the maximum or minimum supported value
          When the offset is applied
          Then the zone level shall change by exactly that offset
          And the level of any alert or chime stream shall remain unchanged.
```

```
AC-001-8  Given a requested offset outside the supported range
          When the write is requested
          Then the system shall reject it with OFFSET_OUT_OF_RANGE
          And shall retain the current value.
```

## 4. Concurrency and persistence

```
AC-001-9  Given the rear occupant and the driver write the same zone within the arbitration window
          When both writes are received
          Then exactly one value shall become active
          And the winner shall be determined by the documented rule — driver precedence
          And the losing writer shall be informed the value was superseded.
```

```
AC-001-11 Given a stored offset and a power cycle
          When the vehicle returns to accessory or run
          Then the stored offset shall be reapplied before the first audio output on that zone.
```

```
AC-001-12 Given a build upgrade from a schema without the offset column
          When the settings repository is opened
          Then existing settings shall be preserved
          And the offset shall default to 0 dB
          And a rollback to the prior build shall leave the prior settings readable.
```

## 5. Non-functional (measurable threshold + method)

| id | Statement | Threshold | Method |
|---|---|---|---|
| NFR-1 | Offset applied promptly after user action | ≤ 200 ms from HMI commit to audible level change | timestamped log pair at HMI commit and zone-gain apply, p95 over 100 trials, bench_hu |
| NFR-2 | Repository write does not stall the settings UI | ≤ 50 ms p95 for the write call | service-side timer around the repository call, 200 trials |
| NFR-3 | Offset reapply does not delay audio start | ≤ 120 ms added to first-output on that zone | first-output timestamp with and without a stored offset, 50 cycles |
| NFR-4 | Failed writes are diagnosable | every rejected write logs the reason code and the requested value | log inspection on each negative case |

## 6. Change log against baseline (§8.6)

| Baseline | Element | Before | After | Reason | Gates reopened |
|---|---|---|---|---|---|
| BL-REQ-001 → BL-REQ-002 | AC-001-9 | "the last write shall win" | "the winner shall be determined by the documented rule — driver precedence" | G0.5 finding MSF-2: "last write wins" is not deterministic across the IPC boundary | G0, G0.5 |

BL-REQ-001 is `superseded`. All gate entries below certify against BL-REQ-002.

## 7. Exit

Four categories present. Every AC independently verifiable, none describing implementation, every AC traced to a UC, every SCN mapped to an AC or deferred with reason (SCN-9 → AC-001-5, SCN-14 → AC-002-1, SCN-15 → AC-001-7 misuse leg).
