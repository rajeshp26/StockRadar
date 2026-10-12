// framework/opencode/plugin/attribution_harness.mjs
// Synthetic-execution attribution harness (P2, critic #10/#12).
//
// PROVES: the telemetry collector attributes every scored unit (invocations,
// tool calls, tokens, taxonomy events) to the correct execution agent, with
// >= 0.99 accuracy over >= 1000 units, on a deterministic corpus that includes
// the adversarial cases from the Sep-7 attribution defects.
//
// METHOD:
//  - Drive the REAL TelemetryPlugin over a scripted + seeded corpus with a
//    stubbed `$` that only captures write-telemetry commands (no filesystem,
//    no python, no side effects).
//  - Compute the EXPECTED state with an independent simulator: its own stack,
//    its own agents/attempts/bg bookkeeping, written from the same
//    execution-envelope spec the plugin implements. It reuses ONLY the
//    already-tested pure vocabulary (normalizeTaskArgs, resolveExecutionAgent,
//    parseSignals, parseGateRequired/parseGateExecutionStarted, the attempt
//    registry, taxonomyEvent) so the only DIFFERENCE from the plugin is the
//    state container itself.
//  - Snapshot both sides at every flush point (started / heartbeat / final),
//    diff consecutive snapshots into units, and score with multiset accuracy.
//
// Metric definition: ATTRIBUTION-METRIC.md (same directory).
// Run:  node framework/opencode/plugin/attribution_harness.mjs [--seed N] [--sessions N] [--json]
// Exit: 0 pass | 1 below metric | 2 harness error | 3 nothing ran
import { fileURLToPath, pathToFileURL } from "node:url"
import { TelemetryPlugin } from "./telemetry.ts"
import { normalizeTaskArgs, resolveExecutionAgent } from "./envelope.mjs"
import { EVENTS, createAttemptRegistry, taxonomyEvent, parseSignals, extractExitCode, isPollOutput } from "./taxonomy.mjs"
import { parseGateRequired, parseGateExecutionStarted } from "./gates.mjs"

const TOKEN_COUNTERS = ["input", "output", "reasoning", "cache_read", "cache_write"]
const MIN_UNITS = 1000
const THRESHOLD = 0.99
const DEFAULT_SEED = 20260911

const zeros = () => ({ input: 0, output: 0, reasoning: 0, cache_read: 0, cache_write: 0 })

