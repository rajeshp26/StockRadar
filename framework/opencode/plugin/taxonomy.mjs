/**
 * P0-1 canonical taxonomy — pure module for the telemetry event vocabulary, the
 * runtime-owned attempt lifecycle, and the signal parsers that replace the dead
 * `/RETRY_(\w+)/` regex in telemetry.ts.
 *
 * WHY .mjs: same rationale as envelope.mjs — framework-agnostic (no
 * @opencode-ai/plugin import) so node:test can import it directly without the
 * opencode runtime. The telemetry plugin imports it too.
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §3 (taxonomy),
 * §4 (single authoritative owner of attempt identity), §6 (invariants), §7
 * (liveness / self-tests), §8 (migration).
 *
 * PURE FUNCTIONS ONLY — no side effects, no I/O, no mutation of caller state.
 * The attempt registry is the ONLY attempt counter; contract `retry_of` lineage
 * is never read as an attempt number (correlation/validation only, §4).
 */
import { parseGateResult, parseGateNotReached, GATE_SCRIPT_RE, shortGateId } from "./gates.mjs"

// ─── Event vocabulary (§3) ────────────────────────────────────────────────────

/**
 * The canonical taxonomy event vocabulary. Exactly the ten events from plan §3.
 * Frozen so the vocabulary cannot drift between the plugin, the self-test, and
 * the report.
 */
export const EVENTS = Object.freeze({
  WORK_ATTEMPTED:       "WORK_ATTEMPTED",       // delegated task opened by runtime supervision → opens attempt N
  TEST_FAILED:          "TEST_FAILED",          // pytest | npm test exit != 0
  REVIEW_REJECTED:      "REVIEW_REJECTED",      // review emitted rejection
  VERIFICATION_FAILED:  "VERIFICATION_FAILED",  // canonical gate result = fail
  INTEGRATION_FAILED:   "INTEGRATION_FAILED",   // cross-component test failure
  BLOCKER_DETECTED:     "BLOCKER_DETECTED",     // write-blocker call; carries signal name
  CONTEXT_INSUFFICIENT: "CONTEXT_INSUFFICIENT", // blocker signal; carries named missing item
  TASK_REOPENED:        "TASK_REOPENED",        // retro trigger written
  RETRY:                "RETRY",                // derived: new WORK_ATTEMPTED for same task with prior non-terminal
  TASK_COMPLETED:       "TASK_COMPLETED",       // COMPLETED event / final gate pass
})

/** All vocabulary event names, in canonical order. */
export const ALL_EVENTS = Object.freeze(Object.values(EVENTS))

// ─── Attempt lifecycle registry (§3 + §4) ────────────────────────────────────

/**
 * Create the runtime-owned attempt registry. Single authoritative owner of
 * `attempt_id` (§4): the registry is the ONLY attempt counter. Contract
 * `retry_of` lineage is correlation/validation only and is never read here.
 *
 * Semantics (§3 attempt lifecycle):
 * - `open(task_id)` opens attempt N for the task. If the previous attempt for
 *   that task is still open/unresolved, the new attempt is N+1 AND the caller
 *   must emit `RETRY` (the returned `retry` flag is the derived indication —
 *   it never decides attempt identity).
 * - `close(task_id)` resolves the open attempt (TASK_COMPLETED). A later
 *   `open` for the same task is then NOT a retry.
 * - `current(task_id)` returns the last opened attempt number, or null if the
 *   task was never opened.
 *
 * @returns {object} { open, close, current }
 */
