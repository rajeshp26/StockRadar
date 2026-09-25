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
import argparse, json, os, re, subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CLAIM_TYPES = {"environment", "behavioral", "data", "causal"}
CLASSIFICATIONS = {"FACT", "HYPOTHESIS", "ASSUMPTION", "UNKNOWN"}
STATUSES = {"UNVERIFIED", "VERIFIED", "REFUTED", "PARTIALLY_VERIFIED"}
IMPACTS = {"high", "medium", "low"}
EVIDENCE_KINDS = {"command_run", "artifact", "observation", "DIRECT", "DERIVED", "INFERRED", "ASSERTED", "UNOBSERVED", "CONTRADICTED"}
# Runtime-backed kinds: directly observed or executed evidence. Weak kinds
# (INFERRED/ASSERTED/UNOBSERVED/CONTRADICTED) are excluded -- inspection,
# assertion, absence, or contradiction cannot establish causation.
RUNTIME_BACKED_KINDS = {"command_run", "artifact", "observation", "DIRECT", "DERIVED"}
EVIDENCE_RESULTS = {"pass", "fail", "inconclusive"}
DISCONFIRMATION_RESULTS = {"confirmed", "refuted", "inconclusive"}
CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")

REQUIRED = ["claim_id", "task_id", "agent", "statement", "claim_type",
            "classification", "status", "impact"]


def _state_root() -> Path:
    """Resolve the GSD state root exactly the way the rest of the framework does.

    Priority: GSD_STATE_ROOT when it names an explicit path (drive-letter or
    root-anchored) -- a bare ".planning" is never an override. Without the env,
    behavior is unchanged: the adapter probe, then .planning. A caller that pins
    the env removes a subprocess-per-call from the ledger's hot path; the probe
    stays as the framework's single source of truth for the fallback.
    """
    env = os.environ.get("GSD_STATE_ROOT")
    if env and (len(env) >= 2 and env[1] == ":" or env.startswith("/")):
        return Path(env)
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


def _has_runtime_backed_evidence(rec: dict) -> bool:
    """Causal conclusion evidence: an entry whose KIND is runtime-backed (observed
    or executed) and carries provenance. Unlike _has_provenance -- which checks the
    fields alone, so an INFERRED/ASSERTED entry stamped with provenance-shape fields
    sneaks through -- this requires the kind itself to carry runtime weight."""
    for e in rec.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("kind") in RUNTIME_BACKED_KINDS and e.get("runtime") and e.get("entry_point") and e.get("reproduced") is True:
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


def _validate_integrity(rec: dict) -> list[str]:
    """Validate evidence integrity per ARIS patterns.
    
    Checks:
    - E1: Claim has evidence
    - E2: Evidence exists and is accessible
    - E3: Evidence belongs to this task
    - E4: Evidence postdates relevant change (git_sha match)
    - E5: Execution receipt exists
    - E6: Gate receipt exists
    - E7: Reviewer actually inspected required artifacts
    - E8: No stale evidence reused
    """
    problems = []
    
    # E1: Claim should have evidence (warnings, not hard failures for some classifications)
    classification = rec.get("classification")
    status = rec.get("status")
    evidence = rec.get("evidence") or []
    
    if status in ("VERIFIED", "PARTIALLY_VERIFIED") and not evidence:
        problems.append("EVIDENCE_MISSING_FOR_VERIFIED")
    
    # E2-E3: Evidence task binding
    task_id = rec.get("task_id")
    for e in evidence:
        if isinstance(e, dict):
            # Evidence should reference the same task
            e_task = e.get("task_id") or task_id  # inherit if not specified
            if e_task and e_task != task_id:
                problems.append("EVIDENCE_TASK_MISMATCH")
                break
    
    # E4: Git SHA consistency (if provided)
    git_sha = rec.get("git_sha")
    if git_sha:
        for e in evidence:
            if isinstance(e, dict) and e.get("git_sha"):
                if e["git_sha"] != git_sha:
                    problems.append("EVIDENCE_GIT_SHA_MISMATCH")
                    break
    
    # E5: Execution timestamp sanity
    execution_ts = rec.get("execution_timestamp")
    created = rec.get("created")
    if execution_ts and created:
        # Execution should not be after claim creation (with 1min tolerance)
        try:
            from datetime import datetime
            exec_dt = datetime.fromisoformat(execution_ts.replace("Z", "+00:00"))
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if exec_dt > created_dt:
                problems.append("EVIDENCE_FUTURE_TIMESTAMP")
        except (ValueError, TypeError):
            pass
    
    return problems


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

    # 3b. A causal claim promoted to a conclusion (FACT) requires runtime-backed
    # evidence. Static configuration, code inspection, logs, or plausibility
    # (weak kinds) cannot establish causation alone -- evidence-provenance rule.
    if rec.get("claim_type") == "causal" and classification == "FACT" and not _has_runtime_backed_evidence(rec):
        problems.append("CLAIM_CAUSAL_NO_RUNTIME")

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

    # 8. Evidence integrity checks (ARIS patterns)
    integrity_problems = _validate_integrity(rec)
    problems.extend(integrity_problems)

    return problems


