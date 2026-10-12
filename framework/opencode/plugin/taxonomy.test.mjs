/**
 * Synthetic self-test for the P0-1 canonical taxonomy (pure module).
 *
 * Runs with `node --test framework/opencode/plugin/taxonomy.test.mjs` — no opencode
 * runtime required. Deliberately generates every taxonomy event and drives
 * every parser/emitter path, then asserts survival end-to-end: a taxonomy
 * event that is silently dropped fails the suite (the §7 liveness authority —
 * production zero counts are NO_OBSERVATIONS, never a liveness verdict).
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §3
 * (taxonomy), §4 (attempt ownership), §6 (invariants), §7 (self-tests),
 * §8 (migration).
 */
import { test } from "node:test"
import assert from "node:assert/strict"
import {
  EVENTS,
  ALL_EVENTS,
  createAttemptRegistry,
  taxonomyEvent,
  parseBlockerDetected,
  parseContextInsufficient,
  parseTestFailed,
  parseVerificationFailed,
  parseTaskReopened,
  parseReviewRejected,
  parseTaskCompleted,
  parseSignals,
  extractExitCode,
  isPollOutput,
} from "./taxonomy.mjs"

const TS = "2026-09-06T00:00:00.000Z"

// ─── Event vocabulary (§3) ───────────────────────────────────────────────────

test("vocabulary holds exactly the ten §3 events, frozen", () => {
  assert.deepEqual(
    [...ALL_EVENTS].sort(),
    [
      "BLOCKER_DETECTED", "CONTEXT_INSUFFICIENT", "INTEGRATION_FAILED",
      "RETRY", "REVIEW_REJECTED", "TASK_COMPLETED", "TASK_REOPENED",
      "TEST_FAILED", "VERIFICATION_FAILED", "WORK_ATTEMPTED",
    ].sort(),
  )
  assert.ok(Object.isFrozen(EVENTS))
  assert.ok(Object.isFrozen(ALL_EVENTS))
})

// ─── Attempt lifecycle (§3 + §4) ─────────────────────────────────────────────

test("attempt registry: open/close/current correctness", () => {
  const reg = createAttemptRegistry()
  assert.equal(reg.current("T-01"), null) // never opened
  assert.equal(reg.close("T-01"), null)   // closing never-opened is a no-op

  const a1 = reg.open("T-01")
  assert.equal(a1.attempt_id, 1)
  assert.equal(a1.retry, false)
  assert.equal(reg.current("T-01"), 1)

  assert.equal(reg.close("T-01"), 1)      // resolves attempt 1
  assert.equal(reg.current("T-01"), 1)    // last opened number is retained

  // A resolved attempt is not a retry: opening again after close → N+1, no RETRY.
  const a2 = reg.open("T-01")
  assert.equal(a2.attempt_id, 2)
  assert.equal(a2.retry, false)

  // Distinct tasks have independent chains.
  const b1 = reg.open("T-02")
  assert.equal(b1.attempt_id, 1)
  assert.equal(b1.retry, false)
})

test("RETRY is derived on N+1 when the prior attempt is still open", () => {
  const reg = createAttemptRegistry()
  const a1 = reg.open("T-01")
  assert.equal(a1.attempt_id, 1)
  assert.equal(a1.retry, false)

  // Second WORK_ATTEMPTED while attempt 1 is unresolved → N+1 AND RETRY.
  const a2 = reg.open("T-01")
  assert.equal(a2.attempt_id, 2)
  assert.equal(a2.retry, true)

  // Third, still unresolved → N+2 AND RETRY.
  const a3 = reg.open("T-01")
  assert.equal(a3.attempt_id, 3)
  assert.equal(a3.retry, true)

  // Resolving stops the retry derivation.
  reg.close("T-01")
  const a4 = reg.open("T-01")
  assert.equal(a4.attempt_id, 4)
  assert.equal(a4.retry, false)
})

// ─── §7 chain ────────────────────────────────────────────────────────────────