export function createAttemptRegistry() {
  /** @type {Map<string, {current: number, open: boolean}>} */
  const attempts = new Map()

  /**
   * Open the next attempt for a task.
   * @param {string} task_id
   * @returns {{attempt_id: number, retry: boolean}} attempt_id = the new
   *   attempt number; retry = true iff the previous attempt was still open.
   */
  const open = (task_id) => {
    const key = String(task_id ?? "")
    const entry = attempts.get(key) ?? { current: 0, open: false }
    const retry = entry.open
    entry.current += 1
    entry.open = true
    attempts.set(key, entry)
    return { attempt_id: entry.current, retry }
  }

  /**
   * Resolve the open attempt for a task (TASK_COMPLETED). No-op when the task
   * has no open attempt.
   * @param {string} task_id
   * @returns {number|null} the closed attempt number, or null.
   */
  const close = (task_id) => {
    const key = String(task_id ?? "")
    const entry = attempts.get(key)
    if (!entry) return null
    entry.open = false
    return entry.current
  }

  /**
   * @param {string} task_id
   * @returns {number|null} the last opened attempt number, or null.
   */
  const current = (task_id) => {
    const key = String(task_id ?? "")
    const entry = attempts.get(key)
    return entry ? entry.current : null
  }

  return { open, close, current }
}

// ─── Event factory (§3 schema) ────────────────────────────────────────────────

/**
 * Build one raw taxonomy event in the exact §3 schema:
 * `{ts, session_id, task_id, attempt_id, parent_task_id, delegated_agent,
 *  execution_agent, model_id, event, detail}` plus the envelope's
 * `attribution_confidence` field.
 *
 * The envelope supplies the identity/attribution fields; `attempt_id` comes
 * from the attempt registry (the caller passes it in the envelope override).
 * When no envelope frame is active the event still records with
 * `attribution_confidence: "fallback"` — events are never silently dropped (§4).
 *
 * @param {object} opts
 * @param {string} opts.event - One of EVENTS.
 * @param {object} [opts.detail] - Free-form detail (signal name, gate id, ...).
 * @param {object} [opts.envelope] - Envelope fields (task_id, session_id, ...).
 * @param {string} [opts.ts] - ISO timestamp; defaults to now.
 * @returns {object} The full event record.
 */
export function taxonomyEvent({ event, detail, envelope = {}, ts }) {
  return {
    ts: ts ?? new Date().toISOString(),
    session_id: envelope.session_id ?? "",
    task_id: envelope.task_id ?? "",
    attempt_id: envelope.attempt_id ?? null,
    parent_task_id: envelope.parent_task_id ?? "",
    delegated_agent: envelope.delegated_agent ?? "team-lead",
    execution_agent: envelope.execution_agent ?? "unknown",
    model_id: envelope.model_id ?? "",
    attribution_confidence: envelope.attribution_confidence ?? "fallback",
    event,
    detail: detail ?? {},
  }
}

// ─── Signal parsers (§3 table — replace the dead /RETRY_(\w+)/ regex) ─────────
// Each parser is a pure function over {cmd, text, exit} (the bash hook inputs)
// returning `{event, detail}` or null. Parsers never manufacture an event from
// absence of evidence — a non-signal input yields null (false-evidence refusal).

/** Extract a task id from a command line when the command carries one. */
function extractTaskId(cmd) {
  const json = cmd.match(/"task_id"\s*:\s*"([^"]+)"/)
  if (json) return json[1]
  const positional = cmd.match(/task-event\s+([A-Za-z0-9_.-]+)/)
  if (positional) return positional[1]
  return ""
}

/**
 * BLOCKER_DETECTED — `write-blocker` call; parse `"signal":"..."` (already
 * parsed today in telemetry.ts; refactored here, `blocker_signals` behavior
 * preserved). A FAIL line always vetoes.
 */
export function parseBlockerDetected({ cmd = "", text = "", exit }) {
  if (!cmd.includes("gsd_state.py write-blocker")) return null
  const ok = exit === 0 || /BLOCKER[_-][A-Za-z0-9]+/.test(text)
  if (!ok || /\bFAIL\b/.test(text)) return null
  const m = cmd.match(/"signal"\s*:\s*"([^"]+)"/)
  if (!m) return null
  return { event: EVENTS.BLOCKER_DETECTED, detail: { signal: m[1], task_id: extractTaskId(cmd) } }
}

