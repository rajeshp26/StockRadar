"""Fixture-free tests for framework/claims/ledger.py validation rules (claims hardening).

Covers the CLAIM_CAUSAL_NO_RUNTIME rule: a causal claim promoted to a conclusion
(classification FACT) must carry at least one runtime-backed evidence entry
(kind DIRECT/DERIVED/command_run/artifact/observation) WITH provenance
(runtime + entry_point + reproduced: true). Static code inspection (INFERRED),
assertion (ASSERTED), absence (UNOBSERVED) or contradiction (CONTRADICTED)
recorded as the only evidence can never establish causation, even when such
entries are stamped with provenance-shaped fields.

validate_record is a pure function over a record dict, so tests assert on the
returned problem-code list, not printed text.
"""
from framework.claims import ledger


def _claim(kind, claim_type="causal", classification="FACT", status="VERIFIED",
           impact="medium", provenance=True, result="pass"):
    """A FACT+VERIFIED record that passes every pre-existing rule: provenance
    fields present, verified_by present, medium impact (no independent_check
    required), free-form runtime (never RT-/ENV- id, so no store binding)."""
    ev = {
        "id": "e1",
        "kind": kind,
        "command": "test command",
        "runtime": "local-test-run",
        "entry_point": "test_entry",
        "reproduced": provenance,
        "result": result,
    }
    return {
        "claim_id": "CLM-TST",
        "task_id": "T00",
        "agent": "test",
        "statement": "test causal claim",
        "claim_type": claim_type,
        "classification": classification,
        "status": status,
        "impact": impact,
        "evidence": [ev],
        "verified_by": "test command",
    }


def test_causal_fact_rejects_static_inspection():
    # Code inspection stamped with provenance-shaped fields passes every OLD
    # rule; the causal rule must be the only problem emitted.
    problems = ledger.validate_record(_claim("INFERRED"))
    assert problems == ["CLAIM_CAUSAL_NO_RUNTIME"]


def test_causal_fact_rejects_asserted():
    problems = ledger.validate_record(_claim("ASSERTED"))
    assert problems == ["CLAIM_CAUSAL_NO_RUNTIME"]


def test_causal_fact_rejects_unobserved_and_contradicted():
    for kind in ("UNOBSERVED", "CONTRADICTED"):
        problems = ledger.validate_record(_claim(kind))
        assert problems == ["CLAIM_CAUSAL_NO_RUNTIME"]


def test_causal_fact_accepts_runtime_backed_kinds():
    for kind in ("DIRECT", "DERIVED", "command_run", "artifact", "observation"):
        problems = ledger.validate_record(_claim(kind))
        assert problems == []


def test_causal_fact_without_any_evidence_rejected():
    rec = _claim("DIRECT")
    rec["evidence"] = []
    problems = ledger.validate_record(rec)
    assert "CLAIM_CAUSAL_NO_RUNTIME" in problems


def test_causal_hypothesis_not_promoted_is_untouched():
    # A HYPOTHESIS is not a conclusion; weak evidence stays legal.
    rec = _claim("INFERRED", classification="HYPOTHESIS", status="UNVERIFIED")
    assert ledger.validate_record(rec) == []


def test_non_causal_fact_untouched():
    # The rule is causal-specific: a behavioral FACT with the same static
    # evidence shape is not a propagation target.
    rec = _claim("INFERRED", claim_type="behavioral")
    problems = ledger.validate_record(rec)
    assert "CLAIM_CAUSAL_NO_RUNTIME" not in problems


def test_auto_claim_id_is_20_digit_ns_epoch():
    ledger._last_claim_ns = 0
    cid = ledger._next_claim_id()
    assert cid.startswith("CLM-") and len(cid) == 4 + 20 and cid[4:].isdigit()


def test_auto_claim_id_strictly_monotonic_on_clock_step_back(monkeypatch):
    ledger._last_claim_ns = 0
    clock = [1_700_000_000_000_000_000]
    monkeypatch.setattr(ledger.time, "time_ns", lambda: clock[0])
    a = ledger._next_claim_id()
    clock[0] -= 1          # NTP step-back: wall clock goes backwards
    b = ledger._next_claim_id()
    assert b > a


def test_append_auto_ids_without_scanning_existing_records(monkeypatch, tmp_path):
    # The old id continued the highest existing number (a full-ledger scan on
    # every append); the new id is clock-only, so the store size cannot change it.
    ledger._last_claim_ns = 0
    monkeypatch.setattr(ledger, "_state_root", lambda: tmp_path)
    rec = _claim("DIRECT")
    del rec["claim_id"]            # append must auto-assign
    cid = ledger.append(rec)
    assert cid.startswith("CLM-")
    got = ledger.load()
    assert len(got) == 1 and got[0]["claim_id"] == cid