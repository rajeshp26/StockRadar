import type { Plugin } from "@opencode-ai/plugin"
import { spawnSync } from "node:child_process"
import { resolveExecutionAgent, createStack, normalizeTaskArgs, createFlushGuard } from "./envelope.mjs"
import { EVENTS, createAttemptRegistry, taxonomyEvent, parseSignals, extractExitCode, isPollOutput } from "./taxonomy.mjs"
import { parseGateRequired, parseGateExecutionStarted, parseGateLaunch, parseGateLine } from "./gates.mjs"
import { createIntakeHooks } from "./intake_hooks.mjs"
import { createProviderObserver } from "./provider_observer.mjs"

/**
 * Telemetry collector. Lifecycle-series per session (started/heartbeat/final), appended
 * through the state adapter. The report collapses each series to one record (last wins).
 *
 * WHY THIS SHAPE: OpenCode prunes old tool outputs and auto-compacts. Anything not written
 * to disk during the run is unrecoverable afterwards, so every counter is flushed to state
 * rather than held for a final summary.
 *
 * EXECUTION ENVELOPE (P0-2, §4): agent/task attribution flows through a hook-layer
 * delegation stack (envelope.mjs), not a single mutable current_agent string. The task
 * tool pushes a frame on tool.execute.before and pops it on tool.execute.after; chat.params
 * and message.updated attribute to top-of-stack; background tasks snapshot the execution
 * agent at launch. rec.current_agent mirrors the stack top so existing agent() default
 * semantics keep working. The stack is the NEW authoritative source.
 *
 * HOOK CONTRACT: `session.idle` is an EVENT TYPE delivered through the `event` hook, not a
 * hook key. A previous version registered "session.idle" as a top-level key; it never fired,
 * so no record was ever written. Keep the `event` indirection.
 *
 * DEFENSIVE READS: field paths differ across OpenCode versions. Every extraction tries
 * several shapes and falls back to 0/unknown rather than throwing. A collector that crashes
 * takes the session's measurements with it.
 */
