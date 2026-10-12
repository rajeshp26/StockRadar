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
import argparse, json, os, re, sys, time
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


LEDGER_SCHEMA_VERSION = 2

# Every validation rule declares a class. The class answers one question: may this
# rule judge a record that predates it? DERIVABLE rules read only data already in the
# record, so an older record either satisfies them or is genuinely malformed -- they
# may judge history. AUTHOR_SUPPLIED rules need information only the recording agent
# had, so they may judge only records written at or after their `since`. VOCABULARY
# rules change an allowed token and keep the old spelling legal for one version.
#
# A rule whose `since` is newer than a record's version is NOT evaluated against that
# record. It is reported in analyse()'s `grandfathered` bucket instead -- counted,
# visible, never blocking -- because a rule that postdates a record says nothing about
# whether the record is sound. `append` re-stamps the current version on every write,
# so a legacy claim that is later re-appended is re-judged under current rules and the
# gap closes itself with no migration script.
LEDGER_RULES = (
    # since 1 -- derivable from record content, or pre-existing author-supplied fields
    {"code": "CLAIM_INCOMPLETE", "cls": "DERIVABLE", "since": 1,
     "desc": "a required top-level field is missing, empty, or None"},
    {"code": "CLAIM_BAD_SCHEMA_VERSION", "cls": "DERIVABLE", "since": 1,
     "desc": "schema_version is present but is not a positive integer"},
    {"code": "CLAIM_BAD_VOCAB", "cls": "VOCABULARY", "since": 1,
     "desc": "a vocabulary value is outside its closed set"},
    {"code": "CLAIM_UNKNOWN_RUNTIME", "cls": "DERIVABLE", "since": 1,
     "desc": "an evidence runtime names an unrecorded RT- id"},
    {"code": "CLAIM_ENV_UNKNOWN", "cls": "DERIVABLE", "since": 1,
     "desc": "an evidence env names an unrecorded ENV- id"},
    {"code": "CLAIM_BAD_DISCONFIRMATION", "cls": "VOCABULARY", "since": 1,
     "desc": "an evidence disconfirmation is outside its closed set"},
    {"code": "CLAIM_DISCONFIRMED_BUT_VERIFIED", "cls": "DERIVABLE", "since": 1,
     "desc": "a VERIFIED claim carries a refuted disconfirmation"},
    {"code": "CLAIM_STORED_CONFIDENCE", "cls": "DERIVABLE", "since": 1,
     "desc": "the record carries a confidence field; confidence is derived"},
    {"code": "CLAIM_FACT_UNVERIFIED", "cls": "DERIVABLE", "since": 1,
     "desc": "classification FACT with a status other than VERIFIED"},
    {"code": "CLAIM_CAUSAL_NO_RUNTIME", "cls": "DERIVABLE", "since": 1,
     "desc": "a causal FACT without runtime-backed evidence"},
    {"code": "CLAIM_VERIFIED_NO_COMMAND", "cls": "AUTHOR_SUPPLIED", "since": 1,
     "desc": "VERIFIED or PARTIALLY_VERIFIED without verified_by"},
    {"code": "CLAIM_VERIFIED_NO_PROVENANCE", "cls": "DERIVABLE", "since": 1,
     "desc": "VERIFIED without evidence naming runtime + entry_point, reproduced"},
    {"code": "CLAIM_REFUTED_NO_EVIDENCE", "cls": "DERIVABLE", "since": 1,
     "desc": "REFUTED without fail evidence carrying expected and actual"},
    # since 2 -- author-supplied and forward-only. Both postdate the existing store:
    # applying them retroactively would demand provenance that cannot be reconstructed,
    # which is manufacturing it, not verifying it.
    {"code": "CLAIM_VERIFIED_NO_SCOPE_LIMIT", "cls": "AUTHOR_SUPPLIED", "since": 2,
     "desc": "VERIFIED without does_not_prove"},
    {"code": "CLAIM_VERIFIED_NO_INDEPENDENT_CHECK", "cls": "AUTHOR_SUPPLIED", "since": 2,
     "desc": "high-impact VERIFIED without independent_check"},
)

RULE_SINCE = {r["code"]: r["since"] for r in LEDGER_RULES}
RULE_CLASS = {r["code"]: r["cls"] for r in LEDGER_RULES}


def _schema_version_problem(rec: dict) -> str | None:
    """CLAIM_BAD_SCHEMA_VERSION when `schema_version` is present but malformed.

    Absent means v1 and stays legal. A present-but-malformed value is a defect, not
    a v1 record. Reading `"2"`, `true` or `0` as v1 exempts the record from the very
    rules it claims to satisfy, so one typo would silently disable validation for
    that record instead of reporting it. The v2 design already depends on the stored
    version being meaningful; a value that is silently coerced destroys that premise.
    """
    if "schema_version" not in rec:
        return None
    v = rec.get("schema_version")
    if v is None or isinstance(v, bool) or not isinstance(v, int) or v < 1:
        return "CLAIM_BAD_SCHEMA_VERSION"
    return None


