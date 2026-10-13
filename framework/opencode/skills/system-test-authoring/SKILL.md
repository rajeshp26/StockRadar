---
name: system-test-authoring
description: Write and run black-box system, integration and end-to-end tests from the requirements alone, against the real running stack and real data, with break-it cases. Use whenever a plan has a criterion tagged integration, e2e, browser or data-invariant, whenever a feature or fix must be proven working, and before anyone claims something works. Covers profiling real data into a manifest, the generated scenario matrix, the tag grammar, independent expected values, red-first and green runs through the harness, and how to report a failing test. Do not read application source while using it.
---

# System-test authoring (black-box, real stack)

You are the tester. You know the requirements and the real data. You do **not** know the
implementation, and you must not look: open no file under `backend/` or `src/`. A test written
from the code proves the code agrees with itself. A test written from the requirement can disagree.

Three rules the tooling enforces: tests come from the **requirements**, run against the **real
running stack** with **real data**, and try to **break** it. Work one criterion at a time; the
scripts do the bookkeeping, you supply judgement.

## Procedure (each step has a command; do not skip)

1. **Read the plan's criteria** (`AC-n [e2e|integration|browser|data-invariant] ...`). Restate what a
   user would observe. If a criterion cannot be observed from outside, send the plan back.
2. **Profile the real data** and write `tests/system/data/MANIFEST.json`. List every distinct shape
   that exists (single holding, mixed kinds, duplicates, nulls, old rows, oversized). Save the
   extract as a file next to the manifest; record its sha256. Shapes you did not list will not be
   tested; look for the odd ones.
3. **Generate the matrix:** `python3 framework/testing/scenario_matrix.py --plan <plan>`. It lists
   every criterion x data shape x break-it scenario. Do not delete rows.
4. **Write tests** in `tests/system/` for the rows (templates below). One behaviour per test.
5. **Resolve every matrix row** as `test:<name>` or `NA: <real reason, four words or more>`.
6. **Lint:** `python3 framework/testing/system_test_lint.py --plan <plan> --matrix <matrix>`. Fix
   every ERROR. Do not edit the lint or the policy.
7. **Freeze and run red** (before implementation):
   `python3 framework/testing/run_system_tests.py freeze --plan <plan>`, then
   `... run --plan <plan> --phase red`. Red must show at least one failing test; that proves the
   suite can fail. (Pure regression work over unchanged behaviour: the plan declares
   `system_tests_red_exempt: <reason>`.)
8. Hand back. The implementer fixes the code; the frozen tests cannot be edited.
9. **Run green:** `... run --plan <plan> --phase green`, then `./framework/gates/g17_system_tests.sh`.

## Tags (first docstring line, or the test title in JS/TS)

`AC-2 kind:negative data:acct-snapshot-2026-10 shape:mixed_lot`

kinds: `positive`, `negative`, `boundary`, `abuse`, `idempotency`, `concurrency`, `regression`.
Every real-stack criterion needs at least one `positive` and one break-it test.

## Template (Python, stdlib only; any HTTP client is fine)

```python
import json, os, pathlib, urllib.request
BASE = os.environ["SYSTEM_TEST_BASE_URL"]
DATA = json.load(open(pathlib.Path(__file__).parent / "data" / "snapshot.json"))

def test_total_equals_independent_sum_per_account():
    """AC-2 kind:positive data:acct-snapshot shape:mixed_lot"""
    for acct in DATA["accounts"]:
        shown = json.load(urllib.request.urlopen(BASE + "/portfolio/" + acct["id"]))["total"]
        expected = sum(l["qty"] * l["price"] for l in acct["lots"])   # from the raw data, not the system
        assert abs(shown - expected) < 0.01, acct["id"]
```

Playwright (TypeScript): `test('AC-4 kind:positive the page shows a stale indicator', async ({ page }) => {...})`
with `expect(...)` on what the user sees. No `page.route` fulfilling responses: that is a mock.

## Expected values come from outside the system

Compute them from the raw data or the requirement's own numbers (a spreadsheet-style recomputation,
an independent SQL aggregate, the arithmetic in the criterion). Never call the system's own
function to produce the expected value, and never copy a value from its current output.

## Break it (the matrix rows tell you where)

For each criterion try: empty or missing input, smallest and largest values and just outside the
limit, the same thing twice, old or stale data, a user who must be refused, records the change must
**not** touch (assert they are identical afterwards), and anything the conditional rows add
(rounding, time boundaries, repeat or concurrent runs, odd text). Assert the observable result, not
just a status code.

## When a test fails

It is a defect report, not a test problem. Do **not** edit the frozen test to make it pass. Record
a blocker with: the test name, the criterion, the input, expected versus observed. Only a human
changes the requirement.

## Forbidden (the lint refuses these)

Mocks, stubs, patches, interception (`page.route`, `nock`, `monkeypatch`); skip, xfail, `.only`;
importing application modules; asserting nothing or `assert True`; tests with no `AC-n` or `kind:`
tag; data tags that are not in the manifest; unresolved matrix rows.

## Limits

The lint and harness check structure, real-stack execution, data integrity and freshness. They
cannot tell whether an assertion is the right one; the reviewer reads the expected values. If the
stack is down the harness reports UNVERIFIABLE (exit 2/3): fix the environment, never skip.

## Tips for small models

Do one criterion fully before the next. Copy the template, change names and values. Run the lint after
every file. Keep tests short and literal. If a row is unclear, mark it and ask rather than guess.
