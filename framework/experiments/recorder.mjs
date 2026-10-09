// framework/experiments/recorder.mjs
// P3 increment 3 - the recorder determines validity. It reconciles three
// sources that must agree (P3 doc hierarchy):
//   manifest (specification) + scheduler ledger (execution record)
//   + telemetry (evidence of what actually happened)
// and for each run builds a capture record, scores RUN_VALIDITY mechanically,
// and persists ONLY the blinded form (arm -> arm_token). The plaintext arm
// exists only transiently in this process - never on disk.
//
// Outputs (append-only, under state/):
//   dataset/runs.jsonl     VALID runs, blinded (the future frozen dataset)
//   dataset/excluded.jsonl every non-VALID run, blinded, with machine reasons
// A run is written at most once: already-present run_ids are skipped, so
// re-running the recorder is idempotent and duplicate run IDs are rejected.
// Invalid runs can never enter the valid population; they are never
// back-corrected.
//
// Ledger semantics: a run has a STARTED record and (for completed runs) a
// terminal COMPLETED/FAILED record. The TERMINAL record (last for the
// run_id) decides supervision: completed -> no gap, STARTED-only -> gap.
// An orphan therefore resolves deterministically to a non-valid state -
// SUPERVISION_GAP or a missing telemetry fact - never to VALID, and never
// disappears.
//
// Usage:
//   node recorder.mjs --reconcile [--state <dir>] [--manifest <f>]
//     [--corpus <f>]
//   env EXPERIMENT_SECRET   base64 secret for blinding (required)
// Exit: 0 ok / 1 error / 2 usage / 3 nothing to reconcile
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { buildPlan } from "./plan.mjs"
import { classifyRun, STATUS } from "./run_validity.mjs"
import { encodeRun, deriveKey } from "./blinding.mjs"
import {
  stateDirs, ensureDirs, readLedger, readDataset, readExcluded,
  appendLine, loadManifestCorpus,
} from "./experiment_state.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DEFAULTS = {
  state: path.join(HERE, "state"),
  manifest: path.join(HERE, "manifest.json"),
  corpus: path.join(HERE, "corpus.json"),
}
// Must match run_experiment.mjs --encode-dataset so artifacts are interchangeable.
const BLIND_SALT = "stockerpro-p3-experiment"

function usage(msg) {
  if (msg) console.error(`[recorder] ${msg}`)
  console.error(`[recorder] usage: node recorder.mjs --reconcile [--state <dir>] [--manifest <f>] [--corpus <f>]`)
  process.exit(2)
}

async function readTelemetry(dirs, runId) {
  try {
    return JSON.parse(await readFile(path.join(dirs.telemetryDir, `${runId}.json`), "utf8"))
  } catch {
    return null
  }
}

async function readOutcome(dirs, runId) {
  try {
    return JSON.parse(await readFile(path.join(dirs.outcomesDir, `${runId}.json`), "utf8"))
  } catch {
    return null
  }
}

async function reconcile(stateDir, manifestFile, corpusFile) {
  const secret = process.env.EXPERIMENT_SECRET
  if (!secret || secret.length === 0) throw new Error("recorder: EXPERIMENT_SECRET env is required (blinding key)")
  const { manifest, corpus } = await loadManifestCorpus(manifestFile, corpusFile)
  const plan = buildPlan(manifest, corpus)
  const dirs = stateDirs(stateDir)
  await ensureDirs(stateDir)
  const key = deriveKey(secret, BLIND_SALT)

  const ledger = await readLedger(stateDir)
  const done = new Set([...await readDataset(stateDir), ...await readExcluded(stateDir)].map((r) => r.run_id))
  let recorded = 0
  let excluded = 0

  for (const run of plan.runs) {
    if (done.has(run.run_id)) continue // idempotent: never rewrite an already-recorded run
    // The TERMINAL ledger record decides supervision: last record for the run.
    const led = [...ledger].reverse().find((l) => l.run_id === run.run_id)
    if (!led) continue // not yet scheduled - nothing to reconcile

    const tele = await readTelemetry(dirs, run.run_id)
    const outcome = await readOutcome(dirs, run.run_id)

    // Capture record: every field a mechanical validator needs, sourced from
    // the ledger (execution) and telemetry (evidence). Metrics ride along so
    // the frozen dataset carries the comparison inputs.
    const capture = {
      run_id: run.run_id,
      arm: run.arm,
      task_id: run.task_id,
      session_id: tele ? tele.session_id : null,
      attempt_id: led.attempt_id,
      framework_commit: led.framework_commit ?? null,
      seed: manifest.seed,
      run_order: run.run_order,
      model_requested: tele ? tele.model_requested : null,
      model_resolved: tele ? tele.model_resolved : null,
      resolved_provider: tele ? tele.resolved_provider : null,
      runtime_version: tele ? tele.runtime_version : null,
      agent_profile: run.profile,
      attribution_status: tele ? tele.attribution_status : "missing",
      supervision_gap: led.status !== "COMPLETED",
      gates_observable: tele ? tele.gates_observable === true : false,
      outcome_produced: outcome ? outcome.produced === true : false,
      infra_violation: tele ? tele.infra_violation === true : false,
      tokens: tele ? tele.tokens : null,
      fresh_tokens: tele ? tele.fresh_tokens : null,
      tool_calls: tele ? tele.tool_calls : null,
      retries: tele ? tele.retries : null,
      rework: tele ? tele.rework : null,
      elapsed_time: tele ? tele.elapsed_time : null,
      gates: tele && tele.gates ? tele.gates : [],
      defects: tele ? tele.defects : null,
    }

    const v = classifyRun(capture)
    const token = encodeRun(key, run.run_id, run.arm)
    const { arm, ...rest } = capture
    const blinded = { ...rest, arm_token: token, run_status: v.status }
    if (v.status === STATUS.VALID) {
      await appendLine(dirs.dataset, { ...blinded, validity: { status: v.status, reasons: [] } })
      recorded++
      console.log(`[recorder] ${run.run_id} VALID -> dataset`)
    } else {
      await appendLine(dirs.excluded, { ...blinded, validity: { status: v.status, reasons: v.reasons } })
      excluded++
      console.log(`[recorder] ${run.run_id} ${v.status} -> excluded (${v.reasons.map((r) => r.code).join(",")})`)
    }
  }
  console.log(`[recorder] reconcile done: ${recorded} valid, ${excluded} excluded`)
  return { recorded, excluded }
}

async function main() {
  const args = process.argv.slice(2)
  const get = (flag) => { const i = args.indexOf(flag); return i === -1 ? null : args[i + 1] }
  if (!args.includes("--reconcile")) usage()
  const stateDir = get("--state") || DEFAULTS.state
  const manifestFile = get("--manifest") || DEFAULTS.manifest
  const corpusFile = get("--corpus") || DEFAULTS.corpus
  const r = await reconcile(stateDir, manifestFile, corpusFile)
  process.exit(r.recorded + r.excluded === 0 ? 3 : 0)
}

main().catch((e) => { console.error(`[recorder] ${e.stack}`); process.exit(1) })
