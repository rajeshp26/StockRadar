# Phase 0b - Dry Run Scenario

## Purpose

Run one trivial task through the complete StockerPro lifecycle and verify that
every subsystem records data correctly.

## Scenario

Task: Add a comment to a Python function explaining its purpose.

This is deliberately trivial. The goal is not to test engineering judgment.
The goal is to test that the machinery runs end-to-end.

## Expected lifecycle

Team Lead receives request -> Classifies L0, local scope -> Routes to Implementer
-> Implementer adds comment -> Verifier runs G4 -> Verifier records gate result
-> Telemetry record written

## What to verify

After the task completes:

1. records.jsonl has a new entry with task_id, agents, gates, duration_s
2. Gate results recorded in telemetry (g4 result pass or fail)
3. No retro trigger (clean execution)
4. No blockers opened
5. Skills loaded reflects what was actually used

## Commands

```bash
# After completion, verify telemetry
python3 framework/telemetry/report.py --verbose

# Check the latest record
tail -1 .planning/telemetry/records.jsonl | python3 -m json.tool

# Verify no retro triggers
ls .planning/retro/triggers/ 2>/dev/null || echo "no triggers (expected)"

# Verify no blockers
python3 framework/adapters/gsd_state.py list-blockers
`

## Pass criteria

- records.jsonl entry exists with all expected fields
- gate results recorded in telemetry
- no retro triggers (clean execution)
- no blockers (clean execution)
- report.py renders without errors

## Fail criteria

- records.jsonl missing or incomplete
- gates not recorded
- unexpected retro triggers or blockers
- framework errors during execution
