/**
 * P0-3 gate accounting self-tests (§7). The only liveness authority for the
 * GATE_* instrumentation: every vocabulary tag, every classifier transition,
 * the canonical line parser (including malformed lines), and the §7
 * false-evidence matrix — the deliberately unobservable cases that verify the
 * system refuses to manufacture knowledge.
 *
 * Design authority: .planning/tasks/P0-INSTRUMENTATION-INTEGRITY.md §5, §6, §7;
 * binding contract T-P0-3R.
 */
import { test } from "node:test"
import assert from "node:assert/strict"
import {
  GATE_EVENTS,
  ALL_GATE_EVENTS,
  GATE_STATES,
  GATE_RESULTS,
  parseGateLine,
  parseGateLaunch,
  parseGateRequired,
  parseGateExecutionStarted,
  parseGateResult,
  parseGateNotReached,
  gateState,
  shortGateId,
  LEGACY_GATE_RE,
  GATE_SCRIPT_RE,
} from "./gates.mjs"

// ─── Vocabulary (§5) ──────────────────────────────────────────────────────────

test("GATE_EVENTS is exactly the four frozen lifecycle events", () => {
  assert.deepEqual(ALL_GATE_EVENTS, [
    "GATE_REQUIRED",
    "GATE_NOT_REACHED",
    "GATE_EXECUTION_STARTED",
    "GATE_RESULT",
  ])
  assert.deepEqual(Object.keys(GATE_EVENTS), ALL_GATE_EVENTS)
  assert.ok(Object.isFrozen(GATE_EVENTS))
})

test("GATE_STATES is exactly the four contract states", () => {
  assert.deepEqual(Object.values(GATE_STATES), [
    "NOT_REACHED",
    "EXECUTED_PASS",
    "EXECUTED_UNVERIFIABLE",
    "UNOBSERVED",
  ])
  assert.ok(Object.isFrozen(GATE_STATES))
})

test("GATE_RESULTS carries the canonical result vocabulary", () => {
  assert.equal(GATE_RESULTS.PASS, "pass")
  assert.equal(GATE_RESULTS.FAIL, "fail")
  assert.equal(GATE_RESULTS.UNVERIFIABLE, "unverifiable")
  assert.equal(GATE_RESULTS.NOT_REACHED, "not_reached")
})

// ─── Canonical line parser (§5) ───────────────────────────────────────────────

test("parseGateLine parses the canonical pass line", () => {
  assert.deepEqual(parseGateLine("[gate] g8 result=pass exit=0 ms=123"), {
    name: "g8",
    result: "pass",
    exit: 0,
    ms: 123,
  })
})

test("parseGateLine tolerates FAIL / UNVERIFIABLE / Start variants", () => {
  assert.deepEqual(parseGateLine("[gate] g2 result=fail exit=1 ms=45"), {
    name: "g2", result: "fail", exit: 1, ms: 45,
  })
  assert.deepEqual(parseGateLine("[gate] g6 result=unverifiable exit=3 ms=0"), {
    name: "g6", result: "unverifiable", exit: 3, ms: 0,
  })
  assert.deepEqual(parseGateLine("[gate] g9 result=started"), {
    name: "g9", result: "started", exit: null, ms: null,
  })
})

test("parseGateLine parses the not_reached disposal line (no exit/ms)", () => {
  assert.deepEqual(parseGateLine("[gate] g3 result=not_reached"), {
    name: "g3", result: "not_reached", exit: null, ms: null,
  })
})

test("parseGateLine refuses malformed lines (false-evidence refusal)", () => {
  for (const bad of [
    "",
    "g8 result=pass",
    "[gate] g8",
    "[gate] g8 result=",
    "[gate] g8 result=maybe",
    "[gate] g8 result=pass exit=abc",
    "[gate] g8 result=pass exit=0 ms=abc",
    "[g8] PASS  everything conforms",          // legacy human line, not canonical
    "[gate] g8 result=pass exit=0 ms=123 extra", // trailing junk
    "  [gate] g8 result=pass exit=0 ms=123",   // leading whitespace not tolerated
  ]) {
    assert.equal(parseGateLine(bad), null, `expected null for: ${JSON.stringify(bad)}`)
  }
})

