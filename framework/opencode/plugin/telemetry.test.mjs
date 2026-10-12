// framework/opencode/plugin/telemetry.test.mjs
// Integration harness for the telemetry collector (T-FX3).
//
// Drives the plugin's hook sequence END TO END with a stubbed `$` host template-tag,
// asserting the CORRECT behaviour per the P0-INSTRUMENTATION-INTEGRITY spec. The
// collector (telemetry.ts) is owned by T-FX1 and is being fixed concurrently; several
// assertions here are RED against the pre-fix collector and GREEN once T-FX1 lands.
// That is expected and acceptable — the deliverable is the harness + wiring, and final
// green is team-lead's job.
//
// Run standalone:  node --test framework/opencode/plugin/telemetry.test.mjs
// Run via g4:      npm test   (once T-FX1 adds "test": "node --test framework/opencode/plugin")
//
// node:test + node:assert ONLY — no framework dependencies. Deterministic and fast (<15s).
import { test, describe, it } from "node:test"
import assert from "node:assert/strict"
import { TelemetryPlugin } from "./telemetry.ts"

// ─── Stub `$` host template-tag ───────────────────────────────────────────────
// The plugin invokes the host `$` exactly as:
//   await $`python3 framework/adapters/gsd_state.py write-telemetry --json ${JSON.stringify(payload)}`
//     .quiet().nothrow()
// We capture the command string and the parsed JSON payload instead of executing python.
// The chain mirrors the real contract: .quiet() and .nothrow() return the chain, and
// .nothrow() resolves to { exit: 0 }.
function makeDollar() {
  const emitted = []
  const dollar = (strings, ...values) => {
    let cmd = ""
    for (let i = 0; i < strings.length; i++) {
      cmd += strings[i]
      if (i < values.length) cmd += String(values[i])
    }
    let payload = null
    const m = cmd.match(/--json\s+(\{.*\})\s*$/)
    if (m) {
      try { payload = JSON.parse(m[1]) } catch { payload = null }
    }
    emitted.push({ cmd, payload })
    const chain = {
      quiet() { return this },
      nothrow() { return Promise.resolve({ exit: 0 }) },
    }
    return chain
  }
  return { dollar, emitted }
}

// Create a fresh plugin instance with a fresh stub.
async function makePlugin() {
  const { dollar, emitted } = makeDollar()
  const hooks = await TelemetryPlugin({ $: dollar })
  return { hooks, emitted }
}

// Drive a full session: session.created -> drive(hooks) -> session.idle (final).
// Returns the emitted write-telemetry records. session.idle clears the heartbeat
// interval so node --test does not hang on a live timer.
async function runSession(drive) {
  const { hooks, emitted } = await makePlugin()
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_test" } } } })
  await drive(hooks)
  await hooks.event({ event: { type: "session.idle", properties: {} } })
  return emitted
}

// The last emitted payload of a given kind, or null.
function lastPayload(emitted, kind) {
  const recs = emitted.filter((e) => e.payload && e.payload.kind === kind)
  return recs.length ? recs[recs.length - 1].payload : null
}

// All taxonomy events in a payload.
function events(payload) {
  return (payload && payload.taxonomy_events) || []
}