// === Deterministic PRNG (mulberry32) ===
function mulberry32(seed) {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// === Stub `$` host template-tag (same contract as telemetry.test.mjs) ===
// The plugin invokes:  await $`python3 ... write-telemetry --json <payload>`.quiet().nothrow()
// We capture command + parsed payload; nothing is executed.
function makeDollar() {
  const emitted = []
  const dollar = (strings, ...values) => {
    let cmd = ""
    for (let i = 0; i < strings.length; i++) {
      cmd += strings[i]
      if (i < values.length) cmd += String(values[i])
    }
    let payload = null
    const m = cmd.match(/--json\s+(\{.*\})\s*$/)
    if (m) {
      try { payload = JSON.parse(m[1]) } catch { payload = null }
    }
    emitted.push({ cmd, payload })
    const chain = {
      quiet() { return this },
      nothrow() { return Promise.resolve({ exit: 0 }) },
    }
    return chain
  }
  return { dollar, emitted }
}

// === Unit extraction ===
// One taxonomy event = event name + execution_agent + attribution_confidence +
// the canonical identity/detail fields; ts is excluded because it is
// wall-clock and cannot be reproduced by a simulator.
function eventUnit(e) {
  const canon = JSON.stringify({
    task_id: e?.task_id ?? "",
    attempt_id: e?.attempt_id ?? null,
    parent_task_id: e?.parent_task_id ?? "",
    delegated_agent: e?.delegated_agent ?? "team-lead",
    model_id: e?.model_id ?? "",
    detail: e?.detail ?? {},
  })
  return `evt|${e?.event ?? ""}|${e?.execution_agent ?? "unknown"}|${e?.attribution_confidence ?? "fallback"}|${canon}`
}

// Diff two snapshots of the same side into a unit map. Counters are monotonic
// per key, so per-pair deltas are >= 0. Exclusions: ms, models[], and every
// payload envelope/global counter (models_seen, bg_poll_total, files_read,
// context_expansions, tools, gates, ...) -- the metric scores only what
// attribution can change: per-agent invocations, tool_calls, token counters,
// and the taxonomy event stream.
function diffUnits(prev, cur) {
  const units = new Map()
  const add = (k, v) => {
    if (v !== 0) units.set(k, (units.get(k) ?? 0) + v)
  }
  const pA = prev?.agents ?? {}
  const cA = cur?.agents ?? {}
  for (const k of new Set([...Object.keys(pA), ...Object.keys(cA)])) {
    const p = pA[k] ?? {}
    const c = cA[k] ?? {}
    add(`inv|${k}`, (c.invocations ?? 0) - (p.invocations ?? 0))
    add(`call|${k}`, (c.tool_calls ?? 0) - (p.tool_calls ?? 0))
    for (const t of TOKEN_COUNTERS) {
      add(`tok|${k}|${t}`, (c.tokens?.[t] ?? 0) - (p.tokens?.[t] ?? 0))
    }
  }
  const pE = prev?.taxonomy_events ?? []
  const cE = cur?.taxonomy_events ?? []
  for (let i = pE.length; i < cE.length; i++) {
    add(eventUnit(cE[i]), 1)
  }
  return units
}

function mergeUnits(target, src) {
  for (const [k, v] of src) target.set(k, (target.get(k) ?? 0) + v)
}

// === Independent simulator (execution-envelope spec, own state) ===
// Mirrors telemetry.ts exactly, minus the host plugin surface. Scored fields
// are the ONLY outputs that matter; every pure helper is shared with the
// plugin so divergence can only come from state handling, which is what the
// metric is designed to catch.
class Simulator {
  constructor(sessionId) {
    this.sessionId = sessionId
    this.taskId = process.env.TASK_ID ?? ""
    this.currentAgent = "team-lead"
    this.agents = {}
    this.tokensGlobal = zeros()
    this.taxonomy_events = []
    this.attempts = createAttemptRegistry()
    this.seenMsg = {}
    this.lastModel = ""
    this.bg_tasks = {}
    this.stackFrames = []
  }

  agent(name) {
    const k = name || this.currentAgent || "unknown"
    if (!this.agents[k]) {
      this.agents[k] = { invocations: 0, tokens: zeros(), tool_calls: 0, ms: 0, models: [] }
    }
    return this.agents[k]
  }

  // stack -- own container with the same semantics envelope.createStack gives
  stackDepth() {
    return this.stackFrames.length
  }
  stackTop() {
    return this.stackFrames.length ? this.stackFrames[this.stackFrames.length - 1] : null
  }
  stackPush(frame) {
    const top = this.stackTop()
    const f = {
      execution_agent: frame.execution_agent,
      delegated_agent: top?.execution_agent ?? "team-lead",
      session_id: this.sessionId,
      task_id: frame.task_id,
      parent_task_id: top?.task_id ?? "",
      attribution_confidence: "stack",
    }
    this.stackFrames.push(f)
    return f
  }
  stackPop() {
    return this.stackFrames.length ? this.stackFrames.pop() : null
  }
  stackCurrent() {
    return this.stackTop()?.execution_agent ?? "team-lead"
  }
  stackPayload(opts = {}) {
    const t = this.stackTop()
    return {
      task_id: t?.task_id ?? opts.task_id ?? "",
      parent_task_id: t?.parent_task_id ?? opts.parent_task_id ?? "",
      delegated_agent: t?.delegated_agent ?? opts.delegated_agent ?? "team-lead",
      execution_agent: t?.execution_agent ?? opts.execution_agent ?? this.stackCurrent(),
      attribution_confidence: t ? "stack" : (opts.attribution_confidence ?? "fallback"),
      attempt_id: null,
    }
  }

  emitTaxonomy(event, detail, env) {
    this.taxonomy_events.push(taxonomyEvent({ event, detail, envelope: env }))
  }

  // --- hook mirrors (scored fields only) ---
  cp(input) {
    const model = input?.model?.modelID ?? input?.model?.id ?? input?.model ?? "unknown"
    const provider = input?.provider?.providerID ?? input?.provider?.id ?? input?.provider ?? ""
    const full = provider ? `${provider}/${model}` : String(model)
    this.lastModel = full
    const a = this.agent(this.stackTop()?.execution_agent ?? input?.agent ?? input?.message?.agent)
    if (!a.models.includes(full)) a.models.push(full)
  }

  msg(m) {
    const id = String(m?.id ?? "")
    const u = m?.tokens ?? m?.usage ?? {}
    const num = (...vals) => {
      for (const v of vals) if (typeof v === "number" && isFinite(v)) return v
      return 0
    }
    const cur = {
      input: num(u.input, u.prompt_tokens, u.promptTokens),
      output: num(u.output, u.completion_tokens, u.completionTokens),
      reasoning: num(u.reasoning, u.reasoning_tokens),
      cache_read: num(u.cache?.read, u.cache_read, u.cacheReadInputTokens),
      cache_write: num(u.cache?.write, u.cache_write, u.cacheCreationInputTokens),
    }
    const prev = this.seenMsg[id] ?? zeros()
    const who = String(this.stackTop()?.execution_agent ?? m?.agent ?? this.currentAgent)
    const a = this.agent(who)
    for (const k of Object.keys(cur)) {
      const d = cur[k] - (prev[k] ?? 0)
      if (d > 0) {
        this.tokensGlobal[k] += d
        a.tokens[k] += d
      }
    }
    this.seenMsg[id] = cur
  }

  toolBefore(input) {
    if (input?.tool === "task") {
      const args = normalizeTaskArgs(input)
      const executionAgent = resolveExecutionAgent(args)
      const taskId = String(args?.task_id ?? this.stackTop()?.task_id ?? this.taskId)
      this.agent(executionAgent).invocations++
      this.stackPush({
        execution_agent: executionAgent,
        session_id: this.sessionId,
        task_id: taskId,
        description: String(args?.description ?? ""),
      })
      this.currentAgent = this.stackCurrent()
      if (this.stackDepth() === 1) {
        const { attempt_id, retry } = this.attempts.open(taskId)
        const env = {
          ...this.stackPayload(),
          session_id: this.sessionId,
          model_id: this.lastModel ?? "",
          attempt_id,
        }
        this.emitTaxonomy(EVENTS.WORK_ATTEMPTED, { execution_agent: executionAgent }, env)
        if (retry) {
          this.emitTaxonomy(EVENTS.RETRY, { previous_attempt: attempt_id - 1 }, env)
        }
      }
    }
    if (input?.tool === "bash") {
      const cmd = String(input?.args?.command ?? "")
      const launchRequired = parseGateRequired({ cmd })
      const launchStarted = parseGateExecutionStarted({ cmd })
      if (launchRequired || launchStarted) {
        const env = {
          ...this.stackPayload(),
          session_id: this.sessionId,
          model_id: this.lastModel ?? "",
          task_id: this.stackTop()?.task_id ?? this.taskId,
          attempt_id: this.attempts.current(this.stackTop()?.task_id ?? this.taskId),
        }
        if (launchRequired) this.emitTaxonomy(launchRequired.event, launchRequired.detail, env)
        if (launchStarted) this.emitTaxonomy(launchStarted.event, launchStarted.detail, env)
      }
    }
    if (input?.tool === "background_output") {
      const tid = String(input?.args?.task_id ?? "unknown")
      if (!this.bg_tasks[tid]) this.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
    }
    if (input?.tool === "background_cancel") {
      const tid = String(input?.args?.taskId ?? "unknown")
      if (this.bg_tasks[tid]) this.bg_tasks[tid].cancelled++
    }
  }

  toolAfter(input, output) {
    const name = String(input?.tool ?? "")
    if (name === "background_output") {
      const tid = String(input?.args?.task_id ?? "unknown")
      if (!this.bg_tasks[tid]) this.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
      const out = String(output?.output ?? output?.title ?? "")
      const stillRunning = isPollOutput(out)
      if (stillRunning && !input?.args?.block) {
        this.bg_tasks[tid].polls++
      } else {
        this.bg_tasks[tid].collects++
      }
    }
    if (name === "task") {
      const out = String(output?.output ?? output?.title ?? "")
      // The plugin registers bg ids from the task-tool output AND snapshots the
      // delegating agent BEFORE the frame is popped (telemetry.ts L310-321).
      const m = out.match(/bg_[a-z0-9]+/)
      if (m) {
        const tid = m[0]
        if (!this.bg_tasks[tid]) this.bg_tasks[tid] = { launched: 0, polls: 0, collects: 0, cancelled: 0 }
        this.bg_tasks[tid].launched++
        this.bg_tasks[tid].agent = this.stackTop()?.execution_agent ?? this.currentAgent
      }
      this.stackPop()
      this.currentAgent = this.stackCurrent()
    }
    const attrAgent = name === "background_output"
      ? (this.bg_tasks[String(input?.args?.task_id ?? "unknown")]?.agent ?? this.currentAgent)
      : this.currentAgent
    this.agent(attrAgent).tool_calls++

    const text = String(output?.output ?? output?.title ?? "")
    const cmd = String(input?.args?.command ?? "")
    if (name === "bash" && cmd) {
      const exit = typeof output?.exit === "number" ? output.exit : extractExitCode(text)
      const signals = parseSignals({ cmd, text, exit })
      for (const s of signals) {
        const taskId = this.stackTop()?.task_id ?? s.detail?.task_id ?? this.taskId
        const env = {
          ...this.stackPayload(),
          session_id: this.sessionId,
          model_id: this.lastModel ?? "",
          task_id: taskId,
          attempt_id: this.attempts.current(taskId),
        }
        this.emitTaxonomy(s.event, s.detail, env)
        if (s.event === EVENTS.TASK_COMPLETED) this.attempts.close(taskId)
      }
    }
  }

  sessionCreated() {}
  compacted() {}

  snapshot() {
    return {
      agents: JSON.parse(JSON.stringify(this.agents)),
      taxonomy_events: this.taxonomy_events.map((e) => ({ ...e })),
    }
  }
}
// === Op dispatcher (drives plugin hook AND simulator from one op) ===
// Every op carries the canonical shape the plugin's hooks expect. The plugin
// and simulator receive SEPARATE output objects so the plugin's in-place
// POLL_VIOLATION annotation can never leak into the expected side.
async function runOp(hooks, sim, o) {
  switch (o.k) {
    case "cp": {
      const input = { model: { modelID: o.model }, provider: { providerID: o.provider } }
      if (o.agent) input.agent = o.agent
      await hooks["chat.params"](input)
      sim.cp(input)
      return
    }
    case "msg": {
      const info = { id: o.id, tokens: o.tokens }
      if (o.agent !== undefined) info.agent = o.agent
      await hooks.event({ event: { type: "message.updated", properties: { info } } })
      sim.msg(info)
      return
    }
    case "task_open": {
      await hooks["tool.execute.before"](o.input)
      sim.toolBefore(o.input)
      return
    }
    case "task_close": {
      const input = { tool: "task", callID: o.callID }
      const hookOut = { output: o.output }
      const simOut = { output: o.output }
      await hooks["tool.execute.after"](input, hookOut)
      sim.toolAfter(input, simOut)
      return
    }
    case "bash": {
      const input = { tool: "bash", callID: o.callID, args: { command: o.cmd } }
      const hookOut = { output: o.text }
      const simOut = { output: o.text }
      if (o.exit !== undefined) {
        hookOut.exit = o.exit
        simOut.exit = o.exit
      }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, hookOut)
      sim.toolAfter(input, simOut)
      return
    }
    case "read": {
      const input = { tool: "read", callID: o.callID }
      const out = { output: o.text ?? "file content" }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, out)
      sim.toolAfter(input, { output: out.output })
      return
    }
    case "skill": {
      const input = { tool: "skill", callID: o.callID, args: { name: o.name } }
      const out = { output: "loaded" }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, out)
      sim.toolAfter(input, { output: out.output })
      return
    }
    case "bg": {
      const args = { task_id: o.task_id }
      if (o.block) args.block = true
      const input = { tool: "background_output", callID: o.callID, args }
      const hookOut = { output: o.text }
      const simOut = { output: o.text }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, hookOut)
      sim.toolAfter(input, simOut)
      return
    }
    case "bg_cancel": {
      const input = { tool: "background_cancel", callID: o.callID, args: { taskId: o.taskId } }
      const out = { output: "cancelled" }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, out)
      sim.toolAfter(input, { output: out.output })
      return
    }
    case "ctx": {
      const input = { tool: "context-builder", callID: o.callID }
      const out = { output: JSON.stringify(o.payload) }
      await hooks["tool.execute.before"](input)
      sim.toolBefore(input)
      await hooks["tool.execute.after"](input, out)
      sim.toolAfter(input, { output: out.output })
      return
    }
    default:
      throw new Error(`unknown op kind: ${o?.k}`)
  }
}

