// framework/experiments/scheduler.mjs
// P3 increment 3 - the scheduler owns run execution. It is deliberately NOT a
// second orchestration system: it spawns one fresh headless OpenCode run per
// scheduled run with the manifest-selected arm profile, records what happened
// in an append-only ledger, and does nothing else. Task lifecycle, recovery,
// gates and telemetry stay with the existing framework machinery; the
// recorder reconciles those sources afterwards.
//
// Hierarchy (P3 doc): manifest -> scheduler -> fresh OpenCode run -> existing
// telemetry -> recorder -> RUN_VALIDITY -> blinding -> frozen dataset ->
// comparator.
//
// Ledger contract (state/ledger/runs.jsonl, append-only):
//   { run_id, run_order, arm, profile, task_id, task_type, attempt_id,
//     driver, framework_commit, status: STARTED|COMPLETED|FAILED, started_at,
//     completed_at, pid }
//   - the STARTED record is appended only AFTER the worker process exists,
//     carrying its pid, so a killed scheduler always leaves an attributable
//     trace of a run that actually began; the terminal record (last for the
//     run_id) is COMPLETED/FAILED and echoes the STARTED record.
//   - a STARTED record with no terminal record is an orphan from a killed or
//     errored scheduler; it is never rerun. The recorder resolves it
//     deterministically to a non-valid state (excluded.jsonl); after that
//     resolution the run is terminal and resume skips it. An UNRESOLVED
//     orphan BLOCKS resume (run the recorder first).
//   - records are appended one per fs call; a crash cannot corrupt earlier
//     records. Reruns of completed runs are skipped - no silent overwrite.
//
// A/B assignment comes from the manifest-derived plan (plan.mjs), never from
// the worker; the worker is spawned fresh per run and never told its arm.
//
// Usage:
//   node scheduler.mjs --dry-run              plan only, writes NOTHING
//   node scheduler.mjs --all                  run every pending run
//   node scheduler.mjs --run R-0003           run one pending run
//   node scheduler.mjs --resume               run pending runs (skip done)
//   --state <dir>   experiment state dir (default framework/experiments/state)
//   --manifest <f>  manifest (default manifest.json)
//   --corpus <f>    corpus (default corpus.json)
//   --driver fixture|opencode  (default fixture; opencode spawns the real CLI)
//   env FIXTURE_DELAY_MS   worker delay for kill-tests
// Exit: 0 ok / 1 operational error / 2 usage / 3 nothing to run
import { spawn } from "node:child_process"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { randomUUID } from "node:crypto"
import { fileURLToPath } from "node:url"
import { buildPlan } from "./plan.mjs"
import {
  stateDirs, ensureDirs, readLedger, readExcluded, appendLine,
  loadManifestCorpus, readJson, frameworkCommit,
} from "./experiment_state.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DEFAULTS = {
  state: path.join(HERE, "state"),
  manifest: path.join(HERE, "manifest.json"),
  corpus: path.join(HERE, "corpus.json"),
}

function usage(msg) {
  if (msg) console.error(`[scheduler] ${msg}`)
  console.error(`[scheduler] usage: node scheduler.mjs --dry-run | --all | --resume | --run <id> [--state <dir>] [--manifest <f>] [--corpus <f>] [--driver fixture|opencode]`)
  process.exit(2)
}

async function prepareRun(scratchDir, run, corpus) {
  // Tasks are self-contained: write the corpus input files into a per-run
  // scratch dir so a fresh headless run has a deterministic workspace.
  const scratch = path.join(scratchDir, run.run_id)
  const task = corpus.tasks.find((t) => t.id === run.task_id)
  if (!task) throw new Error(`scheduler: task ${run.task_id} not found in corpus`)
  await mkdir(scratch, { recursive: true })
  for (const [name, content] of Object.entries(task.input_files || {})) {
    await writeFile(path.join(scratch, name), content, "utf8")
  }
  return scratch
}

function spawnWorker(run, dirs, driver, scratch) {
  const telemetryOut = path.join(dirs.telemetryDir, `${run.run_id}.json`)
  const outcomeOut = path.join(dirs.outcomesDir, `${run.run_id}.json`)
  const delay = process.env.FIXTURE_DELAY_MS || "0"
  let child
  if (driver === "opencode") {
    // Real headless OpenCode run. Wired against the framework CLI surface; the
    // exact argv is configurable because the CLI is env-dependent. This path is
    // NOT exercised by the test suite (no CLI in the harness) - the fixture
    // driver proves the schedule/spawn/ledger contract instead.
    const bin = process.env.OPENCODE_BIN || "opencode"
    const argv = JSON.parse(process.env.OPENCODE_ARGS || `["run","--profile","${run.profile}","<task prompt>"]`)
    const args = argv.map((a) => (a === "<task prompt>" ? run.task_name : a))
    child = spawn(bin, args, { cwd: scratch, stdio: "inherit", shell: false })
  } else {
    // Fixture driver: a separate worker process that fabricates telemetry and
    // an outcome. The worker must outlive the scheduler so a killed scheduler
    // still leaves the run independently attributable.
    const worker = path.join(HERE, "fixture_worker.mjs")
    child = spawn(process.execPath, [worker, run.run_id, telemetryOut, outcomeOut, delay], { stdio: "ignore", detached: true, windowsHide: true })
  }
  const promise = new Promise((resolve) => child.on("exit", (code) => resolve({ exitCode: code })))
  return { promise, pid: child.pid }
}

