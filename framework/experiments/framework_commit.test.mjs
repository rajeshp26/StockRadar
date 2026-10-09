// framework/experiments/framework_commit.test.mjs
// Proves control-plane provenance capture: the framework commit under which a
// run executes is resolved once, stamped into the scheduler ledger record,
// carried into the captured dataset record, and pinned in the freeze marker -
// so a control-plane change between runs is visible in the frozen data instead
// of invisible. No-commit environments record an explicit unknown (null); the
// value is never fabricated, and it is NOT a validity condition.
import { test } from "node:test"
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdtemp, writeFile } from "node:fs/promises"
import { existsSync, readFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { classifyRun, STATUS, MANDATORY_FIELDS } from "./run_validity.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REAL_CORPUS = path.join(HERE, "corpus.json")
const SECRET = "p3-test-secret-00001111222233334444555566667777"
const SHA_RE = /^[0-9a-f]{40}$/

const runNode = (script, args, opts = {}) => new Promise((resolve) => {
  execFile(process.execPath, [script, ...args], { env: { ...process.env, ...opts.env }, cwd: opts.cwd || HERE, maxBuffer: 4 * 1024 * 1024 }, (err, stdout, stderr) => {
    const code = err && typeof err.code === "number" ? err.code : err ? 1 : 0
    resolve({ code, stdout, stderr })
  })
})

const readLines = (file) => {
  if (!existsSync(file)) return []
  return readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((l) => JSON.parse(l))
}

async function fixtureManifest(dir) {
  const manifest = {
    manifest_version: "1.0.0",
    name: "framework-commit-fixture",
    seed: 424242,
    conditions: [
      { id: "A", runs: 2, profile: "baseline", label: "baseline" },
      { id: "B", runs: 2, profile: "tiered", label: "tiered" },
    ],
    corpus: { file: "corpus.json" },
  }
  const f = path.join(dir, "manifest.json")
  await writeFile(f, JSON.stringify(manifest, null, 2), "utf8")
  return f
}

const newState = () => mkdtemp(path.join(os.tmpdir(), "p3commit-"))

// A fresh module instance per unit scenario: frameworkCommit() memoises, so
// each scenario needs its own instance to observe resolution independently.
const freshState = (tag) => import(`./experiment_state.mjs?${tag}`)

const withEnv = async (value, fn) => {
  const prev = process.env.FRAMEWORK_COMMIT
  if (value === undefined) delete process.env.FRAMEWORK_COMMIT
  else process.env.FRAMEWORK_COMMIT = value
  try { return await fn() } finally {
    if (prev === undefined) delete process.env.FRAMEWORK_COMMIT
    else process.env.FRAMEWORK_COMMIT = prev
  }
}

// --- unit: env override is the source of truth, trimmed --------------------
test("frameworkCommit: FRAMEWORK_COMMIT override takes precedence (trimmed)", async () => {
  await withEnv("  c0ffee1234567890abcdef1234567890abcdef12  ", async () => {
    const { frameworkCommit } = await freshState("override")
    assert.equal(frameworkCommit(), "c0ffee1234567890abcdef1234567890abcdef12")
  })
})

// --- unit: resolution is memoised, not re-read -----------------------------
test("frameworkCommit: resolved once, memoised (later env change does not re-resolve)", async () => {
  await withEnv("commit-first", async () => {
    const { frameworkCommit } = await freshState("memo")
    assert.equal(frameworkCommit(), "commit-first")
    process.env.FRAMEWORK_COMMIT = "commit-second"
    assert.equal(frameworkCommit(), "commit-first", "memoised value is stable")
  })
})

// --- unit: absent override -> git HEAD or an explicit null -----------------
test("frameworkCommit: without override resolves to a git sha or null, never fabricated", async () => {
  await withEnv(undefined, async () => {
    const { frameworkCommit } = await freshState("fallback")
    const c = frameworkCommit()
    assert.ok(c === null || SHA_RE.test(c), `expected null or 40-hex sha, got ${c}`)
    assert.equal(frameworkCommit(), c, "stable across calls")
  })
})

// --- unit: provenance is not a validity condition --------------------------
test("framework_commit is provenance, not a validity condition", () => {
  assert.ok(!MANDATORY_FIELDS.includes("framework_commit"), "framework_commit must not be mandatory")
  const v = classifyRun({
    run_id: "R-0001", arm: "A", task_id: "T", session_id: "s", attempt_id: "a",
    seed: 1, run_order: 1, model_requested: "m", model_resolved: "m",
    resolved_provider: "p", runtime_version: "v", agent_profile: "baseline",
    attribution_status: "pass", supervision_gap: false, gates_observable: true,
    outcome_produced: true, infra_violation: false, framework_commit: "abc123",
  })
  assert.equal(v.status, STATUS.VALID)
  assert.deepEqual(v.reasons, [])
})

// --- integration: stamp -> carry -> pin ------------------------------------
test("lifecycle: framework commit stamped in ledger, carried into dataset, pinned in freeze marker", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
  const env = { EXPERIMENT_SECRET: SECRET, FRAMEWORK_COMMIT: COMMIT }

  const s = await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(s.code, 0, s.stderr)
  const ledger = readLines(path.join(state, "ledger", "runs.jsonl"))
  const starts = ledger.filter((l) => l.status === "STARTED")
  assert.equal(starts.length, 4)
  for (const l of starts) assert.equal(l.framework_commit, COMMIT, `${l.run_id} STARTED carries the commit`)
  for (const l of ledger.filter((l) => l.status === "COMPLETED")) {
    assert.equal(l.framework_commit, COMMIT, `${l.run_id} terminal record echoes the commit`)
  }

  const rec = await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(rec.code, 0, rec.stderr)
  const dataset = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.equal(dataset.length, 4)
  for (const d of dataset) {
    assert.equal(d.validity.status, "VALID", `${d.run_id} still VALID with provenance attached`)
    assert.equal(d.framework_commit, COMMIT, `${d.run_id} dataset record carries the commit`)
  }

  const f = await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(f.code, 0, f.stderr)
  const marker = JSON.parse(readFileSync(path.join(state, "freeze.json"), "utf8"))
  assert.equal(marker.framework_commit, COMMIT, "a single commit is the provenance")
  assert.deepEqual(marker.framework_commits, [COMMIT])
})

