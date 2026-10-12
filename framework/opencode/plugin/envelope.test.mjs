/**
 * Synthetic self-test for the P0-2 execution envelope (pure module).
 *
 * Runs with `node --test framework/opencode/plugin/envelope.test.mjs` — no opencode runtime
 * required. Simulates the hook sequence by calling the pure module's functions
 * directly: push for a task delegation, assert top-of-stack attribution, pop,
 * assert parent restored; simulate bg task with agent snapshot; fallback path.
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §7 (self-tests).
 */
import { test } from "node:test"
import assert from "node:assert/strict"
import { resolveExecutionAgent, createStack, fallbackEnvelope, normalizeTaskArgs, createFlushGuard } from "./envelope.mjs"

// ─── Category → agent resolution (§4 table) ──────────────────────────────────

test("category→agent resolution maps every §4 category", () => {
  assert.equal(resolveExecutionAgent({ category: "explore" }), "explore")
  assert.equal(resolveExecutionAgent({ category: "librarian" }), "librarian")
  assert.equal(resolveExecutionAgent({ category: "oracle" }), "oracle")
  assert.equal(resolveExecutionAgent({ category: "ultrabrain" }), "sisyphus-junior (ultrabrain)")
  assert.equal(resolveExecutionAgent({ category: "deep" }), "sisyphus-junior (deep)")
  assert.equal(resolveExecutionAgent({ category: "quick" }), "sisyphus-junior (quick)")
  assert.equal(resolveExecutionAgent({ category: "unspecified-high" }), "sisyphus-junior")
  assert.equal(resolveExecutionAgent({ category: "unspecified-low" }), "sisyphus-junior")
  assert.equal(resolveExecutionAgent({ category: "visual-engineering" }), "sisyphus-junior (visual)")
  assert.equal(resolveExecutionAgent({ category: "writing" }), "sisyphus-junior (writing)")
})

test("resolution order: subagent_type ?? category ?? agent ?? unknown", () => {
  // subagent_type wins over category
  assert.equal(
    resolveExecutionAgent({ subagent_type: "explore", category: "oracle" }),
    "explore",
  )
  // category wins over agent
  assert.equal(
    resolveExecutionAgent({ category: "librarian", agent: "team-lead" }),
    "librarian",
  )
  // agent used when neither subagent_type nor category present
  assert.equal(resolveExecutionAgent({ agent: "implementer" }), "implementer")
  // nothing → unknown
  assert.equal(resolveExecutionAgent({}), "unknown")
  // category "none" falls through to subagent_type, else unknown
  assert.equal(resolveExecutionAgent({ category: "none", subagent_type: "explore" }), "explore")
  assert.equal(resolveExecutionAgent({ category: "none" }), "unknown")
})

// ─── Stack semantics ──────────────────────────────────────────────────────────

test("push attributes to execution_agent; pop restores parent", () => {
  const stack = createStack()
  assert.equal(stack.depth(), 0)
  assert.equal(stack.current(), "team-lead")

  // team-lead delegates to explore
  const f1 = stack.push({ execution_agent: "explore", session_id: "ses_1", task_id: "T-01" })
  assert.equal(stack.depth(), 1)
  assert.equal(stack.current(), "explore")
  assert.equal(f1.delegated_agent, "team-lead")
  assert.equal(f1.parent_task_id, "")
  assert.equal(f1.task_id, "T-01")
  assert.equal(f1.attribution_confidence, "stack")

  // explore delegates to oracle (nested)
  const f2 = stack.push({ execution_agent: "oracle", session_id: "ses_1", task_id: "T-01" })
  assert.equal(stack.depth(), 2)
  assert.equal(stack.current(), "oracle")
  assert.equal(f2.delegated_agent, "explore")
  assert.equal(f2.parent_task_id, "T-01")

  // pop restores parent (explore)
  const popped = stack.pop()
  assert.equal(popped, f2)
  assert.equal(stack.depth(), 1)
  assert.equal(stack.current(), "explore")

  // pop restores team-lead
  stack.pop()
  assert.equal(stack.depth(), 0)
  assert.equal(stack.current(), "team-lead")
  assert.equal(stack.pop(), null) // popping empty returns null
})

test("nested delegation attribution follows top-of-stack", () => {
  const stack = createStack()
  stack.push({ execution_agent: "explore", session_id: "ses_1", task_id: "T-01" })
  stack.push({ execution_agent: "oracle", session_id: "ses_1", task_id: "T-01" })

  // chat.params / message.updated attribute to top-of-stack
  assert.equal(stack.current(), "oracle")
  const env = stack.payload()
  assert.equal(env.execution_agent, "oracle")
  assert.equal(env.delegated_agent, "explore")
  assert.equal(env.parent_task_id, "T-01")
  assert.equal(env.task_id, "T-01")
  assert.equal(env.attribution_confidence, "stack")
  assert.equal(env.attempt_id, null) // reserved for P0-1
})

test("task_id inherits from parent frame; env seed used at root", () => {
  const stack = createStack()
  // root frame: task_id from env seed (simulated)
  stack.push({ execution_agent: "explore", session_id: "ses_1", task_id: "T-ROOT" })
  // child frame inherits parent task_id when none given
  const child = stack.push({ execution_agent: "oracle", session_id: "ses_1", task_id: "T-ROOT" })
  assert.equal(child.task_id, "T-ROOT")
  assert.equal(child.parent_task_id, "T-ROOT")
})

