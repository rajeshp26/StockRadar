# F0 — Feature Qualification

```
Charter: team-lead
Agent-Id: <stable per configured agent instance>
Role: team-lead
Session-Id: <unique per execution context>
Feature: <FEATURE-ID>
Phase: F0
Baseline: pre-baseline
Timestamp: <ISO 8601 with offset>
```

Schema: `.lifecycle/schema/qualification.schema.json`
Spec: §3. First activity for every task without exception.

## 1. Feature type (§3.1) — exactly one

- [ ] new_feature  - [ ] enhancement  - [ ] bug_fix  - [ ] refactoring
- [ ] performance  - [ ] security     - [ ] safety_related
- [ ] regulatory   - [ ] configuration

## 2. Complexity (§3.2)

| Level | Meaning | Selected |
|---|---|---|
| L0 | Local, behaviour-preserving or trivially scoped | |
| L1 | Single component, no contract change | |
| L2 | Multiple components inside one domain, or one contract change | |
| L3 | Cross-domain: HMI + service + platform + persistence, or backend + vehicle | |
| L4 | L3 plus safety relevance, regulatory obligation, security-sensitive data, or irreversible data migration | |

## 3. Impact flags (§3.3) — every one answered explicitly

| Flag | Value | Effect when true |
|---|---|---|
| `contract_change` | | G1 mandatory |
| `public_api_change` | | G1 mandatory, versioning section in F7 |
| `data_change` | | G2 mandatory |
| `persistent_data_change` | | migration + rollback scenarios in F2 |
| `security_sensitive` | | floor L3, security scenarios and NFRs |
| `safety_relevant` | | floor L4 |
| `customer_visible` | | F1/F2/F3 mandatory regardless of complexity |
| `backend_change` | | F14 mandatory |
| `regulatory` | | floor L4, traceability to the obligation |
| `concurrency_change` | | concurrency scenarios in F2 |

No flag may be left blank. An unanswered flag fails F0 exit.

## 4. Project depth floors — pre-check before finalizing

From `config.yml` `depth_floors`. These tighten §3.3; they never loosen it.

| Trigger | Floor | Applies? |
|---|---|---|
| Audio focus or ducking behaviour changes | L3 | |
| Alert, chime or warning audibility affected | L4 | |
| Control scope of an existing setting changes | L3 | |
| Per-user persistence or backend account sync affected | L3 | |

A focus or ducking change cannot be classified below L3 without an explicit, recorded override.

## 5. Resulting depth

```
Complexity from §3.2:        L_
Highest floor from flags:    L_
Highest floor from §4:       L_
DECLARED DEPTH:              L_        # the maximum of the three
```

Ambiguity about depth resolves **upward** (§3.5).

Rationale: <why this depth, in one or two sentences>

## 6. Phase and gate sets — two separate lists (§3.4)

Copy from `config.yml` `depths.<L>`. Do not merge them.

```yaml
phases: [ ... ]
gates:  [ ... ]
```

Rule checks:

- [ ] **D1** — if `F5` is in phases, `G0.5` is in gates. No exception at L1.
- [ ] **D2** — if depth is L2, `F8` and `F9` are in phases abbreviated to one page each, and `G3` is in gates.
- [ ] **D3** — every gate in the list is produced by a phase in the list.
- [ ] UI surface? <yes/no> — drives whether G5 and G6 apply.

## 7. Initial risk profile

Named risks that will drive F2 scenario scoring (§5.2.2). Scores are set in F2 and reviewed at F4.

| Risk | Why it matters | Expected band |
|---|---|---|
| | | |

## 8. Audio Settings instantiation

- [ ] Control scopes touched: vehicle / seat / shared_vehicle
- [ ] Layers crossed, from `config.yml` `layers`: hmi / audio_service / audio_hal / vacs / audio_hub / persistence / backend_sync
- [ ] Process boundaries crossed — each one needs a contract with a real timeout
- [ ] User roles affected: driver / co_pilot / normal / kids / guest
- [ ] Audible outcome changes? If yes, audible-outcome verification is required distinct from state readback
- [ ] Alert, chime or warning audibility touched? If yes, L4 floor and §11 controls apply

## 9. F0 exit criteria (§3.5)

- [ ] Type recorded
- [ ] Complexity recorded
- [ ] Every impact flag answered
- [ ] Depth floors evaluated
- [ ] Resulting depth recorded with rationale
- [ ] Phase and gate sets written as two separate lists
- [ ] D1, D2, D3 checked
