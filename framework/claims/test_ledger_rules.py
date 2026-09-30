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
import json

import pytest

from framework.claims import ledger


def _claim(kind, claim_type="causal", classification="FACT", status="VERIFIED",
           impact="medium", provenance=True, result="pass", version=None):
    """A FACT+VERIFIED record that passes every rule: provenance fields present,
    verified_by present, a scope limit, medium impact (no independent_check
    required), free-form runtime (never RT-/ENV- id, so no store binding).

    The scope limit is unconditional. `append` stamps the current schema version on
    every write, so a VERIFIED fixture that omits it is rejected by
    CLAIM_VERIFIED_NO_SCOPE_LIMIT -- which is the rule working, not a broken test.

    `version` is unset by default, so the record reads as v1. The causal tests want
    that: they exercise DERIVABLE rules, which apply at every version. Pass
    version=2 to opt into the since-2 AUTHOR_SUPPLIED rules, which need information
    only the recording agent has."""
    ev = {
        "id": "e1",
        "kind": kind,
        "command": "test command",
        "runtime": "local-test-run",
        "entry_point": "test_entry",
        "reproduced": provenance,
        "result": result,
    }
    rec = {
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
        "does_not_prove": "the fixture exercises a rule; it asserts nothing about production",
    }
    if version is not None:
        rec["schema_version"] = version
    return rec


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


def test_append_stamps_the_current_schema_version(monkeypatch, tmp_path):
    ledger._last_claim_ns = 0
    monkeypatch.setattr(ledger, "_state_root", lambda: tmp_path)
    rec = _claim("DIRECT")
    del rec["claim_id"]
    ledger.append(rec)
    assert ledger.load()[0]["schema_version"] == ledger.LEDGER_SCHEMA_VERSION


def test_v2_verified_requires_a_scope_limit():
    rec = _claim("DIRECT", version=2)
    rec["does_not_prove"] = None
    assert "CLAIM_VERIFIED_NO_SCOPE_LIMIT" in ledger.validate_record(rec)


def test_v2_scope_limit_must_be_a_usable_string():
    for bad in (None, "", "   ", "  \t ", {}, 0, False, []):
        rec = _claim("DIRECT", version=2)
        rec["does_not_prove"] = bad
        assert "CLAIM_VERIFIED_NO_SCOPE_LIMIT" in ledger.validate_record(rec), bad


def test_v1_verified_without_a_scope_limit_is_grandfathered_not_invalid():
    rec = _claim("DIRECT")
    rec["does_not_prove"] = None
    problems = ledger.validate_record(rec)
    assert "CLAIM_VERIFIED_NO_SCOPE_LIMIT" not in problems
    assert any(s["code"] == "CLAIM_VERIFIED_NO_SCOPE_LIMIT"
               for s in ledger.skipped_rules(rec))


def test_v1_high_impact_without_an_independent_check_is_grandfathered():
    rec = _claim("DIRECT", impact="high")
    rec["independent_check"] = None
    assert "CLAIM_VERIFIED_NO_INDEPENDENT_CHECK" not in ledger.validate_record(rec)


def test_v2_high_impact_requires_an_independent_check():
    rec = _claim("DIRECT", impact="high", version=2)
    rec["independent_check"] = None
    assert "CLAIM_VERIFIED_NO_INDEPENDENT_CHECK" in ledger.validate_record(rec)


def test_absent_schema_version_is_still_legal():
    rec = _claim("DIRECT")
    assert "schema_version" not in rec
    assert "CLAIM_BAD_SCHEMA_VERSION" not in ledger.validate_record(rec)


def test_malformed_schema_version_is_refused_not_read_as_v1():
    for bad in ("2", True, False, 0, -1, 2.0, None, [2], {}):
        rec = _claim("DIRECT")
        rec["schema_version"] = bad
        assert "CLAIM_BAD_SCHEMA_VERSION" in ledger.validate_record(rec), bad


def test_malformed_version_cannot_dodge_a_since_two_rule():
    rec = _claim("DIRECT")
    rec["schema_version"] = "1"
    rec["does_not_prove"] = None
    problems = ledger.validate_record(rec)
    assert "CLAIM_BAD_SCHEMA_VERSION" in problems
    assert "CLAIM_VERIFIED_NO_SCOPE_LIMIT" in problems


def test_malformed_record_is_not_reported_as_grandfathered():
    assert ledger.skipped_rules({"schema_version": "x"}) == []


def test_unregistered_rule_code_raises_instead_of_defaulting_to_since_one():
    with pytest.raises(KeyError):
        ledger._rule_applies("CLAIM_NOT_IN_THE_REGISTRY", {})


def test_every_emitted_rule_code_is_registered():
    assert ledger.registry_gaps() == []


def test_analyse_partitions_the_store_by_scope_limit_eligibility(monkeypatch, tmp_path):
    v2_verified = _claim("DIRECT", version=2)
    v2_verified["claim_id"] = "CLM-A"
    v1_verified = _claim("DIRECT")
    v1_verified["claim_id"] = "CLM-B"
    v1_verified["does_not_prove"] = None
    unverified = _claim("DIRECT", status="UNVERIFIED", classification="HYPOTHESIS")
    unverified["claim_id"] = "CLM-C"
    unverified["evidence"] = []
    del unverified["verified_by"]

    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in (v2_verified, v1_verified, unverified)),
        encoding="utf-8")
    monkeypatch.setattr(ledger, "ledger_path", lambda: path)
    scope = ledger.analyse()["by_scope_limit"]
    assert scope["present"] == 1
    assert scope["grandfathered"] == 1
    assert scope["not_applicable"] == 1
    assert sum(scope.values()) == 3


def test_integrity_e2_tolerates_a_line_anchored_entry_point(monkeypatch, tmp_path):
    # Regression: a citation carries a line anchor, and the anchor is metadata about
    # the file rather than part of its name. Resolving the raw string reported every
    # line-anchored citation as a missing artifact, which is how a gate starts crying
    # wolf on files that exist.
    for anchor in ("framework/claims/ledger.py:91",
                   "framework/claims/ledger.py:91-120",
                   "framework/claims/ledger.py"):
        path = tmp_path / "ledger.jsonl"
        rec = _claim("DIRECT")
        rec["evidence"][0]["entry_point"] = anchor
        path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
        monkeypatch.setattr(ledger, "ledger_path", lambda: path)
        missing = [v for v in ledger.integrity_report()["violations"]
                   if v["check"] == "EVIDENCE_ARTIFACT_MISSING"]
        assert missing == [], anchor


def test_integrity_e2_still_reports_a_genuinely_absent_file(monkeypatch, tmp_path):
    # The relaxation must not become a blind spot: a path that really is gone is
    # still a violation.
    path = tmp_path / "ledger.jsonl"
    rec = _claim("DIRECT")
    rec["evidence"][0]["entry_point"] = "framework/claims/not_a_real_file.py:5"
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    monkeypatch.setattr(ledger, "ledger_path", lambda: path)
    missing = [v for v in ledger.integrity_report()["violations"]
               if v["check"] == "EVIDENCE_ARTIFACT_MISSING"]
    assert len(missing) == 1
    assert "not_a_real_file.py" in missing[0]["message"]