export const TelemetryPlugin: Plugin = async ({ $ }) => {
  const now = () => Date.now()

  const zeroTok = () => ({ input: 0, output: 0, reasoning: 0, cache_read: 0, cache_write: 0 })

  const rec: any = {
    // P0-1 (§8): record_version 2 → 3. Additive taxonomy fields only
    // (taxonomy_events, envelope.attempt_id); every v2 field is retained.
    record_version: 3,
    session_id: "",
    task_id: process.env.TASK_ID ?? "",
    started: now(),
    // Per-agent attribution is the point of the whole record: it answers "which agent is
    // spending the tokens", which is the input to per-agent model assignment.
    agents: {} as Record<string, any>,
    current_agent: "team-lead",
    tokens: zeroTok(),
    models_seen: {} as Record<string, number>,
    tools: {} as Record<string, { count: number; ms: number; fail: number }>,
    gates: {} as Record<string, { result: string; ms: number; exit: number; evidence?: string }>,
    skills_loaded: new Set<string>(),
    graph_queries: 0,
    fallbacks_used: 0,
    provider_tier: null as number | null,
    files_read: 0,
    context_expansions: 0,
    materialised_chars: 0,
    truncations: 0,
    retries: {} as Record<string, number>,
    // P0-1 canonical taxonomy (§3): raw events only — no derived counters in
    // the collector. Derived rework metrics live in report.py. attempt_id is
    // assigned by the runtime attempt registry (single authoritative owner, §4).
    taxonomy_events: [] as any[],
    defect_escapes: 0,
    retros_recorded: 0,
    retro_recurrences: 0,
    retro_fix_targets: [] as string[],
    human_gates: [] as string[],
    // Blocker escalation (G8). g8 refuses completion while any record stays open,
    // so these counters mirror open escalation debt rather than activity.
    blockers_opened: 0,
    blockers_resolved: 0,
    blocker_signals: [] as string[],
    worker_tasks_registered: 0,
    worker_events_written: 0,
    worker_stalls_detected: 0,
    // Claim provenance (G11): ledger appends, and invalid-claim gate verdicts.
    claims_recorded: 0,
    claims_invalid: 0,
    // Background task contract (OMO): fire in background, END the response, wait for the
    // system-reminder, then collect with background_output. Polling before the notification
    // is the anti-pattern this framework now measures. Every extra pre-notification call is
    // a poll; a collect-only call (after notification, output shows completion) is not.
    bg_tasks: {} as Record<string, { launched: number; polls: number; collects: number; cancelled: number }>,
    bg_poll_total: 0,
    seen_msg: {} as Record<string, any>,
  }

  // Execution envelope (§4): hook-layer delegation stack. The stack is the NEW
  // authoritative source for agent/task attribution; rec.current_agent mirrors its
  // top so existing agent() default semantics keep working.
  const stack = createStack()

  // Defensive finalisation (Sep-7 defect: 18/20 sessions unfinalized). The final
  // emit is idempotent — only the FIRST terminal event writes the final record;
  // every later finalisation is a no-op and never writes twice.
  const flushGuard = createFlushGuard()

  // P0-1 (§3/§4): runtime-owned attempt lifecycle. The registry is the ONLY
  // attempt counter — contract retry_of lineage is never read as an attempt
  // number (correlation/validation only).
  const attempts = createAttemptRegistry()

  // P0-1: emit one raw taxonomy event through the collector. The envelope is
  // merged with the runtime attempt_id; events are never dropped — when no
  // envelope frame is active the event still records with
  // attribution_confidence "fallback" (§4).
  const emitTaxonomy = (event: string, detail: any, env: any) => {
    rec.taxonomy_events.push(taxonomyEvent({ event, detail, envelope: env }))
  }

  const agent = (name?: string) => {
    const k = name || rec.current_agent || "unknown"
    if (!rec.agents[k]) {
      rec.agents[k] = { invocations: 0, tokens: zeroTok(), tool_calls: 0, ms: 0, models: [] as string[] }
    }
    return rec.agents[k]
  }

  const num = (...vals: any[]) => {
    for (const v of vals) if (typeof v === "number" && isFinite(v)) return v
    return 0
  }

  const emit = async (kind: "started" | "heartbeat" | "final") => {
    // A session killed before idle/deleted leaves no flush point, so the started and
    // heartbeat emits are the liveness trail; only the final emit is idempotent.
    // Sep-7 defect: 18/20 sessions unfinalized — finalisation now fires on any
    // terminal-ish event (idle/deleted/paused/closed); the flush guard makes the
    // first flush the only writer and every later finalisation a no-op.
    if (!rec.session_id) return
    if (kind === "final" && !flushGuard.claim()) return
    const agents: any = {}
    for (const [k, v] of Object.entries<any>(rec.agents)) {
      agents[k] = { ...v, models: [...new Set(v.models)] }
    }
    const payload = {
      record_version: rec.record_version,
      kind,
      session_id: rec.session_id,
      task_id: rec.task_id,
      // §4 execution envelope: additive identity fields. attribution_confidence is
      // "stack" when a frame is active, "fallback" when none is — events are never
      // dropped, only flagged. P0-1 fills attempt_id from the runtime attempt
      // registry (the emit-time open attempt, or null when none is open).
      envelope: { ...stack.payload(), attempt_id: attempts.current(rec.task_id) },
      started_at: new Date(rec.started).toISOString(),
      duration_s: Math.round((now() - rec.started) / 1000),
      agents,
      tokens: rec.tokens,
      models_seen: rec.models_seen,
      tools: rec.tools,
      gates: rec.gates,
      skills_loaded: [...rec.skills_loaded],
      graph_queries: rec.graph_queries,
      fallbacks_used: rec.fallbacks_used,
      provider_tier: rec.provider_tier,
      files_read: rec.files_read,
      context_expansions: rec.context_expansions,
      materialised_chars: rec.materialised_chars,
      truncations: rec.truncations,
      retries: rec.retries,
      // P0-1 (§3): raw taxonomy events, one record per event in the §3 schema.
      taxonomy_events: rec.taxonomy_events,
      defect_escapes: rec.defect_escapes,
      retros_recorded: rec.retros_recorded,
      retro_recurrences: rec.retro_recurrences,
      retro_fix_targets: rec.retro_fix_targets,
      human_gates: rec.human_gates,
      blockers_opened: rec.blockers_opened,
      blockers_resolved: rec.blockers_resolved,
      blocker_signals: [...rec.blocker_signals],
      worker_tasks_registered: rec.worker_tasks_registered,
      worker_events_written: rec.worker_events_written,
      worker_stalls_detected: rec.worker_stalls_detected,
      claims_recorded: rec.claims_recorded,
      claims_invalid: rec.claims_invalid,
      bg_poll_total: rec.bg_poll_total,
      bg_tasks: rec.bg_tasks,
    }
    await $`python3 framework/adapters/gsd_state.py write-telemetry --json ${JSON.stringify(payload)}`
      .quiet().nothrow()
    if (kind === "final" && hb) clearInterval(hb)
  }

  const heartbeat = () => emit("heartbeat")

  // DID-012 Pillar 1: durable ASK capture (chat.message) and open-ask injection
  // (system.transform / compacting). Opt-in via INTAKE_CAPTURE=1; every hook is a no-op
  // otherwise. Uses the same `$` + python3 route as write-telemetry above.
  const intake = createIntakeHooks({
    run: async (cmd: "capture" | "open", json?: string) => {
      const r = cmd === "capture"
        ? await $`python3 framework/adapters/intake.py capture --json ${json ?? ""}`.quiet().nothrow()
        : await $`python3 framework/adapters/intake.py open`.quiet().nothrow()
      return { exitCode: r.exitCode, stdout: r.text(), stderr: r.stderr?.toString?.() ?? "" }
    },
  })

  // Provider health: record spawn/session failures into the ledger g12 reads, and (opt-in,
  // PROVIDER_PREFLIGHT=1) refuse `task` dispatch while a blocking failure is recorded.
  const providers = createProviderObserver({
    run: async (cmd: "observe" | "check", a?: { error: string; provider: string; model: string }) => {
      const r = cmd === "observe"
        ? await $`python3 framework/providers/healthcheck.py observe --error ${a?.error ?? ""} --provider ${a?.provider ?? ""} --model ${a?.model ?? ""} --source session_error`.quiet().nothrow()
        : await $`python3 framework/providers/healthcheck.py check`.quiet().nothrow()
      return { exitCode: r.exitCode, stdout: r.text(), stderr: r.stderr?.toString?.() ?? "" }
    },
  })

  const started: Record<string, number> = {}
  let hb: ReturnType<typeof setInterval> | null = null

  return {
    ...intake.hooks,
    // Model + agent attribution. Fires before every model request.
    "chat.params": async (input: any) => {
      providers.onParams(input)
      const model = input?.model?.modelID ?? input?.model?.id ?? input?.model ?? "unknown"
      const provider = input?.provider?.providerID ?? input?.provider?.id ?? input?.provider ?? ""
      const full = provider ? `${provider}/${model}` : String(model)
      rec.models_seen[full] = (rec.models_seen[full] ?? 0) + 1
      // P0-1: last-seen model feeds the taxonomy event schema's model_id field.
      rec.last_model = full
      // §4: attribute to top-of-stack execution agent when a delegation is active;
      // otherwise fall back to the input agent (existing behavior).
      const a = agent(stack.top()?.execution_agent ?? input?.agent ?? input?.message?.agent)
      if (!a.models.includes(full)) a.models.push(full)
    },

    "tool.execute.before": async (input: any) => {
      await providers.beforeTool(input)
      const key = `${input?.tool}:${input?.callID ?? input?.sessionID ?? ""}`
      started[key] = now()
      if (input?.tool === "task") {
        // The `task` tool is how the Team Lead delegates. Treat it as the agent boundary so
        // downstream tool calls and tokens attribute to the subagent, not to the lead.
        // §4: resolve execution_agent and push an envelope frame; the stack is the NEW
        // authoritative attribution source (replaces the single mutable current_agent).
        // Sep-7 defect: 539/547 records attributed "unknown" because the args were read
        // from input?.args, which is undefined in this harness — the task tool delivers
        // them under input.input. normalizeTaskArgs reads the first present shape
        // (args ?? input ?? arguments) and merges when several are objects.
        const args = normalizeTaskArgs(input)
        const executionAgent = resolveExecutionAgent(args)
        const taskId = String(args?.task_id ?? stack.top()?.task_id ?? rec.task_id)
        agent(executionAgent).invocations++
        const frame = stack.push({
          execution_agent: executionAgent,
          session_id: rec.session_id,
          task_id: taskId,
          description: String(args?.description ?? ""),
        })
        rec.current_agent = stack.current()
        // P0-1 (§3 attempt lifecycle): WORK_ATTEMPTED opens attempt N for the
        // delegated task. Only a top-level delegation (stack depth 1 after
        // push) opens an attempt — a nested delegation belongs to the current
        // attempt, it is not a retry. Another top-level WORK_ATTEMPTED while
        // the prior attempt is unresolved opens N+1 AND derives RETRY.
        if (stack.depth() === 1) {
          const { attempt_id, retry } = attempts.open(frame.task_id)
          const env = {
            ...stack.payload(),
            session_id: rec.session_id,
            model_id: rec.last_model ?? "",
            attempt_id,
          }
          emitTaxonomy(EVENTS.WORK_ATTEMPTED, { execution_agent: executionAgent }, env)
          if (retry) {
            emitTaxonomy(EVENTS.RETRY, { previous_attempt: attempt_id - 1 }, env)
          }
        }
      }
      if (input?.tool === "skill") {
        // The skill tool's args are not in one fixed place: the task tool delivers them at
        // input.input.args (see the note above), other tools at input.args, and a caller may
        // pass a plain args object. Reading a single location recorded EVERY skill call as
        // "unknown", so skills_loaded said nothing and G-SKILL-USE could never judge. Two
        // attempts to guess the shape both got it wrong -- so unwrap until the id (the skill
        // tool's parameter) or name appears, at any of those depths.
        const skillIdOf = (o: any, depth = 0): any => {
          if (!o || typeof o !== "object" || depth > 3) return undefined
          return o.id || o.name || skillIdOf(o.args, depth + 1) || skillIdOf(o.input, depth + 1)
        }
        rec.skills_loaded.add(String(skillIdOf(input) ?? "unknown"))
      }
      if (input?.tool === "bash") {
        const cmd = String(input?.args?.command ?? "")
        const launchRequired = parseGateRequired({ cmd })
        const launchStarted = parseGateExecutionStarted({ cmd })
        if (launchRequired || launchStarted) {
          const env = {
            ...stack.payload(),
            session_id: rec.session_id,
            model_id: rec.last_model ?? "",
            task_id: stack.top()?.task_id ?? rec.task_id,
            attempt_id: attempts.current(stack.top()?.task_id ?? rec.task_id),
          }
          if (launchRequired) emitTaxonomy(launchRequired.event, launchRequired.detail, env)
          if (launchStarted) emitTaxonomy(launchStarted.event, launchStarted.detail, env)
        }
      }
      // Background task bookkeeping. Polls vs collects are distinguished in .after by
      // checking whether the output reports completion; here we only record the first
      // touch (launched) so counts are never double-allocated.
      if (input?.tool === "background_output") {
        const tid = String(input?.args?.task_id ?? "unknown")
        if (!rec.bg_tasks[tid]) rec.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
      }
      if (input?.tool === "background_cancel") {
        const tid = String(input?.args?.taskId ?? "unknown")
        if (rec.bg_tasks[tid]) rec.bg_tasks[tid].cancelled++
      }
    },

    "tool.execute.after": async (input: any, output: any) => {
      const name = String(input?.tool ?? "")
      const key = `${name}:${input?.callID ?? input?.sessionID ?? ""}`
      const ms = started[key] ? now() - started[key] : 0
      delete started[key]

      // Background task contract enforcement: classify each background_output call.
      // An output that reports the task as still running or "pending" is a POLL (the
      // notification contract says end response and wait). An output reporting
      // completion/final content is a COLLECT (legal). We also register lazily-launched
      // background task ids when the task tool returns them (output title carries "bg_...").
      if (name === "background_output") {
        const tid = String(input?.args?.task_id ?? "unknown")
        if (!rec.bg_tasks[tid]) rec.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
        const out = String(output?.output ?? output?.title ?? "")
        // Sep-7 defect: the bare /Duration/ alternative matched every completed-output
        // summary, so completed background tasks were misclassified as polls (13 poll
        // + 16 stale-bg false positives). isPollOutput requires explicit
        // running/pending evidence now.
        const stillRunning = isPollOutput(out)
        if (stillRunning && !input?.args?.block) {
          rec.bg_tasks[tid].polls++
          rec.bg_poll_total++
          // Make the violation visible to the model that committed it. Hooks mutate output
          // in place and return void, so annotation is the enforcement surface.
          const mark = "\n[POLL_VIOLATION] background_output called before the system-reminder (or with block=true). The contract is: END YOUR RESPONSE, wait for the notification, then collect. bg_poll_total += 1 for this call."
          if (typeof output?.output === "string") output.output += mark
          else if (typeof output?.title === "string") output.title += mark
        } else {
          rec.bg_tasks[tid].collects++
        }
      }
      if (name === "task") {
        const out = String(output?.output ?? output?.title ?? "")
        const m = out.match(/bg_[a-z0-9]+/)
        if (m) {
          const tid = m[0]
          if (!rec.bg_tasks[tid]) rec.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
          rec.bg_tasks[tid].launched++
          // §4 background-task propagation: snapshot the execution agent at launch
          // (top of stack before pop) so background_output interactions attribute
          // to the delegating agent even after the frame is popped.
          rec.bg_tasks[tid].agent = stack.top()?.execution_agent ?? rec.current_agent
        }
        // §4: pop the delegation frame; current_agent restores to the parent.
        const popped = stack.pop()
        if (popped) rec.current_agent = stack.current()
      }

      if (!rec.tools[name]) rec.tools[name] = { count: 0, ms: 0, fail: 0 }
      rec.tools[name].count++
      rec.tools[name].ms += ms
      // §4: background-task interactions attribute to the agent snapshot taken at
      // launch (the delegating agent), not to whoever is current at collect time.
      const attrAgent = name === "background_output"
        ? (rec.bg_tasks[String(input?.args?.task_id ?? "unknown")]?.agent ?? rec.current_agent)
        : rec.current_agent
      agent(attrAgent).tool_calls++
      agent(attrAgent).ms += ms

      if (name === "read") rec.files_read++
      if (name.includes("code_intel") || name.includes("codegraph")) rec.graph_queries++

      const text = String(output?.output ?? output?.title ?? "")
      // args live on the FIRST parameter. A previous version read output?.args?.command,
      // which is always undefined, so no gate result was ever recorded.
      const cmd = String(input?.args?.command ?? "")

      if (name === "context-builder") {
        try {
          const p = JSON.parse(text || "{}")
          rec.materialised_chars += num(p.materialised_chars)
          rec.truncations += Array.isArray(p.truncated) ? p.truncated.length : 0
          const tier = Number(p.provider_tier)
          if (isFinite(tier)) {
            rec.provider_tier = tier
            if (tier >= 4) rec.fallbacks_used++
          }
          if (p.level === "system") rec.context_expansions++
        } catch {}
      }

      if (name === "bash" && cmd) {
        // Exit code is not exposed on this hook in all versions. Gates print a stable
        // [gate] PASS/FAIL/UNVERIFIABLE line precisely so the result survives without it.
        // Sep-7 defect: the legacy /gates\/(g[1-8])_|g1[01]_/ regex missed g9/g12/g13
        // and the g_tool_* scripts, so ZERO gate records were captured on Sep 7.
        // Detection now routes through gates.mjs GATE_SCRIPT_RE + shortGateId and the
        // result through parseGateLine — the same code path gates.test.mjs covers.
        const launch = parseGateLaunch({ cmd })
        if (launch) {
          const gateId = launch.gate
          let result = "unknown", exit = -1
          let evidence: string | undefined
          const line = parseGateLine(text)
          if (line && line.name === gateId) {
            result = line.result
            exit = line.exit ?? -1
            evidence = line.evidence
          } else {
            // Pre-canonical marker fallback: gates/_lib.sh log() lines like "[g8] PASS".
            //
            // ORDERED MOST-SEVERE-FIRST, and the order is load-bearing. This chain
            // is first-match-wins over keywords matched ANYWHERE in the output, so
            // testing PASS first meant a gate that printed PASS for some of its
            // checks and FAIL overall was recorded as result="pass", exit=0. A
            // false green is the worst possible direction for this field: it
            // inflates apparent success and no downstream reader can tell it
            // apart from a real pass.
            //
            // SKIP maps to not_applicable / exit 4, never exit 0. EXIT_CODES.md
            // states "SKIP != PASS" and assigns NOT_APPLICABLE the code 4, so
            // recording a skip as exit 0 manufactured a pass out of a gate that
            // judged nothing. "skip" was also never a declared result token in
            // GATE_RESULTS, so writing it here fed the report layer an
            // off-contract enum value.
            if (/\bFAIL\b/.test(text))               { result = "fail";           exit = 1 }
            else if (/\bBLOCKED\b/.test(text))       { result = "blocked";        exit = 2 }
            else if (/\bUNVERIFIABLE\b/.test(text))  { result = "unverifiable";   exit = 3 }
            else if (/\bNOT_APPLICABLE\b/.test(text)){ result = "not_applicable"; exit = 4 }
            else if (/\bSKIP\b/.test(text))          { result = "not_applicable"; exit = 4 }
            else if (/\bPASS\b/.test(text))          { result = "pass";           exit = 0 }
          }
          // Preserve the previous three-key shape when there is no evidence, so
          // existing telemetry field checks keep passing unchanged.
          rec.gates[gateId] =
            evidence === undefined ? { result, ms, exit } : { result, ms, exit, evidence }
        }
        if (cmd.includes("retro/ledger.py append")) {
          rec.retros_recorded++
          const t = cmd.match(/"fix_target"\s*:\s*"([^"]+)"/)
          if (t) rec.retro_fix_targets.push(t[1])
        }
        if (cmd.includes("retro/escape_path.py")) rec.defect_escapes++
        if (cmd.includes("g7_retro.sh") && /RECURR/i.test(text)) rec.retro_recurrences++
        if (cmd.includes("claims/ledger.py append")) rec.claims_recorded++
        if (cmd.includes("g11_evidence.sh") && /\bFAIL\b/.test(text)) rec.claims_invalid++
        const h = text.match(/\b(H[123])\b/)
        if (h && !rec.human_gates.includes(h[1])) rec.human_gates.push(h[1])
        // P0-1 (§3): taxonomy signal parsers replace the dead /RETRY_(\w+)/ regex.
        // Raw events only — derived rework metrics live in report.py. Each event
        // inherits the execution envelope; attempt_id comes from the runtime
        // attempt registry (single authoritative owner, §4).
        // Sep-7 defect: output.exit was null on TEST_FAILED events even though the
        // runner printed the code. Fall back to extracting it from the output text;
        // record null only when no pattern matches (never fabricate).
        const exit = typeof output?.exit === "number" ? output.exit : extractExitCode(text)
        const signals = parseSignals({ cmd, text, exit })
        for (const s of signals) {
          const taskId = stack.top()?.task_id ?? s.detail?.task_id ?? rec.task_id
          const env = {
            ...stack.payload(),
            session_id: rec.session_id,
            model_id: rec.last_model ?? "",
            task_id: taskId,
            attempt_id: attempts.current(taskId),
          }
          emitTaxonomy(s.event, s.detail, env)
          // TASK_COMPLETED resolves the open attempt for that task.
          if (s.event === EVENTS.TASK_COMPLETED) attempts.close(taskId)
        }
      }
        // Exit codes are not exposed on this hook in every OpenCode version, so a
        // positive stdout marker is accepted as well; a FAIL line always vetoes.
        if (cmd.includes("gsd_state.py write-blocker")
            && (output?.exit === 0 || /BLOCKER[_-][A-Za-z0-9]+/.test(text))
            && !/\bFAIL\b/.test(text)) {
          rec.blockers_opened++
          const bs = cmd.match(/"signal"\s*:\s*"([^"]+)"/)
          if (bs && !rec.blocker_signals.includes(bs[1])) rec.blocker_signals.push(bs[1])
        }
        if (cmd.includes("gsd_state.py resolve-blocker")
            && (output?.exit === 0 || /\bRESOLVED\b/i.test(text))) {
          rec.blockers_resolved++
        }
        if (cmd.includes("gsd_state.py task-register")
            && (output?.exit === 0 || /\bSPAWNED\b/.test(text))
            && !/\bFAIL\b/.test(text)) {
          rec.worker_tasks_registered++
        }
        if (cmd.includes("gsd_state.py task-event")
            && (output?.exit === 0 || /"emitter"\s*:/.test(text))
            && !/\bFAIL\b/.test(text)) {
          rec.worker_events_written++
        }
        if (cmd.includes("gsd_state.py task-status")
            && /"health"\s*:\s*"(STALLED|OVERDUE)"/.test(text)
            && !/\bFAIL\b/.test(text)) {
          rec.worker_stalls_detected++
        }
    },

    event: async ({ event }: any) => {
      intake.onEvent(event)
      await providers.onEvent(event)
      const t = String(event?.type ?? "")

      if (t === "session.created") {
        rec.session_id = String(event?.properties?.info?.id ?? event?.properties?.sessionID ?? rec.session_id)
        await emit("started")
        hb = setInterval(heartbeat, 60_000)
      }

      if (t === "message.updated") {
        const m = event?.properties?.info ?? event?.properties?.message ?? {}
        const id = String(m?.id ?? "")
        const u = m?.tokens ?? m?.usage ?? {}
        // Streaming delivers cumulative counts on repeated updates. Store per-message
        // totals and diff, or the same tokens get counted many times over.
        const cur = {
          input: num(u.input, u.prompt_tokens, u.promptTokens),
          output: num(u.output, u.completion_tokens, u.completionTokens),
          reasoning: num(u.reasoning, u.reasoning_tokens),
          cache_read: num(u.cache?.read, u.cache_read, u.cacheReadInputTokens),
          cache_write: num(u.cache?.write, u.cache_write, u.cacheCreationInputTokens),
        }
        const prev = rec.seen_msg[id] ?? zeroTok()
        // §4: attribute to top-of-stack execution agent when a delegation is active;
        // otherwise fall back to the message agent, then to current_agent.
        const who = String(stack.top()?.execution_agent ?? m?.agent ?? rec.current_agent)
        const a = agent(who)
        for (const k of Object.keys(cur) as Array<keyof typeof cur>) {
          const d = cur[k] - (prev as any)[k]
          if (d > 0) { rec.tokens[k] += d; a.tokens[k] += d }
        }
        rec.seen_msg[id] = cur
      }

      if (t === "session.compacted") { rec.context_expansions++; await heartbeat() }

      // The real flush point. Registering "session.idle" as a hook key silently collects
      // nothing, which is how this plugin previously wrote zero records.
      // Sep-7 defect: 18/20 sessions unfinalized — a session killed without the clean
      // idle path still writes one final record on any terminal-ish event. emit("final")
      // is idempotent (flush guard): only the first flush writes; a subsequent
      // finalisation is a no-op and never writes twice.
      if (t === "session.idle" || t === "session.deleted"
          || t === "session.paused" || t === "session.closed") await emit("final")
    },
  }
}
// ─────────────────────────────────────────────────────────────────────────────────────────
// V2 ENTRYPOINT (OpenCode v2.x plugin API)
// ─────────────────────────────────────────────────────────────────────────────────────────
// WHY THIS EXISTS
// ===============
// v2 validates the default export as a plugin DEFINITION -- `{ id, setup }` or
// `{ id, effect }` -- and rejects the V1 factory shape outright:
//
//   Plugin must export a default definition with an id and an effect or setup function
//
// From the host upgrade onward the collector loaded nothing and records.jsonl stopped being
// written (last row 2026-10-12). A collector that does not load reports zero, and zero is
// indistinguishable from "no work happened" to every consumer: G-SKILL-USE, G-TELEMETRY-LIVE,
// report.py. That is a sensor defect, not a quiet period.
//
// SHAPE
// =====
// v2 registers hooks imperatively inside `setup(ctx)`. The V1 hook bodies above are reused
// unchanged -- they are the collector, and reimplementing them for v2 would create a second
// source of truth for the same facts.
//
// TRANSLATION, NOT PASS-THROUGH
// =============================
// v2 events are `{ id, created, type, durable, location, data }`; the V1 body reads
// `{ type, properties }`. Handing a v2 event straight to it yields `session_id: ""` and a
// record full of zeros -- the same silent-zero failure in a new costume. Every mapping below
// was measured against host v2.2.4 with a probe plugin:
//
//   session.execution.started  data.sessionID                      -> session.created
//   session.step.started       data.model{id,providerID}, .agent    -> chat.params
//   session.step.ended         data.tokens{input,output,reasoning,cache{read,write}}
//                                                                  -> message.updated
//   session.execution.succeeded / .failed / .cancelled / deleted    -> terminal flush
//
// DELIBERATELY UNMAPPED
// =====================
// `session.usage.updated` carries the CUMULATIVE session token figure. Mapping it alongside
// `session.step.ended` would count every token twice, so it is dropped on purpose. Dropping
// is explicit here rather than an accident of a field name that does not exist.

