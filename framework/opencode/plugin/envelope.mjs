/**
 * Execution envelope — pure module for agent/task attribution via a hook-layer delegation stack.
 *
 * WHY .mjs: This module is framework-agnostic (no @opencode-ai/plugin import) so node:test
 * can import it directly without the opencode runtime. The telemetry plugin imports it too;
 * ES modules are the lingua franca between the two worlds.
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §4 (execution envelope).
 * Single source of truth for the category→agent resolution table; the telemetry plugin and
 * self-test both consume it through the exported resolveExecutionAgent().
 */

// ─── Task-tool args shape normalisation (Sep-7 attribution defect) ────────────

/**
 * Normalize task-tool hook input to a single args object. The task tool's
 * argument shape differs across OpenCode versions: args may arrive at
 * input.args, input.input, or input.arguments. Reads the FIRST present shape
 * and merges when several are objects (Sep-7 defect: 539/547 records
 * attributed "unknown" because input.args was undefined at runtime — the real
 * args were nested under input.input).
 *
 * When the input itself already carries the task fields (subagent_type /
 * category / agent / task_id / description) it is returned as-is, so callers
 * that pass a plain args object keep working.
 *
 * @param {object} input - Hook input (or a plain args object).
 * @returns {object} The merged args object (never null).
 */
export function normalizeTaskArgs(input = {}) {
  if (!input || typeof input !== "object") return {}
  const hasOwnFields = ["subagent_type", "category", "agent", "task_id", "description"]
    .some((k) => input[k] !== undefined)
  if (hasOwnFields) return input
  const shapes = [input.args, input.input, input.arguments]
  const present = shapes.filter((s) => s && typeof s === "object")
  if (present.length === 0) return {}
  // First-present shape wins conflicts; later shapes fill gaps.
  return Object.assign({}, ...[...present].reverse())
}

// ─── Category → actual agent resolution (§4 table) ───────────────────────────

/**
 * Map a raw agent/category/subagent_type string to its canonical execution_agent.
 * Resolution order per §4: subagent_type ?? category ?? agent ?? "unknown".
 * The mapping table is the single source of truth; both the plugin and self-test use it.
 *
 * The input is normalised through normalizeTaskArgs first, so the fields are
 * resolved from whichever runtime shape is present (args / input / arguments).
 *
 * @param {object} input - Hook input from the task tool invocation (or a plain
 *   args object carrying subagent_type / category / agent).
 * @returns {string} The resolved execution_agent name.
 */
export function resolveExecutionAgent(input = {}) {
  const args = normalizeTaskArgs(input)
  const raw = args.subagent_type ?? args.category ?? args.agent ?? "unknown"
  const name = String(raw).toLowerCase().trim()
  const CATEGORY_MAP = {
    "explore":          "explore",
    "librarian":        "librarian",
    "oracle":           "oracle",
    "ultrabrain":       "sisyphus-junior (ultrabrain)",
    "deep":             "sisyphus-junior (deep)",
    "quick":            "sisyphus-junior (quick)",
    "unspecified-high": "sisyphus-junior",
    "unspecified-low":  "sisyphus-junior",
    "visual-engineering": "sisyphus-junior (visual)",
    "writing":          "sisyphus-junior (writing)",
  }
  // "none" → fall through to subagent_type, else "unknown"
  if (name === "none") {
    const fallback = String(args.subagent_type ?? "unknown")
    return CATEGORY_MAP[fallback] ?? fallback
  }
  return CATEGORY_MAP[name] ?? String(raw)
}

// ─── Stack container (§4 hook-layer stack) ────────────────────────────────────

/**
 * Create an empty delegation stack. Each frame carries the identity fields required
 * by §4; the stack provides push/pop/top/current/payload-assembly semantics.
 *
 * @returns {object} A fresh stack instance.
 */