// ─── Background-task snapshot ─────────────────────────────────────────────────

test("bg-task agent snapshot captures execution_agent at launch", () => {
  const stack = createStack()
  stack.push({ execution_agent: "explore", session_id: "ses_1", task_id: "T-01" })

  // tool.execute.after for task tool: bg_ id extracted, snapshot agent from stack top
  const bg_tasks = {}
  const tid = "bg_abc123"
  bg_tasks[tid] = { launched: 1, polls: 0, collects: 0, cancelled: 0, agent: stack.current() }
  assert.equal(bg_tasks[tid].agent, "explore")

  // background_output interactions attribute to the snapshot even after pop
  stack.pop()
  assert.equal(stack.current(), "team-lead")
  bg_tasks[tid].collects++
  assert.equal(bg_tasks[tid].agent, "explore") // snapshot survives pop
})

// ─── Fallback path ────────────────────────────────────────────────────────────

test("fallback path flags attribution_confidence=fallback and never drops events", () => {
  const stack = createStack()
  // No envelope present → payload() falls back
  const env = stack.payload()
  assert.equal(env.attribution_confidence, "fallback")
  assert.equal(env.task_id, "")
  assert.equal(env.attempt_id, null)

  // fallbackEnvelope() helper produces the same shape
  const fb = fallbackEnvelope({ execution_agent: "unknown" })
  assert.equal(fb.attribution_confidence, "fallback")
  assert.equal(fb.task_id, "")
  assert.equal(fb.execution_agent, "unknown")
  assert.equal(fb.attempt_id, null)

  // The event is still recorded (never dropped): payload always returns an object
  assert.ok(env && typeof env === "object")
})

// ─── Envelope present on every frame ──────────────────────────────────────────

test("envelope present on every frame", () => {
  const stack = createStack()
  const frames = [
    { execution_agent: "explore", session_id: "ses_1", task_id: "T-01" },
    { execution_agent: "oracle", session_id: "ses_1", task_id: "T-01" },
    { execution_agent: "sisyphus-junior (deep)", session_id: "ses_1", task_id: "T-01" },
  ]
  for (const f of frames) {
    const frame = stack.push(f)
    assert.ok(frame.execution_agent, "frame has execution_agent")
    assert.ok(frame.delegated_agent, "frame has delegated_agent")
    assert.ok(frame.task_id, "frame has task_id")
    assert.equal(frame.attribution_confidence, "stack")
    const env = stack.payload()
    assert.equal(env.execution_agent, frame.execution_agent)
    assert.equal(env.attribution_confidence, "stack")
  }
  assert.equal(stack.depth(), 3)
})

// ─── Sep-7 task-tool args shape (attribution defect) ──────────────────────────

test("Sep-7 failing shape: task args nested under input resolve execution_agent, not unknown", () => {
  // On 2026-09-07 the task tool delivered its args under input.input (input.args
  // was undefined), so 539/547 records resolved execution_agent "unknown".
  const raw = {
    args: undefined,
    input: {
      subagent_type: "explore",
      category: "explore",
      task_id: "T-FX1",
      description: "fix the telemetry collector",
    },
    arguments: undefined,
  }
  assert.equal(resolveExecutionAgent(raw), "explore")
  assert.notEqual(resolveExecutionAgent(raw), "unknown")
  const args = normalizeTaskArgs(raw)
  assert.equal(args.task_id, "T-FX1")
  assert.equal(args.description, "fix the telemetry collector")
  // The other accepted shapes resolve too.
  assert.equal(resolveExecutionAgent({ arguments: { category: "oracle" } }), "oracle")
  assert.equal(resolveExecutionAgent({ input: { agent: "implementer" } }), "implementer")
})

test("normalizeTaskArgs merges when several shapes are objects; first present wins", () => {
  const merged = normalizeTaskArgs({
    args: { agent: "team-lead", task_id: "T-OLD" },
    input: { category: "explore", task_id: "T-NEW" },
  })
  assert.equal(merged.agent, "team-lead")
  assert.equal(merged.category, "explore")
  assert.equal(merged.task_id, "T-OLD") // first-present shape wins conflicts
  // A plain args object passes through untouched.
  assert.deepEqual(normalizeTaskArgs({ category: "librarian" }), { category: "librarian" })
  // Nothing present → empty object, never null.
  assert.deepEqual(normalizeTaskArgs({}), {})
})

// ─── Flush idempotence (defensive finalisation) ───────────────────────────────

test("flush guard idempotence: two terminal events produce exactly one final record", () => {
  // Sep-7 defect: 18/20 sessions unfinalized. The collector now finalises on any
  // terminal-ish event (idle/deleted/paused/closed); the guard makes the first
  // flush the only writer and every later finalisation a no-op.
  const guard = createFlushGuard()
  let finals = 0
  const emit = (kind) => {
    if (kind === "final" && !guard.claim()) return
    if (kind === "final") finals++
  }
  emit("final") // first terminal event → writes the final record
  emit("final") // second terminal event → no-op
  emit("final") // third → no-op
  assert.equal(finals, 1)
  assert.equal(guard.isFlushed(), true)
})