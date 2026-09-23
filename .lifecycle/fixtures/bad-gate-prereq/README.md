# bad-gate-prereq — negative fixture

A copy of the FEAT-2026-001 worked reference (L2 depth) with **one injected
defect**: the fork-point transition into `REQUIREMENTS_BASELINED` claims its
gates passed but records **no gate authorization**.

## The injected defect

`state.json`, transition 8 (`REQUIREMENTS_CHALLENGED -> REQUIREMENTS_BASELINED`):

```json
{ "from": "REQUIREMENTS_CHALLENGED", "to": "REQUIREMENTS_BASELINED",
  "authorized_by": "-",
  "reason": "G0 PASS + G0.5 PASS — fork point" }
```

The reason asserts `G0 PASS + G0.5 PASS` but `authorized_by` is `"-"` — no
ledger entries are recorded. `config.yml` declares
`REQUIREMENTS_BASELINED: [G0, "G0.5"]` as gate prerequisites, so the recorded
authorization set (`{}`) does not contain what the config requires
(`{G0, G0.5}`). The claim and the record disagree.

## What must happen

`lifecycle-validate.py` reports a **GATE-PREREQ** error and exits 1.

## Reproduce

```bash
python3 .lifecycle/scripts/lifecycle-validate.py .lifecycle/fixtures/bad-gate-prereq
```

Expected: `FAIL [GATE-PREREQ]` and exit code 1. The pytest suite asserts the
same outcome (`test_lifecycle.py::TestBadFixtures::test_gate_prereq`).