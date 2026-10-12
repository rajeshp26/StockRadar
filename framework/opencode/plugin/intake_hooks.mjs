// framework/opencode/plugin/intake_hooks.mjs
//
// DID-012 Pillar 1 -- the PRODUCER and the CONSUMER of the durable ASK record.
//
// Why this file exists (facts, each verified in the tree this was written against):
//   * framework/adapters/intake.py (PR-D1) can fold an ASK log into derived state, but
//     nothing ever called its `capture` command: DID-012 section 3.5 requires "a hook in
//     the plugin layer ... not the model" to write the ASK, and no such hook existed
//     (telemetry.ts registered only `chat.params` and `event`). No asks.jsonl existed.
//   * DID-012 section 4.5 requires context to be "a cache of durable state, not the state
//     itself". Nothing rendered the ASK record back into the model's context, so after a
//     compaction the model's memory of the user's ask was whatever it chose to summarise.
//
// What it does:
//   chat.message                          -> capture each real user message verbatim
//   experimental.chat.system.transform    -> every model request, state the open ASKs
//   experimental.session.compacting       -> hand the open ASKs to the summariser too
//   onEvent(session.created)              -> remember which sessions are delegations
//
// What it deliberately does NOT do:
//   * It never classifies, summarises, splits or judges a message. Capture is
//     deterministic and verbatim (DID-012 3.1/3.5, non-goal 1.5: no regex heuristics).
//   * It never writes a status. The adapter allocates the id and establishes CAPTURED
//     (invariant I8). Closing an ASK is not this module's act.
//   * It never throws into the host. A failed capture is COUNTED and SHOWN in the next
//     injection -- never swallowed silently (DID-012 5.6: never convert uncertainty into
//     success).
//
// OPT-IN. Capture is gated by INTAKE_CAPTURE=1 because the granularity question
// (is every user message an ASK?) is an open decision recorded in
// .planning/patches/PR-D1b/RECORD.md. Disabled, every hook is a no-op.
//
// Plain ESM, no dependencies: runs under `node --test` with the real adapter.

export const CAPTURE_ENV = "INTAKE_CAPTURE"
export const DEFAULT_MAX_BLOCK_CHARS = 6000
export const DEFAULT_MAX_ASK_CHARS = 1500
export const DEFAULT_TTL_MS = 5000

const ADAPTER = "python3 framework/adapters/intake.py"

/** Verbatim text of the user's own parts: not synthetic (auto-continue, injected), not ignored. */
export function userAskText(parts) {
  if (!Array.isArray(parts)) return ""
  return parts
    .filter(
      (p) =>
        p &&
        p.type === "text" &&
        !p.synthetic &&
        !p.ignored &&
        typeof p.text === "string" &&
        p.text.trim() !== "",
    )
    .map((p) => p.text)
    .join("\n\n")
}

/** Render open asks as a bounded, deterministic block. Same input -> same output (I10). */
export function renderOpenAsks(asks, { maxBlockChars = DEFAULT_MAX_BLOCK_CHARS, maxAskChars = DEFAULT_MAX_ASK_CHARS } = {}) {
  const lines = [
    "OPEN USER ASKS - durable record (framework/adapters/intake.py). The conversation is not the source of truth.",
    "None of these has terminated. Only the user, or a recorded verified outcome, may mark one COMPLETED, DEFERRED or REJECTED; do not drop, narrow or reorder them yourself.",
    "",
  ]
  let used = lines.join("\n").length
  let shown = 0
  for (const a of asks) {
    let text = String(a.original_text ?? "")
    let cut = ""
    if (text.length > maxAskChars) {
      text = text.slice(0, maxAskChars)
      cut = `\n  [truncated; full text: ${ADAPTER} show --id ${a.ask_id}]`
    }
    const entry =
      `${a.ask_id} [${a.status}] captured ${a.created_at ?? "?"}\n` +
      text.split("\n").map((l) => `  > ${l}`).join("\n") +
      cut
    if (shown > 0 && used + entry.length + 1 > maxBlockChars) {
      lines.push(`[+${asks.length - shown} more open asks not shown: ${ADAPTER} open]`)
      return lines.join("\n")
    }
    lines.push(entry)
    used += entry.length + 1
    shown++
  }
  return lines.join("\n")
}

/**
 * @param {object}   o
 * @param {(cmd: "capture"|"open", json?: string) => Promise<{exitCode:number, stdout:string, stderr?:string}>} o.run
 * @param {Record<string,string|undefined>} [o.env]
 * @param {() => number} [o.now]
 * @param {(msg: string) => void} [o.log]
 */
