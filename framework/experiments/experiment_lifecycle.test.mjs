// framework/experiments/experiment_lifecycle.test.mjs
// P3 increment 3 - proves the full experiment lifecycle against the
// acceptance criteria the user approved for increment 3:
//   manifest -> scheduler -> fresh run -> telemetry -> recorder ->
//   RUN_VALIDITY -> blinding -> staged dataset -> explicit freeze ->
//   comparator gate
// Each test uses a disposable temp state dir + a 4-run fixture manifest
// (2xA, 2xB) against the real corpus, so the suite is hermetic and fast.
import { test } from "node:test"
import assert from "node:assert/strict"
import { spawn, execFile } from "node:child_process"
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises"
import { existsSync, readFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { buildPlan } from "./plan.mjs"
import { revealRun, deriveKey } from "./blinding.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REAL_CORPUS = path.join(HERE, "corpus.json")
const SALT = "stockerpro-p3-experiment"
const SECRET = "p3-test-secret-00001111222233334444555566667777"

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
const waitFor = async (fn, ms = 8000, what = "condition") => {
  const start = Date.now()
  for (;;) {
    if (fn()) return
    if (Date.now() - start > ms) throw new Error(`timed out waiting for ${what}`)
    await new Promise((r) => setTimeout(r, 100))
  }
}

async function fixtureManifest(dir) {
  const manifest = {
    manifest_version: "1.0.0",
    name: "lifecycle-fixture",
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

const newState = () => mkdtemp(path.join(os.tmpdir(), "p3state-"))

// --- 1. plan determinism, arm counts, unique ids, task cycle -------------
test("plan: deterministic, exact arm counts, unique run ids, corpus cycle", () => {
  const manifest = {
    manifest_version: "1.0.0", seed: 424242,
    conditions: [{ id: "A", runs: 2, profile: "baseline", label: "baseline" }, { id: "B", runs: 2, profile: "tiered", label: "tiered" }],
    corpus: { file: "corpus.json" },
  }
  const corpus = JSON.parse(readFileSync(REAL_CORPUS, "utf8"))
  const p1 = buildPlan(manifest, corpus)
  const p2 = buildPlan(manifest, corpus)
  assert.equal(p1.total, 4)
  assert.equal(p1.runs.filter((r) => r.arm === "A").length, 2)
  assert.equal(p1.runs.filter((r) => r.arm === "B").length, 2)
  assert.equal(new Set(p1.runs.map((r) => r.run_id)).size, 4)
  assert.deepEqual(p1.runs.map((r) => r.run_id), p2.runs.map((r) => r.run_id))
  assert.deepEqual(p1.runs.map((r) => r.arm), p2.runs.map((r) => r.arm))
  // deterministic task cycle over the 8-task corpus
  assert.equal(p1.runs[0].task_id, corpus.tasks[0].id)
  assert.equal(p1.runs[3].task_id, corpus.tasks[3].id)
  for (const r of p1.runs) {
    const t = corpus.tasks.find((x) => x.id === r.task_id)
    assert.ok(t, `task ${r.task_id} exists`)
    assert.ok(t.expected_outcome && t.expected_outcome.length > 0, `task ${r.task_id} has expected_outcome`)
  }
})

// --- 2. dry-run writes nothing --------------------------------------------
test("scheduler --dry-run produces ZERO experimental records", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const r = await runNode("scheduler.mjs", ["--dry-run", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(r.code, 0, r.stderr)
  assert.match(r.stdout, /DRY-RUN 4 runs/)
  for (const f of ["ledger/runs.jsonl", "dataset/runs.jsonl", "dataset/excluded.jsonl", "freeze.json"]) {
    assert.ok(!existsSync(path.join(state, f)), `${f} must not exist after dry-run`)
  }
})

// --- 3. full 4-run lifecycle ----------------------------------------------
test("lifecycle: schedule -> reconcile -> blinded VALID dataset + telemetry linkage", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const corpus = JSON.parse(readFileSync(REAL_CORPUS, "utf8"))

  const s = await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(s.code, 0, s.stderr)
  const ledger = readLines(path.join(state, "ledger", "runs.jsonl"))
  assert.equal(ledger.filter((l) => l.status === "STARTED").length, 4)
  assert.equal(ledger.filter((l) => l.status === "COMPLETED").length, 4)
  const starts = ledger.filter((l) => l.status === "STARTED")
  const comps = ledger.filter((l) => l.status === "COMPLETED")
  for (const c of comps) {
    const st = starts.find((x) => x.run_id === c.run_id)
    assert.deepEqual(
      { run_id: st.run_id, arm: st.arm, profile: st.profile, task_id: st.task_id, attempt_id: st.attempt_id, driver: st.driver },
      { run_id: c.run_id, arm: c.arm, profile: c.profile, task_id: c.task_id, attempt_id: c.attempt_id, driver: c.driver },
      `COMPLETED record echoes its STARTED record (${c.run_id})`,
    )
    assert.ok(c.completed_at, `${c.run_id} completed_at set`)
    assert.ok(c.pid === null || typeof c.pid === "number")
  }

  // A/B assignment comes from the plan, never the worker / telemetry
  const planArms = new Map(ledger.filter((l) => l.status === "STARTED").map((l) => [l.run_id, l.arm]))
  for (const runId of planArms.keys()) {
    const tele = JSON.parse(readFileSync(path.join(state, "telemetry", `${runId}.json`), "utf8"))
    assert.ok(!("arm" in tele), `telemetry for ${runId} carries no arm`)
    assert.equal(tele.session_id, `ses_fixture_${runId}`, `telemetry links to its run`)
  }

  const rec = await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { EXPERIMENT_SECRET: SECRET } })
  assert.equal(rec.code, 0, rec.stderr)
  const dataset = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.equal(dataset.length, 4)
  const excluded = readLines(path.join(state, "dataset", "excluded.jsonl"))
  assert.equal(excluded.length, 0)
  for (const d of dataset) {
    assert.equal(d.validity.status, "VALID")
    assert.deepEqual(d.validity.reasons, [])
    assert.ok(d.arm_token && typeof d.arm_token === "string", `${d.run_id} has arm_token`)
    assert.ok(!("arm" in d), `${d.run_id} carries no plaintext arm`)
    assert.ok(d.session_id, `${d.run_id} session_id recorded`)
    assert.ok(d.attempt_id, `${d.run_id} attempt_id recorded`)
    assert.equal(d.attribution_status, "pass")
    assert.equal(d.run_status, "VALID")
    // plan arm matches plan-owned record, and the token decrypts to it
    const expectedArm = planArms.get(d.run_id)
    const revealed = revealRun(deriveKey(SECRET, SALT), d.run_id, d.arm_token)
    assert.equal(revealed, expectedArm, `${d.run_id} token reveals the planned arm`)

    assert.equal(d.model_requested, "opencode/big-pickle")  // fixture telemetry values
    assert.equal(d.model_resolved, "opencode/big-pickle")
    assert.equal(d.outcome_produced, true)
    assert.equal(d.supervision_gap, false)
    assert.ok(corpus.tasks.some((t) => t.id === d.task_id), `${d.run_id} task_id from corpus`)
  }
})

// --- 4. recorder idempotence / duplicate rejection -------------------------
test("recorder: re-running is idempotent, duplicate run ids never written twice", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const env = { EXPERIMENT_SECRET: SECRET }
  await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  const datasetBefore = JSON.stringify(readLines(path.join(state, "dataset", "runs.jsonl")))
  const exclBefore = JSON.stringify(readLines(path.join(state, "dataset", "excluded.jsonl")))
  const r2 = await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(r2.code, 3, r2.stderr)  // nothing new to reconcile = idempotent
  assert.equal(JSON.stringify(readLines(path.join(state, "dataset", "runs.jsonl"))), datasetBefore, "dataset unchanged on re-reconcile")
  assert.equal(JSON.stringify(readLines(path.join(state, "dataset", "excluded.jsonl"))), exclBefore, "excluded unchanged on re-reconcile")
})