// === Snapshot capture helper ===
// The last captured write-telemetry command must be the flush we just asked
// for. A zero-payload capture or a wrong kind is an anomaly (exit 2).
function takeEmitted(emitted, expectedKind) {
  if (emitted.length === 0) throw new Error("no emitted payload captured")
  const e = emitted[emitted.length - 1]
  if (!e.payload) throw new Error("write-telemetry payload failed to parse")
  if (e.payload.kind !== expectedKind) {
    throw new Error(`expected ${expectedKind} payload, got ${e.payload.kind}`)
  }
  return e.payload
}

// === Run one session: fresh plugin instance + simulator, drive steps ===
async function runSession(session) {
  const { dollar, emitted } = makeDollar()
  const hooks = await TelemetryPlugin({ $: dollar })
  const sim = new Simulator(session.id)
  const expSnaps = []
  const obsSnaps = []
  let ok = true
  let anomaly = ""
  try {
    await hooks.event({ event: { type: "session.created", properties: { info: { id: session.id } } } })
    sim.sessionCreated()
    expSnaps.push(sim.snapshot())
    obsSnaps.push(takeEmitted(emitted, "started"))
    for (const op of session.steps) {
      if (op.k === "flush") {
        await hooks.event({ event: { type: "session.compacted", properties: {} } })
        sim.compacted()
        expSnaps.push(sim.snapshot())
        obsSnaps.push(takeEmitted(emitted, "heartbeat"))
      } else {
        await runOp(hooks, sim, op)
      }
    }
  } catch (err) {
    ok = false
    anomaly = String(err?.stack ?? err)
  } finally {
    // Always terminate the session so the heartbeat interval is cleared
    // (otherwise node --test would hang on a live timer).
    try { await hooks.event({ event: { type: "session.idle", properties: {} } }) } catch {}
    if (ok) {
      try {
        expSnaps.push(sim.snapshot())
        obsSnaps.push(takeEmitted(emitted, "final"))
      } catch (err) {
        ok = false
        anomaly = String(err?.stack ?? err)
      }
    }
  }
  return { session, expSnaps, obsSnaps, ok, anomaly, cmds: emitted.map((e) => e.cmd) }
}

