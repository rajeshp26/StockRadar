# F10 — Impact Analysis

```
Charter: architect
Agent-Id: <...>
Role: architect
Session-Id: <...>
Feature: <FEATURE-ID>
Depth: <L0..L4>
Phase: F10
Baseline: <BL-id>
Timestamp: <ISO 8601 with offset>
```

Spec: §6.11. Hard gate before implementation. Two directions, both mandatory. **A forward-only analysis fails G2.**

## Part 1 — Forward impact: what does this change touch?

Every row answered, or marked not applicable with a reason.

| Category | Impact | Detail |
|---|---|---|
| requirements | | |
| architecture | | |
| components | | |
| classes | | |
| interfaces | | |
| public APIs | | |
| events | | |
| database and schema | | |
| configuration | | |
| HMI | | |
| apps | | |
| backend | | |
| vehicle services | | |
| platform | | |
| HAL | | |
| build | | |
| deployment and rollout | | |
| security posture | | |
| logging | | |
| telemetry | | |
| diagnostics | | |
| documentation | | |

## Part 2 — Reverse impact: what depends on what I am changing?

**Mandatory. An empty section fails G2.** This is where regression defects hide.

For every symbol, contract, event, table, column, config key and file being modified:

| Changed thing | Existing consumers | Features relying on current behaviour | Existing tests / regression suites | Documented behaviour |
|---|---|---|---|---|

## Part 3 — Impacted-path list → verification path

Handed to the Verifier, who converts it into regression selection at F5.

```yaml
impacted_paths:
  - changed: <IFC-/EVT-/table/config key/symbol>
    dependents: [CMP-…]
    regression: [ST-…, IT-…]
```

- [ ] Every impacted path has at least one selected regression test (zero `orphan impact`)
- [ ] The list was handed to the Verifier and appears in `F5-test-analysis.md`

## Part 4 — Schema, config and migration

- [ ] Schema changes with forward and backward compatibility stated
- [ ] Config key changes with behaviour on absent keys
- [ ] Where `persistent_data_change` is true: migration **and** rollback scenarios exist in F2
- [ ] At L4: migration has a tested rollback

## Part 5 — Audio Settings instantiation

- [ ] Every changed setting key checked for existing readers across hmi, audio_service, audio_hal, vacs, audio_hub, persistence, backend_sync
- [ ] Control-scope changes traced to every existing per-seat and per-vehicle expectation they alter
- [ ] Focus and ducking changes traced to every other feature that acquires focus or is duckable
- [ ] Alert, chime and warning audibility paths checked
- [ ] Backend schema changes checked against older vehicle software still writing the previous shape
- [ ] Persisted per-user values checked for **downgrade**, not only upgrade
- [ ] Regression selection includes a case on a real audio path where the audio path is touched

## Exit criteria

- [ ] Both sections non-empty
- [ ] Every forward category answered or marked N/A with a reason
- [ ] Every changed thing has a reverse-impact row
- [ ] Impacted-path list handed over and reflected in F5
