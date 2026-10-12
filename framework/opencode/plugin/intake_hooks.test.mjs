// framework/opencode/plugin/intake_hooks.test.mjs
// Run: node --test framework/opencode/plugin/intake_hooks.test.mjs   (from the repo root)
//
// Uses the REAL framework/adapters/intake.py against a temp INTAKE_ROOT, so what is proven
// is the producer -> durable log -> render path, not a stub's idea of it.
import { test, describe } from "node:test"
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtempSync, readFileSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import {
  createIntakeHooks, userAskText, renderOpenAsks, CAPTURE_ENV,
} from "./intake_hooks.mjs"

const REPO = resolve(fileURLToPath(new URL("../../..", import.meta.url)))
const PY = process.env.INTAKE_TEST_PYTHON || "python3"

function realRun(root, calls = []) {
  return async (cmd, json) => {
    calls.push(cmd)
    const args = cmd === "capture"
      ? ["framework/adapters/intake.py", "capture", "--json", json]
      : ["framework/adapters/intake.py", "open"]
    const r = spawnSync(PY, args, { cwd: REPO, env: { ...process.env, INTAKE_ROOT: root }, encoding: "utf8" })
    return { exitCode: r.status, stdout: r.stdout, stderr: r.stderr }
  }
}
const mk = (over = {}) => {
  const root = mkdtempSync(join(tmpdir(), "intake-"))
  const calls = []
  const logs = []
  const h = createIntakeHooks({
    run: realRun(root, calls), env: { [CAPTURE_ENV]: "1" }, log: (m) => logs.push(m), ...over,
  })
  return { root, calls, logs, h }
}
const text = (t, extra = {}) => ({ type: "text", text: t, ...extra })
const send = (h, sid, mid, parts) =>
  h.hooks["chat.message"]({ sessionID: sid, messageID: mid, agent: "Sisyphus" }, { message: { id: mid, sessionID: sid }, parts })