// === Scripted corpus: the nine adversarial scenarios ===
// Each session isolates one defect class from the Sep-7 post-mortem so a
// regression names the scenario, not just a unit diff.
function sess(id, steps) {
  return { id, scripted: true, steps }
}
// The task-tool hook input carries args at input.args (json-shape), at
// input.input (Sep-7 defect: the runtime delivered them nested), or spread
// directly on the input object (flat). All three must resolve identically.
const taskOpen = (callID, args, shape = "args") => {
  const input = shape === "nested"
    ? { tool: "task", callID, input: args }
    : shape === "flat"
      ? { tool: "task", callID, ...args }
      : { tool: "task", callID, args }
  return { k: "task_open", callID, input }
}
const taskClose = (callID, output) => ({ k: "task_close", callID, output })
const cp = (model, provider) => ({ k: "cp", model, provider })
const msg = (id, tokens, agent) => ({ k: "msg", id, tokens, agent })
const bash = (callID, cmd, text, exit) => ({ k: "bash", callID, cmd, text, exit })
const read = (callID, text) => ({ k: "read", callID, text })
const skill = (callID, name) => ({ k: "skill", callID, name })
const bg = (callID, task_id, text) => ({ k: "bg", callID, task_id, text })
const bgCancel = (callID, taskId) => ({ k: "bg_cancel", callID, taskId })
const ctx = (callID, payload) => ({ k: "ctx", callID, payload })
const flush = () => ({ k: "flush" })

