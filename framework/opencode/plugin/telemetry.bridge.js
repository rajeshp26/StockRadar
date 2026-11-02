// .opencode/plugins/telemetry.js
// BRIDGE -- not an implementation (validate.py fails discovery files that carry hooks).
//
// OpenCode v2 validates the DEFAULT export as a plugin definition: { id, setup } (or
// { id, effect }). The V1 envelope exported here -- { server: factory } -- was rejected with
// "Plugin must export a default definition with an id and an effect or setup function", so
// the collector never loaded and records.jsonl stopped growing on 2026-10-12. Only the export
// envelope changes; the collector itself still lives in exactly one place, telemetry.ts.
const path = require("node:path")
const IMPL = path.resolve(__dirname, "../../framework/opencode/plugin/telemetry.ts")
const mod = require(IMPL)
const definition = mod && mod.default && typeof mod.default.setup === "function" ? mod.default : null
if (!definition) {
  throw new TypeError(
    "telemetry bridge: " + IMPL + " must default-export a v2 plugin definition { id, setup }",
  )
}
module.exports = definition
