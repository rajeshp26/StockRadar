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
import { TelemetryPlugin, dispatchV2, shellFor, v2Event, v2ToolAfter, v2ToolBefore } from "./telemetry.ts"

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


// ─── V2 adapter ───────────────────────────────────────────────────────────────────────────
// These cases exist because the v2 payload shapes are DIFFERENT from v1 in ways that fail
// silently: a pass-through records `session_id: ""` and zero tokens while every counter still
// looks present. Each shape below was measured on host v2.2.4.
describe("v2 adapter", () => {
  it("captures the skill id from a v2 execute.before event", () => {
    const input = v2ToolBefore({
      tool: "skill", id: "call_1", sessionID: "ses_x", input: { id: "istqb-testing" },
    })
    assert.equal(input.tool, "skill")
    assert.equal(input.args.id, "istqb-testing")
    assert.equal(input.callID, "call_1")
  })

  it("reads v2 bash text and exit from result.output", () => {
    const [input, output] = v2ToolAfter({
      tool: "bash", id: "c1", input: { command: "echo hi" }, status: "success",
      result: { output: { exit: 0, truncated: false, output: "hi\n", status: "success" } },
    })
    assert.equal(input.args.command, "echo hi")
    assert.equal(output.output, "hi\n")
    assert.equal(output.exit, 0)
  })

  it("turns the first execution.started into session.created, later turns into nothing", () => {
    const seen = new Set()
    const first = v2Event({ type: "session.execution.started", data: { sessionID: "ses_a" } }, seen)
    assert.equal(first.event.properties.info.id, "ses_a")
    assert.equal(v2Event({ type: "session.execution.started", data: { sessionID: "ses_a" } }, seen), null)
  })

  it("does NOT map session.usage.updated -- it would double count step tokens", () => {
    assert.equal(
      v2Event({ type: "session.usage.updated", data: { sessionID: "s", tokens: { input: 99 } } }, new Set()),
      null,
    )
  })

  it("maps step tokens to a per-message update", () => {
    const step = v2Event({
      type: "session.step.ended",
      data: { assistantMessageID: "msg_1", tokens: { input: 10, output: 20, reasoning: 0, cache: { read: 0, write: 0 } } },
    }, new Set())
    assert.equal(step.event.type, "message.updated")
    assert.equal(step.event.properties.info.id, "msg_1")
    assert.equal(step.event.properties.info.tokens.input, 10)
  })

  it("spawns with an argv array so a JSON payload keeps its quotes", async () => {
    // The defect this pins: a shell-concatenated command lost every quote inside the payload
    // and the record was appended as `{record_version:3,...}` -- unparsable, unrecoverable.
    const $ = shellFor(process.cwd())
    const payload = JSON.stringify({ text: "a b", quoted: '"x"' })
    const r = await $`python3 -c ${'import json,sys;print(json.loads(sys.argv[1])["quoted"])'} ${payload}`
      .quiet().nothrow()
    assert.equal(r.exitCode, 0, "spawn failed: " + r.stderr)
    assert.equal(r.text().trim(), '"x"')
  })

  it("drives a full v2 session into a final record with real skills and tokens", async () => {
    const { hooks, emitted } = await makePlugin()
    const seen = new Set()
    await dispatchV2({ type: "session.execution.started", data: { sessionID: "ses_v2" } }, hooks, seen)
    await dispatchV2({
      type: "session.step.started",
      data: { sessionID: "ses_v2", agent: "team-lead", model: { id: "big-pickle", providerID: "opencode" } },
    }, hooks, seen)
    await hooks["tool.execute.before"](v2ToolBefore({
      tool: "skill", id: "c1", sessionID: "ses_v2", input: { id: "istqb-testing" },
    }))
    await hooks["tool.execute.after"](...v2ToolAfter({
      tool: "bash", id: "c2", input: { command: "bash framework/gates/g8_state.sh" }, status: "success",
      result: { output: { exit: 0, output: "[g8] PASS\n", status: "success" } },
    }))
    await dispatchV2({
      type: "session.step.ended",
      data: { assistantMessageID: "msg_1", tokens: { input: 10, output: 20, reasoning: 0, cache: { read: 5, write: 0 } } },
    }, hooks, seen)
    await dispatchV2({ type: "session.execution.succeeded", data: { sessionID: "ses_v2" } }, hooks, seen)

    const final = lastPayload(emitted, "final")
    assert.ok(final, "expected a final record")
    assert.equal(final.session_id, "ses_v2")
    assert.ok(final.skills_loaded.includes("istqb-testing"), "skill id must be recorded, not 'unknown'")
    assert.equal(final.tokens.input, 10)
    assert.equal(final.tokens.output, 20)
    assert.equal(final.tokens.cache_read, 5)
    assert.ok(final.models_seen["opencode/big-pickle"] >= 1, "model identity comes from step.started")
    assert.equal(final.gates.g8.result, "pass")
  })
})