function buildScriptedCorpus() {
  return [
    // S1 lead-only: chat.params + streaming tokens + test failure + read, all team-lead.
    sess("ses_a1", [
      cp("m1", "p1"),
      msg("ap-a-1", { input: 150, output: 80, reasoning: 10, cache_read: 0, cache_write: 0 }),
      bash("c-a1", "npm test", "1 failing test\n  FAIL  test/foo.test.js\n  exit code 1", 1),
      read("c-a2"),
      msg("ap-a-1", { input: 300, output: 200, reasoning: 10, cache_read: 0, cache_write: 0 }),
    ]),
    // S2 single delegate via subagent_type AND category; bg snapshot survives pop.
    sess("ses_a2", [
      taskOpen("c-a2-1", { subagent_type: "deep", task_id: "T-D1", description: "deep corpus" }),
      taskClose("c-a2-1", "done"),
      msg("ap-b-1", { input: 500, output: 320, reasoning: 40, cache_read: 100, cache_write: 0 }),
      taskOpen("c-a2-2", { category: "deep", task_id: "T-D2" }),
      msg("ap-b-2", { input: 900, output: 540, reasoning: 60, cache_read: 200, cache_write: 40 }),
      read("c-b3"),
      taskClose("c-a2-2", "bg_d2x1"),
      bg("c-b4", "bg_d2x1", "Duration: 4.2s"),
      flush(),
      msg("ap-b-3", { input: 300, output: 100, reasoning: 0, cache_read: 0, cache_write: 0 }),
    ]),
    // S3 nested explore -> oracle: no attempt for nested; pops restore parents.
    sess("ses_a3", [
      taskOpen("c-a3-1", { subagent_type: "explore", task_id: "T-E1", description: "nested" }),
      taskOpen("c-a3-2", { subagent_type: "oracle", task_id: "T-O1" }),
      msg("ap-c-1", { input: 700, output: 400, reasoning: 30, cache_read: 150, cache_write: 20 }),
      read("c-c1"),
      taskClose("c-a3-2", "ok"),
      msg("ap-c-2", { input: 450, output: 210, reasoning: 25, cache_read: 80, cache_write: 0 }),
      taskClose("c-a3-1", "ok"),
    ]),
    // S4 poll vs collect vs unregistered bg id; bg_cancel.
    sess("ses_a4", [
      taskOpen("c-a4-1", { subagent_type: "librarian", task_id: "T-L1" }),
      taskClose("c-a4-1", "bg_l1a9"),
      bg("c-b1", "bg_l1a9", "still running Status: running"),
      read("c-b2"),
      bg("c-b3", "bg_never9", "Duration: 1.0s"),
      bgCancel("c-b4", "bg_l1a9"),
    ]),
    // S5 Sep-7 nested args shape (input.input), flat object, plain json args.
    sess("ses_a5", [
      taskOpen("c-a5-1", { subagent_type: "librarian", task_id: "T-L2", description: "nested args" }, "nested"),
      msg("ap-e-1", { input: 600, output: 250, reasoning: 20, cache_read: 90, cache_write: 10 }),
      taskClose("c-a5-1", "ok"),
      taskOpen("c-a5-2", { subagent_type: "quick", task_id: "T-Q1" }, "flat"),
      taskClose("c-a5-2", "ok"),
      taskOpen("c-a5-3", { subagent_type: "oracle", task_id: "T-F1", description: "plain" }),
      taskClose("c-a5-3", "ok"),
    ]),
    // S6 fallback gate lifecycle on an EMPTY stack (attribution_confidence fallback).
    sess("ses_a6", [
      bash("c-b1", "bash framework/gates/g8_blockers.sh", "[gate] g8 result=pass exit=0 ms=3"),
      bash("c-b2", "bash framework/gates/g6_browser.sh", "[gate] g6 result=fail exit=1 ms=4"),
      bash("c-b3", "bash framework/gates/g4_contracts.sh", "[gate] g4 result=not_reached"),
    ]),
    // S7 retry derivation + TASK_COMPLETED closes the attempt (retryless reopen).
    sess("ses_a7", [
      taskOpen("c-a7-1", { subagent_type: "quick", task_id: "T-R1" }),
      taskClose("c-a7-1", "ok"),
      taskOpen("c-a7-2", { subagent_type: "quick", task_id: "T-R1" }),
      taskClose("c-a7-2", "ok"),
      flush(),
      bash("c-b1", 'python3 framework/adapters/gsd_state.py task-event --json {"task_id": "T-R1"}',
        '{"state": "COMPLETED", "task_id": "T-R1"}'),
      taskOpen("c-a7-3", { subagent_type: "quick", task_id: "T-R1" }),
      taskClose("c-a7-3", "ok"),
    ]),
    // S8 category "none" -> subagent_type fallback; unknown category -> raw string.
    sess("ses_a8", [
      taskOpen("c-a8-1", { category: "none", subagent_type: "oracle", task_id: "T-N1" }),
      taskClose("c-a8-1", "ok"),
      taskOpen("c-a8-2", { category: "bogus", task_id: "T-U1" }),
      taskClose("c-a8-2", "ok"),
      taskOpen("c-a8-3", { agent: "custom-ag", task_id: "T-U2" }),
      taskClose("c-a8-3", "ok"),
    ]),
    // S9 3-level nesting; TASK_COMPLETED for a nested id is a no-op close; reopen after complete.
    sess("ses_a9", [
      taskOpen("c-a9-1", { subagent_type: "explore", task_id: "T-E9" }),
      taskOpen("c-a9-2", { subagent_type: "deep", task_id: "T-D9" }),
      taskOpen("c-a9-3", { subagent_type: "oracle", task_id: "T-O9" }),
      msg("ap-9-1", { input: 800, output: 460, reasoning: 50, cache_read: 180, cache_write: 30 }),
      taskClose("c-a9-3", "ok"),
      taskClose("c-a9-2", "ok"),
      msg("ap-9-2", { input: 350, output: 150, reasoning: 15, cache_read: 0, cache_write: 0 }),
      taskClose("c-a9-1", "ok"),
      flush(),
      bash("c-b1", 'python3 framework/adapters/gsd_state.py task-event --json {"task_id": "T-E9"}',
        '{"state": "COMPLETED", "task_id": "T-E9"}'),
      taskOpen("c-a9-4", { subagent_type: "explore", task_id: "T-E9" }),
      taskClose("c-a9-4", "ok"),
    ]),
  ]
}
// === Seeded random corpus ===
// Deterministic (mulberry32) so two runs of the suite with the same seed must
// produce byte-identical units. Weights push the mix toward the failure modes
// the metric exists to catch: delegation frames, token attribution inside and
// outside frames, gate lifecycles, retries, and background snapshots.
function buildRandomCorpus(rnd, count) {
  const AGENT_SPECS = [
    { subagent_type: "explore" },
    { subagent_type: "librarian" },
    { subagent_type: "oracle" },
    { category: "deep" },
    { category: "quick" },
    { category: "visual-engineering" },
    { category: "unspecified-high" },
    { category: "writing" },
    { category: "none", subagent_type: "oracle" },
    { agent: "custom-ag" },
  ]
  const GATES = [
    { id: "g1", result: "pass" },
    { id: "g3", result: "pass" },
    { id: "g5", result: "unverifiable" },
    { id: "g8", result: "fail" },
    { id: "g12", result: "pass" },
    { id: "g_tool_readiness", result: "pass" },
  ]
  const GATE_SCRIPTS = {
    g1: "framework/gates/g1_taxonomy.sh",
    g3: "framework/gates/g3_architecture.sh",
    g5: "framework/gates/g5_frontend_stack.sh",
    g8: "framework/gates/g8_blockers.sh",
    g12: "framework/gates/g12_provider.sh",
    g_tool_readiness: "framework/gates/g_tool_readiness.sh",
  }
  const RUNNERS = ["pytest", "npm test", "node --test"]
  const sessions = []
  for (let i = 0; i < count; i++) {
    const steps = []
    let seq = 0
    const topLevelIds = []
    const bgPool = []
    let depth = 0
    const nOps = 10 + Math.floor(rnd() * 13)
    const pickSpec = () => AGENT_SPECS[Math.floor(rnd() * AGENT_SPECS.length)]
    const emitNested = () => {
      const spec = pickSpec()
      const callID = `c-r${seq++}`
      const tid = `T-r${i + 1}-n${steps.length}`
      steps.push({ k: "task_open", callID, input: { tool: "task", callID, args: { ...spec, task_id: tid, description: "rand nested" } } })
      depth++
      const inner = 2 + Math.floor(rnd() * 3)
      for (let j = 0; j < inner; j++) emitOne()
      depth--
      steps.push({ k: "task_close", callID, output: "ok" })
    }
    const emitOne = () => {
      const pick = rnd()
      if (pick < 0.24 && depth < 2) {
        const spec = pickSpec()
        const callID = `c-r${seq++}`
        let tid
        let launch = false
        if (depth === 0 && topLevelIds.length > 0 && rnd() < 0.25) {
          tid = topLevelIds[Math.floor(rnd() * topLevelIds.length)] // retry reuse
        } else {
          tid = `T-r${i + 1}-${steps.length}`
          if (depth === 0) topLevelIds.push(tid)
        }
        if (depth === 0 && rnd() < 0.2) launch = true
        const ident = launch ? `bg_r${i + 1}_${bgPool.length + 1}` : "ok"
        steps.push({ k: "task_open", callID, input: { tool: "task", callID, args: { ...spec, task_id: tid, description: "rand task" } } })
        depth++
        steps.push({ k: "task_close", callID, output: ident })
        depth--
        if (launch) bgPool.push(ident)
      } else if (pick >= 0.24 && pick < 0.46) {
        const tokens = {
          input: 100 + Math.floor(rnd() * 800),
          output: 50 + Math.floor(rnd() * 350),
          reasoning: Math.floor(rnd() * 61),
          cache_read: Math.floor(rnd() * 501),
          cache_write: Math.floor(rnd() * 201),
        }
        const agentField = depth === 0 && rnd() < 0.15 ? "custom-m-agt" : undefined
        steps.push({ k: "msg", id: `m-r${i + 1}-${steps.length}`, tokens, agent: agentField })
      } else if (pick >= 0.46 && pick < 0.64) {
        const kind = rnd()
        if (kind < 0.3) {
          const g = GATES[Math.floor(rnd() * GATES.length)]
          const exit = g.result === "pass" ? 0 : (g.result === "unverifiable" ? 3 : 1)
          steps.push({
            k: "bash", callID: `c-r${seq++}`,
            cmd: `bash ${GATE_SCRIPTS[g.id]}`,
            text: `[gate] ${g.id} result=${g.result} exit=${exit} ms=${1 + Math.floor(rnd() * 9)}`,
            exit,
          })
        } else if (kind < 0.5) {
          const runner = RUNNERS[Math.floor(rnd() * RUNNERS.length)]
          steps.push({ k: "bash", callID: `c-r${seq++}`, cmd: runner, text: "2 failing tests\n  FAIL  test/spec.js\n  exit code 1", exit: 1 })
        } else if (kind < 0.65) {
          const tid = topLevelIds.length ? topLevelIds[Math.floor(rnd() * topLevelIds.length)] : `T-r${i + 1}-9`
          steps.push({
            k: "bash", callID: `c-r${seq++}`,
            cmd: 'python3 framework/adapters/gsd_state.py task-event --json {"task_id": "' + tid + '"}',
            text: '{"state": "COMPLETED", "task_id": "' + tid + '"}',
          })
        } else if (kind < 0.78) {
          const tid = `T-r${i + 1}-x`
          steps.push({
            k: "bash", callID: `c-r${seq++}`,
            cmd: 'python3 framework/adapters/gsd_state.py write-blocker --json {"signal": "CONTEXT_INSUFFICIENT", "task_id": "' + tid + '", "missing_item": "map", "agent": "test"}',
            text: "BLOCKER_OPEN CONTEXT_INSUFFICIENT BLK-001\nblocker written",
            exit: 0,
          })
        } else if (kind < 0.88) {
          steps.push({ k: "bash", callID: `c-r${seq++}`, cmd: "opencode --agent reviewer check", text: "REVIEW_REJECTED: found 3 findings" })
        } else {
          steps.push({ k: "bash", callID: `c-r${seq++}`, cmd: "node framework/opencode/plugin/attribution_harness.mjs --seed 1", text: "ok" })
        }
      } else if (pick >= 0.64 && pick < 0.73) {
        const tid = bgPool.length && rnd() < 0.85 ? bgPool[Math.floor(rnd() * bgPool.length)] : `bg_r${i + 1}_x`
        const poll = rnd() < 0.3
        steps.push({ k: "bg", callID: `c-r${seq++}`, task_id: tid, text: poll ? "still running Status: running" : "Duration: 3.3s" })
      } else if (pick >= 0.73 && pick < 0.82) {
        steps.push({ k: "read", callID: `c-r${seq++}` })
      } else if (pick >= 0.82 && pick < 0.88) {
        const mid = 1 + Math.floor(rnd() * 3)
        steps.push({ k: "cp", model: `m${mid}`, provider: "p1" })
      } else if (pick >= 0.88 && pick < 0.93) {
        steps.push({ k: "skill", callID: `c-r${seq++}`, name: "frontend-react" })
      } else if (pick >= 0.93 && pick < 0.97) {
        steps.push({ k: "ctx", callID: `c-r${seq++}`, payload: { provider_tier: 1, materialised_chars: 1234, truncated: [], level: "targeted" } })
      } else {
        const tid = bgPool.length ? bgPool[Math.floor(rnd() * bgPool.length)] : "bg_r0"
        steps.push({ k: "bg_cancel", callID: `c-r${seq++}`, taskId: tid })
      }
    }
    while (steps.length < nOps) {
      if (depth < 2 && rnd() < 0.18) emitNested()
      else emitOne()
    }
    if (rnd() < 0.4 && steps.length > 4) {
      const at = Math.floor(steps.length / 2)
      steps.splice(at, 0, flush())
    }
    sessions.push({ id: `ses_r${i + 1}`, scripted: false, steps })
  }
  return sessions
}