test("§7 chain: WORK_ATTEMPTED → TEST_FAILED → RETRY(WORK_ATTEMPTED#2) → TASK_COMPLETED", () => {
  const reg = createAttemptRegistry()
  const events = []
  const emit = (event, detail, envelope) =>
    events.push(taxonomyEvent({ event, detail, envelope, ts: TS }))

  // Attempt 1 opens.
  const a1 = reg.open("T-01")
  assert.equal(a1.attempt_id, 1)
  assert.equal(a1.retry, false)
  emit(EVENTS.WORK_ATTEMPTED, { execution_agent: "implementer" },
    { task_id: "T-01", attempt_id: a1.attempt_id, attribution_confidence: "stack" })

  // Test failure belongs to the open attempt 1.
  const tf = parseTestFailed({ cmd: "pytest tests", text: "FAILED tests/test_x.py", exit: 1 })
  assert.equal(tf.event, EVENTS.TEST_FAILED)
  emit(tf.event, tf.detail, { task_id: "T-01", attempt_id: reg.current("T-01"), attribution_confidence: "stack" })

  // Retry: attempt 2 opens AND RETRY is derived.
  const a2 = reg.open("T-01")
  assert.equal(a2.attempt_id, 2)
  assert.equal(a2.retry, true)
  emit(EVENTS.WORK_ATTEMPTED, { execution_agent: "implementer" },
    { task_id: "T-01", attempt_id: a2.attempt_id, attribution_confidence: "stack" })
  emit(EVENTS.RETRY, { previous_attempt: a2.attempt_id - 1 },
    { task_id: "T-01", attempt_id: a2.attempt_id, attribution_confidence: "stack" })

  // Completion closes attempt 2.
  const tc = parseTaskCompleted({
    cmd: "python3 framework/adapters/gsd_state.py task-event T-01 --json '{\"state\":\"COMPLETED\",\"emitter\":\"implementer\"}'",
    text: '"state": "COMPLETED"',
  })
  assert.equal(tc.event, EVENTS.TASK_COMPLETED)
  emit(tc.event, tc.detail, { task_id: "T-01", attempt_id: reg.current("T-01"), attribution_confidence: "stack" })
  reg.close("T-01")

  // The chain, in order, with correct attempt ownership.
  assert.deepEqual(events.map((e) => e.event), [
    EVENTS.WORK_ATTEMPTED, EVENTS.TEST_FAILED,
    EVENTS.WORK_ATTEMPTED, EVENTS.RETRY, EVENTS.TASK_COMPLETED,
  ])
  assert.equal(events[0].attempt_id, 1) // WORK_ATTEMPTED #1
  assert.equal(events[1].attempt_id, 1) // TEST_FAILED belongs to attempt 1
  assert.equal(events[2].attempt_id, 2) // WORK_ATTEMPTED #2
  assert.equal(events[3].attempt_id, 2) // RETRY carries the new attempt
  assert.equal(events[4].attempt_id, 2) // TASK_COMPLETED closes attempt 2
  assert.equal(events[3].detail.previous_attempt, 1)

  // After close, a fresh open is not a retry.
  const a3 = reg.open("T-01")
  assert.equal(a3.attempt_id, 3)
  assert.equal(a3.retry, false)
})

// ─── Every signal parser (§3 table) ──────────────────────────────────────────

test("every signal parser emits its taxonomy event from its own source", () => {
  const cases = [
    {
      fn: parseBlockerDetected,
      args: {
        cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"BLOCKED\",\"task_id\":\"T-01\",\"agent\":\"implementer\"}'",
        text: '{"id": "BLK-001", "retries": 1, "upserted": false}',
        exit: 0,
      },
      event: EVENTS.BLOCKER_DETECTED,
    },
    {
      fn: parseContextInsufficient,
      args: {
        cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"CONTEXT_INSUFFICIENT\",\"task_id\":\"T-01\",\"agent\":\"implementer\",\"missing_item\":\"the plan file\"}'",
        text: '{"id": "BLK-002", "retries": 1, "upserted": false}',
        exit: 0,
      },
      event: EVENTS.CONTEXT_INSUFFICIENT,
    },
    {
      fn: parseTestFailed,
      args: { cmd: "pytest tests", text: "FAILED tests/test_x.py - AssertionError", exit: 1 },
      event: EVENTS.TEST_FAILED,
    },
    {
      fn: parseVerificationFailed,
      args: { cmd: "bash framework/gates/g8_blockers.sh", text: "[g8_blockers] FAIL  open blocker", exit: 1 },
      event: EVENTS.VERIFICATION_FAILED,
    },
    {
      fn: parseTaskReopened,
      args: { cmd: "bash framework/gates/g7_retro.sh", text: "FAIL  1 recurring gap signature(s) — a previous fix did not close the gap", exit: 1 },
      event: EVENTS.TASK_REOPENED,
    },
    {
      fn: parseReviewRejected,
      args: { cmd: "review-work", text: "REVIEW_REJECTED: findings remain", exit: 1 },
      event: EVENTS.REVIEW_REJECTED,
    },
    {
      fn: parseTaskCompleted,
      args: {
        cmd: "python3 framework/adapters/gsd_state.py task-event T-01 --json '{\"state\":\"COMPLETED\",\"emitter\":\"implementer\"}'",
        text: '"state": "COMPLETED"',
      },
      event: EVENTS.TASK_COMPLETED,
    },
  ]
  for (const c of cases) {
    const ev = c.fn(c.args)
    assert.ok(ev, `${c.fn.name} returned null for its own source`)
    assert.equal(ev.event, c.event, `${c.fn.name} emitted the wrong event`)
  }
})