export function createStack() {
  const frames = []

  /** @returns {number} Number of frames on the stack. */
  const depth = () => frames.length

  /**
   * Push a new delegation frame. The caller's current_agent becomes the
   * delegated_agent of the new frame; the resolved execution_agent becomes
   * the frame's execution_agent and the new current_agent.
   *
   * @param {object} opts
   * @param {string} opts.execution_agent - Resolved agent name.
   * @param {string} opts.session_id - Current session id.
   * @param {string} opts.task_id - Task id (inherited from parent or env seed).
   * @returns {object} The pushed frame.
   */
  const push = ({ execution_agent, session_id, task_id }) => {
    const delegated_agent = top()?.execution_agent ?? "team-lead"
    const parent_task_id = top()?.task_id ?? ""
    const frame = {
      execution_agent,
      delegated_agent,
      session_id,
      task_id,
      parent_task_id,
      attribution_confidence: "stack",
    }
    frames.push(frame)
    return frame
  }

  /**
   * Pop the most recent frame and return it, or null if the stack is empty.
   * The caller should restore current_agent from the new top after popping.
   *
   * @returns {object|null} The popped frame, or null.
   */
  const pop = () => frames.length > 0 ? frames.pop() : null

  /** @returns {object|null} The top frame without removing it, or null. */
  const top = () => frames.length > 0 ? frames[frames.length - 1] : null

  /**
   * Return the current (top-of-stack) execution_agent, or "team-lead" if empty.
   *
   * @returns {string}
   */
  const current = () => top()?.execution_agent ?? "team-lead"

  /**
   * Build the envelope payload object for inclusion in the emitted record.
   * Fields match §4: task_id, parent_task_id, delegated_agent, execution_agent,
   * attribution_confidence.  attempt_id is reserved for P0-1 (set to null here).
   *
   * @param {object} [opts] - Override fields (e.g. fallback mode).
   * @returns {object} The envelope payload.
   */
  const payload = (opts = {}) => {
    const t = top()
    return {
      task_id:          t?.task_id          ?? opts.task_id          ?? "",
      parent_task_id:   t?.parent_task_id   ?? opts.parent_task_id   ?? "",
      delegated_agent:  t?.delegated_agent  ?? opts.delegated_agent  ?? "team-lead",
      execution_agent:  t?.execution_agent  ?? opts.execution_agent  ?? current(),
      attribution_confidence: t ? "stack" : (opts.attribution_confidence ?? "fallback"),
      attempt_id:       null,  // reserved for P0-1
    }
  }

  return { push, pop, top, current, depth, payload }
}

// ─── Convenience: fallback envelope ───────────────────────────────────────────

/**
 * Build a fallback envelope when no stack is active. §4: "events still recorded with
 * task_id: '', attempt_id: null, attribution_confidence: 'fallback' — never silently dropped."
 *
 * @param {object} [opts] - Optional overrides.
 * @returns {object}
 */
export function fallbackEnvelope(opts = {}) {
  return {
    task_id:                  opts.task_id                  ?? "",
    parent_task_id:           opts.parent_task_id           ?? "",
    delegated_agent:          opts.delegated_agent          ?? "team-lead",
    execution_agent:          opts.execution_agent          ?? "unknown",
    attribution_confidence:   "fallback",
    attempt_id:               null,
  }
}

// ─── Flush guard (defensive finalisation) ─────────────────────────────────────

/**
 * Idempotence guard for the telemetry final record. Only the FIRST terminal
 * event writes the final record; every subsequent finalisation is a no-op and
 * never writes twice (Sep-7 defect: 18/20 sessions unfinalized — the collector
 * now finalises on any terminal-ish event, so the guard is what keeps the
 * record single). Encapsulated here so the contract is testable without the
 * opencode runtime.
 *
 * @returns {{claim: () => boolean, isFlushed: () => boolean}}
 */
export function createFlushGuard() {
  let flushed = false
  return {
    /** @returns {boolean} true on the first call (proceed), false afterwards (no-op). */
    claim: () => {
      if (flushed) return false
      flushed = true
      return true
    },
    /** @returns {boolean} whether a final record has already been claimed. */
    isFlushed: () => flushed,
  }
}