// ─── Launch detection ─────────────────────────────────────────────────────────

test("shortGateId reduces gN script names to the numeric short id", () => {
  assert.equal(shortGateId("g8_blockers.sh"), "g8")
  assert.equal(shortGateId("g6-browser.sh"), "g6")
  assert.equal(shortGateId("g1_contract.sh"), "g1")
  assert.equal(shortGateId("g_tool_utilization.sh"), "g_tool_utilization")
  assert.equal(shortGateId("g_tool_readiness.sh"), "g_tool_readiness")
})

test("parseGateLaunch detects every gate script family on disk", () => {
  assert.deepEqual(parseGateLaunch({ cmd: "bash framework/gates/g8_blockers.sh" }), { gate: "g8" })
  assert.deepEqual(parseGateLaunch({ cmd: "framework/gates/g5-stack.sh" }), { gate: "g5" })
  assert.deepEqual(parseGateLaunch({ cmd: "bash framework/gates/g_tool_utilization.sh" }), { gate: "g_tool_utilization" })
  assert.deepEqual(parseGateLaunch({ cmd: "bash framework/gates/g13_worker.sh" }), { gate: "g13" })
})

test("parseGateLaunch refuses non-gate commands", () => {
  for (const cmd of [
    "",
    "npm test",
    "python3 framework/telemetry/report.py --json",
    "bash framework/gates/_lib.sh", // helper library, not a gate
    "grep gates/g8_blockers.sh README.md",
  ]) {
    assert.equal(parseGateLaunch({ cmd }), null, `expected null for: ${cmd}`)
  }
})

test("legacy regex fallback is exactly the pre-canonical g1-g8/g10-g11 shape", () => {
  assert.ok(LEGACY_GATE_RE.test("bash framework/gates/g8_blockers.sh"))
  assert.ok(LEGACY_GATE_RE.test("bash framework/gates/g10_permission.sh"))
  assert.ok(!LEGACY_GATE_RE.test("bash framework/gates/g9_scope.sh")) // the g9 hole the canonical line fixes
  assert.ok(!LEGACY_GATE_RE.test("bash framework/gates/g12_provider.sh"))
  assert.ok(GATE_SCRIPT_RE.test("bash framework/gates/g9_scope.sh"))
  assert.ok(GATE_SCRIPT_RE.test("bash framework/gates/g12_provider.sh"))
})

test("Sep-7 gate regex hole: g9/g12/g_tool_* commands record their gate ids", () => {
  // The legacy /gates\/(g[1-8])_|g1[01]_/ regex missed g9, g12, g13 and the
  // g_tool_* scripts — ZERO gate records were captured on Sep 7. The collector
  // now routes through GATE_SCRIPT_RE + shortGateId, so these must resolve.
  assert.deepEqual(parseGateLaunch({ cmd: "framework/gates/g9_scope.sh deploy" }), { gate: "g9" })
  assert.deepEqual(parseGateLaunch({ cmd: "framework/gates/g12_provider.sh" }), { gate: "g12" })
  assert.deepEqual(parseGateLaunch({ cmd: "framework/gates/g_tool_readiness.sh" }), { gate: "g_tool_readiness" })
  assert.equal(shortGateId("g9_scope.sh"), "g9")
  assert.equal(shortGateId("g12_provider.sh"), "g12")
  assert.equal(shortGateId("g_tool_readiness.sh"), "g_tool_readiness")
})

// ─── Lifecycle event parsers ──────────────────────────────────────────────────

test("parseGateRequired emits GATE_REQUIRED on launch observation", () => {
  assert.deepEqual(parseGateRequired({ cmd: "bash framework/gates/g8_blockers.sh" }), {
    event: "GATE_REQUIRED",
    detail: { gate: "g8" },
  })
  assert.equal(parseGateRequired({ cmd: "npm test" }), null)
})

test("parseGateExecutionStarted emits GATE_EXECUTION_STARTED on launch observation", () => {
  assert.deepEqual(parseGateExecutionStarted({ cmd: "bash framework/gates/g8_blockers.sh" }), {
    event: "GATE_EXECUTION_STARTED",
    detail: { gate: "g8" },
  })
  assert.equal(parseGateExecutionStarted({ cmd: "npm test" }), null)
})

