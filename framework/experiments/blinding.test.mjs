// framework/experiments/blinding.test.mjs
// Contract tests for the blinding layer (P3 increment 2).
//
// Prove: encode/reveal round-trip restores arms; tokens are bound to run_id
// (swap fails); tampering fails loudly; encode is deterministic; the wrong
// key never yields a wrong answer (it throws); tokens are opaque and
// length-uniform; revealed records still classify VALID under RUN_VALIDITY.
import { test } from "node:test"
import assert from "node:assert/strict"
import { encodeRun, revealRun, encodeDataset, revealDataset, deriveKey, generateSecret } from "./blinding.mjs"
import { classifyRun, STATUS } from "./run_validity.mjs"

const KEY = deriveKey("test-secret", "test-salt")

function validRecord(runId, arm, overrides = {}) {
  return {
    run_id: runId,
    arm,
    task_id: "TASK-01",
    session_id: `ses_${runId}`,
    attempt_id: `att_${runId}`,
    seed: 20260911,
    run_order: Number(String(runId).replace(/\D/g, "")) || 1,
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

const dataset = () => [
  validRecord("run-1", "A"),
  validRecord("run-2", "B"),
  validRecord("run-3", "A"),
  validRecord("run-4", "B"),
]

test("encodeRun -> revealRun round-trip restores the arm label", () => {
  assert.equal(revealRun(KEY, "run-1", encodeRun(KEY, "run-1", "A")), "A")
  assert.equal(revealRun(KEY, "run-2", encodeRun(KEY, "run-2", "B")), "B")
})

test("encodeDataset -> revealDataset restores every arm; recall parity for the classifier", () => {
  const blind = encodeDataset(KEY, dataset())
  assert.equal(blind.opaque, true)
  for (const rec of blind.dataset) {
    assert.equal(rec.arm, undefined)
    assert.ok(typeof rec.arm_token === "string" && rec.arm_token.length > 0)
  }
  const revealed = revealDataset(KEY, blind)
  assert.deepEqual(revealed.map((r) => r.arm), ["A", "B", "A", "B"])
  for (const rec of revealed) {
    assert.equal(classifyRun(rec).status, STATUS.VALID)
  }
})

test("tokens are bound to run_id: swapping tokens between records FAILS", () => {
  const blind = encodeDataset(KEY, dataset())
  const [r1, r2, , r4] = blind.dataset
  const tampered = blind.dataset.map((r) => ({ ...r }))
  tampered[1] = { ...r2, arm_token: r1.arm_token }
  assert.throws(() => revealDataset(KEY, { dataset: tampered }))
  tampered[3] = { ...r4, arm_token: r2.arm_token }
  assert.throws(() => revealDataset(KEY, { dataset: tampered }))
})

test("tampering fails loudly: missing / edited token throws, never a guess", () => {
  const blind = encodeDataset(KEY, dataset())
  const noToken = blind.dataset.map(({ arm_token, ...rest }) => rest)
  assert.throws(() => revealDataset(KEY, { dataset: noToken }))
  const edited = blind.dataset.map((r, i) => (i === 0 ? { ...r, arm_token: r.arm_token.slice(0, -1) + "A" } : r))
  assert.throws(() => revealDataset(KEY, { dataset: edited }))
  const foreign = blind.dataset.map((r, i) => (i === 0 ? { ...r, arm_token: encodeRun(KEY, "other-run", "B") } : r))
  assert.throws(() => revealDataset(KEY, { dataset: foreign }))
})

test("encodeDataset is deterministic: byte-identical across calls", () => {
  const a = JSON.stringify(encodeDataset(KEY, dataset()))
  const b = JSON.stringify(encodeDataset(KEY, dataset()))
  assert.equal(a, b)
})

test("the wrong key throws an auth failure - never a wrong answer", () => {
  const blind = encodeDataset(KEY, dataset())
  const wrongKey = deriveKey("test-secret", "different-salt")
  assert.throws(() => revealDataset(wrongKey, blind))
  assert.throws(() => revealRun(wrongKey, "run-1", blind.dataset[0].arm_token))
})

test("tokens are opaque and length-uniform for both arms", () => {
  const toksA = [encodeRun(KEY, "run-a1", "A"), encodeRun(KEY, "run-a2", "A")]
  const toksB = [encodeRun(KEY, "run-b1", "B"), encodeRun(KEY, "run-b2", "B")]
  const lens = [...toksA, ...toksB].map((t) => t.length)
  assert.ok(new Set(lens).size === 1, "all token lengths equal")
  assert.ok(new Set(toksA).size === 2, "distinct runs -> distinct tokens even for the same arm")
  for (const t of [...toksA, ...toksB]) {
    assert.ok(!/^[AB]$/.test(t), "token is not the arm label")
    assert.ok(/^[A-Za-z0-9+/]+={0,2}$/.test(t), "token is opaque base64 ciphertext")
  }
})

test("malformed inputs are rejected loudly", () => {
  assert.throws(() => encodeDataset(KEY, "not-an-array"))
  assert.throws(() => encodeDataset(KEY, [validRecord("run-1", "A", { run_id: undefined })]))
  assert.throws(() => encodeDataset(KEY, [validRecord("run-1", "A", { arm: "" })]))
  assert.throws(() => revealDataset(KEY, null))
  assert.throws(() => revealDataset(KEY, { dataset: [{}] }))
  assert.throws(() => revealRun(KEY, "run-1", ""))
})

test("generateSecret produces fresh, distinct, non-empty secrets", () => {
  const s1 = generateSecret()
  const s2 = generateSecret()
  assert.ok(s1.length > 0 && s2.length > 0)
  assert.notEqual(s1, s2)
})

test("deriveKey is deterministic for fixed secret+salt and sensitive to both", () => {
  assert.deepEqual(deriveKey("s", "t"), deriveKey("s", "t"))
  assert.notDeepEqual(deriveKey("s", "t"), deriveKey("s", "u"))
  assert.notDeepEqual(deriveKey("s", "t"), deriveKey("u", "t"))
})

