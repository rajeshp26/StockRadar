# FEAT-2026-001 — worked reference feature

Per-seat volume offset for the rear-seat audio zone. **L2 depth.** Copy this
directory as the starting shape for a new feature rather than reading the
1,492-line spec cold.

## Why L2 and not L3

`F0-qualification.md` runs the four `depth_floors` from `config.yml` explicitly
and none trigger: focus and ducking policy are untouched, the alert path is
excluded by requirement, the `seat` control scope is reused rather than changed,
and there is no per-user persistence or account sync. Ten impact flags are
answered; four are true but none raises the floor above L2.

At L2 the pack requires F0–F10 plus F12–F15, with F8 and F9 abbreviated to one
page each (Rule D2), and gates G0, G0.5, G1, G2, G3, G4, G7. G0.5 is present
because F5 is performed (Rule D1). G3 is present because L2 now produces F8.
Not exercised here: F11, F16, G3.5, G5, G6, G8.

## What each artifact demonstrates

| File | The mechanism it shows working |
|---|---|
| `F0-qualification.md` | depth floors checked before classification, not after |
| `F1-context.md` | every claim tagged `[verified]`, `[inferred]` or `[assumption]`; two assumptions resolved before G0 |
| `F2-scenarios.md` | 15 scenarios risk-scored; selection by equivalence, boundary, pairwise, state-transition and one domain-mandatory combination — not Cartesian expansion |
| `F3-requirements.md` | four categories; a superseded baseline with its change log |
| `F4-requirements-challenge.md` | six blocking findings; the Verifier *overrides the author's own risk scores* |
| `F5-test-analysis.md` | five test conditions no AC mentions (TC-17…TC-21); three MSF raised, one of which superseded a baseline |
| `F6-decomposition.md` | cohesion argued rather than operations counted; ownership register with one owner |
| `F7-contracts/` | per-semantic `applicable` decisions; `validateOffset` declares timeout inapplicable because it is in-process |
| `F8-architecture.md` | full nine-item concurrency model with a deterministic winner; reuse search finding three existing mechanisms and introducing none |
| `F9-detailed-design.md` | state machine with all five error transitions; no class diagram, because no design question needed one |
| `F10-impact-analysis.md` | the reverse pass finds the ducking dependency on zone gain that a forward-only pass misses |
| `trace.yml` | zero orphans across all ten §8.4 classes |
| `state.json` | a real reverse transition — MSF-2 moved the feature back to `REQUIREMENTS_DRAFTED` |
| `gates/` | seven ledger entries, each with identity-based independence and checksummed evidence |
| `defects/DEF-001.md` | `process_originated: false` — the case v1.0 would have forced a pointless checklist change for |

## The two things worth reading first

**`F5-test-analysis.md` §2 and §3.** TC-17 through TC-21 are not derivable from
any acceptance criterion. That is the detectable signature that the Verifier did
not transcribe. MSF-2 then found that "last write wins" is not deterministic
across an IPC boundary, which amended AC-001-9, superseded BL-REQ-001 and
reopened G0. Test analysis changed the requirements — which is the point of
running it at F5 rather than after code exists.

**`defects/DEF-001.md`.** A concurrency defect where the requirement,
architecture, concurrency model and detailed design were all correct. It is
classified `process_originated: false`, so it takes a symptom correction and a
rewritten unit test, and *no* checklist change. Under v1.0's unconditional rule
this defect would have inflated a checklist for no preventive value.

## Verify it yourself

```bash
python3 .lifecycle/scripts/orphan-check.py features/FEAT-2026-001/trace.yml
python3 .lifecycle/scripts/lifecycle-validate.py features/FEAT-2026-001
```

Expected: 0 orphans across ten classes, and D1/D2/D3, identity independence,
baseline currency, transition legality, gate prerequisites, config/schema sync,
kind attribution, F17 rate and CONDITIONAL rules all passing.

## What is deliberately fictional

Commit SHAs, agent ids, component numbers outside CMP-01/02/05, source paths,
build commands and measured values are illustrative. The *shapes* are real: the
evidence blocks carry every field §9.1.2 requires, and the checksums in the
gate ledger match the actual bundled result files.
