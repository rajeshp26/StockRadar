// framework/experiments/run_validity.mjs
// Mechanical RUN_VALIDITY classifier (DID-009 / P3-EXPERIMENT-INTEGRITY).
//
// Every experimental run ends in exactly one of VALID / INVALID / ABORTED /
// INCOMPLETE, decided by this pure function from captured execution facts.
// Contract rules:
//   - No run enters the experimental dataset as VALID unless validity is
//     mechanically established from captured facts.
//   - requested_model != resolved_model -> INVALID (MODEL_DRIFT)
//   - provider/runtime/version mismatch -> INVALID
//   - attribution preflight failure -> INVALID
//   - missing mandatory identity/attempt/arm fields -> INVALID
//   - unresolved supervision/execution-integrity condition -> INVALID
//   - deliberate protocol cancel -> ABORTED (wins over all other checks)
//   - clean but outcome not produced -> INCOMPLETE
//   - never statistically back-correct an invalid run (caller's duty)
//   - VALIDITY NEVER READS COMPARISON METRICS. tokens/rework/gates-passes do
//     not influence classification; only the boolean outcome fact does. This
//     keeps validity independent of the A-vs-B analysis, so the experiment
//     cannot select the data that makes its conclusion look cleaner.
//   - deterministic and reproducible: pure, no randomness, fixed rule order.

export const STATUS = Object.freeze({
  VALID: "VALID",
  INVALID: "INVALID",
  ABORTED: "ABORTED",
  INCOMPLETE: "INCOMPLETE",
})

export const REASON = Object.freeze({
  MODEL_DRIFT: "MODEL_DRIFT",             // requested_model != resolved_model
  PROVIDER_MISMATCH: "PROVIDER_MISMATCH", // resolved_provider missing/empty
  RUNTIME_MISSING: "RUNTIME_MISSING",     // runtime_version missing/empty
  ATTRIBUTION_FAILED: "ATTRIBUTION_FAILED", // attribution_status != "pass"
  MISSING_FIELD: "MISSING_FIELD",         // mandatory capture field absent
  WRONG_ARM: "WRONG_ARM",                 // arm not A or B
  SUPERVISION_GAP: "SUPERVISION_GAP",     // unresolved supervision gap
  GATES_NOT_OBSERVABLE: "GATES_NOT_OBSERVABLE", // required gates not observable
  INFRA_VIOLATION: "INFRA_VIOLATION",     // infrastructure violation
  OUTCOME_MISSING: "OUTCOME_MISSING",     // required outcome not produced
  DELIBERATE_ABORT: "DELIBERATE_ABORT",   // cancelled per experiment protocol
})

// Minimum a run needs to be evidence: identity, attempt, arm, drift facts,
// attribution integrity, and the mechanistic condition booleans. Blinding
// metadata (arm_encoding) is NOT mandatory here: blinding is a later increment.
export const MANDATORY_FIELDS = Object.freeze([
  "run_id",
  "arm",
  "task_id",
  "session_id",
  "attempt_id",
  "seed",
  "run_order",
  "model_requested",
  "model_resolved",
  "resolved_provider",
  "runtime_version",
  "agent_profile",
  "attribution_status",
  "supervision_gap",
  "gates_observable",
  "outcome_produced",
  "infra_violation",
])

const BOOLEAN_FIELDS = new Set([
  "supervision_gap",
  "gates_observable",
  "outcome_produced",
  "infra_violation",
])

function missing(v, f) {
  return v === undefined || v === null || v === "" || (BOOLEAN_FIELDS.has(f) && typeof v !== "boolean")
}

// Deterministic. Rule order is fixed and documented; reasons array order is
// stable across calls and machines.
export function classifyRun(record) {
  // Deliberate protocol cancel wins: an aborted run is never judged on merits.
  if (record && typeof record.abort_reason === "string" && record.abort_reason.length > 0) {
    return { status: STATUS.ABORTED, reasons: [{ code: REASON.DELIBERATE_ABORT, detail: record.abort_reason }] }
  }

  if (!record || typeof record !== "object") {
    return { status: STATUS.INVALID, reasons: [{ code: REASON.MISSING_FIELD, detail: "record" }] }
  }

  const reasons = []

  // 1. Completeness: identity / attempt / arm / drift / integrity fields.
  for (const f of MANDATORY_FIELDS) {
    if (missing(record[f], f)) {
      reasons.push({ code: REASON.MISSING_FIELD, detail: f })
    }
  }

  // 2. Arm validity.
  if (!(record.arm === "A" || record.arm === "B")) {
    reasons.push({ code: REASON.WRONG_ARM, detail: String(record.arm) })
  }

  // 3. Model drift: requested vs resolved must agree.
  if (record.model_requested !== undefined && record.model_resolved !== undefined
      && record.model_requested !== record.model_resolved) {
    reasons.push({ code: REASON.MODEL_DRIFT, detail: `${record.model_requested} -> ${record.model_resolved}` })
  }

  // 4. Provider / runtime / version integrity.
  if (record.resolved_provider === "") reasons.push({ code: REASON.PROVIDER_MISMATCH, detail: "resolved_provider" })
  if (record.runtime_version === "") reasons.push({ code: REASON.RUNTIME_MISSING, detail: "runtime_version" })

  // 5. Attribution integrity.
  if (record.attribution_status !== undefined && record.attribution_status !== "pass") {
    reasons.push({ code: REASON.ATTRIBUTION_FAILED, detail: String(record.attribution_status) })
  }

  // 6. Supervision / execution integrity.
  if (record.supervision_gap === true) reasons.push({ code: REASON.SUPERVISION_GAP, detail: "unresolved supervision gap" })
  if (record.infra_violation === true) reasons.push({ code: REASON.INFRA_VIOLATION, detail: "infrastructure violation" })

  // 7. Required gates observable.
  if (record.gates_observable === false) reasons.push({ code: REASON.GATES_NOT_OBSERVABLE, detail: "required gates not observable" })

  // 8. Outcome. Only the boolean fact; never comparison metrics.
  if (record.outcome_produced === false) reasons.push({ code: REASON.OUTCOME_MISSING, detail: "required outcome not produced" })

  if (reasons.length === 0) return { status: STATUS.VALID, reasons: [] }

  // Hard invalids outrank a missing outcome: a drifted run is INVALID even if
  // it also produced no outcome. Only clean-but-unfinished is INCOMPLETE.
  const blocking = reasons.filter((r) => r.code !== REASON.OUTCOME_MISSING)
  if (blocking.length === 0) return { status: STATUS.INCOMPLETE, reasons }
  return { status: STATUS.INVALID, reasons }
}
