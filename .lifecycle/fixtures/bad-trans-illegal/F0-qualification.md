# F0 — Feature Qualification

Feature: FEAT-2026-001
Title: Per-seat volume offset for the rear-seat audio zone
Spec version: 1.1

## Charter header

```yaml
author: { agent_id: tl-1a03, role: team-lead, session_id: s-2026-08-24-a, timestamp: 2026-08-24T09:10:00-04:00 }
charter: .lifecycle/agents/team-lead.md
```

## 1. Feature type (§3.1)

`enhancement` — extends an existing Audio Settings control with a seat-scoped offset.

## 2. Depth floor pre-check (config.yml `depth_floors`)

| Floor rule | Triggered | Note |
|---|---|---|
| audio focus or ducking behaviour changed → L3 | no | offset applies post-arbitration; focus policy untouched |
| alert or chime audibility affected → L4 | no | offset excluded from the alert/chime path; verified by AC-001-7 |
| control scope of an existing setting changed → L3 | no | new setting, existing `seat` scope reused |
| per-user persistence or account sync added → L3 | no | per-seat only; no account binding, no backend sync |

No floor triggered. Classification proceeds on complexity and flags.

## 3. Complexity (§3.2)

**L2** — multiple components inside one domain: HMI, GM Audio Service, settings repository. One new contract operation on an existing interface. No HAL, VACS or backend change.

## 4. Impact flags (§3.3)

| Flag | Value | Consequence |
|---|---|---|
| `contract_change` | true | G1 mandatory |
| `public_api_change` | false | internal IPC surface only |
| `data_change` | true | G2 mandatory |
| `persistent_data_change` | true | migration + rollback scenarios mandatory in F2 |
| `security_sensitive` | false | — |
| `safety_relevant` | false | alert path excluded; verified at G7 |
| `customer_visible` | true | F1/F2/F3 mandatory |
| `backend_change` | false | F14 still performed; L2 includes it |
| `regulatory` | false | — |
| `concurrency_change` | true | concurrency scenarios mandatory in F2 |

## 5. Resulting depth

**L2.** No flag raises the floor. §3.5 upward-resolution not needed; no ambiguity.

## 6. Phase and gate set (§3.4, config.yml `depths.L2`)

Phases: F0, F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F12, F13, F14, F15.
F8/F9 abbreviated to one page each (Rule D2); no alternatives record.

Gates: G0, G0.5, G1, G2, G3, G4, G7.

Rule D1: F5 is performed, so **G0.5 is mandatory**. Rule D2/D3: G3 required because L2 produces F8.

Not applicable here: F11, F16, F17 (unless a defect arises); G3.5, G5, G6, G8. G5/G6 would apply if the HMI surface changed beyond adding one control.

## 7. Exit (§3.5)

Type, complexity, all ten flags, depth, phase/gate set recorded; floors checked explicitly. F0 complete.
