// framework/experiments/run_experiment.mjs
// P2/P3 experiment controller: attribution-gated A/B model-profile comparison,
// with mechanical per-run RUN_VALIDITY classification (DID-009).
//
// The experiment measures token spend and rework between the `baseline` and
// `tiered` profiles in framework/models/profiles.sh over comparable work. The
// report that comparison depends on is only trustworthy if the telemetry
// collector attributes every unit to the correct agent, so this controller
// REFUSES to schedule unless the attribution metric passes. That refusal is a
// hard gate (exit 2), not a warning. Per-run validity is mechanical
// (run_validity.mjs): no run enters a dataset as VALID unless captured facts
// say so, and validity never reads comparison metrics.
//
// Modes:
//   node framework/experiments/run_experiment.mjs --dry-run
//     validate manifest + attribution preflight only; writes nothing
//   node framework/experiments/run_experiment.mjs --check-run <record.json>
//     classify one fabricated/recorded run via RUN_VALIDITY; no scheduling
//   node framework/experiments/run_experiment.mjs --encode-dataset <in.json> <out.json>
//     blind an explicit-arm dataset (arm -> opaque arm_token), key from
//     EXPERIMENT_SECRET env; the FROZEN artifact is the encoded output
//   node framework/experiments/run_experiment.mjs --reveal-dataset <in.json> <out.json>
//     restore arms from a blinded dataset (freeze must already have happened);
//     tampered or wrong-key input exits 1, never a wrong answer
//   node framework/experiments/run_experiment.mjs
//     schedule 20xA / 20xB (not yet implemented)
//
// Exit codes:
//   0  dry-run validated, check-run VALID, encode/reveal written, or
//      experiment complete
//   1  manifest invalid, check-run classified INVALID/INCOMPLETE/ABORTED, or
//      encode/reveal rejected tampered/wrong-key input
//   2  attribution preflight FAILED - collector not trustworthy, do not
//      schedule (also: unreadable/undecodable input, missing EXPERIMENT_SECRET)
//   3  real scheduling not yet implemented (blinding + 20x20 are later
//      increments per P3-EXPERIMENT-INTEGRITY)
//
// Dry-run and check-run write nothing; encode/reveal write exactly one file.
import { readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { runAttributionSuite } from "../../.opencode/plugin/attribution_harness.mjs"
import { classifyRun, STATUS } from "./run_validity.mjs"
import { encodeDataset, revealDataset, deriveKey } from "./blinding.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const MANIFEST = path.join(HERE, "manifest.json")
const BLIND_SALT = "stockerpro-p3-experiment"

function fail(code, msg) {
  console.error(`[experiment] ${msg}`)
  process.exit(code)
}

function stripBom(text) {
  return text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text
}

function validateManifest(m) {
  if (!m || typeof m !== "object") return "manifest is not an object"
  if (!Array.isArray(m.conditions) || m.conditions.length !== 2) return "manifest.conditions must have exactly 2 entries"
  const ids = m.conditions.map((c) => c.id)
  if (ids.join(",") !== "A,B") return "conditions must be A then B"
  for (const c of m.conditions) {
    if (!Number.isInteger(c.runs) || c.runs < 1) return `condition ${c.id} has invalid runs`
    if (typeof c.profile !== "string" || c.profile.length === 0) return `condition ${c.id} has no profile`
  }
  return null
}

async function preflight(seed) {
  const res = await runAttributionSuite({ seed })
  return { ok: res.exitCode === 0, res }
}

async function checkRun(file) {
  let text
  try {
    text = stripBom(await readFile(file, "utf8"))
  } catch (e) {
    fail(2, `cannot read run record ${file}: ${e.message}`)
  }
  let rec
  try {
    rec = JSON.parse(text)
  } catch (e) {
    fail(2, `cannot parse run record ${file}: ${e.message}`)
  }
  const v = classifyRun(rec)
  console.log(`[run-validity] ${v.status}`)
  for (const r of v.reasons) console.log(`[run-validity]   ${r.code}${r.detail ? ": " + r.detail : ""}`)
  console.log(v.status === STATUS.VALID ? "[run-validity] eligible for the experiment dataset" : "[run-validity] excluded from the experiment dataset (never back-corrected)")
  process.exit(v.status === STATUS.VALID ? 0 : 1)
}

async function blindingMode(kind) {
  const inIdx = process.argv.indexOf(kind)
  const inFile = process.argv[inIdx + 1]
  const outFile = process.argv[inIdx + 2]
  const secret = process.env.EXPERIMENT_SECRET
  if (!inFile || !outFile) fail(2, `${kind} requires <in.json> <out.json>`)
  if (!secret || secret.length === 0) fail(2, `${kind} requires EXPERIMENT_SECRET env (base64 from blinding.generateSecret)`)
  let text
  try {
    text = stripBom(await readFile(inFile, "utf8"))
  } catch (e) {
    fail(2, `cannot read ${inFile}: ${e.message}`)
  }
  let data
  try {
    data = JSON.parse(text)
  } catch (e) {
    fail(2, `cannot parse ${inFile}: ${e.message}`)
  }
  const key = deriveKey(secret, BLIND_SALT)
  try {
    const out = kind === "--encode-dataset" ? encodeDataset(key, data) : revealDataset(key, data)
    await writeFile(outFile, JSON.stringify(out, null, 2) + "\n", "utf8")
    console.log(`[blinding] ${kind === "--encode-dataset" ? "encoded (arms hidden)" : "revealed (arms restored)"} -> ${outFile}`)
    process.exit(0)
  } catch (e) {
    fail(1, `${kind} rejected input: ${e.message}`)
  }
}

async function main() {
  const dryRun = process.argv.includes("--dry-run")
  const crIdx = process.argv.indexOf("--check-run")
  if (crIdx !== -1) {
    const file = process.argv[crIdx + 1]
    if (!file) fail(2, "--check-run requires a JSON record file path")
    await checkRun(file)
  }
  for (const kind of ["--encode-dataset", "--reveal-dataset"]) {
    if (process.argv.includes(kind)) await blindingMode(kind)
  }

  let manifest
  try {
    manifest = JSON.parse(stripBom(await readFile(MANIFEST, "utf8")))
  } catch (e) {
    fail(1, `cannot read manifest: ${e.message}`)
  }
  const invalid = validateManifest(manifest)
  if (invalid) fail(1, `manifest invalid: ${invalid}`)

  const pf = await preflight(manifest.seed)
  if (!pf.ok) {
    fail(2, `attribution preflight FAILED: exit=${pf.res.exitCode} accuracy=${pf.res.accuracy} units=${pf.res.totalUnits}`)
  }

  const plan = manifest.conditions.map((c) => `${c.id} (${c.label}) x ${c.runs} runs, profile=${c.profile}`).join(" | ")
  if (dryRun) {
    console.log(`[experiment] DRY-RUN ok: manifest valid, attribution preflight PASS (accuracy=${pf.res.accuracy}, units=${pf.res.totalUnits})`)
    console.log(`[experiment] would schedule: ${plan}`)
    console.log(`[experiment] nothing written`)
    process.exit(0)
  }
  console.error(`[experiment] real scheduling (blinding + 20x20) is a later P3 increment; run with --dry-run, --check-run, --encode-dataset or --reveal-dataset`)
  process.exit(3)
}

main().catch((e) => fail(1, `unhandled error: ${e.stack}`))