test("parseGateResult emits GATE_RESULT for pass/fail/unverifiable canonical lines", () => {
  assert.deepEqual(parseGateResult({ cmd: "bash framework/gates/g8_blockers.sh", text: "[gate] g8 result=pass exit=0 ms=123" }), {
    event: "GATE_RESULT",
    detail: { gate: "g8", result: "pass", exit: 0, ms: 123 },
  })
  assert.deepEqual(parseGateResult({ cmd: "bash framework/gates/g2_impact.sh", text: "[gate] g2 result=fail exit=1 ms=45" }), {
    event: "GATE_RESULT",
    detail: { gate: "g2", result: "fail", exit: 1, ms: 45 },
  })
  assert.deepEqual(parseGateResult({ cmd: "bash framework/gates/g6_browser.sh", text: "[gate] g6 result=unverifiable exit=3 ms=0" }), {
    event: "GATE_RESULT",
    detail: { gate: "g6", result: "unverifiable", exit: 3, ms: 0 },
  })
})

test("parseGateResult refuses not_reached and started variants", () => {
  assert.equal(parseGateResult({ cmd: "bash framework/gates/g3_architecture.sh", text: "[gate] g3 result=not_reached" }), null)
  assert.equal(parseGateResult({ cmd: "bash framework/gates/g9_scope.sh", text: "[gate] g9 result=started" }), null)
  assert.equal(parseGateResult({ cmd: "bash framework/gates/g8_blockers.sh", text: "[g8] PASS  no open blockers" }), null)
})

test("parseGateNotReached emits GATE_NOT_REACHED only for the explicit disposal line", () => {
  assert.deepEqual(parseGateNotReached({ cmd: "bash framework/gates/g3_architecture.sh", text: "[gate] g3 result=not_reached" }), {
    event: "GATE_NOT_REACHED",
    detail: { gate: "g3" },
  })
  assert.equal(parseGateNotReached({ cmd: "bash framework/gates/g8_blockers.sh", text: "[gate] g8 result=pass exit=0 ms=1" }), null)
  assert.equal(parseGateNotReached({ cmd: "bash framework/gates/g8_blockers.sh", text: "" }), null)
})

// ─── Four-state classifier (§5) ───────────────────────────────────────────────

test("gateState: execution + pass → EXECUTED_PASS", () => {
  const evs = [
    { event: "GATE_REQUIRED", detail: { gate: "g8" } },
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g8" } },
    { event: "GATE_RESULT", detail: { gate: "g8", result: "pass", exit: 0, ms: 123 } },
  ]
  assert.equal(gateState("g8", evs), "EXECUTED_PASS")
})

test("gateState: execution + fail → EXECUTED_UNVERIFIABLE (never a pass)", () => {
  const evs = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g2" } },
    { event: "GATE_RESULT", detail: { gate: "g2", result: "fail", exit: 1, ms: 45 } },
  ]
  assert.equal(gateState("g2", evs), "EXECUTED_UNVERIFIABLE")
})

test("gateState: UNVERIFIABLE is a DISTINCT state, never EXECUTED_PASS", () => {
  const evs = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g6" } },
    { event: "GATE_RESULT", detail: { gate: "g6", result: "unverifiable", exit: 3, ms: 0 } },
  ]
  assert.equal(gateState("g6", evs), "EXECUTED_UNVERIFIABLE")
  assert.notEqual(gateState("g6", evs), "EXECUTED_PASS")
})

test("gateState: explicit GATE_NOT_REACHED → NOT_REACHED, never inferred from absence", () => {
  const evs = [{ event: "GATE_NOT_REACHED", detail: { gate: "g3" } }]
  assert.equal(gateState("g3", evs), "NOT_REACHED")
  // A contradictory execution record does not override the deliberate disposition.
  const contradictory = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g3" } },
    { event: "GATE_RESULT", detail: { gate: "g3", result: "pass", exit: 0, ms: 1 } },
    { event: "GATE_NOT_REACHED", detail: { gate: "g3" } },
  ]
  assert.equal(gateState("g3", contradictory), "NOT_REACHED")
})

