# bad-orphan-risk — negative fixture

A copy of the FEAT-2026-001 worked reference (L2 depth) with **one injected
defect**: a scenario in `trace.yml` carries `priority: MISSING` instead of a
scored risk, leaving it unscored and orphaned from the risk model.

## The injected defect

`trace.yml`, `SCN-1`:

```yaml
SCN-1: { title: "offset applied and audible", class: normal,
         technique: equivalence, priority: MISSING, cases: [UT-1, ST-1] }
```

The other 14 scenarios each carry a scored `priority` block
(`likelihood`, `impact`, `detectability`, `priority`, `band`). `SCN-1` is the
only scenario whose risk was never scored.

## What must happen

`orphan-check.py` reports orphan risk count **greater than zero** and exits 1.

## Reproduce

```bash
python3 .lifecycle/scripts/orphan-check.py .lifecycle/fixtures/bad-orphan-risk/trace.yml
```

Expected: `orphan risk` reported with a non-zero count and exit code 1. The
pytest suite asserts the same outcome
(`test_lifecycle.py::TestBadFixtures::test_orphan_risk`).