/** v2 `execute.before`/`execute.after` event -> the V1 hook's first parameter. */
export function v2ToolBefore(e: any) {
  const input = e?.input ?? e?.args
  return {
    tool: String(e?.tool ?? e?.name ?? ""),
    // `args` is where the V1 bodies read tool arguments (bash: input.args.command,
    // skill: the unwrapped id). `input` is kept because the task tool has historically
    // delivered its args there.
    args: input,
    input,
    callID: e?.id,
    sessionID: e?.sessionID,
  }
}

/** v2 `execute.after` event -> [V1 input, V1 output]. v2 carries the tool name itself, so
 *  no before/after pairing is needed and a dropped event cannot misattribute a result. */
export function v2ToolAfter(e: any) {
  const r: any = e?.result
  let text = ""
  if (typeof r === "string") text = r
  else if (typeof r?.output?.output === "string") text = r.output.output
  else if (r) {
    try { text = JSON.stringify(r) } catch { text = "" }
  }
  const exit = typeof r?.output?.exit === "number" ? r.output.exit
    : typeof r?.metadata?.exit === "number" ? r.metadata.exit
    : undefined
  return [v2ToolBefore(e), { output: text, title: "", exit }] as const
}

/** One v2 stream event -> the instruction the V1 collector understands.
 *  `null` means "the collector has no counter for this event" and is explicit. */