test("gateState: no evidence whatsoever → UNOBSERVED", () => {
  assert.equal(gateState("g9", []), "UNOBSERVED")
  assert.equal(gateState("g9", [{ event: "WORK_ATTEMPTED", detail: {} }]), "UNOBSERVED")
})

test("gateState: result without start → UNOBSERVED (execution not established)", () => {
  const evs = [{ event: "GATE_RESULT", detail: { gate: "g4", result: "pass", exit: 0, ms: 1 } }]
  assert.equal(gateState("g4", evs), "UNOBSERVED")
})

test("gateState: start without result → UNOBSERVED (executed-but-unparseable)", () => {
  const evs = [{ event: "GATE_EXECUTION_STARTED", detail: { gate: "g4" } }]
  assert.equal(gateState("g4", evs), "UNOBSERVED")
})

test("gateState: malformed output → UNOBSERVED (parser refuses, classifier follows)", () => {
  const evs = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g4" } },
    // parseGateResult returns null for the malformed line, so no GATE_RESULT exists.
  ]
  assert.equal(gateState("g4", evs), "UNOBSERVED")
})

test("gateState: last GATE_RESULT wins for a gate", () => {
  const evs = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g8" } },
    { event: "GATE_RESULT", detail: { gate: "g8", result: "fail", exit: 1, ms: 1 } },
    { event: "GATE_RESULT", detail: { gate: "g8", result: "pass", exit: 0, ms: 2 } },
  ]
  assert.equal(gateState("g8", evs), "EXECUTED_PASS")
})

test("gateState: events for other gates never affect the classification", () => {
  const evs = [
    { event: "GATE_EXECUTION_STARTED", detail: { gate: "g8" } },
    { event: "GATE_RESULT", detail: { gate: "g8", result: "pass", exit: 0, ms: 1 } },
  ]
  assert.equal(gateState("g2", evs), "UNOBSERVED")
})

// ─── §7 false-evidence matrix (deliberately unobservable cases) ───────────────

test("false-evidence matrix resolves to exactly the expected states", () => {
  const cases = [
    { name: "gate executes and passes", evs: [
      { event: "GATE_EXECUTION_STARTED", detail: { gate: "g1" } },
      { event: "GATE_RESULT", detail: { gate: "g1", result: "pass", exit: 0, ms: 1 } },
    ], expected: "EXECUTED_PASS" },
    { name: "gate executes and fails", evs: [
      { event: "GATE_EXECUTION_STARTED", detail: { gate: "g1" } },
      { event: "GATE_RESULT", detail: { gate: "g1", result: "fail", exit: 1, ms: 1 } },
    ], expected: "EXECUTED_UNVERIFIABLE" },
    { name: "gate explicitly marked NOT_REACHED", evs: [
      { event: "GATE_NOT_REACHED", detail: { gate: "g1" } },
    ], expected: "NOT_REACHED" },
    { name: "gate has no evidence whatsoever", evs: [], expected: "UNOBSERVED" },
    { name: "gate output malformed", evs: [
      { event: "GATE_EXECUTION_STARTED", detail: { gate: "g1" } },
    ], expected: "UNOBSERVED" },
    { name: "gate executes but collector cannot parse result", evs: [
      { event: "GATE_EXECUTION_STARTED", detail: { gate: "g1" } },
    ], expected: "UNOBSERVED" },
  ]
  for (const c of cases) {
    assert.equal(gateState("g1", c.evs), c.expected, `case: ${c.name}`)
  }
})

// ─── Liveness: every GATE_* event is produced by the chain (§7) ───────────────

test("every GATE_* event is produced by the parser chain (pass run + disposal run)", () => {
  const cmd = "bash framework/gates/g8_blockers.sh"
  const text = "[g8] PASS  no open blockers\n[gate] g8 result=pass exit=0 ms=123"
  const emitted = [
    parseGateRequired({ cmd }),
    parseGateExecutionStarted({ cmd }),
    parseGateResult({ cmd, text }),
  ].filter(Boolean)
  const events = emitted.map((e) => e.event)
  assert.deepEqual(events, ["GATE_REQUIRED", "GATE_EXECUTION_STARTED", "GATE_RESULT"])
  // GATE_NOT_REACHED comes from the disposal path (asserted above); together
  // the chain covers every vocabulary tag.
  const disposal = parseGateNotReached({
    cmd: "bash framework/gates/g3_architecture.sh",
    text: "[gate] g3 result=not_reached",
  })
  assert.equal(disposal.event, "GATE_NOT_REACHED")
  const all = [...events, disposal.event]
  for (const ev of ALL_GATE_EVENTS) {
    assert.ok(all.includes(ev), `expected ${ev} to be produced by the chain`)
  }
})

