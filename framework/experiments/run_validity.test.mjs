// framework/experiments/run_validity.test.mjs
// Contract tests for the mechanical RUN_VALIDITY classifier (P3 increment 1).
//
// Prove: validity is decided only from captured execution facts, is
// deterministic and reproducible, never reads comparison metrics, and maps
// each contracted condition to exactly the right status/reason.
import { test } from "node:test"
import assert from "node:assert/strict"
import { classifyRun, STATUS, REASON, MANDATORY_FIELDS } from "./run_validity.mjs"

// A fabricated capture record that satisfies every contract condition.
function validRecord(overrides = {}) {
  return {
    run_id: "R-0001",
    arm: "A",
    task_id: "TASK-01",
    session_id: "ses_x",
    attempt_id: "att_1",
    seed: 20260911,
    run_order: 1,
    model_requested: "opencode/big-pickle",
    model_resolved: "opencode/big-pickle",
    resolved_provider: "opencode",
    runtime_version: "v24.14.1",
    agent_profile: "baseline",
    attribution_status: "pass",
    supervision_gap: false,
    gates_observable: true,
    outcome_produced: true,
    infra_violation: false,
    ...overrides,
  }
}

const codes = (v) => v.reasons.map((r) => r.code)

test("a complete, drift-free run classifies VALID with no reasons", () => {
  const v = classifyRun(validRecord())
  assert.equal(v.status, STATUS.VALID)
  assert.deepEqual(v.reasons, [])
})

test("requested_model != resolved_model -> INVALID (MODEL_DRIFT)", () => {
  const v = classifyRun(validRecord({ model_resolved: "opencode/big-pickle-x" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.MODEL_DRIFT))
})

test("empty resolved_provider -> INVALID (PROVIDER_MISMATCH)", () => {
  const v = classifyRun(validRecord({ resolved_provider: "" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.PROVIDER_MISMATCH))
})

test("empty runtime_version -> INVALID (RUNTIME_MISSING)", () => {
  const v = classifyRun(validRecord({ runtime_version: "" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.RUNTIME_MISSING))
})

test("attribution preflight failure -> INVALID (ATTRIBUTION_FAILED)", () => {
  const v = classifyRun(validRecord({ attribution_status: "fail" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.ATTRIBUTION_FAILED))
})

test("arm outside {A,B} -> INVALID (WRONG_ARM)", () => {
  const v = classifyRun(validRecord({ arm: "C" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.WRONG_ARM))
})

test("missing mandatory identity/attempt/arm field -> INVALID (MISSING_FIELD) naming the field", () => {
  for (const f of ["attempt_id", "session_id", "run_id", "arm", "seed", "run_order"]) {
    const v = classifyRun(validRecord({ [f]: undefined }))
    assert.equal(v.status, STATUS.INVALID, `field ${f}`)
    assert.ok(codes(v).includes(REASON.MISSING_FIELD), `field ${f}`)
    assert.ok(v.reasons.some((r) => r.code === REASON.MISSING_FIELD && r.detail === f), `names ${f}`)
  }
})

test("boolean condition fields must be booleans, else MISSING_FIELD", () => {
  const v = classifyRun(validRecord({ supervision_gap: "yes" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.MISSING_FIELD))
})

test("unresolved supervision gap -> INVALID (SUPERVISION_GAP)", () => {
  const v = classifyRun(validRecord({ supervision_gap: true }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.SUPERVISION_GAP))
})

test("required gates not observable -> INVALID (GATES_NOT_OBSERVABLE)", () => {
  const v = classifyRun(validRecord({ gates_observable: false }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.GATES_NOT_OBSERVABLE))
})

test("infrastructure violation -> INVALID (INFRA_VIOLATION)", () => {
  const v = classifyRun(validRecord({ infra_violation: true }))
  assert.equal(v.status, STATUS.INVALID)
  assert.ok(codes(v).includes(REASON.INFRA_VIOLATION))
})

test("clean but outcome not produced -> INCOMPLETE (OUTCOME_MISSING)", () => {
  const v = classifyRun(validRecord({ outcome_produced: false }))
  assert.equal(v.status, STATUS.INCOMPLETE)
  assert.deepEqual(codes(v), [REASON.OUTCOME_MISSING])
})

test("drift plus missing outcome -> INVALID, not INCOMPLETE (hard invalids outrank)", () => {
  const v = classifyRun(validRecord({ outcome_produced: false, model_resolved: "other" }))
  assert.equal(v.status, STATUS.INVALID)
  assert.deepEqual(codes(v), [REASON.MODEL_DRIFT, REASON.OUTCOME_MISSING])
})

test("deliberate protocol cancel -> ABORTED, wins over drift", () => {
  const v = classifyRun(validRecord({ abort_reason: "scheduled maintenance" }))
  assert.equal(v.status, STATUS.ABORTED)
  assert.deepEqual(codes(v), [REASON.DELIBERATE_ABORT])
})

test("drifted run that self-aborts is ABORTED, not INVALID", () => {
  const v = classifyRun(validRecord({ abort_reason: "manifest superseded", model_resolved: "other" }))
  assert.equal(v.status, STATUS.ABORTED)
})

test("non-object / null input -> INVALID (MISSING_FIELD: record)", () => {
  for (const bad of [null, undefined, 42, "str", []]) {
    const v = classifyRun(bad)
    assert.equal(v.status, STATUS.INVALID)
    assert.ok(codes(v).includes(REASON.MISSING_FIELD))
  }
})

test("deterministic: same record -> identical classification across calls", () => {
  const base = validRecord()
  assert.deepEqual(classifyRun(base), classifyRun(base))
  const drifted = validRecord({ model_resolved: "other", outcome_produced: false })
  assert.deepEqual(classifyRun(drifted), classifyRun(drifted))
})

test("validity is independent of comparison metrics", () => {
  // tokens / rework / gates passes are A-vs-B analysis inputs; they must never
  // change a classification. Values chosen to be absurd either way.
  const a = classifyRun(validRecord())
  const b = classifyRun(validRecord({
    tokens: 999999, fresh_tokens: 500000, cache_read: 499999,
    tool_calls: 77, retries: 9, rework: 12, elapsed_time: 99999,
    gates: [{ id: "g4", result: "pass" }], defects: 5,
  }))
  assert.deepEqual(b, a)

  const aInv = classifyRun(validRecord({ model_resolved: "other" }))
  const bInv = classifyRun(validRecord({ model_resolved: "other", tokens: 999999, rework: 12, defects: 5 }))
  assert.deepEqual(bInv, aInv)
})

test("MANDATORY_FIELDS cover identity, attempt, arm, drift, attribution, conditions", () => {
  for (const f of ["run_id", "arm", "task_id", "session_id", "attempt_id", "seed",
    "run_order", "model_requested", "model_resolved", "resolved_provider",
    "runtime_version", "agent_profile", "attribution_status", "supervision_gap",
    "gates_observable", "outcome_produced", "infra_violation"]) {
    assert.ok(MANDATORY_FIELDS.includes(f), `missing ${f}`)
  }
})