def _record_version(rec: dict) -> int:
    """The rule-set version a record was written under. Absent means v1.

    Raises ValueError on a present-but-malformed value. Callers that need a version
    for reporting screen with `_schema_version_problem` first.
    """
    v = rec.get("schema_version")
    if v is None:
        return 1
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError("CLAIM_BAD_SCHEMA_VERSION")
    return v


def _version_ok(rec: dict) -> bool:
    return _schema_version_problem(rec) is None


def _rule_applies(code: str, rec: dict) -> bool:
    """True when `code` was in force when `rec` was written.

    Two failure modes this refuses:

    An unregistered code raises instead of defaulting. `RULE_SINCE.get(code, 1)`
    would make a newly added rule inherit `since=1` and retroactively judge every
    historical record -- exactly the invalidation the v2 design exists to prevent,
    and it would do so silently, because an unregistered code has no other symptom.

    A malformed version fails closed onto the current rule set rather than being
    read as v1. A record cannot opt out of a rule by corrupting the field that
    decides which rules apply to it.
    """
    if code not in RULE_SINCE:
        raise KeyError("rule %r is not registered in LEDGER_RULES" % (code,))
    if not _version_ok(rec):
        return True
    return _record_version(rec) >= RULE_SINCE[code]


# Which records a rule has anything to say about, independent of version. Without
# this the `grandfathered` report counts rules against records the rules never
# governed, which buries the records that genuinely rest on an older rule set.
_RULE_TARGETS = {
    "CLAIM_VERIFIED_NO_SCOPE_LIMIT":
        lambda rec: rec.get("status") == "VERIFIED",
    "CLAIM_VERIFIED_NO_INDEPENDENT_CHECK":
        lambda rec: (rec.get("status") == "VERIFIED" and rec.get("impact") == "high"),
}


def _rule_targets(code: str, rec: dict) -> bool:
    """Whether a rule's subject condition matches this record, ignoring version."""
    pred = _RULE_TARGETS.get(code)
    return True if pred is None else bool(pred(rec))


def registry_gaps() -> list[dict]:
    """CLAIM_ codes validate_record() can emit that LEDGER_RULES does not register.

    An emitted-but-unregistered code is the precondition for the retroactive
    default in `_rule_applies`, so it is reported rather than tolerated. Extracted
    from the function's own source, which means a rule added to validate_record
    without a registry entry is detected rather than waiting to misjudge history.

    Scoped to the CLAIM_ namespace on purpose. _validate_integrity emits EVIDENCE_*
    codes on the separate E1-E8 integrity channel reported by integrity_report();
    those are integrity signals, not versioned validation rules, and counting them
    as registry gaps would report four permanent phantom gaps on every run.
    """
    import inspect
    body = inspect.getsource(validate_record)
    emitted = set(re.findall(r'problems\.append\(\s*"(CLAIM_[A-Z0-9_]+)"', body))
    return [{"code": c, "since": None, "cls": None}
            for c in sorted(emitted - set(RULE_SINCE))]


def _scope_limit_present(rec: dict) -> bool:
    """A usable scope limit is a non-empty, non-blank string.

    `not rec.get("does_not_prove")` accepts `{}`, `0`, `False` and `"   "`, all of
    which satisfy the rule while documenting nothing -- the same empty_string escape
    the analyse() metric exists to make visible. The rule and its own metric must
    agree on what counts, or the metric stops describing the rule.
    """
    v = rec.get("does_not_prove")
    return isinstance(v, str) and bool(v.strip())


def skipped_rules(rec: dict) -> list[dict]:
    """Rules that exist but were not in force for this record.

    A record whose version is malformed is not grandfathered -- it is reported as
    invalid. Listing it here would present a defect as a compatibility exemption.
    """
    if not _version_ok(rec):
        return []
    v = _record_version(rec)
    return [{"code": r["code"], "cls": r["cls"], "since": r["since"],
             "record_version": v}
            for r in LEDGER_RULES if r["since"] > v]


# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework.adapters.gsd_state import root as _gsd_state_root
from framework import locate as _locate

_REPO_ROOT = _locate.app_root()  # E2 evidence-existence resolution (was parents[2])


def _state_root() -> Path:
    """Delegate to the single source, keeping this module's env-var override.

    GSD_STATE_ROOT is honoured here and nowhere else in the framework. That asymmetry is
    deliberate, not an oversight: it is this ledger's documented escape hatch for pinning
    state in a disposable environment during verification runs.
    """
    env = os.environ.get("GSD_STATE_ROOT")
    if env and (len(env) >= 2 and env[1] == ":" or env.startswith("/")):
        return Path(env)
    return _gsd_state_root()