_last_claim_ns = 0


def _next_claim_id() -> str:
    """CLM-<20-digit ns-epoch> -- stateless, no ledger scan.

    The old id continued the highest number across ALL records, so every append
    re-read the whole ledger and the scan grew with the store (the quadratic hot
    path this change removes). A wall-clock-ns id is unique without any scan;
    _last_claim_ns keeps it strictly monotonic even across an NTP step back.
    ns-epoch is ~1.8e18 in 2026, safely under int64's 9.2e18; uniqueness does
    not rely on the file -- one process is fenced by the monotonic guard and
    cross-process ns collisions are a one-in-a-trillion race the atomic per-line
    append serialises past anyway.
    """
    global _last_claim_ns
    ns = time.time_ns()
    if ns <= _last_claim_ns:
        ns = _last_claim_ns + 1
    _last_claim_ns = ns
    return f"CLM-{ns:020d}"


def append(entry: dict) -> str:
    if "claim_id" not in entry:
        entry["claim_id"] = _next_claim_id()
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


_INTEGRITY_MESSAGES = {
    "EVIDENCE_MISSING_FOR_VERIFIED": "VERIFIED claim has no evidence",
    "EVIDENCE_TASK_MISMATCH": "evidence references a different task",
    "EVIDENCE_GIT_SHA_MISMATCH": "evidence git_sha differs from claim git_sha",
    "EVIDENCE_FUTURE_TIMESTAMP": "execution_timestamp is after claim creation",
}


def _gate_receipts() -> set:
    """Gate names with a recorded run receipt in any phases/*/VERIFICATION.md."""
    receipts = set()
    base = _state_root()
    for md in sorted((base / "phases").glob("*/VERIFICATION.md")):
        for ln in md.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*gate:\s*(g[a-z0-9_]+)", ln)
            if m:
                receipts.add(m.group(1))
    return receipts


def _open_suspicions() -> set:
    """Task ids with an OPEN suspicion in the reviewer suspicion log."""
    out = set()
    p = _state_root() / "verification" / "suspicion_log.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") == "OPEN" and rec.get("task_id"):
            out.add(str(rec["task_id"]))
    return out


def _unfinished_reviews() -> set:
    """Task ids whose review loop did not reach COMPLETED."""
    out = set()
    p = _state_root() / "verification" / "review_state.json"
    if not p.exists():
        return out
    try:
        state = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return out
    for rec in state.values():
        if isinstance(rec, dict) and rec.get("status") != "COMPLETED" and rec.get("task_id"):
            out.add(str(rec["task_id"]))
    return out