// === Suite: run everything, score, report ===
export async function runAttributionSuite({ seed = DEFAULT_SEED, randomSessions = 30 } = {}) {
  const rnd = mulberry32(seed)
  const sessions = [...buildScriptedCorpus(), ...buildRandomCorpus(rnd, randomSessions)]
  const expUnits = new Map()
  const obsUnits = new Map()
  const anomalies = []
  let flushCount = 0

  for (const session of sessions) {
    const s = await runSession(session)
    if (!s.ok) {
      anomalies.push({ session: session.id, detail: s.anomaly })
      continue
    }
    for (const cmd of s.cmds) {
      if (!cmd.startsWith("python3 framework/adapters/gsd_state.py write-telemetry")) {
        anomalies.push({ session: session.id, detail: `unexpected host command: ${cmd.slice(0, 80)}` })
      }
    }
    if (s.expSnaps.length !== s.obsSnaps.length) {
      anomalies.push({ session: session.id, detail: `snapshot count mismatch exp=${s.expSnaps.length} obs=${s.obsSnaps.length}` })
      continue
    }
    if (s.expSnaps.length < 2) {
      anomalies.push({ session: session.id, detail: "no snapshot pairs" })
      continue
    }
    for (let i = 1; i < s.expSnaps.length; i++) {
      const e = diffUnits(s.expSnaps[i - 1], s.expSnaps[i])
      const o = diffUnits(s.obsSnaps[i - 1], s.obsSnaps[i])
      mergeUnits(expUnits, e)
      mergeUnits(obsUnits, o)
      flushCount++
    }
  }

  let inter = 0
  let totalUnits = 0
  const mismatchKeys = []
  const keys = new Set([...expUnits.keys(), ...obsUnits.keys()])
  for (const k of keys) {
    const ev = Math.max(0, expUnits.get(k) ?? 0)
    const ov = Math.max(0, obsUnits.get(k) ?? 0)
    inter += Math.min(ev, ov)
    totalUnits += Math.max(ev, ov)
    if (ev !== ov) mismatchKeys.push({ key: k, expected: ev, observed: ov })
  }
  const accuracy = totalUnits > 0 ? inter / totalUnits : 1

  mismatchKeys.sort((a, b) => Math.abs(b.observed - b.expected) - Math.abs(a.observed - a.expected))

  let exitCode
  if (anomalies.length > 0) exitCode = 2
  else if (flushCount === 0) exitCode = 3
  else if (accuracy >= THRESHOLD && totalUnits >= MIN_UNITS) exitCode = 0
  else exitCode = 1

  return {
    seed,
    accuracy,
    totalUnits,
    inter,
    mismatchKeys,
    anomalies,
    exitCode,
    sessions: sessions.length,
    scripted: sessions.filter((s) => s.scripted).length,
    randomSessions,
    flushCount,
    minUnits: MIN_UNITS,
    threshold: THRESHOLD,
  }
}