// --- integration: mixed commits are disclosed, never hidden ---------------
test("freeze: runs from two framework commits disclose a mixed set (single field null)", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const C1 = "1111111111111111111111111111111111111111"
  const C2 = "2222222222222222222222222222222222222222"
  const base = { EXPERIMENT_SECRET: SECRET }

  // one commit per run, so the dataset spans a control-plane change
  await runNode("scheduler.mjs", ["--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { ...base, FRAMEWORK_COMMIT: C1 } })
  await runNode("scheduler.mjs", ["--run", "R-0002", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { ...base, FRAMEWORK_COMMIT: C1 } })
  await runNode("scheduler.mjs", ["--run", "R-0003", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { ...base, FRAMEWORK_COMMIT: C2 } })
  await runNode("scheduler.mjs", ["--run", "R-0004", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { ...base, FRAMEWORK_COMMIT: C2 } })

  const rec = await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: base })
  assert.equal(rec.code, 0, rec.stderr)
  const dataset = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.equal(dataset.length, 4)
  assert.deepEqual([...new Set(dataset.map((d) => d.framework_commit))].sort(), [C1, C2], "both commits present in the dataset")

  const f = await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: base })
  assert.equal(f.code, 0, f.stderr)
  const marker = JSON.parse(readFileSync(path.join(state, "freeze.json"), "utf8"))
  assert.equal(marker.framework_commit, null, "a mixed set has no single provenance")
  assert.deepEqual(marker.framework_commits, [C1, C2], "both commits disclosed, sorted")
})
