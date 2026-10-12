// framework/opencode/plugin/intake_wiring.test.mjs
// Run: node --test framework/opencode/plugin/intake_wiring.test.mjs   (from the repo root)
//
// Proves the hooks are actually REGISTERED by TelemetryPlugin and reach the real adapter
// through the same `$` + python3 route the plugin already uses for write-telemetry. The
// stub `$` mirrors Bun's contract: the interpolated value is delivered as ONE argv element,
// and the result exposes { exitCode, text(), stderr } like BunShellOutput.
import { test, describe, before, after } from "node:test"
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtempSync, readFileSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { TelemetryPlugin } from "./telemetry.ts"

const REPO = resolve(fileURLToPath(new URL("../../..", import.meta.url)))
const PY = process.env.INTAKE_TEST_PYTHON || "python3"

function makeDollar() {
  const calls = []
  const dollar = (strings, ...values) => {
    const argv = strings.join("\u0000").split(/\s+/).filter(Boolean)
    // Rebuild argv the way Bun does: literal words split on whitespace, each interpolated
    // value kept as a single element.
    const out = []
    let vi = 0
    for (let i = 0; i < strings.length; i++) {
      out.push(...strings[i].split(/\s+/).filter(Boolean))
      if (i < values.length) out.push(String(values[vi++]))
    }
    calls.push(out)
    const run = () => {
      if (out[1]?.endsWith("intake.py")) {
        const r = spawnSync(out[0], out.slice(1), { cwd: REPO, env: process.env, encoding: "utf8" })
        return { exitCode: r.status, text: () => r.stdout, stderr: Buffer.from(r.stderr ?? "") }
      }
      return { exitCode: 0, text: () => "", stderr: Buffer.from("") } // write-telemetry etc.
    }
    return { quiet() { return this }, nothrow() { return Promise.resolve(run()) } }
  }
  return { dollar, calls }
}

const text = (t) => ({ type: "text", text: t })
let root
const asksLog = () => {
  const p = join(root, "intake", "asks.jsonl")
  return existsSync(p) ? readFileSync(p, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []
}

describe("TelemetryPlugin registers and drives the intake hooks", () => {
  before(() => { root = mkdtempSync(join(tmpdir(), "intake-wire-")); process.env.INTAKE_ROOT = root })
  after(() => { delete process.env.INTAKE_ROOT; delete process.env.INTAKE_CAPTURE })

  test("the three intake hooks are registered alongside the existing telemetry hooks", async () => {
    const { dollar } = makeDollar()
    const hooks = await TelemetryPlugin({ $: dollar })
    for (const k of ["chat.message", "experimental.chat.system.transform", "experimental.session.compacting", "chat.params", "event"]) {
      assert.equal(typeof hooks[k], "function", k)
    }
  })

  test("disabled (default): a user message causes no adapter call", async () => {
    delete process.env.INTAKE_CAPTURE
    const { dollar, calls } = makeDollar()
    const hooks = await TelemetryPlugin({ $: dollar })
    await hooks["chat.message"]({ sessionID: "ses_a", messageID: "m1" }, { message: {}, parts: [text("hello")] })
    assert.equal(calls.filter((c) => c.some((w) => w.endsWith("intake.py"))).length, 0)
    assert.deepEqual(asksLog(), [])
  })

  test("enabled: capture reaches the real adapter with the JSON as a single argv element, then the ask is injected", async () => {
    process.env.INTAKE_CAPTURE = "1"
    const { dollar, calls } = makeDollar()
    const hooks = await TelemetryPlugin({ $: dollar })
    await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_root" } } } })
    const original = 'add logs\n"quoted" and \'single\' and $dollar and `tick`'
    await hooks["chat.message"]({ sessionID: "ses_root", messageID: "m1", agent: "Sisyphus" }, { message: {}, parts: [text(original)] })

    const cap = calls.find((c) => c[2] === "capture")
    assert.ok(cap, "capture was invoked"); assert.equal(cap[3], "--json"); assert.equal(cap.length, 5)
    const ev = asksLog()
    assert.equal(ev.length, 1); assert.equal(ev[0].record.original_text, original)

    const sys = { system: [] }
    await hooks["experimental.chat.system.transform"]({ sessionID: "ses_root" }, sys)
    assert.match(sys.system.join("\n"), /ASK-001 \[CAPTURED\]/)

    await hooks.event({ event: { type: "session.idle", properties: {} } }) // clears the heartbeat timer
  })

  test("a delegation session announced through the plugin's own event hook is not captured", async () => {
    process.env.INTAKE_CAPTURE = "1"
    const before = asksLog().length
    const { dollar } = makeDollar()
    const hooks = await TelemetryPlugin({ $: dollar })
    await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_kid", parentID: "ses_root" } } } })
    await hooks["chat.message"]({ sessionID: "ses_kid", messageID: "m9" }, { message: {}, parts: [text("explore X")] })
    assert.equal(asksLog().length, before)
    await hooks.event({ event: { type: "session.idle", properties: {} } })
  })
})