// === CLI ===
function printHelp() {
  process.stdout.write(`attribution harness (synthetic-execution attribution metric)

Usage: node framework/opencode/plugin/attribution_harness.mjs [options]

Options:
  --seed N        PRNG seed for the random corpus (default ${DEFAULT_SEED})
  --sessions N    number of random sessions (default 30)
  --json          machine-readable result object
  --help          this message

Exit codes:
  0  pass (accuracy >= ${THRESHOLD} and units >= ${MIN_UNITS})
  1  below metric
  2  harness error (anomalies)
  3  nothing ran
`)
}

async function main() {
  const argv = process.argv.slice(2)
  const opts = { seed: DEFAULT_SEED, json: false, randomSessions: 30 }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--seed") opts.seed = Number(argv[++i])
    else if (argv[i] === "--sessions") opts.randomSessions = Number(argv[++i])
    else if (argv[i] === "--json") opts.json = true
    else if (argv[i] === "--help") { printHelp(); process.exit(0) }
  }
  const res = await runAttributionSuite({ seed: opts.seed, randomSessions: opts.randomSessions })
  const f = (x) => x.toFixed(6)
  process.stdout.write(`attribution suite: seed=${res.seed} sessions=${res.sessions} (scripted ${res.scripted}, random ${res.randomSessions}) flushPairs=${res.flushCount}\n`)
  process.stdout.write(`accuracy=${f(res.accuracy)} units=${res.totalUnits} (min ${res.minUnits}) threshold=${res.threshold}\n`)
  if (res.anomalies.length) {
    process.stdout.write(`ANOMALIES (${res.anomalies.length}):\n`)
    for (const a of res.anomalies.slice(0, 10)) {
      process.stdout.write(`  ${a.session}: ${a.detail.split("\n")[0]}\n`)
    }
  }
  if (res.mismatchKeys.length) {
    process.stdout.write(`MISMATCHED UNITS (${res.mismatchKeys.length}):\n`)
    for (const m of res.mismatchKeys.slice(0, 20)) {
      process.stdout.write(`  ${m.key} expected=${m.expected} observed=${m.observed}\n`)
    }
  }
  process.stdout.write(`exit ${res.exitCode}\n`)
  if (opts.json) {
    process.stdout.write(JSON.stringify(res, null, 2) + "\n")
  }
  process.exit(res.exitCode)
}

if (process.argv[1] && fileURLToPath(import.meta.url) === fileURLToPath(pathToFileURL(process.argv[1]).href)) {
  main()
}
