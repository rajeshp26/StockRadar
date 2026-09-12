# Model-Profile A/B Experiment (P2)

Comparison of model profiles on comparable work, gated by the attribution
metric. Read `framework/models/profiles.sh` for the condition definitions and
the measurement protocol this skeleton operationalizes.

## Conditions

| Condition | Profile | Design |
| --- | --- | --- |
| A | `baseline` | Control: every agent on one strong model |
| B | `tiered` | Implementer/Architect/Reviewer strong; Lead/Planner/Verifier cheap |

`framework/experiments/manifest.json` pins N = 20 runs per condition, the
shared seed (20260911), and the attribution gate thresholds.

## Attribution gate (why it exists)

The experiment's whole output is the telemetry report (tokens per session,
rework rate). A collector whose agent attribution is regressed produces a
report that is wrong per-bucket, so the comparison would be built on noise.
`run_experiment.mjs` therefore runs the synthetic-execution attribution metric
(`.opencode/plugin/attribution_harness.mjs`, see ATTRIBUTION-METRIC.md) as a
preflight and REFUSES to schedule on failure (exit 2). Preflight failure means
"fix the collector first", never "run anyway".

## Usage

    node framework/experiments/run_experiment.mjs --dry-run   # validate + preflight only
    node framework/experiments/run_experiment.mjs             # schedule (not yet implemented)

Exit codes: 0 ok (dry-run or complete), 1 manifest invalid, 2 attribution
preflight failed, 3 scheduling not yet implemented.

## Protocol (from profiles.sh)

1. `source framework/models/profiles.sh baseline` and run ~20 comparable
   tasks; record the telemetry report.
2. `source framework/models/profiles.sh tiered` and run ~20 comparable tasks;
   record the telemetry report.
3. Compare tokens per session AND rework rate together. A token saving with
   higher rework is a loss, not a win.

## Status

Skeleton only: manifest, attribution-gated preflight, and dry-run are
implemented and green. Task scheduling, per-run recording, and the comparison
report are the next increment. The dry-run writes nothing.