/**
 * CONTEXT_INSUFFICIENT — a blocker whose signal is CONTEXT_INSUFFICIENT;
 * extends the blocker parse to capture the named `missing_item`.
 */
export function parseContextInsufficient({ cmd = "", text = "", exit }) {
  const b = parseBlockerDetected({ cmd, text, exit })
  if (!b || b.detail.signal !== "CONTEXT_INSUFFICIENT") return null
  const m = cmd.match(/"missing_item"\s*:\s*"([^"]+)"/)
  return {
    event: EVENTS.CONTEXT_INSUFFICIENT,
    detail: { signal: "CONTEXT_INSUFFICIENT", missing_item: m ? m[1] : "", task_id: extractTaskId(cmd) },
  }
}

/**
 * TEST_FAILED — pytest / npm test / node --test output containing a FAIL marker
 * with a non-zero exit. When the exit code is not exposed (undefined) the FAIL
 * marker in test output is accepted — a real runner never prints FAIL and exits
 * 0, and the invariant is "no taxonomy event silently disappears".
 */
export function parseTestFailed({ cmd = "", text = "", exit }) {
  const isTest = /pytest|npm test|node --test|vitest|jest|mocha/.test(cmd)
  if (!isTest) return null
  if (!/\bFAIL(?:ED|URES?)?\b/i.test(text)) return null
  if (typeof exit === "number" && exit === 0) return null
  return { event: EVENTS.TEST_FAILED, detail: { runner: "test", exit: typeof exit === "number" ? exit : null } }
}

/**
 * Extract a numeric exit code from tool output text when the hook does not
 * expose one (Sep-7 defect: TEST_FAILED events carried exit null even though
 * the runner printed the code). Patterns: "exit code N", "exit=N",
 * "process exited with code N". Returns null when no pattern matches — never
 * fabricates a code.
 *
 * @param {string} text - Tool output text.
 * @returns {number|null}
 */
export function extractExitCode(text) {
  const m = String(text ?? "").match(/(?:exit code|process exited with code)[:\s]+(\d+)|exit[=:\s]+(\d+)/i)
  if (!m) return null
  return Number(m[1] ?? m[2])
}

/**
 * POLL classification for background_output calls. An output reporting the
 * task as still running / pending means the call happened before the
 * system-reminder → POLL (the notification contract says end response and
 * wait). An output reporting completion/final content is a COLLECT. Requires
 * EXPLICIT running/pending evidence: the bare word "Duration" appears in every
 * completed-output summary and must never classify as a poll (Sep-7 defect:
 * 13 poll + 16 stale-bg false positives came from the /Duration/ alternative).
 *
 * @param {string} out - background_output tool output text.
 * @returns {boolean}
 */
export function isPollOutput(out) {
  return /still running|Pending|Status[^,;]*running|is still running/i.test(String(out ?? ""))
}

/**
 * VERIFICATION_FAILED — canonical `[gate] result=fail` line form. Parses what
 * exists today (the `[gN] FAIL` line from gates/_lib.sh log()) plus the
 * canonical `[gate] gN result=fail` form. Sep-7 defect: the legacy
 * /gates\/(g[1-8])_|g1[01]_/ gate-detection regex missed g9/g12/g13 and the
 * g_tool_* scripts, so VERIFICATION_FAILED was never emitted for them — the
 * detection now routes through gates.mjs GATE_SCRIPT_RE (the same code path
 * gates.test.mjs covers), and extracted gate ids normalise through shortGateId.
 */
export function parseVerificationFailed({ cmd = "", text = "" }) {
  const isGate = GATE_SCRIPT_RE.test(cmd)
  if (!isGate) return null
  const canonical = text.match(/\[gate\]\s+([A-Za-z0-9_-]+)\s+result=fail\b/)
  if (canonical) return { event: EVENTS.VERIFICATION_FAILED, detail: { gate: shortGateId(canonical[1]), result: "fail" } }
  const today = text.match(/\[([A-Za-z0-9_-]+)[^\]]*\]\s+FAIL\b/)
  if (today) return { event: EVENTS.VERIFICATION_FAILED, detail: { gate: shortGateId(today[1]), result: "fail" } }
  return null
}