async function runOne(stateDir, manifestFile, corpusFile, driver, run, resolvedOrphans) {
  const dirs = stateDirs(stateDir)
  await ensureDirs(stateDir)
  const corpus = await readJson(corpusFile)
  const ledger = await readLedger(stateDir)
  // The TERMINAL ledger record decides: last record for this run_id.
  const prior = [...ledger].reverse().find((l) => l.run_id === run.run_id)
  if (prior && prior.status === "COMPLETED") {
    console.log(`[scheduler] ${run.run_id} already complete - skip (no overwrite)`)
    return "skipped"
  }
  if (prior && prior.status === "STARTED") {
    if (resolvedOrphans.has(run.run_id)) {
      console.log(`[scheduler] ${run.run_id} orphan already resolved by recorder to excluded - terminal, skip`)
      return "skipped"
    }
    console.error(`[scheduler] ${run.run_id} was STARTED but never completed (schedule may have been killed). Refusing to rerun - run the recorder to resolve it.`)
    process.exit(1)
  }

  const attempt_id = randomUUID()
  const startedAt = new Date().toISOString()
  const scratch = await prepareRun(dirs.scratchDir, run, corpus)
  // Spawn FIRST so the worker outlives this process; the STARTED record is
  // appended only after the worker exists, carrying its pid. A scheduler that
  // dies mid-run therefore always leaves a run that demonstrably began.
  const { promise, pid } = spawnWorker(run, dirs, driver, scratch)
  const startRecord = {
    run_id: run.run_id, run_order: run.run_order, arm: run.arm,
    profile: run.profile, task_id: run.task_id, task_type: run.task_type,
    attempt_id, driver, framework_commit: frameworkCommit(), status: "STARTED", pid,
    started_at: startedAt, completed_at: null,
  }
  await appendLine(dirs.ledger, startRecord)
  const { exitCode } = await promise
  const settled = exitCode === 0 ? "COMPLETED" : "FAILED" // validity is the recorder's call, not the scheduler's
  await appendLine(dirs.ledger, { ...startRecord, status: settled, completed_at: new Date().toISOString() })
  console.log(`[scheduler] ${run.run_id} ${settled} (${driver})`)
  return settled
}

async function main() {
  const args = process.argv.slice(2)
  const get = (flag) => { const i = args.indexOf(flag); return i === -1 ? null : args[i + 1] }
  const stateDir = get("--state") || DEFAULTS.state
  const manifestFile = get("--manifest") || DEFAULTS.manifest
  const corpusFile = get("--corpus") || DEFAULTS.corpus
  const driver = get("--driver") || "fixture"
  const dryRun = args.includes("--dry-run")
  const runId = get("--run")
  const all = args.includes("--all")
  const resume = args.includes("--resume")
  if (!dryRun && !runId && !all && !resume) usage()
  const { manifest, corpus } = await loadManifestCorpus(manifestFile, corpusFile)
  const plan = buildPlan(manifest, corpus)
  const total = plan.total

  if (dryRun) {
    console.log(`[scheduler] DRY-RUN ${total} runs (${manifest.conditions[0].runs}x${manifest.conditions[0].id} ${manifest.conditions[1].runs}x${manifest.conditions[1].id}), manifest ${manifest.manifest_version}, corpus ${corpus.corpus_version}`)
    for (const r of plan.runs) console.log(`[scheduler]   ${r.run_id} arm=${r.arm} profile=${r.profile} task=${r.task_id} (${r.task_type})`)
    console.log(`[scheduler] dry-run writes nothing`)
    process.exit(0)
  }

  const ledger = await readLedger(stateDir)
  const completed = new Set(ledger.filter((l) => l.status === "COMPLETED").map((l) => l.run_id))
  const started = new Set(ledger.filter((l) => l.status === "STARTED" && !completed.has(l.run_id)).map((l) => l.run_id))
  const resolvedOrphans = new Set((await readExcluded(stateDir)).map((r) => r.run_id))

  let targets = plan.runs
  if (runId) targets = plan.runs.filter((r) => r.run_id === runId)
  if (resume) targets = plan.runs.filter((r) => !completed.has(r.run_id) && !resolvedOrphans.has(r.run_id))

  // Unresolved orphans must be resolved by the recorder, never rerun (would mask the kill).
  for (const t of targets) {
    if (started.has(t.run_id) && !resolvedOrphans.has(t.run_id)) {
      console.error(`[scheduler] ${t.run_id} is an UNRESOLVED orphan (STARTED, no terminal record). Refusing to rerun - run the recorder first.`)
      process.exit(1)
    }
  }

  let ran = 0
  for (const t of targets) {
    const outcome = await runOne(stateDir, manifestFile, corpusFile, driver, t, resolvedOrphans)
    if (outcome !== "skipped") ran++
  }
  console.log(`[scheduler] done: ${ran} scheduled, ${total - ran} pending`)
  process.exit(ran === 0 ? 3 : 0)
}

main().catch((e) => { console.error(`[scheduler] ${e.stack}`); process.exit(1) })
