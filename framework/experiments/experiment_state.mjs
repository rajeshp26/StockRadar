// framework/experiments/experiment_state.mjs
// Shared state I/O for the scheduler -> recorder -> freeze -> comparator chain
// (P3 increment 3). All experiment state lives under one directory per run of
// the experiment (CLI --state, default framework/experiments/state). Records
// are append-only JSONL; the dataset and the ledger are never rewritten.
import { readFile, appendFile, mkdir } from "node:fs/promises"
import { createHash } from "node:crypto"
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
