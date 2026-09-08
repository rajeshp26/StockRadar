#!/usr/bin/env python3
"""Claim ledger. Append-only record of claims used in decisions and the evidence behind them.

A claim is the unit of truth-used-in-decisions. The ledger stores every claim an agent
records, with the provenance that would let a second agent reproduce it. Multiple records
per claim_id are allowed (history is retained); the LATEST record per claim_id wins in
analyse. The G11 gate judges ledger validity on every functional run.

Exit codes:
  0  append accepted (claim_id printed on stdout) | analyse: all latest records valid
  1  append rejected (validation code on stdout) | analyse: invalid records found
  3  analyse: ledger empty or missing (nothing to judge -- never a pass)
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CLAIM_TYPES = {"environment", "behavioral", "data", "causal"}
CLASSIFICATIONS = {"FACT", "HYPOTHESIS", "ASSUMPTION", "UNKNOWN"}
STATUSES = {"UNVERIFIED", "VERIFIED", "REFUTED", "PARTIALLY_VERIFIED"}
IMPACTS = {"high", "medium", "low"}
EVIDENCE_KINDS = {"command_run", "artifact", "observation"}
EVIDENCE_RESULTS = {"pass", "fail", "inconclusive"}
DISCONFIRMATION_RESULTS = {"confirmed", "refuted", "inconclusive"}
CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")

REQUIRED = ["claim_id", "task_id", "agent", "statement", "claim_type",
            "classification", "status", "impact"]


def _state_root() -> Path:
    """Resolve the GSD state root exactly the way the rest of the framework does."""
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")


def _runtime_recorded(runtime_id: str) -> bool:
    """True iff an execution context row with that id exists binding provider+model.

    The ledger stays self-contained (no framework imports, matching the pattern of the
    retro and claim ledgers): it reads the context file directly. A claim whose evidence
    names a canonical RT- id must resolve to a recorded context; an unknown id is
    provenance the ledger cannot reproduce, and is refused.
    """
    p = _state_root() / "contexts" / "execution.jsonl"
    if not p.exists():
        return False
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("runtime_id") == runtime_id and rec.get("model") and rec.get("provider"):
            return True
    return False


def _env_recorded(env_id: str) -> bool:
    """True iff a command-environment row with that id exists in environments.jsonl.

    Mirrors _runtime_recorded: the ledger reads the context file directly and stays
    self-contained. An evidence `env` that names a canonical ENV- id must resolve to a
    recorded command environment; an unknown id is provenance the ledger cannot
    reproduce, and is refused.
    """
    p = _state_root() / "contexts" / "environments.jsonl"
    if not p.exists():
        return False
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("env_id") == env_id and rec.get("interpreter_path"):
            return True
    return False


def ledger_path() -> Path:
    return _state_root() / "claims" / "ledger.jsonl"


def load() -> list[dict]:
    p = ledger_path()
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN: claim ledger line {i} is not valid JSON -- skipped", file=sys.stderr)
    return out


def _has_provenance(rec: dict) -> bool:
    """VERIFIED provenance: an evidence entry naming runtime AND entry_point, reproduced."""
    for e in rec.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("runtime") and e.get("entry_point") and e.get("reproduced") is True:
            return True
    return False


def _has_pass_or_fail_evidence(rec: dict) -> bool:
    for e in rec.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("result") in ("pass", "fail"):
            return True
    return False


def _has_refutation_evidence(rec: dict) -> bool:
    for e in rec.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("result") == "fail" and e.get("expected") and e.get("actual"):
            return True
    return False


def derive_confidence(rec: dict) -> str:
    """Confidence from evidence structure, never from a stored field.

    LOW        no evidence, or evidence without provenance (runtime+entry_point+reproduced)
    MEDIUM     provenance present but no verdict (result not pass/fail)
    HIGH       provenance plus a pass/fail verdict
    VERY_HIGH  an independent_check, or two or more evidence entries with verdicts
    """
    ev = rec.get("evidence") or []
    if not isinstance(ev, list):
        ev = []
    verdicts = 0
    for e in ev:
        if not isinstance(e, dict):
            continue
        if e.get("runtime") and e.get("entry_point") and e.get("reproduced") is True:
            if e.get("result") in ("pass", "fail"):
                verdicts += 1
    if rec.get("independent_check") or verdicts >= 2:
        return "VERY_HIGH"
    if verdicts >= 1:
        return "HIGH"
    if any(isinstance(e, dict) and e.get("runtime") and e.get("entry_point")
           and e.get("reproduced") is True for e in ev):
        return "MEDIUM"
    return "LOW"


def validate_record(rec: dict) -> list[str]:
    """Return the problem codes for a record; empty list means valid.

    The same rules run at append time and at analyse time, so a hand-edited or corrupt
    store is caught exactly like a rejected append.
    """
    problems = []

    # 1. Required top-level fields.
    for k in REQUIRED:
        v = rec.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            problems.append("CLAIM_INCOMPLETE")
            break

    # 2. Vocabulary.
    if rec.get("claim_type") not in CLAIM_TYPES:
        problems.append("CLAIM_BAD_VOCAB")
    if rec.get("classification") not in CLASSIFICATIONS:
        problems.append("CLAIM_BAD_VOCAB")
    if rec.get("status") not in STATUSES:
        problems.append("CLAIM_BAD_VOCAB")
    if rec.get("impact") not in IMPACTS:
        problems.append("CLAIM_BAD_VOCAB")
    ev = rec.get("evidence")
    if ev is not None:
        if not isinstance(ev, list):
            problems.append("CLAIM_BAD_VOCAB")
        else:
            for e in ev:
                if not isinstance(e, dict):
                    problems.append("CLAIM_BAD_VOCAB")
                    continue
                if e.get("kind") not in EVIDENCE_KINDS:
                    problems.append("CLAIM_BAD_VOCAB")
                if e.get("result") not in EVIDENCE_RESULTS:
                    problems.append("CLAIM_BAD_VOCAB")
                if not isinstance(e.get("reproduced"), bool):
                    problems.append("CLAIM_BAD_VOCAB")

    # 2b. Runtime-scope integrity: an evidence runtime that names a canonical RT- id
    # must resolve to a recorded execution context. A free-form runtime (legacy, e.g.
    # 'local-wsl') stays legal - it names a runtime without claiming a binding.
    for e in rec.get("evidence") or []:
        if isinstance(e, dict):
            rt = e.get("runtime")
            if isinstance(rt, str) and re.match(r"^RT-\d+$", rt) and not _runtime_recorded(rt):
                problems.append("CLAIM_UNKNOWN_RUNTIME")
                break

    classification = rec.get("classification")
    status = rec.get("status")
    impact = rec.get("impact")

    # 2c. Command-environment binding and disconfirmation. An evidence `env` that names
    # a canonical ENV- id must resolve to a recorded command environment (record-env);
    # a free-form env string (legacy) stays legal. Disconfirmation uses the closed
    # result vocab, and a VERIFIED claim may not carry a refuted disconfirmation --
    # that is a contradiction.
    for e in rec.get("evidence") or []:
        if isinstance(e, dict):
            env = e.get("env")
            if isinstance(env, str) and re.match(r"^ENV-\d+$", env) and not _env_recorded(env):
                problems.append("CLAIM_ENV_UNKNOWN")
                break
            d = e.get("disconfirmation")
            if d is not None and d not in DISCONFIRMATION_RESULTS:
                problems.append("CLAIM_BAD_DISCONFIRMATION")
                break
            if status == "VERIFIED" and d == "refuted":
                problems.append("CLAIM_DISCONFIRMED_BUT_VERIFIED")
                break

    # 2d. Confidence is derived at analyse time from evidence structure; a stored
    # confidence field is a gaming surface and is refused.
    if "confidence" in rec:
        problems.append("CLAIM_STORED_CONFIDENCE")

    # 3. A FACT must be VERIFIED.
    if classification == "FACT" and status != "VERIFIED":
        problems.append("CLAIM_FACT_UNVERIFIED")

    # 4-6. VERIFIED requirements.
    if status == "VERIFIED":
        if not rec.get("verified_by"):
            problems.append("CLAIM_VERIFIED_NO_COMMAND")
        if not _has_provenance(rec):
            problems.append("CLAIM_VERIFIED_NO_PROVENANCE")
        if impact == "high" and not rec.get("independent_check"):
            problems.append("CLAIM_VERIFIED_NO_INDEPENDENT_CHECK")

    # PARTIALLY_VERIFIED: a verifying command plus evidence with a pass/fail result.
    if status == "PARTIALLY_VERIFIED":
        if not rec.get("verified_by"):
            problems.append("CLAIM_VERIFIED_NO_COMMAND")
        if not _has_pass_or_fail_evidence(rec):
            problems.append("CLAIM_VERIFIED_NO_PROVENANCE")

    # 7. REFUTED needs failing evidence with expected vs actual.
    if status == "REFUTED":
        if not _has_refutation_evidence(rec):
            problems.append("CLAIM_REFUTED_NO_EVIDENCE")

    return problems


def _next_claim_id(records: list[dict]) -> str:
    """CLM-NNN continuing the highest existing number across ALL records."""
    highest = 0
    for r in records:
        cid = str(r.get("claim_id") or "")
        if cid.startswith("CLM-"):
            try:
                highest = max(highest, int(cid[4:]))
            except ValueError:
                continue
    return f"CLM-{highest + 1:03d}"


def append(entry: dict) -> str:
    if "claim_id" not in entry:
        entry["claim_id"] = _next_claim_id(load())
    problems = validate_record(entry)
    if problems:
        print(problems[0])
        sys.exit(1)
    entry["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry["claim_id"]


def analyse() -> dict:
    p = ledger_path()
    if not p.exists():
        return {"status": "empty", "entries": 0, "claims": 0, "invalid": [],
                "by_type": {}, "by_classification": {}, "by_status": {}, "by_confidence": {}}
    lines = [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]
    records = []
    for ln in lines:
        try:
            records.append(json.loads(ln))
        except json.JSONDecodeError:
            print("WARN: claim ledger line is not valid JSON -- skipped", file=sys.stderr)
    if not records:
        return {"status": "empty", "entries": len(lines), "claims": 0, "invalid": [],
                "by_type": {}, "by_classification": {}, "by_status": {}, "by_confidence": {}}

    # Latest record per claim_id wins (file order = chronological order).
    latest: dict[str, dict] = {}
    for r in records:
        latest[str(r.get("claim_id") or "?")] = r
    claims = list(latest.values())

    invalid = []
    for r in claims:
        problems = validate_record(r)
        if problems:
            invalid.append({
                "claim_id": r.get("claim_id"),
                "task_id": r.get("task_id"),
                "status": r.get("status"),
                "classification": r.get("classification"),
                "problems": problems,
            })

    return {
        "status": "invalid" if invalid else "ok",
        "entries": len(lines),
        "claims": len(claims),
        "invalid": invalid,
        "by_type": dict(Counter(r.get("claim_type", "?") for r in claims)),
        "by_classification": dict(Counter(r.get("classification", "?") for r in claims)),
        "by_status": dict(Counter(r.get("status", "?") for r in claims)),
        "by_confidence": dict(Counter(derive_confidence(r) for r in claims)),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Claim ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyse")
    sub.add_parser("path")
    ad = sub.add_parser("append")
    ad.add_argument("--json", required=True)
    a = ap.parse_args()

    if a.cmd == "path":
        print(ledger_path()); sys.exit(0)
    if a.cmd == "append":
        try:
            entry = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"})); sys.exit(1)
        if not isinstance(entry, dict):
            print(json.dumps({"error": "append payload must be a JSON object"})); sys.exit(1)
        cid = append(entry)
        print(json.dumps({"claim_id": cid})); sys.exit(0)

    out = analyse()
    print(json.dumps(out, indent=2))
    if out["status"] == "empty":
        sys.exit(3)
    sys.exit(1 if out["invalid"] else 0)