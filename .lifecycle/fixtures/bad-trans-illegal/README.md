# bad-trans-illegal — negative fixture

A copy of the FEAT-2026-001 worked reference (L2 depth) with **one injected
defect**: `state.json` gains a spurious final transition that is not in
`config.yml` `state_machine.legal_transitions`.

## The injected defect

`state.json` ends its `transitions` list with:

```json
{ "from": "QUALIFIED", "to": "COMPLETE", "authorized_by": "gates/G0.md" }
```

`QUALIFIED -> COMPLETE` is **not** a legal transition — the machine reaches
`COMPLETE` only via `RELEASE_PENDING`, and a transition out of `QUALIFIED`
may only go to `UNDERSTANDING` or the DEFECT_LOOP reentry. The record also
carries none of the authorship fields (`timestamp`, `charter`, `agent_id`,
`session_id`, `reason`) every real entry has.

## What must happen

`lifecycle-validate.py` reports a **TRANS-ILLEGAL** error and exits 1.

## Reproduce

```bash
python3 .lifecycle/scripts/lifecycle-validate.py .lifecycle/fixtures/bad-trans-illegal
```

Expected: `FAIL [TRANS-ILLEGAL]` and exit code 1. The pytest suite asserts
the same outcome (`test_lifecycle.py::TestBadFixtures::test_trans_illegal`).