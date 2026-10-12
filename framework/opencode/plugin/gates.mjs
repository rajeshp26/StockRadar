/**
 * P0-3 gate accounting — pure module for the GATE_* lifecycle vocabulary, the
 * canonical [gate] protocol, and the four-state classifier.
 *
 * WHY .mjs: same rationale as envelope.mjs / taxonomy.mjs — framework-agnostic
 * (no @opencode-ai/plugin import) so node:test can import it directly without
 * the opencode runtime. The telemetry plugin imports it too.
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §5 (gate
 * accounting), §6 (invariants), §7 (self-tests / false-evidence matrix), §8
 * (migration); binding contract T-P0-3R.
 *
 * PURE FUNCTIONS ONLY — no side effects, no I/O, no mutation of caller state.
 */

// ─── Gate lifecycle vocabulary (§5) ───────────────────────────────────────────

/**
 * The canonical gate lifecycle vocabulary. Exactly the four events from plan
 * §5. Frozen so the vocabulary cannot drift between the plugin, the self-test,
 * and the report.
 */
export const GATE_EVENTS = Object.freeze({
  GATE_REQUIRED: "GATE_REQUIRED",                 // orchestration records gate X required for task (impact-derived)
  GATE_NOT_REACHED: "GATE_NOT_REACHED",           // explicit lifecycle disposal: an earlier condition prevented reaching the gate
  GATE_EXECUTION_STARTED: "GATE_EXECUTION_STARTED", // gate process launched
  GATE_RESULT: "GATE_RESULT",                     // canonical outcome (pass / fail / unverifiable)
})

/** All vocabulary event names, in canonical order. */
export const ALL_GATE_EVENTS = Object.freeze(Object.values(GATE_EVENTS))

// ─── Four-state semantics (§5, contract T-P0-3R) ──────────────────────────────

/**
 * The four gate states. Contract T-P0-3R names the vocabulary explicitly:
 * UNOBSERVED / NOT_REACHED / EXECUTED_PASS / EXECUTED_UNVERIFIABLE. A canonical
 * result of fail OR unverifiable classifies as EXECUTED_UNVERIFIABLE — the
 * state means "executed and never a pass"; the raw result (fail vs
 * unverifiable) is preserved in the GATE_RESULT event detail so the report can
 * still surface the distinction.
 *
 * Epistemic rule (§5 line 144): absence of evidence produces UNOBSERVED;
 * explicit lifecycle evidence produces NOT_REACHED. UNOBSERVED never collapses
 * into PASS or NOT_REACHED (§5 line 152).
 */
export const GATE_STATES = Object.freeze({
  NOT_REACHED: "NOT_REACHED",             // required + explicit GATE_NOT_REACHED lifecycle evidence
  EXECUTED_PASS: "EXECUTED_PASS",         // execution observed (GATE_EXECUTION_STARTED + GATE_RESULT), canonical result = pass
  EXECUTED_UNVERIFIABLE: "EXECUTED_UNVERIFIABLE", // execution observed, canonical result = fail | unverifiable (never a pass)
  UNOBSERVED: "UNOBSERVED",               // execution/result cannot be established from available evidence
})

/** Canonical result vocabulary for the [gate] line. */
export const GATE_RESULTS = Object.freeze({
  PASS: "pass",
  FAIL: "fail",
  UNVERIFIABLE: "unverifiable",
  NOT_REACHED: "not_reached",
  STARTED: "started", // tolerated Start variant (GATE_EXECUTION_STARTED marker)
  // Classified non-judgement verdicts (framework/gates/_lib.sh non_judgement).
  // None is a pass; all route to EXECUTED_UNVERIFIABLE via the existing
  // "anything other than pass" branch, so no fifth GATE_STATES member is needed.
  NOT_APPLICABLE: "not_applicable",
  PRECONDITION_MISSING: "precondition_missing",
  CAPABILITY_MISSING: "capability_missing",
})

// ─── Canonical [gate] protocol (§5) ───────────────────────────────────────────

/**
 * The canonical line, exactly as emitted by gates/_lib.sh:
 *   [gate] g8 result=pass exit=0 ms=123
 *   [gate] g9 result=not_applicable exit=4 ms=7 evidence={"changed_source_files": 0}
 * result ∈ pass | fail | unverifiable | not_reached | started | not_applicable
 * | precondition_missing | capability_missing. The three classified
 * non-judgement tokens are the result vocabulary of _lib.sh non_judgement;
 * the result token IS the reason_code, so no separate reason= field exists.
 * The Start variant is tolerated so a gate that announces its launch on the
 * same line still parses. exit/ms/evidence are optional — the not_reached
 * disposal line carries none of them.
 */
