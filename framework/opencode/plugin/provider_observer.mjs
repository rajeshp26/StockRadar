// framework/opencode/plugin/provider_observer.mjs
//
// Producer + enforcement point for the provider health ledger (framework/providers/healthcheck.py).
//
// Facts (verified in the tree this was written against):
//   * healthcheck.py has a classifier, a ledger, and a pre-flight (`check`, gate g12) -- but nothing
//     ever WROTE to the ledger after 2026-09-06 (one hand-written record), although spawned
//     sessions kept dying on "Insufficient credits". g12 therefore kept reporting a healthy provider.
//   * team-lead.md:211 makes the pre-flight a declared obligation; nothing enforced it, and the
//     sessions in question run as Sisyphus, which team-lead.md does not govern.
//   * telemetry.ts handled no `session.error` event. The SDK types a session.error with a
//     structured `error` (ApiError | ProviderAuthError | UnknownError | ...).
//
// What it does:
//   onParams(input)       remember which provider/model each session is using (chat.params)
//   onEvent(event)        on session.error: forward the error text to `healthcheck.py observe`,
//                         which classifies with the EXISTING lexer and records only blocking
//                         provider classes
//   beforeTool(input)     OPT-IN (PROVIDER_PREFLIGHT=1): before a `task` dispatch run
//                         `healthcheck.py check`; exit 1 (a named blocking failure) throws, which
//                         refuses the dispatch. Any other outcome (0, or 2/4 = could not determine)
//                         lets it proceed and is logged -- decision D6 in PR-D1c RECORD.md.
//
// Never throws from onParams/onEvent. No regexes of its own: classification is healthcheck.py's.

export const PREFLIGHT_ENV = "PROVIDER_PREFLIGHT"

export function errorText(error) {
  if (!error || typeof error !== "object") return ""
  const d = error.data && typeof error.data === "object" ? error.data : {}
  return [error.name, d.message, d.statusCode, typeof d.responseBody === "string" ? d.responseBody : ""]
    .filter((x) => x !== undefined && x !== null && String(x).trim() !== "")
    .join(" ")
    .slice(0, 1000)
}

/**
 * @param {object} o
 * @param {(cmd:"observe"|"check", a?:{error:string, provider:string, model:string}) => Promise<{exitCode:number, stdout:string, stderr?:string}>} o.run
 */
export function createProviderObserver({ run, env = process.env, log = (m) => process.stderr.write(m + "\n") } = {}) {
  if (typeof run !== "function") throw new Error("createProviderObserver: run() is required")
  const sessions = new Map() // sessionID -> { provider, model }

  return {
    onParams(input) {
      try {
        const sid = input?.sessionID
        const provider = input?.provider?.providerID ?? input?.provider?.id ?? ""
        const model = input?.model?.modelID ?? input?.model?.id ?? ""
        if (sid && model) sessions.set(sid, { provider: String(provider || "unknown"), model: provider ? `${provider}/${model}` : String(model) })
      } catch (e) { log(`[provider-observer] onParams: ${e?.message ?? e}`) }
    },

    async onEvent(event) {
      try {
        if (event?.type !== "session.error") return
        const err = event?.properties?.error
        const text = errorText(err)
        if (!text) return
        const known = sessions.get(event?.properties?.sessionID)
        const provider = known?.provider ?? err?.data?.providerID ?? "unknown"
        const model = known?.model ?? "unknown"
        const r = await run("observe", { error: text, provider, model })
        if (!r || r.exitCode !== 0) log(`[provider-observer] observe exited ${r?.exitCode}: ${String(r?.stderr ?? r?.stdout ?? "").slice(0, 200)}`)
      } catch (e) { log(`[provider-observer] onEvent: ${e?.message ?? e}`) }
    },

    async beforeTool(input) {
      if (env[PREFLIGHT_ENV] !== "1" || input?.tool !== "task") return
      let r
      try { r = await run("check") } catch (e) { log(`[provider-observer] preflight could not run: ${e?.message ?? e}`); return }
      if (r?.exitCode === 1) {
        throw new Error(
          "NO TASK DISPATCH: provider pre-flight failed (healthcheck.py check exit 1). " +
          String(r.stdout ?? "").slice(0, 600) +
          " Fix the provider (credits/key/model) or record a later OK; do not retry the dispatch.")
      }
      if (r?.exitCode !== 0) log(`[provider-observer] preflight UNVERIFIED (exit ${r?.exitCode}); dispatch allowed`)
    },
  }
}