export function v2Event(ev: any, seen: Set<string>) {
  const t = String(ev?.type ?? "")
  const d: any = ev?.data ?? {}

  if (t === "session.execution.started") {
    const sid = String(d.sessionID ?? "")
    // v2 emits execution.started once PER TURN; V1's session.created fired once per session
    // and starts a 60s heartbeat interval. Passing every turn through would stack intervals
    // and multiply the write rate, so only the first turn creates the session.
    if (!sid || seen.has(sid)) return null
    seen.add(sid)
    return { kind: "event" as const,
             event: { type: "session.created", properties: { info: { id: sid } } } }
  }

  if (t === "session.step.started") {
    // v2 has no `chat.params` hook; model/provider identity rides on the step event.
    return {
      kind: "chat" as const,
      input: {
        model: { modelID: d?.model?.id },
        provider: { providerID: d?.model?.providerID },
        agent: d.agent,
      },
    }
  }

  if (t === "session.step.ended") {
    return {
      kind: "event" as const,
      event: {
        type: "message.updated",
        properties: { info: { id: d.assistantMessageID, tokens: d.tokens } },
      },
    }
  }

  if (t === "session.compacted") {
    return { kind: "event" as const, event: { type: "session.compacted", properties: {} } }
  }

  if (t === "session.execution.succeeded" || t === "session.execution.failed"
      || t === "session.execution.cancelled" || t === "session.deleted") {
    // `emit("final")` is idempotent, so the first turn end writes the record and later
    // terminal events are no-ops; heartbeats keep the series alive in between.
    return { kind: "event" as const, event: { type: "session.idle", properties: {} } }
  }

  return null
}