test("VERIFICATION_FAILED parses the canonical [gate] result=fail line", () => {
  const ev = parseVerificationFailed({
    cmd: "bash framework/gates/g8_blockers.sh",
    text: "[gate] g8 result=fail exit=1 ms=123",
  })
  assert.equal(ev.event, EVENTS.VERIFICATION_FAILED)
  assert.equal(ev.detail.gate, "g8")
  assert.equal(ev.detail.result, "fail")
})

test("VERIFICATION_FAILED fires for g9/g12/g_tool_* gates (Sep-7 regex hole)", () => {
  // The legacy /gates\/(g[1-8])_|g1[01]_/ detection regex missed these scripts,
  // so VERIFICATION_FAILED was never emitted for them on Sep 7. Detection now
  // routes through gates.mjs GATE_SCRIPT_RE; ids normalise through shortGateId.
  const ev9 = parseVerificationFailed({
    cmd: "framework/gates/g9_scope.sh deploy",
    text: "[gate] g9 result=fail exit=1 ms=5",
  })
  assert.equal(ev9.event, EVENTS.VERIFICATION_FAILED)
  assert.equal(ev9.detail.gate, "g9")
  const ev12 = parseVerificationFailed({
    cmd: "framework/gates/g12_provider.sh",
    text: "[g12_provider] FAIL  provider unhealthy",
  })
  assert.equal(ev12.event, EVENTS.VERIFICATION_FAILED)
  assert.equal(ev12.detail.gate, "g12")
  const evt = parseVerificationFailed({
    cmd: "framework/gates/g_tool_readiness.sh",
    text: "[g_tool_readiness] FAIL  tool missing",
  })
  assert.equal(evt.event, EVENTS.VERIFICATION_FAILED)
  assert.equal(evt.detail.gate, "g_tool_readiness")
})

test("TEST_FAILED exit captured from output text when the hook exit is null", () => {
  // Sep-7 defect: output.exit was null on TEST_FAILED events even though the
  // runner printed the code. The collector falls back to extractExitCode(text).
  const text = "FAILED tests/test_x.py - AssertionError\nprocess exited with code 1"
  const exit = extractExitCode(text)
  assert.equal(exit, 1)
  const ev = parseTestFailed({ cmd: "npm test", text, exit })
  assert.equal(ev.event, EVENTS.TEST_FAILED)
  assert.equal(ev.detail.exit, 1)
  // Other accepted patterns.
  assert.equal(extractExitCode("exit code 2"), 2)
  assert.equal(extractExitCode("exit=3"), 3)
  // No pattern → null, never fabricated.
  assert.equal(extractExitCode("Duration: 5.2s"), null)
  assert.equal(extractExitCode(""), null)
})

test("poll classification requires explicit running/pending evidence", () => {
  // Sep-7 defect: the bare /Duration/ alternative matched every completed-output
  // summary, so completed background tasks were misclassified as polls (13 poll
  // + 16 stale-bg false positives).
  assert.equal(isPollOutput("Duration: 5.2s"), false) // completed-output summary, NOT a poll
  assert.equal(isPollOutput("Task still running..."), true)
  assert.equal(isPollOutput("Status: running"), true)
  assert.equal(isPollOutput("Pending"), true)
  assert.equal(isPollOutput(""), false)
})

