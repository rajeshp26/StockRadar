// framework/experiments/freeze.mjs
// P3 increment 3 - the explicit, immutable experiment freeze. Freeze is the
// boundary after which the comparator may operate: the frozen artifact is the
// blinded dataset plus a marker that pins manifest/corpus version, run count,
// checksum and timestamp. Freeze is refused until the experiment is COMPLETE
// (every planned run present and VALID in the dataset - excluded runs are not
// part of the eligible population), and it refuses a dataset that leaks a
// plaintext arm. freeze.json is written exactly once; a second freeze fails.
//
// Usage:
//   node freeze.mjs --freeze [--state <dir>] [--manifest <f>] [--corpus <f>]
// Exit: 0 frozen / 1 cannot freeze (incomplete, tampered, or already frozen) /
//       2 usage
import { writeFile, stat } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { buildPlan } from "./plan.mjs"
import {
  stateDirs, ensureDirs, readDataset, loadManifestCorpus, sha256Hex, readLines,
} from "./experiment_state.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DEFAULTS = { state: path.join(HERE, "state"), manifest: path.join(HERE, "manifest.json"), corpus: path.join(HERE, "corpus.json") }

function fail(msg) {
  console.error(`[freeze] ${msg}`)
  process.exit(1)
}

async function freeze(stateDir, manifestFile, corpusFile) {
  const { manifest, corpus } = await loadManifestCorpus(manifestFile, corpusFile)
  const plan = buildPlan(manifest, corpus)
  const dirs = stateDirs(stateDir)
  await ensureDirs(stateDir)

  // Immutable: a freeze already exists.
  try {
    await stat(dirs.freeze)
    fail("already frozen - freeze.json exists; the dataset is immutable")
  } catch (e) {
    if (e.code !== "ENOENT") throw e
  }

  // Completeness: every planned run must be present and VALID in the dataset.
  const dataset = await readDataset(stateDir)
  const datasetIds = new Set(dataset.map((r) => r.run_id))
  const plannedIds = new Set(plan.runs.map((r) => r.run_id))
  const missing = plan.runs.filter((r) => !datasetIds.has(r.run_id)).map((r) => r.run_id)
  const extra = dataset.filter((r) => !plannedIds.has(r.run_id)).map((r) => r.run_id)
  if (missing.length > 0) fail(`incomplete: ${missing.length} planned runs missing from the dataset (${missing.slice(0, 5).join(", ")}...)`)
  if (extra.length > 0) fail(`dataset contains runs outside the plan (${extra.join(", ")})`)
  if (dataset.length !== plan.total) fail(`incomplete: dataset has ${dataset.length} runs, plan requires ${plan.total}`)

  // No plaintext arm may survive anywhere in the frozen dataset.
  const raw = await readLines(dirs.dataset)
  for (const line of raw) {
    if (/"arm"\s*:/.test(line)) fail("dataset leaks a plaintext arm - refusing to freeze")
    if (!/"arm_token"/.test(line)) fail("dataset record without arm_token - refusing to freeze")
  }
  const checksum = sha256Hex(raw.join("\n"))

  const marker = {
    frozen: true,
    frozen_at: new Date().toISOString(),
    manifest_version: manifest.manifest_version,
    corpus_version: corpus.corpus_version,
    run_count: dataset.length,
    dataset_file: "dataset/runs.jsonl",
    dataset_checksum: checksum,
    note: "freeze is the immutable boundary; comparator operates only after this marker exists",
  }
  await writeFile(dirs.freeze, JSON.stringify(marker, null, 2) + "\n", "utf8")
  console.log(`[freeze] FROZEN ${dataset.length} runs, manifest ${manifest.manifest_version}, corpus ${corpus.corpus_version}, sha256=${checksum}`)
  return marker
}

async function main() {
  const args = process.argv.slice(2)
  const get = (flag) => { const i = args.indexOf(flag); return i === -1 ? null : args[i + 1] }
  if (!args.includes("--freeze")) { console.error(`[freeze] usage: node freeze.mjs --freeze [--state <dir>] [--manifest <f>] [--corpus <f>]`); process.exit(2) }
  const stateDir = get("--state") || DEFAULTS.state
  const manifestFile = get("--manifest") || DEFAULTS.manifest
  const corpusFile = get("--corpus") || DEFAULTS.corpus
  await freeze(stateDir, manifestFile, corpusFile)
  process.exit(0)
}

main().catch((e) => { console.error(`[freeze] ${e.stack}`); process.exit(1) })
