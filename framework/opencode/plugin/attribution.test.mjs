// framework/opencode/plugin/attribution.test.mjs
// P2 regression gate for the synthetic-execution attribution metric.
//
// Runs the REAL collector (telemetry.ts) over a deterministic corpus against an
// independent simulator and asserts the metric: accuracy >= 0.99 over >= 1000
// units, zero anomalies, zero mismatched units, and determinism across two runs
// with the same seed. See ATTRIBUTION-METRIC.md for the definition.
//
// Run standalone:  node --test framework/opencode/plugin/attribution.test.mjs
// Run via npm:     npm test
import { test } from "node:test"
import assert from "node:assert/strict"
import { runAttributionSuite } from "./attribution_harness.mjs"

const SEED = 20260911

test("attribution metric: exit 0, accuracy >= 0.99, units >= 1000", async () => {
  const res = await runAttributionSuite({ seed: SEED })
  assert.equal(res.exitCode, 0, `exitCode=${res.exitCode}`)
  assert.ok(res.accuracy >= 0.99, `accuracy=${res.accuracy} < 0.99`)
  assert.ok(res.totalUnits >= 1000, `totalUnits=${res.totalUnits} < 1000`)
  assert.equal(res.anomalies.length, 0, `anomalies=${res.anomalies.length}`)
  assert.equal(res.mismatchKeys.length, 0, `mismatched units: ${JSON.stringify(res.mismatchKeys.slice(0, 5))}`)
  assert.ok(res.scripted === 9, `scripted sessions=${res.scripted}`)
})

test("attribution metric: deterministic across two same-seed runs", async () => {
  const a = await runAttributionSuite({ seed: SEED })
  const b = await runAttributionSuite({ seed: SEED })
  assert.equal(a.accuracy, b.accuracy)
  assert.equal(a.totalUnits, b.totalUnits)
  assert.equal(a.flushCount, b.flushCount)
  assert.deepEqual(a.mismatchKeys, b.mismatchKeys)
  assert.deepEqual(a.anomalies, b.anomalies)
})