/**
 * TASK_REOPENED — `g7_retro.sh` output carrying the RECURR marker on a FAIL
 * line ("FAIL  N recurring gap signature(s) — a previous fix did not close the
 * gap" → the task is effectively reopened). The marker must appear in a FAIL
 * context: the PASS line "no recurrence" also contains "recurr" and must never
 * manufacture a TASK_REOPENED (false-evidence refusal).
 */
export function parseTaskReopened({ cmd = "", text = "" }) {
  if (!cmd.includes("g7_retro.sh")) return null
  if (!/\bFAIL\b/i.test(text) || !/recurr/i.test(text)) return null
  return { event: EVENTS.TASK_REOPENED, detail: { source: "g7_retro.sh", marker: "RECURR" } }
}

/**
 * REVIEW_REJECTED — review tool invocation whose output carries a rejection
 * marker, or output that literally contains REVIEW_REJECTED.
 */
export function parseReviewRejected({ cmd = "", text = "" }) {
  const reviewTool = /review/i.test(cmd)
  const rejected = /REVIEW_REJECTED|rejected/i.test(text)
  if (!rejected) return null
  if (!reviewTool && !/REVIEW_REJECTED/.test(text)) return null
  return { event: EVENTS.REVIEW_REJECTED, detail: { source: reviewTool ? "review tool" : "REVIEW_REJECTED text" } }
}

/**
 * TASK_COMPLETED — the supervision lifecycle COMPLETED event written via
 * `gsd_state.py task-event` (output carries `"state": "COMPLETED"`). Carries
 * the task id from the command so the plugin can close the right attempt even
 * when no envelope frame is active.
 */
export function parseTaskCompleted({ cmd = "", text = "" }) {
  if (!cmd.includes("gsd_state.py task-event")) return null
  if (!/"state"\s*:\s*"COMPLETED"/.test(text)) return null
  return { event: EVENTS.TASK_COMPLETED, detail: { source: "task-event COMPLETED", task_id: extractTaskId(cmd) } }
}

/**
 * Dispatch every signal parser over one hook observation. Returns an array of
 * `{event, detail}` (possibly empty — a non-signal input never manufactures an
 * event). CONTEXT_INSUFFICIENT is a specialization of BLOCKER_DETECTED, so a
 * CONTEXT_INSUFFICIENT blocker yields both events.
 *
 * @param {object} obs - { cmd, text, exit } from the bash tool hook.
 * @returns {Array<{event: string, detail: object}>}
 */
export function parseSignals({ cmd = "", text = "", exit }) {
  const events = []
  const c = parseContextInsufficient({ cmd, text, exit })
  if (c) events.push(c)
  const b = parseBlockerDetected({ cmd, text, exit })
  if (b) events.push(b)
  const t = parseTestFailed({ cmd, text, exit })
  if (t) events.push(t)
  const v = parseVerificationFailed({ cmd, text })
  if (v) events.push(v)
  // P0-3: canonical [gate] lifecycle. The line is the protocol — parsed from
  // text regardless of cmd; a stray canonical line without a matched launch
  // still classifies UNOBSERVED (gateState requires GATE_EXECUTION_STARTED).
  // A fail line dual-fires VERIFICATION_FAILED (above) + GATE_RESULT (below) —
  // intentional: the taxonomy event drives rework routing, the GATE_RESULT
  // drives four-state accounting.
  const gr = parseGateResult({ cmd, text })
  if (gr) events.push(gr)
  const gnr = parseGateNotReached({ cmd, text })
  if (gnr) events.push(gnr)
  const r = parseTaskReopened({ cmd, text })
  if (r) events.push(r)
  const rr = parseReviewRejected({ cmd, text })
  if (rr) events.push(rr)
  const tc = parseTaskCompleted({ cmd, text })
  if (tc) events.push(tc)
  return events
}