test("CONTEXT_INSUFFICIENT captures the named missing_item", () => {
  const ev = parseContextInsufficient({
    cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"CONTEXT_INSUFFICIENT\",\"task_id\":\"T-01\",\"agent\":\"implementer\",\"missing_item\":\"the plan file\"}'",
    text: '{"id": "BLK-002"}',
    exit: 0,
  })
  assert.equal(ev.event, EVENTS.CONTEXT_INSUFFICIENT)
  assert.equal(ev.detail.missing_item, "the plan file")
  assert.equal(ev.detail.signal, "CONTEXT_INSUFFICIENT")
})

test("BLOCKER_DETECTED keeps the blocker_signals behavior (signal name parsed)", () => {
  const ev = parseBlockerDetected({
    cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"TEST_FAILED\",\"task_id\":\"T-01\",\"agent\":\"implementer\"}'",
    text: '{"id": "BLK-003"}',
    exit: 0,
  })
  assert.equal(ev.event, EVENTS.BLOCKER_DETECTED)
  assert.equal(ev.detail.signal, "TEST_FAILED")
})

test("parseSignals dispatches every parser; a CONTEXT_INSUFFICIENT blocker yields both events", () => {
  const evs = parseSignals({
    cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"CONTEXT_INSUFFICIENT\",\"task_id\":\"T-01\",\"agent\":\"implementer\",\"missing_item\":\"plan\"}'",
    text: '{"id": "BLK-002"}',
    exit: 0,
  })
  const kinds = evs.map((e) => e.event)
  assert.ok(kinds.includes(EVENTS.BLOCKER_DETECTED))
  assert.ok(kinds.includes(EVENTS.CONTEXT_INSUFFICIENT))
})

// ─── False-evidence refusal (§7 matrix — no event → no inference) ────────────

test("parsers refuse to manufacture events from non-signals", () => {
  // Test runner passed → no TEST_FAILED.
  assert.equal(parseTestFailed({ cmd: "pytest tests", text: "1 passed", exit: 0 }), null)
  assert.equal(parseTestFailed({ cmd: "pytest tests", text: "1 passed", exit: undefined }), null)
  // Not a test command → no TEST_FAILED even with FAIL text.
  assert.equal(parseTestFailed({ cmd: "ls", text: "FAIL", exit: 1 }), null)
  // Gate passed → no VERIFICATION_FAILED (either line form).
  assert.equal(parseVerificationFailed({ cmd: "bash framework/gates/g8_blockers.sh", text: "[g8] PASS  all clear" }), null)
  assert.equal(parseVerificationFailed({ cmd: "bash framework/gates/g8_blockers.sh", text: "[gate] g8 result=pass exit=0 ms=5" }), null)
  // Not a gate command → no VERIFICATION_FAILED.
  assert.equal(parseVerificationFailed({ cmd: "ls", text: "[g8] FAIL  x" }), null)
  // g7 without RECURR → no TASK_REOPENED.
  assert.equal(parseTaskReopened({ cmd: "bash framework/gates/g7_retro.sh", text: "PASS  no recurrence" }), null)
  // resolve-blocker is not write-blocker → no BLOCKER_DETECTED.
  assert.equal(parseBlockerDetected({ cmd: "python3 framework/adapters/gsd_state.py resolve-blocker --id BLK-001", text: '{"resolved": true}', exit: 0 }), null)
  // task-event with a non-terminal state → no TASK_COMPLETED.
  assert.equal(parseTaskCompleted({ cmd: "python3 framework/adapters/gsd_state.py task-event T-01 --json '{\"state\":\"STARTED\"}'", text: '"state": "STARTED"' }), null)
  // Review output without a rejection marker → no REVIEW_REJECTED.
  assert.equal(parseReviewRejected({ cmd: "review-work", text: "all findings resolved" }), null)
  // Non-signal input → empty array, never a manufactured event.
  assert.deepEqual(parseSignals({ cmd: "ls", text: "nothing", exit: 0 }), [])
})

// ─── Events without envelope (§4 fallback) ───────────────────────────────────