export function createIntakeHooks({
  run,
  env = process.env,
  now = Date.now,
  log = (m) => process.stderr.write(m + "\n"),
  ttlMs = DEFAULT_TTL_MS,
  maxBlockChars = DEFAULT_MAX_BLOCK_CHARS,
  maxAskChars = DEFAULT_MAX_ASK_CHARS,
} = {}) {
  if (typeof run !== "function") throw new Error("createIntakeHooks: run() is required")

  const enabled = () => env[CAPTURE_ENV] === "1"
  const seen = new Set()
  const children = new Set()
  const roots = new Set()
  const failures = { count: 0, last: "" }
  let cache = null // { at, asks }

  const fail = (what) => {
    failures.count++
    failures.last = String(what).slice(0, 300)
    log(`[intake] ${failures.last}`)
  }

  async function fetchOpen() {
    if (cache && now() - cache.at < ttlMs) return { ok: true, asks: cache.asks }
    const r = await run("open")
    if (!r || r.exitCode !== 0) {
      return { ok: false, detail: `open exited ${r?.exitCode}: ${String(r?.stderr ?? r?.stdout ?? "").slice(0, 200)}` }
    }
    let asks
    try {
      asks = JSON.parse(r.stdout)
      if (!Array.isArray(asks)) throw new Error("not a list")
    } catch (e) {
      return { ok: false, detail: `open returned unparseable output: ${e.message}` }
    }
    cache = { at: now(), asks }
    return { ok: true, asks }
  }

  async function block() {
    const parts = []
    if (failures.count > 0) {
      parts.push(
        `INTAKE CAPTURE FAILED ${failures.count} time(s) this process; last: ${failures.last}. ` +
          "Messages whose capture failed are NOT in the durable record.",
      )
    }
    const r = await fetchOpen()
    if (!r.ok) {
      parts.push(
        `INTAKE STORE UNREADABLE (${r.detail}). Do not assume there are no open asks; ` +
          `read them with: ${ADAPTER} open`,
      )
    } else if (r.asks.length > 0) {
      parts.push(renderOpenAsks(r.asks, { maxBlockChars, maxAskChars }))
    }
    return parts.length ? parts.join("\n\n") : null
  }

  const isChild = (sid) => !!sid && children.has(sid)

  return {
    /** Feed every host event through here; only session.created matters. */
    onEvent(event) {
      try {
        if (event?.type !== "session.created") return
        const info = event?.properties?.info
        if (!info?.id) return
        if (info.parentID) children.add(info.id)
        else roots.add(info.id)
      } catch (e) {
        fail(`onEvent: ${e?.message ?? e}`)
      }
    },

    hooks: {
      "chat.message": async (input, output) => {
        try {
          if (!enabled()) return
          const sid = input?.sessionID ?? output?.message?.sessionID
          const mid = input?.messageID ?? output?.message?.id
          if (!sid) return fail("chat.message without a sessionID; cannot bind an ASK")
          if (isChild(sid)) return // a delegation prompt, not a user ask
          const text = userAskText(output?.parts)
          if (!text) return
          const key = `${sid}:${mid ?? text}`
          if (seen.has(key)) return
          seen.add(key)
          const payload = {
            session_id: sid,
            source: "user",
            emitter: "intake-hook",
            original_text: text,
            provenance: {
              session: sid,
              message_id: mid ?? null,
              agent: input?.agent ?? output?.message?.agent ?? null,
              parent_known: roots.has(sid),
            },
          }
          const r = await run("capture", JSON.stringify(payload))
          if (!r || r.exitCode !== 0) {
            return fail(`capture exited ${r?.exitCode}: ${String(r?.stderr ?? r?.stdout ?? "").slice(0, 200)}`)
          }
          cache = null // our own write changed the record
        } catch (e) {
          fail(`chat.message: ${e?.message ?? e}`)
        }
      },

      "experimental.chat.system.transform": async (input, output) => {
        try {
          if (!enabled() || isChild(input?.sessionID)) return
          const b = await block()
          if (b) output.system.push(b)
        } catch (e) {
          fail(`system.transform: ${e?.message ?? e}`)
        }
      },

      "experimental.session.compacting": async (input, output) => {
        try {
          if (!enabled() || isChild(input?.sessionID)) return
          const b = await block()
          if (b) output.context.push("Carry these into the summary verbatim:\n" + b)
        } catch (e) {
          fail(`compacting: ${e?.message ?? e}`)
        }
      },
    },
  }
}
