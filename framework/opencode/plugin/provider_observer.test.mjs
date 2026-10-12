// Run: node --test framework/opencode/plugin/provider_observer.test.mjs   (from the repo root)
// observe tests use the REAL framework/providers/healthcheck.py against a temp ledger.
import { test, describe, before, after } from "node:test"
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtempSync, readFileSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { createProviderObserver, errorText, PREFLIGHT_ENV } from "./provider_observer.mjs"
import { TelemetryPlugin } from "./telemetry.ts"

const REPO = resolve(fileURLToPath(new URL("../../..", import.meta.url)))
const PY = process.env.INTAKE_TEST_PYTHON || "python3"
let ledger
before(() => { ledger = join(mkdtempSync(join(tmpdir(), "hc-")), "health.jsonl"); process.env.PROVIDER_HEALTH_FILE = ledger })
after(() => { delete process.env.PROVIDER_HEALTH_FILE; delete process.env.PROVIDER_PREFLIGHT })
const rows = () => existsSync(ledger) ? readFileSync(ledger, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []

const realRun = async (cmd, a) => {
  assert.equal(cmd, "observe")
  const r = spawnSync(PY, ["framework/providers/healthcheck.py", "observe", "--error", a.error, "--provider", a.provider, "--model", a.model, "--source", "session_error"],
    { cwd: REPO, env: process.env, encoding: "utf8" })
  return { exitCode: r.status, stdout: r.stdout, stderr: r.stderr }
}
const credit = { name: "APIError", data: { message: "Insufficient credits. This account never purchased credits.", statusCode: 402, isRetryable: false } }

describe("errorText", () => {
  test("joins name, message, status and body", () => {
    assert.equal(errorText({ name: "APIError", data: { message: "m", statusCode: 402, responseBody: "b" } }), "APIError m 402 b")
  })
  test("non-objects give empty", () => { assert.equal(errorText(null), ""); assert.equal(errorText("x"), "") })
})

describe("observe on session.error (real healthcheck.py)", () => {
  test("a credit failure from a known session is recorded against that session's provider/model", async () => {
    const o = createProviderObserver({ run: realRun, log: () => {} })
    o.onParams({ sessionID: "ses_c", provider: { providerID: "opencode" }, model: { modelID: "big-pickle" } })
    await o.onEvent({ type: "session.error", properties: { sessionID: "ses_c", error: credit } })
    const r = rows(); assert.equal(r.length, 1)
    assert.equal(r[0].class, "QUOTA_FAILURE"); assert.equal(r[0].model, "opencode/big-pickle"); assert.equal(r[0].provider, "opencode"); assert.equal(r[0].source, "session_error")
  })
  test("unknown session: provider from ProviderAuthError, model 'unknown'", async () => {
    const o = createProviderObserver({ run: realRun, log: () => {} })
    await o.onEvent({ type: "session.error", properties: { sessionID: "ses_x", error: { name: "ProviderAuthError", data: { providerID: "openrouter", message: "401 Unauthorized: invalid API key" } } } })
    const last = rows().at(-1); assert.equal(last.class, "AUTH_FAILURE"); assert.equal(last.provider, "openrouter"); assert.equal(last.model, "unknown")
  })
  test("an error that is not a provider failure records nothing", async () => {
    const n = rows().length
    const o = createProviderObserver({ run: realRun, log: () => {} })
    await o.onEvent({ type: "session.error", properties: { sessionID: "s", error: { name: "UnknownError", data: { message: "all good here" } } } })
    await o.onEvent({ type: "session.idle", properties: {} })
    assert.equal(rows().length, n)
  })
  test("a throwing run() never escapes", async () => {
    const o = createProviderObserver({ run: async () => { throw new Error("spawn ENOENT") }, log: () => {} })
    await assert.doesNotReject(o.onEvent({ type: "session.error", properties: { error: credit } }))
  })
})

describe("beforeTool pre-flight", () => {
  const mk = (exitCode, env) => { const logs = []; return { logs, o: createProviderObserver({ run: async () => ({ exitCode, stdout: '{"status":"fail"}' }), env, log: (m) => logs.push(m) }) } }
  test("off by default", async () => { const { o } = mk(1, {}); await assert.doesNotReject(o.beforeTool({ tool: "task" })) })
  test("only the task tool is checked", async () => { const { o } = mk(1, { [PREFLIGHT_ENV]: "1" }); await assert.doesNotReject(o.beforeTool({ tool: "bash" })) })
  test("exit 1 refuses the dispatch", async () => {
    const { o } = mk(1, { [PREFLIGHT_ENV]: "1" })
    await assert.rejects(o.beforeTool({ tool: "task" }), /NO TASK DISPATCH/)
  })
  test("exit 0 allows", async () => { const { o } = mk(0, { [PREFLIGHT_ENV]: "1" }); await assert.doesNotReject(o.beforeTool({ tool: "task" })) })
  test("exit 2 (could not determine) allows but is logged as UNVERIFIED", async () => {
    const { o, logs } = mk(2, { [PREFLIGHT_ENV]: "1" }); await o.beforeTool({ tool: "task" })
    assert.match(logs.join(" "), /UNVERIFIED/)
  })
})

describe("wired through TelemetryPlugin", () => {
  const dollar = (strings, ...values) => {
    const out = []; let vi = 0
    for (let i = 0; i < strings.length; i++) { out.push(...strings[i].split(/\s+/).filter(Boolean)); if (i < values.length) out.push(String(values[vi++])) }
    const run = () => {
      if (out[1]?.endsWith("healthcheck.py") && out[2] === "check") return { exitCode: 1, text: () => '{"status":"fail"}', stderr: Buffer.from("") }
      if (out[1]?.endsWith("healthcheck.py")) { const r = spawnSync(out[0], out.slice(1), { cwd: REPO, env: process.env, encoding: "utf8" }); return { exitCode: r.status, text: () => r.stdout, stderr: Buffer.from(r.stderr ?? "") } }
      return { exitCode: 0, text: () => "", stderr: Buffer.from("") }
    }
    return { quiet() { return this }, nothrow() { return Promise.resolve(run()) } }
  }
  test("chat.params + session.error through the plugin land in the ledger", async () => {
    const hooks = await TelemetryPlugin({ $: dollar })
    await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_w" } } } })
    await hooks["chat.params"]({ sessionID: "ses_w", agent: "explore", provider: { providerID: "openrouter" }, model: { modelID: "wired-model" } })
    const n = rows().length
    await hooks.event({ event: { type: "session.error", properties: { sessionID: "ses_w", error: credit } } })
    const last = rows().at(-1); assert.equal(rows().length, n + 1); assert.equal(last.model, "openrouter/wired-model"); assert.equal(last.class, "QUOTA_FAILURE")
    await hooks.event({ event: { type: "session.idle", properties: {} } })
  })
  test("PROVIDER_PREFLIGHT=1 makes the plugin's tool.execute.before refuse a task dispatch", async () => {
    process.env.PROVIDER_PREFLIGHT = "1"
    const hooks = await TelemetryPlugin({ $: dollar })
    await assert.rejects(hooks["tool.execute.before"]({ tool: "task", callID: "c1", sessionID: "s" }, { args: {} }), /NO TASK DISPATCH/)
    delete process.env.PROVIDER_PREFLIGHT
    await assert.doesNotReject(hooks["tool.execute.before"]({ tool: "read", callID: "c2", sessionID: "s" }, { args: {} }))
  })
})
