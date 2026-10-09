// framework/experiments/experiment_state.mjs
// Shared state I/O for the scheduler -> recorder -> freeze -> comparator chain
// (P3 increment 3). All experiment state lives under one directory per run of
// the experiment (CLI --state, default framework/experiments/state). Records
// are append-only JSONL; the dataset and the ledger are never rewritten.
import { readFile, appendFile, mkdir } from "node:fs/promises"
import { createHash } from "node:crypto"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

export const LEDGER_FILE = "ledger/runs.jsonl"
export const DATASET_FILE = "dataset/runs.jsonl"
export const EXCLUDED_FILE = "dataset/excluded.jsonl"
export const FREEZE_FILE = "freeze.json"

export function stripBom(text) {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
}

export async function readJson(file) {
  const text = stripBom(await readFile(file, "utf8"))
  return JSON.parse(text)
}

export function sha256Hex(data) {
  return createHash("sha256").update(data).digest("hex")
}

// The framework (control-plane) commit under which a run executes. This is the
// provenance that ties an experiment run to the agent/skill/rule set that
// produced it - without it, a control-plane change between runs is invisible in
// the frozen dataset. Precedence: an explicit FRAMEWORK_COMMIT override
// (detached installs, tests), else the git HEAD of the repository containing
// this module. Returns null when neither is available: capture records an
// unknown, it never fabricates a version. Memoised - resolved at most once per
// process, so a 40-run schedule does not shell out 40 times.
let _frameworkCommit
export function frameworkCommit() {
  if (_frameworkCommit !== undefined) return _frameworkCommit
  const override = process.env.FRAMEWORK_COMMIT
  if (override && override.trim().length > 0) {
    _frameworkCommit = override.trim()
    return _frameworkCommit
  }
  try {
    const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
    const r = spawnSync("git", ["-C", repo, "rev-parse", "HEAD"], { encoding: "utf8" })
    if (r.status === 0 && typeof r.stdout === "string" && r.stdout.trim().length > 0) {
      _frameworkCommit = r.stdout.trim()
      return _frameworkCommit
    }
  } catch {
    // git unavailable - the commit is unknown, never fabricated
  }
  _frameworkCommit = null
  return _frameworkCommit
}

export function stateDirs(state) {
  return {
    ledgerDir: path.join(state, "ledger"),
    telemetryDir: path.join(state, "telemetry"),
    outcomesDir: path.join(state, "outcomes"),
    scratchDir: path.join(state, "scratch"),
    datasetDir: path.join(state, "dataset"),
    ledger: path.join(state, LEDGER_FILE),
    dataset: path.join(state, DATASET_FILE),
    excluded: path.join(state, EXCLUDED_FILE),
    freeze: path.join(state, FREEZE_FILE),
  }
}

export async function ensureDirs(state) {
  const d = stateDirs(state)
  for (const dir of [d.ledgerDir, d.telemetryDir, d.outcomesDir, d.scratchDir, d.datasetDir]) {
    await mkdir(dir, { recursive: true })
  }
}

export async function readLines(file) {
  try {
    const text = stripBom(await readFile(file, "utf8"))
    return text.split(/\r?\n/).filter((l) => l.trim().length > 0)
  } catch (e) {
    if (e.code === "ENOENT") return []
    throw e
  }
}

export async function readLedger(state) {
  const lines = await readLines(stateDirs(state).ledger)
  return lines.map((l) => JSON.parse(l))
}

export async function readDataset(state) {
  return (await readLines(stateDirs(state).dataset)).map((l) => JSON.parse(l))
}

export async function readExcluded(state) {
  return (await readLines(stateDirs(state).excluded)).map((l) => JSON.parse(l))
}

export async function appendLine(file, record) {
  await appendFile(file, JSON.stringify(record) + "\n", "utf8")
}

export async function loadManifestCorpus(manifestFile, corpusFile) {
  const [manifest, corpus] = await Promise.all([readJson(manifestFile), readJson(corpusFile)])
  if (!manifest || !corpus) throw new Error("state: manifest and corpus must both load")
  return { manifest, corpus }
}
