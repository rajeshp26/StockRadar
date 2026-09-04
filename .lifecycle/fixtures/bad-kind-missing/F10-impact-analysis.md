# F10 — Impact Analysis

Feature: FEAT-2026-001

```yaml
author: { agent_id: arch-4c19, role: architect, session_id: s-2026-08-26-b, timestamp: 2026-08-27T10:05:00-04:00 }
charter: .lifecycle/agents/architect.md
```

Both directions are mandatory. A forward-only analysis fails G2.

## 1. Forward impact — what this change touches

| Area | Touched | Detail |
|---|---|---|
| Requirements | yes | US-001, US-002 and their AC set |
| Architecture | yes | CMP-02 gains the offset ownership and one queue |
| Interfaces | yes | IFC-1 v1.0.0 → v1.1.0, one operation added |
| Events | yes | EVT-1 new |
| Database / schema | yes | one nullable column, additive migration |
| Configuration | yes | offset range limits added to the audio settings config |
| HMI | yes | one control on an existing screen |
| Platform / HAL / VACS | no | offset applies above the HAL boundary |
| Backend | no | no account binding |
| Build | no | no new module |
| Logging / diagnostics | yes | reason-code logging for rejected writes (NFR-4) |
| Documentation | yes | settings reference, service interface doc |

## 2. Reverse impact — what depends on what I am changing

| Changed element | Existing consumers | Existing features relying on current behaviour | Existing tests | Documented behaviour |
|---|---|---|---|---|
| IFC-1 (interface version) | CMP-01, CMP-09 diagnostics reader | CMP-09 reads zone state during service diagnostics | ST-101, ST-102 | service interface doc §4 |
| seat settings table | settings backup/restore path | factory reset, seat settings restore | ST-110, ST-111 | settings persistence doc |
| zone gain apply path | source-select and ducking paths | ducking depth is computed from zone gain — an offset changes the input to that computation | ST-120, ST-121, ST-122 | audio policy doc §7 |
| settings change event publisher | analytics consumer | settings telemetry counts events per key | ST-130 | telemetry schema |

The third row is the one that matters. The offset changes an input to the existing ducking computation, so ducking regression is selected even though ducking policy itself is untouched. A forward-only pass would have missed it.

## 3. Impacted-path list handed to F5 (§6.11)

| id | Changed | Dependents | Regression selected |
|---|---|---|---|
| IMP-P1 | IFC-1 | CMP-09 | ST-101, ST-102 |
| IMP-P2 | seat settings table | backup/restore, factory reset | ST-110, ST-111 |
| IMP-P3 | zone gain apply path | ducking, source select | ST-120, ST-121, ST-122 |
| IMP-P4 | settings change event publisher | analytics | ST-130 |

Every impacted path has at least one selected regression test. An impacted path with none is an orphan impact per §8.4.