def _runtime_recorded(runtime_id: str) -> bool:
    """True iff an execution context row with that id exists binding provider+model.

    The ledger reads the context file directly rather than importing the
    execution_context module, so the two cannot disagree about the record shape. A claim
    whose evidence names a canonical RT- id must resolve to a recorded context; an unknown
    id is provenance the ledger cannot reproduce, and is refused.
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

    # 2e. The stored version decides which rules apply. A present-but-malformed value
    # is refused rather than coerced, so a record cannot drop out of the rules it is
    # written under by corrupting the field that selects them.
    ver_problem = _schema_version_problem(rec)
    if ver_problem:
        problems.append(ver_problem)

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
        # AUTHOR_SUPPLIED: a scope limit and a second command cannot be reconstructed
        # from a record written before the rules existed. Each is judged only against
        # records at or after its `since`; older records are reported in `grandfathered`.
        if _rule_applies("CLAIM_VERIFIED_NO_SCOPE_LIMIT", rec) and not _scope_limit_present(rec):
            problems.append("CLAIM_VERIFIED_NO_SCOPE_LIMIT")
        if _rule_applies("CLAIM_VERIFIED_NO_INDEPENDENT_CHECK", rec) and impact == "high" and not rec.get("independent_check"):
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
    # Stamp the rule set in force at write time, before validation, so a rule added
    # today can never become a retroactive verdict on a record written before it.
    # Unconditional: a caller cannot declare a weaker rule set for itself, and any
    # re-append re-judges the claim under current rules (self-healing grandfathering).
    entry["schema_version"] = LEDGER_SCHEMA_VERSION
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
                "by_type": {}, "by_classification": {}, "by_status": {}, "by_confidence": {},
                "grandfathered": [], "by_scope_limit": {}}
    lines = [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]
    records = []
    for ln in lines:
        try:
            records.append(json.loads(ln))
        except json.JSONDecodeError:
            print("WARN: claim ledger line is not valid JSON -- skipped", file=sys.stderr)
    if not records:
        return {"status": "empty", "entries": len(lines), "claims": 0, "invalid": [],
                "by_type": {}, "by_classification": {}, "by_status": {}, "by_confidence": {},
                "grandfathered": [], "by_scope_limit": {}}

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

    # Rules that postdate a record are reported, not failed: counted and visible so the
    # gap stays auditable, never blocking so the gate is not trained into being routed
    # around. Scope-limit quality is measured the same way -- `empty_string` is the
    # documented way to satisfy the rule without doing it, so it gets its own count.
    grandfathered = []
    scope_limits = Counter()
    for r in claims:
        v = _record_version(r) if _version_ok(r) else None
        for s in skipped_rules(r):
            # Only rules that would have had something to say about this record. A
            # VERIFIED-only rule is not evidence that an UNVERIFIED record predates
            # it, and counting it there buries the records that genuinely rest on
            # an older rule set behind rows that mean nothing.
            if not _rule_targets(s["code"], r):
                continue
            grandfathered.append({"claim_id": r.get("claim_id"),
                                  "status": r.get("status"),
                                  "code": s["code"], "since": s["since"],
                                  "record_version": v})
        # Scope-limit quality is reported per record the rule actually governs, so
        # the number answers "of the claims that must state a limit, how many do?"
        # rather than counting records the rule says nothing about.
        if not _rule_targets("CLAIM_VERIFIED_NO_SCOPE_LIMIT", r):
            scope_limits["not_applicable"] += 1
        elif not _rule_applies("CLAIM_VERIFIED_NO_SCOPE_LIMIT", r):
            scope_limits["grandfathered"] += 1
        elif not _scope_limit_present(r):
            raw = r.get("does_not_prove")
            if raw is None:
                scope_limits["missing"] += 1
            elif not isinstance(raw, str):
                scope_limits["not_a_string"] += 1
            else:
                scope_limits["empty_string"] += 1
        else:
            scope_limits["present"] += 1

    return {
        "status": "invalid" if invalid else "ok",
        "entries": len(lines),
        "claims": len(claims),
        "invalid": invalid,
        "by_type": dict(Counter(r.get("claim_type", "?") for r in claims)),
        "by_classification": dict(Counter(r.get("classification", "?") for r in claims)),
        "by_status": dict(Counter(r.get("status", "?") for r in claims)),
        "by_confidence": dict(Counter(derive_confidence(r) for r in claims)),
        "grandfathered": grandfathered,
        "by_scope_limit": dict(scope_limits),
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
                # A citation may carry a line anchor (`f.py:246`, `f.py:12-20`). The
                # anchor is metadata about the file, not part of its name, so it is
                # stripped before resolution. Leaving it attached makes every
                # line-anchored citation report a file as missing, and a gate that
                # cries wolf on files that exist is worse than no gate at all -- it
                # teaches reviewers to ignore E2. Resolution is anchored to the repo
                # root rather than the caller's cwd, so the verdict does not depend
                # on where the gate was invoked from.
                target = re.sub(r":\d+(-\d+)?$", "", ep)
                if not (_REPO_ROOT / target).exists():
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