/** Dispatch one v2 event into the V1 collector. Shared with the test harness so the test
 *  exercises the production path rather than a copy of it. */
export async function dispatchV2(ev: any, hooks: any, seen: Set<string>) {
  const step = v2Event(ev, seen)
  if (!step) return
  if (step.kind === "chat") await hooks?.["chat.params"]?.(step.input)
  else await hooks?.event?.({ event: step.event })
}

/** v2 does not hand the plugin a `$`. The collector uses exactly two chain methods
 *  (`.quiet().nothrow()`), so that is all this needs to provide. Commands are repo-relative,
 *  hence the plugin's own location as cwd.
 *
 *  NO SHELL, ON PURPOSE. The V1 host `$` escapes every interpolated value itself. A naive
 *  reimplementation that concatenates a command string does not, and on Windows cmd.exe
 *  consumes the quotes inside the JSON payload. Measured on the first write after the v2
 *  port landed: the record was appended as `{record_version:3,...}` -- every quote stripped --
 *  which is not JSON and cannot be read back. Building an argv array and spawning without a
 *  shell removes the whole class: no quoting rules, no metacharacter expansion, no
 *  command-length ceiling. */
export function shellFor(cwd: string) {
  return (strings: TemplateStringsArray, ...values: any[]) => {
    const argv: string[] = []
    for (let i = 0; i < strings.length; i++) {
      const chunk = strings[i].trim()
      if (chunk) argv.push(...chunk.split(/\s+/))
      // Each interpolated value is ONE argument, never re-split and never re-quoted.
      if (i < values.length) argv.push(String(values[i] ?? ""))
    }
    const chain = {
      quiet() { return chain },
      nothrow() {
        try {
          const r = spawnSync(argv[0], argv.slice(1), { cwd, encoding: "utf8", timeout: 60_000 })
          return Promise.resolve({
            exitCode: r.status ?? 1,
            text: () => r.stdout ?? "",
            stderr: r.stderr ?? "",
          })
        } catch (err: any) {
          return Promise.resolve({ exitCode: 1, text: () => "", stderr: String(err?.message ?? err) })
        }
      },
    }
    return chain
  }
}

export const TelemetryV2 = {
  id: "telemetry",
  async setup(ctx: any) {
    const hooks: any = await TelemetryPlugin({
      $: shellFor(String(ctx?.location?.directory ?? process.cwd())),
    })

    await ctx?.tool?.hook?.("execute.before", async (e: any) => {
      await hooks["tool.execute.before"]?.(v2ToolBefore(e))
    })

    await ctx?.tool?.hook?.("execute.after", async (e: any) => {
      const [input, output] = v2ToolAfter(e)
      await hooks["tool.execute.after"]?.(input, output)
    })

    const seen = new Set<string>()
    void (async () => {
      try {
        for await (const ev of ctx.event.subscribe()) await dispatchV2(ev, hooks, seen)
      } catch {
        // The subscription ends on host unload and on restart; both are normal.
      }
    })()
  },
}

export default TelemetryV2