test("a disposal run emits GATE_NOT_REACHED and nothing else", () => {
  const cmd = "bash framework/gates/g3_architecture.sh"
  const text = "[gate] g3 result=not_reached"
  assert.equal(parseGateResult({ cmd, text }), null)
  assert.deepEqual(parseGateNotReached({ cmd, text }), {
    event: "GATE_NOT_REACHED",
    detail: { gate: "g3" },
  })
})

test("UNOBSERVED never collapses into PASS or NOT_REACHED", () => {
  const state = gateState("g9", [])
  assert.equal(state, "UNOBSERVED")
  assert.notEqual(state, "EXECUTED_PASS")
  assert.notEqual(state, "NOT_REACHED")
})

// ─── Classified non-judgement verdicts (framework/gates/_lib.sh non_judgement) ──

const CLASSIFIED = [
  ["not_applicable", '{"changed_source_files": 0}'],
  ["precondition_missing", '{"SCOPE_PLAN": null, "changed_source_files": 207}'],
  ["capability_missing", '{"required_tool": "playwright", "found": false}'],
]

test("GATE_RESULTS declares the three classified non-judgement tokens", () => {
  assert.equal(GATE_RESULTS.NOT_APPLICABLE, "not_applicable")
  assert.equal(GATE_RESULTS.PRECONDITION_MISSING, "precondition_missing")
  assert.equal(GATE_RESULTS.CAPABILITY_MISSING, "capability_missing")
})

test("parseGateLine parses a classified verdict and captures its evidence", () => {
  for (const [token, evidence] of CLASSIFIED) {
    assert.deepEqual(
      parseGateLine(`[gate] g9 result=${token} exit=4 ms=7 evidence=${evidence}`),
      { name: "g9", result: token, exit: 4, ms: 7, evidence },
      `expected ${token} to parse with evidence`,
    )
  }
})

test("parseGateLine omits the evidence key when the line carries none", () => {
  // Regression guard: existing tests deepEqual a four-key object, so evidence
  // must be absent rather than null when the line has no evidence field.
  const parsed = parseGateLine("[gate] g8 result=pass exit=0 ms=123")
  assert.equal("evidence" in parsed, false)
  assert.deepEqual(Object.keys(parsed), ["name", "result", "exit", "ms"])
})

test("parseGateLine REFUSES a classified verdict that carries no evidence", () => {
  // The invariant, enforced on the reading side. A classified token without
  // evidence is an assertion, not a verdict: it must not become a recorded
  // result. null routes it to UNOBSERVED, which never passes.
  for (const [token] of CLASSIFIED) {
    const parsed = parseGateLine(`[gate] g9 result=${token} exit=4 ms=7`)
    assert.equal(parsed, null, `expected bare ${token} to be refused`)
  }
})

test("parseGateResult classifies a non-judgement verdict as GATE_RESULT", () => {
  const text = '[gate] g9 result=not_applicable exit=4 ms=7 evidence={"changed_source_files": 0}'
  assert.deepEqual(parseGateResult({ cmd: "", text }), {
    event: "GATE_RESULT",
    detail: { gate: "g9", result: "not_applicable", exit: 4, ms: 7 },
  })
})

test("a classified non-judgement verdict is NEVER EXECUTED_PASS", () => {
  // The core safety property, per gate: no state may be added that would make
  // an unjudged outcome readable as a pass.
  for (const [token, evidence] of CLASSIFIED) {
    const state = gateState("g9", [
      { event: "GATE_EXECUTION_STARTED", detail: { gate: "g9" } },
      { event: "GATE_RESULT", detail: { gate: "g9", result: token } },
    ])
    assert.equal(state, "EXECUTED_UNVERIFIABLE", `expected ${token} to be non-pass`)
    assert.notEqual(state, "EXECUTED_PASS")
  }
})