// --- 5. rerun cannot silently overwrite ------------------------------------
test("scheduler: rerunning a completed run is skipped - no overwrite", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  const before = readLines(path.join(state, "ledger", "runs.jsonl"))
  const r = await runNode("scheduler.mjs", ["--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(r.code, 3, `nothing to run -> exit 3 (got ${r.code}: ${r.stdout}${r.stderr})`)
  const after = readLines(path.join(state, "ledger", "runs.jsonl"))
  assert.equal(after.length, before.length, "no new ledger lines for a rerun")
  assert.equal(after.filter((l) => l.run_id === "R-0001" && l.status === "COMPLETED").length, 1, "R-0001 still exactly one COMPLETED record")
})

// --- 6. incomplete experiment cannot freeze --------------------------------
test("freeze: refused while the experiment is incomplete", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  await runNode("scheduler.mjs", ["--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env: { EXPERIMENT_SECRET: SECRET } })
  const dataset = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.equal(dataset.length, 1)
  const f = await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(f.code, 1, `incomplete freeze must fail (got ${f.code})`)
  assert.match(f.stderr, /incomplete/)
  assert.ok(!existsSync(path.join(state, "freeze.json")), "no freeze marker written")
})

// --- 7. plaintext arm tamper cannot freeze ---------------------------------
test("freeze: refused when the dataset leaks a plaintext arm", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const env = { EXPERIMENT_SECRET: SECRET }
  await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  // tamper: append a plaintext-arm record after freeze already succeeded once?
  // no - start over with a tampered dataset pre-freeze
  const state2 = await newState()
  const mf2 = await fixtureManifest(state2)
  await runNode("scheduler.mjs", ["--all", "--state", state2, "--manifest", mf2, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state2, "--manifest", mf2, "--corpus", REAL_CORPUS], { env })
  const datasetFile = path.join(state2, "dataset", "runs.jsonl")
  await writeFile(datasetFile, `{"run_id":"R-9999","arm":"A"}\n`, { flag: "a" })
  const f = await runNode("freeze.mjs", ["--freeze", "--state", state2, "--manifest", mf2, "--corpus", REAL_CORPUS])
  assert.equal(f.code, 1, `plaintext-arm dataset must not freeze (got ${f.code})`)
  assert.match(f.stderr, /plaintext arm|outside the plan/)
  assert.ok(!existsSync(path.join(state2, "freeze.json")))
})

// --- 8. freeze success + immutability + marker fields ----------------------
test("freeze: complete experiment freezes with full marker, second freeze refused", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const env = { EXPERIMENT_SECRET: SECRET }
  await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  const datasetBefore = JSON.stringify(readLines(path.join(state, "dataset", "runs.jsonl")))

  const f = await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(f.code, 0, f.stderr)
  const marker = JSON.parse(readFileSync(path.join(state, "freeze.json"), "utf8"))
  assert.equal(marker.frozen, true)
  assert.equal(marker.manifest_version, "1.0.0")
  assert.equal(marker.corpus_version, "1.0.0")
  assert.equal(marker.run_count, 4)
  assert.match(marker.dataset_checksum, /^[0-9a-f]{64}$/)
  assert.ok(!Number.isNaN(Date.parse(marker.frozen_at)), "frozen_at is an ISO timestamp")

  // immutable: second freeze fails, dataset bytes unchanged
  const f2 = await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(f2.code, 1)
  assert.match(f2.stderr, /already frozen/)
  assert.equal(JSON.stringify(readLines(path.join(state, "dataset", "runs.jsonl"))), datasetBefore, "dataset unchanged after second freeze attempt")
})