test("events without envelope fall back with attribution_confidence=fallback and are never dropped", () => {
  const ev = taxonomyEvent({ event: EVENTS.TEST_FAILED, detail: { runner: "pytest" }, ts: TS })
  assert.equal(ev.attribution_confidence, "fallback")
  assert.equal(ev.task_id, "")
  assert.equal(ev.attempt_id, null)
  assert.equal(ev.parent_task_id, "")
  assert.equal(ev.delegated_agent, "team-lead")
  assert.equal(ev.execution_agent, "unknown")
  assert.equal(ev.model_id, "")
  assert.equal(ev.session_id, "")
  assert.equal(ev.event, EVENTS.TEST_FAILED)
  assert.ok(ev.ts, "event carries a timestamp")
})

test("envelope fields flow through the event factory", () => {
  const ev = taxonomyEvent({
    event: EVENTS.WORK_ATTEMPTED,
    detail: { execution_agent: "explore" },
    envelope: {
      session_id: "ses_1",
      task_id: "T-01",
      attempt_id: 2,
      parent_task_id: "T-ROOT",
      delegated_agent: "team-lead",
      execution_agent: "explore",
      model_id: "opencode/big-pickle",
      attribution_confidence: "stack",
    },
    ts: TS,
  })
  assert.equal(ev.session_id, "ses_1")
  assert.equal(ev.task_id, "T-01")
  assert.equal(ev.attempt_id, 2)
  assert.equal(ev.parent_task_id, "T-ROOT")
  assert.equal(ev.delegated_agent, "team-lead")
  assert.equal(ev.execution_agent, "explore")
  assert.equal(ev.model_id, "opencode/big-pickle")
  assert.equal(ev.attribution_confidence, "stack")
})

// ─── Liveness: no taxonomy event silently disappears (§7) ────────────────────

test("no taxonomy event is silently dropped: every vocabulary event is produced by the chain", () => {
  const reg = createAttemptRegistry()
  const produced = new Set()
  const emit = (event, detail, envelope) => {
    produced.add(event)
    return taxonomyEvent({ event, detail, envelope, ts: TS })
  }

  // Drive every emitter/parser path — the §7 synthetic liveness authority.
  const a1 = reg.open("T-01")
  emit(EVENTS.WORK_ATTEMPTED, { execution_agent: "implementer" }, { task_id: "T-01", attempt_id: a1.attempt_id })
  emit(parseTestFailed({ cmd: "pytest tests", text: "FAILED", exit: 1 }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  const a2 = reg.open("T-01")
  emit(EVENTS.WORK_ATTEMPTED, { execution_agent: "implementer" }, { task_id: "T-01", attempt_id: a2.attempt_id })
  emit(EVENTS.RETRY, { previous_attempt: 1 }, { task_id: "T-01", attempt_id: a2.attempt_id })
  emit(parseReviewRejected({ cmd: "review-work", text: "REVIEW_REJECTED" }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(parseVerificationFailed({ cmd: "bash framework/gates/g8_blockers.sh", text: "[g8] FAIL  x" }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(parseTaskReopened({ cmd: "bash framework/gates/g7_retro.sh", text: "FAIL  1 recurring gap signature(s)" }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(parseBlockerDetected({
    cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"BLOCKED\",\"task_id\":\"T-01\",\"agent\":\"implementer\"}'",
    text: '{"id":"BLK-001"}', exit: 0,
  }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(parseContextInsufficient({
    cmd: "python3 framework/adapters/gsd_state.py write-blocker --json '{\"signal\":\"CONTEXT_INSUFFICIENT\",\"task_id\":\"T-01\",\"agent\":\"implementer\",\"missing_item\":\"plan\"}'",
    text: '{"id":"BLK-002"}', exit: 0,
  }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(EVENTS.INTEGRATION_FAILED, { source: "cross-component" }, { task_id: "T-01", attempt_id: reg.current("T-01") })
  emit(parseTaskCompleted({
    cmd: "python3 framework/adapters/gsd_state.py task-event T-01 --json '{\"state\":\"COMPLETED\"}'",
    text: '"state": "COMPLETED"',
  }).event, {}, { task_id: "T-01", attempt_id: reg.current("T-01") })
  reg.close("T-01")

  // Every vocabulary event must have been produced — silence is a failure.
  for (const e of ALL_EVENTS) {
    assert.ok(produced.has(e), `taxonomy event ${e} was silently dropped`)
  }
})