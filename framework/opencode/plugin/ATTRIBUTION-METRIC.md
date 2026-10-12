# Attribution Metric (P2)

Synthetic-execution metric that PROVES the telemetry collector attributes every
measured unit to the correct agent. This is the executable answer to critic
finding 10 (attribution accuracy) and finding 12 (no synthetic-execution
harness) from `framework/models/attribution_review.md`.

## Purpose

The collector accumulates counters per executing agent (`rec.agents`). A
regression in agent attribution is silent unless something asserts the correct
buckets. This metric re-executes the collector over a deterministic corpus and
compares its captured unit stream against an independent simulator that
computes the expected stream from first principles.

## Unit vocabulary

Every counted item is a unit. A snapshot is the JSON the collector would have
persisted (`agents` map + `taxonomy_events`); the harness captures one per
flush op and one at session end. Units accumulate as deltas between consecutive
snapshots.

| Unit key | Meaning | Value |
| --- | --- | --- |
| `inv|<agent>` | tool invocations attributed to an agent | count |
| `call|<agent>` | task() delegations attributed to an agent | count |
| `tok|<agent>|<counter>` | token measurements (`input`, `output`, `reasoning`, `cache_read`, `cache_write`) | per token |
| `evt|<event>|<execution_agent>|<confidence>` | taxonomy event occurrences | count |

Agent names use the collector's resolved strings, e.g. `team-lead`,
`sisyphus-junior (deep)`, `sisyphus-junior (oracle)`, `explore`.

## Formula

Merge per-snapshot-pair delta maps into two totals, expected E (simulator) and
observed O (collector):

    accuracy = SUM_k min(E_k, O_k) / SUM_k max(E_k, O_k)

- A unit the collector got exactly right contributes 1/1.
- A unit attributed to the wrong agent removes it from the correct key and
  adds it to the wrong key, so it is counted twice against the total.
- Unattributable noise (model detail, timestamps, envelope) is excluded so it
  can never move the metric.

PASS requires `accuracy >= 0.99` AND `SUM max(E_k, O_k) >= 1000` sampled units.

## Exclusions

`ms` durations, `models[]` arrays, the payload envelope (`kind`, `ts`,
`session_id`, `task_id`, `attempt_id`), and global counters that are not
per-agent (session length, toolbox state).

## How it is exercised

`attribution_harness.mjs` is the standalone runner; `attribution.test.mjs` is
the npm-test gate. The harness:

1. Builds a deterministic corpus: 9 hand-written scripted sessions
   (`ses_a1..ses_a9`) covering delegation, nesting, background-task snapshot
   timing, polled tasks, verb-shape edge cases, gate outcomes, retries,
   reopens, agent-resolution edge cases, and a 3-level nest; plus 30 seeded
   random sessions (mulberry32, seed 20260911, 10-22 ops each).
2. For each session, drives the real `TelemetryPlugin` through the full hook
   sequence with a stubbed `$` that captures every `write-telemetry` payload
   (matching `telemetry.test.mjs`), and runs the independent simulator over the
   same op stream.
3. Compares both snapshots at every flush op and at session end via the
   formula above.

The simulator is deliberately not shared code: it has its own stack, agent,
background-task, and attempt state, and reuses only the pure tested vocabulary.
Both sides parse the same op stream, so any divergence in attribution is a real
collector defect, not a shared bug.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | PASS: accuracy >= 0.99 and units >= 1000 and no harness anomaly |
| 1 | FAIL: metric below threshold/sample floor, or mismatched units |
| 2 | HARNESS ERROR: session anomaly (e.g. missing payloads) |
| 3 | NOTHING RAN: suite produced no sessions |

## Determinism

Seed 20260911 is fixed. Two runs with the same seed produce identical
accuracy, unit totals, flush count, anomalies, and mismatched units
(asserted by `attribution.test.mjs`).

## Run

    node framework/opencode/plugin/attribution_harness.mjs            # standalone, exit code
    node framework/opencode/plugin/attribution_harness.mjs --json     # machine-readable result
    npm test                                                  # full suite incl. this gate

## Known limitation

Token units are scored per token, so a single small mis-attributed message
(e.g. 150 tokens in a 100k-unit run) may not breach the 0.99 floor on its own.
Any mis-attribution nonetheless moves accuracy away from 1.000000 and is
reported verbatim in `mismatchKeys` and the `--json` output, and the scripted
scenarios pin exact values for the adversarial cases.
