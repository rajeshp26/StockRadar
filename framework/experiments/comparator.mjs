// framework/experiments/comparator.mjs
// P3 increment 3 gate stub. The comparator is the ONLY component allowed to
// reveal/decode the frozen dataset. This stub enforces the boundary: before
// freeze.json exists it refuses with exit 2 (unverifiable - the dataset is
// not immutable evidence yet). The comparison itself (efficiency / work
// quality / process reliability, pilot interpretation rules) is P3 increment 4.
//
// Usage:
//   node comparator.mjs --compare [--state <dir>]
// Exit: 0 frozen dataset present (comparison pending increment 4) / 2 not frozen
import { stat } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { stateDirs } from "./experiment_state.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))

async function main() {
  const args = process.argv.slice(2)
  const get = (flag) => { const i = args.indexOf(flag); return i === -1 ? null : args[i + 1] }
  if (!args.includes("--compare")) { console.error(`[comparator] usage: node comparator.mjs --compare [--state <dir>]`); process.exit(2) }
  const stateDir = get("--state") || path.join(HERE, "state")
  const dirs = stateDirs(stateDir)
  try {
    const marker = JSON.parse(await (await import("node:fs/promises")).readFile(dirs.freeze, "utf8"))
    if (!marker.frozen) { console.error(`[comparator] freeze marker present but not frozen - refusing`); process.exit(2) }
    console.log(`[comparator] frozen dataset present (${marker.run_count} runs, sha256=${marker.dataset_checksum}).`)
    console.log(`[comparator] full A/B comparison is P3 increment 4; gate only here.`)
    process.exit(0)
  } catch (e) {
    console.error(`[comparator] dataset is NOT frozen - comparator operates only after freeze. (${e.code || e.message})`)
    process.exit(2)
  }
}

main().catch((e) => { console.error(`[comparator] ${e.stack}`); process.exit(1) })
