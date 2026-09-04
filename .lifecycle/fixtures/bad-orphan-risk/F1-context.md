# F1 — Feature Understanding

Feature: FEAT-2026-001
Depth: L2

```yaml
author: { agent_id: res-9b41, role: researcher, session_id: s-2026-08-24-b, timestamp: 2026-08-24T11:40:00-04:00 }
charter: .lifecycle/agents/researcher.md
```

Every claim below is tagged `[verified: source]`, `[inferred]` or `[assumption: how to verify]` per §4.2.

## 1. Customers

| id | Customer | Relationship to the feature |
|---|---|---|
| CUS-1 | Rear-seat occupant | sets and experiences the offset for their own zone |
| CUS-2 | Driver | may inspect and reset rear offsets; retains override authority |
| CUS-3 | Service technician | resets seat-scoped values during diagnostics |

## 2. Environment dimensions (§5.1 baseline + audio set)

Baseline swept: vehicle state, ignition/power state, connectivity, network availability, region, user/account state, device state, active source, vehicle configuration/variant, software version, hardware variant, language, privacy settings, permissions, driving context, online/offline, time.

Audio-specific: focus owner, ducking active, mute state, zone set, concurrent streams, endpoint set, amp/DSP variant, seat occupancy.

Values that matter here:

* Zone set — `[verified: config.yml layers]` rear zone exists only on variants with the rear-zone endpoint. Two-zone and three-zone variants both ship.
* Seat occupancy — `[assumption: confirm with platform team]` occupancy is not an input to settings authority today; offset is settable regardless of occupancy. Verification route: read the seat-control authority code path before G0.
* Amp/DSP variant — `[verified]` three amp variants; offset applies in the service layer, above the variant boundary, so variant count does not multiply the design.
* Ignition/power state — `[inferred]` offset must survive accessory-off and full power cycle, since the value is per-seat persistent.

No dimension left unknown.

## 3. Operating conditions (§5.1)

`normal`, `degraded` (repository slow), `unavailable` (repository unreachable), `failure` (write rejected), `recovery` (repository returns after outage), `interrupted` (power loss mid-write), `concurrent` (rear occupant and driver writing together), `repeated` (rapid slider changes), `boundary` (offset at ±limit), `misuse` (offset set to defeat an alert), `unexpected_sequence` (offset written before zone enumeration completes).

## 4. Constraints

| Constraint | Owner | Verification route |
|---|---|---|
| Offset must not alter alert or chime level | Audio Service | AC-001-7, ST-4 on a real audio path |
| Offset applies after arbitration, not before | Audio Service | F8 dependency direction; G3 |
| Repository write budget 50 ms p95 | Persistence | NFR-2, measured at G7 |
| No new IPC interface; extend IFC-1 | Architect | G1 |

## 5. Dependencies

Settings repository (existing), GM Audio Service settings orchestration (existing), HMI Audio Settings screen (existing). No VACS change — `[verified: reverse impact in F10]` offset is applied to the zone gain the service already owns.

## 6. Assumptions

| Assumption | Route to resolution | Status |
|---|---|---|
| Seat occupancy is not an authority input | read authority path | resolved before G0; confirmed not an input |
| Rear zone endpoint present on all target variants | variant matrix review | resolved; two variants lack it → SCN-9 unsupported-config |

## 7. Exit (§5.1)

No environment dimension unknown; every assumption resolved before G0.
