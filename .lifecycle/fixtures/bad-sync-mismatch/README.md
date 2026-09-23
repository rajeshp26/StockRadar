# bad-sync-mismatch — negative fixture

A copy of the FEAT-2026-001 worked reference (L2 depth) paired with a
project-instantiation config that has **drifted from the schema**. The fixture
ships its own `bad_config.yml`; the check fires only when that config is
explicitly passed.

## The injected defect

`bad_config.yml`, `scenario_classes`:

```yaml
scenario_classes: [fakeclass, normal, alternate, ...]
```

`fakeclass` is not a value in the `class` enum of
`.lifecycle/schema/trace.schema.json`, and the config's block header states the
list is the single source of truth that *must* match the schema exactly. The
config declares a scenario class the schema does not know.

## Why `--config` is required

The validator's default config is the project's `.lifecycle/config.yml`, which
is in sync — so a plain run on this directory passes. The drift lives in the
fixture's own instantiation, `bad_config.yml`, and must be passed explicitly:

```bash
python3 .lifecycle/scripts/lifecycle-validate.py .lifecycle/fixtures/bad-sync-mismatch \
    --config .lifecycle/fixtures/bad-sync-mismatch/bad_config.yml
```

Expected: `FAIL [SYNC-MISMATCH]` and exit code 1. The pytest suite exercises
exactly this invocation (`test_lifecycle.py::TestBadFixtures::test_sync_mismatch`).