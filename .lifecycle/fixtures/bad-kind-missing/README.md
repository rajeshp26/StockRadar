# bad-kind-missing — negative fixture

A copy of the FEAT-2026-001 worked reference (L2 depth) with **one injected
defect**: a test case in `trace.yml` is missing its `kind` attribution.

## The injected defect

`trace.yml`, `UT-1`:

```yaml
UT-1: { covers: [AC-001-1], type: positive, surface: host_unit, result: pass }
```

Every other `UT-*`/`IT-*`/`ST-*` case carries `kind: verified_by`; `UT-1` is the
only case that omits it. Without a `kind`, the case has no stated relationship
to the evidence that is supposed to verify it.

## What must happen

`lifecycle-validate.py` reports a **KIND** error (missing kind attribution) and
exits 1.

## Reproduce

```bash
python3 .lifecycle/scripts/lifecycle-validate.py .lifecycle/fixtures/bad-kind-missing
```

Expected: `FAIL [KIND]` and exit code 1. The pytest suite asserts the same
outcome (`test_lifecycle.py::TestBadFixtures::test_kind_missing`).