export const GATE_LINE_RE = /^\[gate\]\s+([A-Za-z0-9_-]+)\s+result=(pass|fail|unverifiable|not_applicable|precondition_missing|capability_missing|not_reached|started)(?:\s+exit=(\d+))?(?:\s+ms=(\d+))?(?:\s+evidence=(.+))?$/m

// Classified non-judgement tokens. A gate that emits one of these without
// evidence has not made a verdict, it has made an assertion — the parser
// refuses it so it lands in UNOBSERVED (never a pass) rather than recording a
// claim nothing supports. _lib.sh already hard-fails on missing evidence; this
// is the same invariant enforced on the reading side, for gates that do not go
// through _lib.sh.
const CLASSIFIED_NON_JUDGEMENT = new Set([
  GATE_RESULTS.NOT_APPLICABLE,
  GATE_RESULTS.PRECONDITION_MISSING,
  GATE_RESULTS.CAPABILITY_MISSING,
])

/**
 * Parse a canonical [gate] line. Canonical-only: a line that is not exactly
 * the protocol shape yields null (false-evidence refusal — a malformed line
 * must never manufacture a result).
 *
 * `evidence` is a key ONLY when the line carries it, so the four-key shape
 * asserted by gates.test.mjs for pre-existing lines is unchanged.
 *
 * @param {string} line
 * @returns {{name: string, result: string, exit: number|null, ms: number|null, evidence?: string}|null}
 */
export function parseGateLine(line) {
  const m = GATE_LINE_RE.exec(String(line ?? ""))
  if (!m) return null
  if (CLASSIFIED_NON_JUDGEMENT.has(m[2]) && m[5] === undefined) return null
  const parsed = {
    name: m[1],
    result: m[2],
    exit: m[3] !== undefined ? Number(m[3]) : null,
    ms: m[4] !== undefined ? Number(m[4]) : null,
  }
  if (m[5] !== undefined) parsed.evidence = m[5]
  return parsed
}

/**
 * Legacy filename-regex fallback (§5): the pre-canonical collector matched
 * `gates/g8_blockers.sh` → g8 via /gates\/(g[1-8])_/ and /gates\/(g1[01])_/.
 * Kept exactly as the legacy behavior — the canonical line is the fix for the
 * g9/g12 regex hole, not a widened fallback.
 */
export const LEGACY_GATE_RE = /gates\/(g[1-8])_|gates\/(g1[01])_/

/**
 * Broad gate-script launch detection: every gate on disk (g1..g13 plus the
 * g_tool_* scripts). Anchored to the command start so a grep/echo that merely
 * mentions a gate path is never read as a launch (false-evidence refusal).
 * Tolerates the invocation shapes used by the verifier: `bash
 * framework/gates/gN.sh`, `./framework/gates/gN.sh`, and the bare path. Used
 * by the .before hook to emit GATE_REQUIRED + GATE_EXECUTION_STARTED. The
 * legacy regex above stays the fallback for pre-canonical records.
 */
export const GATE_SCRIPT_RE = /^(?:bash\s+)?(?:\.\/)?framework\/gates\/(g[0-9]+(?:[-_][A-Za-z0-9_-]+)?|g_tool_[A-Za-z0-9_-]+)\.sh/

/**
 * Short gate id from a script name: g8_blockers.sh → g8, g6-browser.sh → g6,
 * g_tool_utilization.sh stays g_tool_utilization (no numeric short form).
 * Mirrors gate_id() in framework/gates/_lib.sh.
 *
 * @param {string} scriptName
 * @returns {string}
 */
export function shortGateId(scriptName) {
  const base = String(scriptName ?? "").replace(/\.sh$/, "")
  if (/^g[0-9]/.test(base)) return base.split(/[-_]/)[0]
  return base
}

/**
 * Detect a gate launch from a bash command line. Returns the short gate id or
 * null when the command does not invoke a gate script.
 *
 * @param {{cmd?: string}} obs
 * @returns {{gate: string}|null}
 */
export function parseGateLaunch({ cmd = "" }) {
  const m = GATE_SCRIPT_RE.exec(String(cmd ?? ""))
  if (!m) return null
  return { gate: shortGateId(m[1]) }
}