describe("telemetry collector integration harness", () => {
  it("emits a started record on session.created", async () => {
    const emitted = await runSession(async () => {})
    const started = lastPayload(emitted, "started")
    assert.ok(started, "expected a started record")
    assert.equal(started.session_id, "ses_test")
    assert.equal(started.kind, "started")
  })

  it("attributes a TASK delegation to the resolved execution_agent (not unknown)", async () => {
    const emitted = await runSession(async (hooks) => {
      // REAL runtime arg shape: args nested under input.
      const input = {
        tool: "task",
        callID: "call-task-1",
        input: { args: { subagent_type: "librarian", prompt: "explore the codebase" } },
      }
      await hooks["tool.execute.before"](input)
      await hooks["tool.execute.after"](input, { output: "done" })
    })
    const final = lastPayload(emitted, "final")
    const work = events(final).find((e) => e.event === "WORK_ATTEMPTED")
    assert.ok(work, "expected a WORK_ATTEMPTED taxonomy event")
    assert.equal(work.execution_agent, "librarian")
    assert.notEqual(work.execution_agent, "unknown")
  })

  it("attributes chat.params to the model/provider", async () => {
    const emitted = await runSession(async (hooks) => {
      await hooks["chat.params"]({ model: { modelID: "m1" }, provider: { providerID: "p1" } })
    })
    const final = lastPayload(emitted, "final")
    assert.equal(final.models_seen["p1/m1"], 1)
  })

  it("captures gate records with the correct shortGateId (g9/g12/g_tool_readiness)", async () => {
    const emitted = await runSession(async (hooks) => {
      const gates = [
        { cmd: "bash framework/gates/g9_scope.sh deploy", id: "g9" },
        { cmd: "bash framework/gates/g12_provider.sh", id: "g12" },
        { cmd: "bash framework/gates/g_tool_readiness.sh", id: "g_tool_readiness" },
      ]
      for (const g of gates) {
        const input = { tool: "bash", callID: "c-" + g.id, args: { command: g.cmd } }
        await hooks["tool.execute.before"](input)
        await hooks["tool.execute.after"](input, { output: `[gate] ${g.id} result=pass exit=0 ms=1` })
      }
    })
    const final = lastPayload(emitted, "final")
    const evs = events(final)
    for (const g of ["g9", "g12", "g_tool_readiness"]) {
      const required = evs.find((e) => e.event === "GATE_REQUIRED" && e.detail.gate === g)
      const started = evs.find((e) => e.event === "GATE_EXECUTION_STARTED" && e.detail.gate === g)
      const result = evs.find((e) => e.event === "GATE_RESULT" && e.detail.gate === g)
      assert.ok(required, `expected GATE_REQUIRED for ${g}`)
      assert.ok(started, `expected GATE_EXECUTION_STARTED for ${g}`)
      assert.ok(result, `expected GATE_RESULT for ${g}`)
      assert.equal(result.detail.result, "pass")
    }
  })

  it("classifies a pre-notification background_output as a poll", async () => {
    const emitted = await runSession(async (hooks) => {
      const input = { tool: "background_output", callID: "c-bg1", args: { task_id: "bg_123" } }
      await hooks["tool.execute.before"](input)
      await hooks["tool.execute.after"](input, { output: "still running" })
    })
    const final = lastPayload(emitted, "final")
    assert.equal(final.bg_poll_total, 1)
    assert.equal(final.bg_tasks["bg_123"].polls, 1)
    assert.equal(final.bg_tasks["bg_123"].collects, 0)
  })

  it("does NOT classify a completed background_output (Duration, no running/pending) as a poll", async () => {
    const emitted = await runSession(async (hooks) => {
      const input = { tool: "background_output", callID: "c-bg2", args: { task_id: "bg_456" } }
      await hooks["tool.execute.before"](input)
      await hooks["tool.execute.after"](input, { output: "Duration: 5.2s" })
    })
    const final = lastPayload(emitted, "final")
    assert.equal(final.bg_poll_total, 0)
    assert.equal(final.bg_tasks["bg_456"].collects, 1)
    assert.equal(final.bg_tasks["bg_456"].polls, 0)
  })

  it("emits exactly one final record and a second terminal event emits nothing", async () => {
    const { hooks, emitted } = await makePlugin()
    await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_final" } } } })
    await hooks.event({ event: { type: "session.idle", properties: {} } })
    await hooks.event({ event: { type: "session.deleted", properties: {} } })
    const finals = emitted.filter((e) => e.payload && e.payload.kind === "final")
    assert.equal(finals.length, 1)
    assert.equal(finals[0].payload.session_id, "ses_final")
  })
})