const sysFor = async (h, sid) => {
  const out = { system: [] }
  await h.hooks["experimental.chat.system.transform"]({ sessionID: sid }, out)
  return out.system
}
const log = (root) => {
  const p = join(root, "intake", "asks.jsonl")
  return existsSync(p) ? readFileSync(p, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []
}

describe("userAskText", () => {
  test("keeps only real user text, verbatim", () => {
    assert.equal(
      userAskText([text("a  b"), text("auto", { synthetic: true }), text("ign", { ignored: true }), { type: "file", text: "x" }, text("   "), text("c")]),
      "a  b\n\nc",
    )
  })
  test("non-array -> empty", () => { assert.equal(userAskText(undefined), ""); assert.equal(userAskText(null), "") })
})

describe("capture (chat.message)", () => {
  test("disabled by default: no adapter call, nothing written", async () => {
    const { root, calls, h } = mk({ env: {} })
    await send(h, "ses_1", "msg_1", [text("do the thing")])
    assert.deepEqual(calls, []); assert.deepEqual(log(root), [])
  })

  test("enabled: captures the message verbatim with adapter-allocated id and CAPTURED status", async () => {
    const { root, h } = mk()
    const original = "i dont understand how did you claim everything is working fine\n\nwhy do i see spike on 2025-6-6, 2025-7-7?"
    await send(h, "ses_1", "msg_1", [text(original)])
    const ev = log(root)
    assert.equal(ev.length, 1)
    assert.equal(ev[0].event, "ASK_CAPTURED"); assert.equal(ev[0].ask_id, "ASK-001")
    assert.equal(ev[0].emitter, "intake-hook")
    assert.equal(ev[0].record.original_text, original)
    assert.equal(ev[0].record.session_id, "ses_1"); assert.equal(ev[0].record.source, "user")
    assert.equal(ev[0].record.provenance.message_id, "msg_1")
    assert.equal(ev[0].record.provenance.agent, "Sisyphus")
  })

  test("a message with only synthetic parts is not an ask", async () => {
    const { root, h } = mk()
    await send(h, "ses_1", "msg_1", [text("continue", { synthetic: true })])
    assert.deepEqual(log(root), [])
  })

  test("delegation sessions (parentID set) are not captured", async () => {
    const { root, h } = mk()
    h.onEvent({ type: "session.created", properties: { info: { id: "ses_child", parentID: "ses_1" } } })
    await send(h, "ses_child", "msg_9", [text("explore the repo for X")])
    assert.deepEqual(log(root), [])
  })

  test("root sessions are captured and marked parent_known", async () => {
    const { root, h } = mk()
    h.onEvent({ type: "session.created", properties: { info: { id: "ses_1" } } })
    await send(h, "ses_1", "msg_1", [text("real ask")])
    assert.equal(log(root)[0].record.provenance.parent_known, true)
  })

  test("a session never seen created is still captured (conserve), marked parent_known=false", async () => {
    const { root, h } = mk()
    await send(h, "ses_resumed", "msg_1", [text("real ask")])
    assert.equal(log(root)[0].record.provenance.parent_known, false)
  })

  test("the same message id is captured once", async () => {
    const { root, h } = mk()
    await send(h, "ses_1", "msg_1", [text("x")]); await send(h, "ses_1", "msg_1", [text("x")])
    assert.equal(log(root).length, 1)
  })

  test("missing sessionID cannot be bound: counted as a failure, not thrown, nothing written", async () => {
    const { root, h, logs } = mk()
    await h.hooks["chat.message"]({}, { message: {}, parts: [text("x")] })
    assert.deepEqual(log(root), []); assert.equal(logs.length, 1)
  })

  test("a failing adapter never throws into the host, is counted, and is SHOWN in the next injection", async () => {
    const { h, logs } = mk({ run: async () => ({ exitCode: 2, stdout: "", stderr: "BLOCKED: boom" }) })
    await send(h, "ses_1", "msg_1", [text("x")])
    assert.equal(logs.length, 1)
    const out = await sysFor(h, "ses_1")
    assert.match(out.join("\n"), /INTAKE CAPTURE FAILED 1 time/)
    assert.match(out.join("\n"), /INTAKE STORE UNREADABLE/)
  })

  test("a throwing run() never escapes the hook", async () => {
    const { h } = mk({ run: async () => { throw new Error("spawn ENOENT") } })
    await assert.doesNotReject(send(h, "ses_1", "msg_1", [text("x")]))
  })
})

describe("injection (system.transform / compacting)", () => {
  test("open asks are stated verbatim on every request; terminated asks are not", async () => {
    const { root, h } = mk()
    await send(h, "ses_1", "m1", [text("first ask")]); await send(h, "ses_1", "m2", [text("second ask")])
    const done = spawnSync(PY, ["framework/adapters/intake.py", "transition", "--id", "ASK-001", "--json", '{"status":"REJECTED"}'],
      { cwd: REPO, env: { ...process.env, INTAKE_ROOT: root }, encoding: "utf8" })
    assert.equal(done.status, 0, done.stderr)
    const out = (await sysFor(mk({ run: realRun(root) }).h, "ses_1")).join("\n")
    assert.match(out, /ASK-002 \[CAPTURED\]/); assert.match(out, /> second ask/)
    assert.doesNotMatch(out, /ASK-001/)
  })

  test("nothing is injected when there are no open asks and no failures (no token cost)", async () => {
    const { h } = mk()
    assert.deepEqual(await sysFor(h, "ses_1"), [])
  })

  test("disabled: nothing injected", async () => {
    const { h } = mk({ env: {} })
    assert.deepEqual(await sysFor(h, "ses_1"), [])
  })

  test("delegation sessions do not receive the root ask block", async () => {
    const { root, h } = mk()
    await send(h, "ses_1", "m1", [text("ask")])
    const h2 = mk({ run: realRun(root) }).h
    h2.onEvent({ type: "session.created", properties: { info: { id: "ses_child", parentID: "ses_1" } } })
    assert.deepEqual(await sysFor(h2, "ses_child"), [])
  })

  test("SURVIVES A RESTART: a fresh plugin instance (no in-memory state) still states the ask verbatim", async () => {
    const { root, h } = mk()
    const multi = "1. add logs\n2. test end to end\n3. explain 2025-06-06 and 2025-07-07"
    await send(h, "ses_1", "m1", [text(multi)])
    const fresh = mk({ run: realRun(root) }).h
    const out = (await sysFor(fresh, "ses_1")).join("\n")
    for (const line of multi.split("\n")) assert.ok(out.includes("  > " + line), line)
  })

  test("an unreadable store says so instead of implying there are no asks", async () => {
    const { h } = mk({ run: async () => ({ exitCode: 2, stdout: "", stderr: "ASK_INTAKE_BLOCKED: corrupt" }) })
    assert.match((await sysFor(h, "ses_1")).join("\n"), /Do not assume there are no open asks/)
  })

  test("compaction receives the same block", async () => {
    const { h } = mk()
    await send(h, "ses_1", "m1", [text("keep me")])
    const out = { context: [] }
    await h.hooks["experimental.session.compacting"]({ sessionID: "ses_1" }, out)
    assert.equal(out.context.length, 1); assert.match(out.context[0], /> keep me/)
  })

  test("open list is cached for the TTL and invalidated by our own capture", async () => {
    let t = 1000
    const { h, calls } = mk({ now: () => t, ttlMs: 5000 })
    await send(h, "ses_1", "m1", [text("a")])
    await sysFor(h, "ses_1"); await sysFor(h, "ses_1")
    assert.equal(calls.filter((c) => c === "open").length, 1)
    await send(h, "ses_1", "m2", [text("b")])
    await sysFor(h, "ses_1")
    assert.equal(calls.filter((c) => c === "open").length, 2)
    t += 6000; await sysFor(h, "ses_1")
    assert.equal(calls.filter((c) => c === "open").length, 3)
  })
})

describe("renderOpenAsks bounds", () => {
  const ask = (n, len) => ({ ask_id: `ASK-${String(n).padStart(3, "0")}`, status: "CAPTURED", created_at: "t", original_text: "x".repeat(len) })
  test("a long ask is truncated with a pointer to the full text", () => {
    const r = renderOpenAsks([ask(1, 5000)], { maxAskChars: 100 })
    assert.match(r, /truncated; full text: .*show --id ASK-001/); assert.ok(r.length < 800)
  })
  test("the block is capped and reports how many asks were not shown", () => {
    const r = renderOpenAsks(Array.from({ length: 50 }, (_, i) => ask(i + 1, 300)), { maxBlockChars: 1500 })
    assert.match(r, /\[\+\d+ more open asks not shown/); assert.ok(r.length < 2200)
  })
  test("deterministic: same input -> identical output", () => {
    const a = [ask(1, 10), ask(2, 20)]
    assert.equal(renderOpenAsks(a), renderOpenAsks(a))
  })
  test("the first ask is always shown even if it alone exceeds the cap", () => {
    assert.match(renderOpenAsks([ask(1, 4000)], { maxBlockChars: 10, maxAskChars: 4000 }), /ASK-001/)
  })
})