/**
 * GATE_REQUIRED — launch-observed: when a gate from the registry is launched
 * for the current task, orchestration records it as required (impact-derived
 * in the plan; the plugin observes the launch, which is the only implementable
 * registry read without filesystem access).
 *
 * @param {{cmd?: string}} obs
 * @returns {{event: string, detail: {gate: string}}|null}
 */
export function parseGateRequired({ cmd = "" }) {
  const launch = parseGateLaunch({ cmd })
  if (!launch) return null
  return { event: GATE_EVENTS.GATE_REQUIRED, detail: { gate: launch.gate } }
}

/**
 * GATE_EXECUTION_STARTED — the gate process launched.
 *
 * @param {{cmd?: string}} obs
 * @returns {{event: string, detail: {gate: string}}|null}
 */
export function parseGateExecutionStarted({ cmd = "" }) {
  const launch = parseGateLaunch({ cmd })
  if (!launch) return null
  return { event: GATE_EVENTS.GATE_EXECUTION_STARTED, detail: { gate: launch.gate } }
}

/**
 * GATE_RESULT — canonical outcome parsed from the [gate] line. result ∈
 * pass | fail | unverifiable. The not_reached and started variants are NOT
 * results — they belong to parseGateNotReached / parseGateExecutionStarted.
 *
 * @param {{cmd?: string, text?: string}} obs
 * @returns {{event: string, detail: {gate: string, result: string, exit: number|null, ms: number|null}}|null}
 */
export function parseGateResult({ cmd = "", text = "" }) {
  const line = parseGateLine(text)
  if (!line) return null
  if (line.result === GATE_RESULTS.NOT_REACHED || line.result === GATE_RESULTS.STARTED) return null
  return {
    event: GATE_EVENTS.GATE_RESULT,
    detail: { gate: line.name, result: line.result, exit: line.exit, ms: line.ms },
  }
}

/**
 * GATE_NOT_REACHED — explicit lifecycle disposal parsed from the canonical
 * `[gate] <id> result=not_reached` line. Never inferred from absence (§5 line
 * 139): only this explicit record produces the NOT_REACHED state.
 *
 * @param {{cmd?: string, text?: string}} obs
 * @returns {{event: string, detail: {gate: string}}|null}
 */
export function parseGateNotReached({ cmd = "", text = "" }) {
  const line = parseGateLine(text)
  if (!line || line.result !== GATE_RESULTS.NOT_REACHED) return null
  return { event: GATE_EVENTS.GATE_NOT_REACHED, detail: { gate: line.name } }
}

// ─── Four-state classifier (§5) ───────────────────────────────────────────────

/**
 * Classify one required gate from the events seen for its task.
 *
 * Transitions:
 * - explicit GATE_NOT_REACHED record        → NOT_REACHED (explicit lifecycle
 *   evidence wins; a contradictory execution record is a recording error and
 *   the deliberate disposition is the safer reading)
 * - GATE_EXECUTION_STARTED + GATE_RESULT:
 *     result = pass                         → EXECUTED_PASS
 *     result = fail | unverifiable          → EXECUTED_UNVERIFIABLE
 * - anything else (no evidence, malformed
 *   output, executed-but-unparseable,
 *   result without start, start without
 *   result)                                 → UNOBSERVED
 *
 * UNOBSERVED never collapses into PASS or NOT_REACHED (§5 line 152).
 *
 * @param {string} requiredName - the required gate id (e.g. "g8").
 * @param {Array<{event: string, detail: object}>} seenEvents - the task's
 *   taxonomy events (GATE_* subset is what matters).
 * @returns {string} one of GATE_STATES.
 */
export function gateState(requiredName, seenEvents) {
  const evs = Array.isArray(seenEvents) ? seenEvents : []
  const forGate = (event) =>
    evs.some((e) => e?.event === event && e?.detail?.gate === requiredName)
  if (forGate(GATE_EVENTS.GATE_NOT_REACHED)) return GATE_STATES.NOT_REACHED
  const started = forGate(GATE_EVENTS.GATE_EXECUTION_STARTED)
  const result = [...evs]
    .reverse()
    .find((e) => e?.event === GATE_EVENTS.GATE_RESULT && e?.detail?.gate === requiredName)
  if (started && result) {
    if (result.detail.result === GATE_RESULTS.PASS) return GATE_STATES.EXECUTED_PASS
    return GATE_STATES.EXECUTED_UNVERIFIABLE
  }
  return GATE_STATES.UNOBSERVED
}