// --- 9. comparator gate ----------------------------------------------------
test("comparator: refuses before freeze, runs after freeze", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const env = { EXPERIMENT_SECRET: SECRET }
  const pre = await runNode("comparator.mjs", ["--compare", "--state", state])
  assert.equal(pre.code, 2, `pre-freeze comparator must refuse (got ${pre.code})`)
  assert.match(pre.stderr, /NOT frozen/)

  await runNode("scheduler.mjs", ["--all", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  await runNode("freeze.mjs", ["--freeze", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  const post = await runNode("comparator.mjs", ["--compare", "--state", state])
  assert.equal(post.code, 0, post.stderr)
})

// --- 10. kill-scheduler: orphan resolves deterministically, never vanishes --
test("kill scheduler mid-run: worker stays attributable, run -> deterministic INVALID, never VALID, resume proceeds", async () => {
  const state = await newState()
  const mf = await fixtureManifest(state)
  const env = { EXPERIMENT_SECRET: SECRET }

  // record R-0002 first so we can prove a later scheduler failure cannot
  // corrupt already-recorded runs
  const first = await runNode("scheduler.mjs", ["--run", "R-0002", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(first.code, 0, first.stderr)

  // schedule R-0001 with a slow worker, then kill the scheduler after STARTED
  const child = spawn(process.execPath, ["scheduler.mjs", "--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], {
    cwd: HERE, env: { ...process.env, EXPERIMENT_SECRET: SECRET, FIXTURE_DELAY_MS: "1500" }, stdio: "ignore",
  })
  await waitFor(() => {
    const lines = readLines(path.join(state, "ledger", "runs.jsonl"))
    return lines.some((l) => l.run_id === "R-0001" && l.status === "STARTED" && typeof l.pid === "number")
  }, 10000, "R-0001 STARTED in ledger")
  child.kill() // scheduler dies mid-run; the worker is a separate process and survives

  // the worker still produces its telemetry + outcome independently
  await waitFor(() => existsSync(path.join(state, "telemetry", "R-0001.json")), 8000, "worker telemetry after scheduler death")
  assert.ok(existsSync(path.join(state, "outcomes", "R-0001.json")), "worker outcome file exists")
  const tele = JSON.parse(readFileSync(path.join(state, "telemetry", "R-0001.json"), "utf8"))
  assert.equal(tele.session_id, "ses_fixture_R-0001", "orphan telemetry independently attributable")

  // ledger: R-0001 STARTED with no COMPLETED (a true orphan)
  const orphanLedger = readLines(path.join(state, "ledger", "runs.jsonl"))
  assert.ok(orphanLedger.some((l) => l.run_id === "R-0001" && l.status === "STARTED"))
  assert.ok(!orphanLedger.some((l) => l.run_id === "R-0001" && l.status === "COMPLETED"))

  // the scheduler refuses to rerun an UNRESOLVED orphan
  const rerun = await runNode("scheduler.mjs", ["--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(rerun.code, 1, `unresolved orphan rerun must be refused (got ${rerun.code})`)
  assert.match(rerun.stderr, /Refusing to rerun/)

  // recorder resolves the orphan to a deterministic non-valid state
  const rec = await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(rec.code, 0, rec.stderr)
  const excluded = readLines(path.join(state, "dataset", "excluded.jsonl"))
  const orphanExcluded = excluded.filter((e) => e.run_id === "R-0001")
  assert.equal(orphanExcluded.length, 1, "orphan recorded exactly once in excluded")
  assert.equal(orphanExcluded[0].validity.status, "INVALID")
  assert.ok(orphanExcluded[0].validity.reasons.some((r) => r.code === "SUPERVISION_GAP"), "reason is SUPERVISION_GAP")
  assert.equal(orphanExcluded[0].supervision_gap, true)
  assert.ok(typeof orphanExcluded[0].arm_token === "string", "excluded record is still blinded")
  const dataset = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.ok(!dataset.some((d) => d.run_id === "R-0001"), "orphan never entered the valid population")

  // re-reconcile is deterministic: same result, no duplication
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  assert.equal(readLines(path.join(state, "dataset", "excluded.jsonl")).filter((e) => e.run_id === "R-0001").length, 1, "redo yields the same single excluded record")
  assert.equal(readLines(path.join(state, "dataset", "runs.jsonl")).some((d) => d.run_id === "R-0001"), false)

  // the resolved orphan is terminal: rerun still refused, no new ledger lines
  const rerun2 = await runNode("scheduler.mjs", ["--run", "R-0001", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(rerun2.code, 3, "resolved orphan is terminal (nothing to run)")
  assert.equal(readLines(path.join(state, "ledger", "runs.jsonl")).filter((l) => l.run_id === "R-0001" && l.status === "STARTED").length, 1, "no second STARTED line")

  // resume proceeds with the OTHER runs; the resolved orphan is skipped,
  // the earlier valid run is untouched
  const resume = await runNode("scheduler.mjs", ["--resume", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(resume.code, 0, resume.stderr)
  const finalLedger = readLines(path.join(state, "ledger", "runs.jsonl"))
  for (const id of ["R-0001", "R-0002", "R-0003", "R-0004"]) {
    assert.ok(finalLedger.some((l) => l.run_id === id), `ledger has ${id}`)
  }
  assert.equal(finalLedger.filter((l) => l.run_id === "R-0002" && l.status === "COMPLETED").length, 1, "R-0002 intact (scheduler failure did not corrupt prior records)")
  assert.equal(finalLedger.filter((l) => l.run_id === "R-0001" && l.status === "STARTED").length, 1, "R-0001 still a single orphan, never rerun")
  assert.ok(!finalLedger.some((l) => l.run_id === "R-0001" && l.status === "COMPLETED"), "R-0001 never silently fixed up")

  // full reconcile still leaves R-0001 excluded; R-0003/R-0004 valid
  await runNode("recorder.mjs", ["--reconcile", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS], { env })
  const d2 = readLines(path.join(state, "dataset", "runs.jsonl"))
  assert.equal(d2.filter((d) => d.validity.status === "VALID").length, 3, "R-0002, R-0003, R-0004 valid")
  assert.ok(!d2.some((d) => d.run_id === "R-0001"))
  assert.equal(readLines(path.join(state, "dataset", "excluded.jsonl")).filter((e) => e.run_id === "R-0001").length, 1)
})

// --- 11. real 40-run manifest dry-runs cleanly -----------------------------
test("real manifest: 40-run plan built and dry-runs cleanly", async () => {
  const manifest = JSON.parse(readFileSync(path.join(HERE, "manifest.json"), "utf8"))
  const corpus = JSON.parse(readFileSync(REAL_CORPUS, "utf8"))
  const plan = buildPlan(manifest, corpus)
  assert.equal(plan.total, 40)
  assert.equal(plan.runs.filter((r) => r.arm === "A").length, 20)
  assert.equal(plan.runs.filter((r) => r.arm === "B").length, 20)
  assert.equal(new Set(plan.runs.map((r) => r.run_id)).size, 40)
  const state = await newState()
  const mf = path.join(state, "manifest.json")
  await writeFile(mf, JSON.stringify(manifest, null, 2), "utf8")
  const r = await runNode("scheduler.mjs", ["--dry-run", "--state", state, "--manifest", mf, "--corpus", REAL_CORPUS])
  assert.equal(r.code, 0, r.stderr)
  assert.match(r.stdout, /DRY-RUN 40 runs/)
})