def integrity_report() -> dict:
    """E1-E8 evidence integrity over the latest claim per id.

    Distinct from validate_record: validation answers "is the record well-formed and
    truthful per its own fields"; integrity answers "does the evidence exist, belong to
    this work, and was it actually produced". A claim can be valid yet carry fabricated,
    borrowed, or stale evidence; G14 exists to catch that class.
    """
    violations = []
    p = ledger_path()
    if not p.exists():
        return {"status": "empty", "entries": 0, "claims": 0, "violations": []}
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    records = []
    for ln in lines:
        try:
            records.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    if not records:
        return {"status": "empty", "entries": len(lines), "claims": 0, "violations": []}

    latest: dict[str, dict] = {}
    for r in records:
        latest[str(r.get("claim_id") or "?")] = r
    claims = list(latest.values())

    def _add(cid, tid, code, message):
        violations.append({"claim_id": cid, "task_id": tid, "check": code, "message": message})

    # E1/E3/E4/E5: record-structure integrity, shared with validate_record.
    for c in claims:
        for code in _validate_integrity(c):
            _add(c.get("claim_id"), c.get("task_id"), code,
                 _INTEGRITY_MESSAGES.get(code, code))

    # E2: repo-relative entry_points must resolve to a real file. Command-like
    # entry_points (containing a space) and non-repo prefixes are not path claims.
    for c in claims:
        for e in c.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            ep = e.get("entry_point")
            if isinstance(ep, str) and re.match(r"^(framework|src|backend)/", ep) and " " not in ep:
                if not Path(ep).exists():
                    _add(c.get("claim_id"), c.get("task_id"), "EVIDENCE_ARTIFACT_MISSING",
                         f"evidence entry_point does not exist: {ep}")

    # E6: evidence naming a gate script requires a recorded gate receipt.
    for c in claims:
        for e in c.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            text = " ".join(str(e.get(k) or "") for k in ("command", "entry_point"))
            m = re.search(r"framework/gates/(g[a-z0-9_]+)\.sh", text)
            if m and m.group(1) not in _gate_receipts():
                _add(c.get("claim_id"), c.get("task_id"), "EVIDENCE_GATE_RECEIPT_MISSING",
                     f"gate {m.group(1)} named in evidence but no receipt in VERIFICATION.md")

    # E7: an open reviewer suspicion or an unfinished review loop blocks a VERIFIED claim.
    open_suspicions = _open_suspicions()
    unfinished = _unfinished_reviews()
    for c in claims:
        tid = str(c.get("task_id") or "")
        if c.get("status") in ("VERIFIED", "PARTIALLY_VERIFIED"):
            if tid in open_suspicions:
                _add(c.get("claim_id"), tid, "EVIDENCE_OPEN_SUSPICION",
                     f"task {tid} has an open reviewer suspicion")
            if tid in unfinished:
                _add(c.get("claim_id"), tid, "EVIDENCE_REVIEW_UNFINISHED",
                     f"task {tid} review loop did not complete")

    # E8: the identical evidence payload (full dict set) recorded for 2+ different
    # tasks is evidence reuse -- a fabricated- or stale-evidence signal. A full-payload
    # match across tasks is far too specific to be a coincidence.
    if len(claims) > 1:
        fp_to_tasks: dict[tuple, set] = {}
        fp_to_claims: dict[tuple, list] = {}
        for c in claims:
            payload = tuple(sorted(
                json.dumps(e, sort_keys=True) for e in (c.get("evidence") or [])
                if isinstance(e, dict)))
            if not payload:
                continue
            fp_to_tasks.setdefault(payload, set()).add(str(c.get("task_id") or "?"))
            fp_to_claims.setdefault(payload, []).append(c.get("claim_id"))
        for fp, tasks in fp_to_tasks.items():
            if len(tasks) > 1:
                for cid in fp_to_claims[fp]:
                    _add(cid, latest[cid].get("task_id"), "EVIDENCE_STALE_REUSE",
                         f"identical evidence payload recorded across tasks {sorted(tasks)}")

    return {"status": "violations" if violations else "ok",
            "entries": len(lines), "claims": len(claims), "violations": violations}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Claim ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyse")
    sub.add_parser("integrity")
    sub.add_parser("path")
    ad = sub.add_parser("append")
    ad.add_argument("--json", default="")
    ad.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    if a.cmd == "append" and not getattr(a, "json", ""):
        ap.error("--json or --json-file is required for append")

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

    if a.cmd == "integrity":
        out = integrity_report()
        print(json.dumps(out, indent=2))
        if out["status"] == "empty":
            sys.exit(3)
        sys.exit(1 if out["violations"] else 0)

    out = analyse()
    print(json.dumps(out, indent=2))
    if out["status"] == "empty":
        sys.exit(3)
    sys.exit(1 if out["invalid"] else 0)



