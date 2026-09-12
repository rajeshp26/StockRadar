// framework/experiments/fixture_worker.mjs
// Per-run worker for the FIXTURE driver (P3 increment 3). Reproduces the shape
// of a headless OpenCode run WITHOUT invoking the CLI: it writes the telemetry
// record a real session would leave and an outcome file, then exits. Used by
// the scheduler when --driver fixture (the default for tests) and by the
// kill-scheduler-integrity test (the worker must outlive a scheduler kill and
// remain independently attributable).
//
// Args: <run_id> <telemetry_out> <outcome_out> <delay_ms>
//   telemetry_out: JSON { session_id, model_requested, model_resolved,
//     resolved_provider, runtime_version, attribution_status,
//     gates_observable, outcome_produced, infra_violation, tokens,
//     fresh_tokens, tool_calls, retries, rework, elapsed_time, gates,
//     defects, arm_key0 }  - arm is intentionally NEVER written here.
//   outcome_out: JSON { run_id, produced: <expected_outcome result> }
//   delay_ms: sleep before writing (lets a test kill the parent first)
import { writeFile, mkdir } from "node:fs/promises"
import path from "node:path"

const [, , runId, telemetryOut, outcomeOut, delayMs] = process.argv
if (!runId || !telemetryOut || !outcomeOut) {
  console.error("fixture_worker: usage <run_id> <telemetry_out> <outcome_out> [delay_ms]")
  process.exit(64)
}

const delay = Number(delayMs || 0)
if (delay > 0) {
  await new Promise((r) => setTimeout(r, delay))
}

// Fabricated but schema-identical to what a real run's telemetry record carries.
const telemetry = {
  session_id: `ses_fixture_${runId}`,
  attempt_id: `att_fixture_${runId}`,
  model_requested: "opencode/big-pickle",
  model_resolved: "opencode/big-pickle",
  resolved_provider: "opencode",
  runtime_version: "v24.14.1",
  agent_profile_error: null,
  attribution_status: "pass",
  gates_observable: true,
  outcome_produced: true,
  infra_violation: false,
  tokens: 1000 + Math.floor(Math.random() * 2000),
  fresh_tokens: 500,
  tool_calls: 4,
  retries: 0,
  rework: 0,
  elapsed_time: 30 + Math.floor(Math.random() * 60),
  gates: [{ id: "g4", result: "pass" }],
  defects: 0,
}

try {
  await mkdir(path.dirname(telemetryOut), { recursive: true })
  await writeFile(telemetryOut, JSON.stringify(telemetry, null, 2) + "\n", "utf8")
  await writeFile(outcomeOut, JSON.stringify({ run_id: runId, produced: true, note: "fixture outcome" }) + "\n", "utf8")
  console.log(`fixture_worker: ${runId} complete`)
  process.exit(0)
} catch (e) {
  console.error(`fixture_worker: ${runId} failed: ${e.message}`)
  process.exit(1)
}
