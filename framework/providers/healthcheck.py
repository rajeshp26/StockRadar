#!/usr/bin/env python3
"""Provider health pre-flight for task delegation.

Answers one question before dispatch: **is this model safe to spawn right now?**

The framework previously delegated first and learned about provider health from
dead workers: three explore subagents were spawned against an OpenRouter account
with no credits, each died at spawn ("Insufficient credits. This account never
purchased credits."), and each execution report classified the outcome as a
liveness/stall problem. That is the wrong layer, the wrong vocabulary, and a
guaranteed repeat spawn.

This module owns the provider boundary instead:

  classify   map raw error text to a failure class (vocabulary below)
  record     append a provider health record to <state_root>/providers/health.jsonl
  check      pre-flight verdict: PASS (0) | FAIL (1) | BLOCKED (2) | NOT_APPLICABLE (4)

The hard rule this enforces: never dispatch a production task to a model/provider
that has a recorded blocking failure within the current execution window. First
dispatch in a window is the probe; its outcome is recorded, and a blocking outcome
refuses the next dispatch. Inventory (opencode models) confirms the model exists;
the health ledger confirms it has not recently failed.

Failure taxonomy (from the Team Lead decision model, .opencode/agents/team-lead.md):

  SUSPECTED_STALL          process exists, no output (worker-level, not provider)
  AUTH_FAILURE             401/403, invalid or missing api key
  QUOTA_FAILURE            insufficient credits, payment required
  MODEL_UNAVAILABLE        model id not in inventory / 404
  PROVIDER_TIMEOUT         request timed out, 504, deadline exceeded
  PROVIDER_NETWORK_FAILURE connection refused, DNS, socket, fetch failed
  AGENT_STALL              worker responds but makes no progress (worker-level)
  AGENT_FAILURE            worker produced invalid work (worker-level)

Blocking classes (refuse dispatch): AUTH_FAILURE, QUOTA_FAILURE, MODEL_UNAVAILABLE,
PROVIDER_TIMEOUT, PROVIDER_NETWORK_FAILURE. Worker-level classes belong to task
supervision, not the provider boundary, so they never block here.

Blocking classes differ in how they expire (see TRANSIENT_CLASSES):

  transient  PROVIDER_TIMEOUT / PROVIDER_NETWORK_FAILURE clear once they fall
             outside the window. A blip is not a reason to refuse dispatch forever.
  persistent AUTH_FAILURE / QUOTA_FAILURE / MODEL_UNAVAILABLE ignore the window
             entirely. An unpaid account or a revoked key does not heal on a timer,
             and a uniform TTL on those silently re-enables dispatch against a
             provider that is still broken. They clear only when a later OK record
             for the same model is appended.

Exit codes: 0 pass | 1 fail (blocking class named) | 2 blocked (cannot determine:
CLI missing, inventory unreadable) | 3 usage | 4 not applicable (nothing resolved).
Blocked is never a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "framework"))

try:
    from models import resolve as _res
    _RES_OK = True
    _RES_ERR = ""
except Exception as _e:  # pragma: no cover - import failure path
    _RES_OK = False
    _RES_ERR = str(_e)

# --- failure taxonomy -------------------------------------------------------

# ordered: first matching rule wins. Worker-level classes are recognised so the
# same lexer serves task-event classification, but they do not block dispatch.
_RULES: list[tuple[str, re.Pattern]] = [
    ("AUTH_FAILURE", re.compile(r"401|403|unauthor|invalid api ?key|api ?key.*(invalid|missing)|authentication", re.I)),
    ("QUOTA_FAILURE", re.compile(r"insufficient credits|never purchased credits|quota|payment required|credit balance|billing|402", re.I)),
    ("MODEL_UNAVAILABLE", re.compile(r"model .*not found|no such model|404|not a valid model|unknown model|does not exist", re.I)),
    ("PROVIDER_TIMEOUT", re.compile(r"timed? ?out|504|deadline|timeout", re.I)),
    ("PROVIDER_NETWORK_FAILURE", re.compile(r"ECONNREFUSED|ENOTFOUND|ECONNRESET|socket|fetch failed|network|connection", re.I)),
    ("AGENT_STALL", re.compile(r"no progress|not responding|no output", re.I)),
    ("AGENT_FAILURE", re.compile(r"invalid work|malformed output|syntax error|agent failure", re.I)),
]

BLOCKING_CLASSES = {
    "AUTH_FAILURE", "QUOTA_FAILURE", "MODEL_UNAVAILABLE",
    "PROVIDER_TIMEOUT", "PROVIDER_NETWORK_FAILURE",
}
ALL_CLASSES = BLOCKING_CLASSES | {"SUSPECTED_STALL", "AGENT_STALL", "AGENT_FAILURE"}

# Blocking classes that legitimately heal on their own. Everything else in
# BLOCKING_CLASSES is persistent and is NOT subject to the window.
TRANSIENT_CLASSES = {"PROVIDER_TIMEOUT", "PROVIDER_NETWORK_FAILURE"}

DEFAULT_WINDOW_MIN = 30  # "current execution context" — overridable via env / flag


def classify(text: str) -> tuple[str | None, str]:
    """Map raw error text to (failure_class, matched_rule). None if no rule fires."""
    for cls, rx in _RULES:
        if rx.search(text):
            return cls, rx.pattern
    return None, ""


# --- health ledger ----------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from framework.adapters.gsd_state import root as _gsd_state_root


def _state_root() -> Path:
    """Delegate to the single source of GSD state-root resolution."""
    return _gsd_state_root()


def health_path() -> Path:
    override = os.environ.get("PROVIDER_HEALTH_FILE")
    if override:
        return Path(override)
    return _state_root() / "providers" / "health.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_records() -> list[dict]:
    p = health_path()
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            out.append({"parse_error": True, "line": i})
            continue
        out.append(rec)
    return out


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _order_key(rec: dict, index: int) -> tuple[float, int] | None:
    """Sort key that never ties across distinct rows.

    Timestamps are written at second precision (see _now), so two records written
    inside the same second compare equal on ts alone. A `ts > best_ts` test then
    keeps the FIRST of the two and silently ignores the newer one. Tie-breaking on
    append order makes the later line authoritative, which is what an append-only
    ledger means.
    """
    ts = _parse_ts(rec.get("ts"))
    if ts is None:
        return None
    return (ts.timestamp(), index)


def latest_for_model(records: list[dict], model: str, window_min: int) -> dict | None:
    """Most recent record for this model within the window. Used for reporting."""
    now = datetime.now(timezone.utc)
    best: dict | None = None
    best_key: tuple[float, int] | None = None
    for i, rec in enumerate(records):
        if rec.get("model") != model or rec.get("parse_error"):
            continue
        ts = _parse_ts(rec.get("ts"))
        if ts is None:
            continue
        if (now - ts).total_seconds() / 60 > window_min:
            continue
        key = _order_key(rec, i)
        if key is None:
            continue
        if best_key is None or key > best_key:
            best, best_key = rec, key
    return best


def latest_blocking_for_model(records: list[dict], model: str, window_min: int) -> dict | None:
    """Most recent *live* blocking record for this model, or None.

    "Live" is class-dependent: see the module docstring. A persistent blocking
    record (quota / auth / model) blocks no matter how old it is; a transient one
    only inside the window. An OK record is always live and therefore clears an
    earlier block.

    `records` must be in append order (load_records preserves it). Iteration is
    bounded by the caller's list, so this is O(n) in ledger size, not O(n^2).
    """
    now = datetime.now(timezone.utc)
    latest_live: dict | None = None
    latest_key: tuple[float, int] | None = None
    for i, rec in enumerate(records):
        if rec.get("model") != model or rec.get("parse_error"):
            continue
        cls = rec.get("class")
        if cls == "OK":
            pass                       # an OK is always live
        elif cls in BLOCKING_CLASSES and cls in TRANSIENT_CLASSES:
            ts = _parse_ts(rec.get("ts"))
            if ts is None or (now - ts).total_seconds() / 60 > window_min:
                continue              # expired blip: not live, cannot clear or block
        elif cls in BLOCKING_CLASSES:
            pass                       # persistent: live regardless of age
        else:
            continue                   # worker-level class: not a provider signal
        key = _order_key(rec, i)
        if key is None:
            continue
        if latest_key is not None and key <= latest_key:
            continue                   # an older record cannot override a newer one
        latest_live, latest_key = rec, key
    if latest_live is None:
        return None
    if latest_live.get("class") in BLOCKING_CLASSES:
        return latest_live
    return None


def record(provider: str, model: str, cls: str, detail: str = "",
           source: str = "manual", task_id: str = "") -> tuple[bool, str]:
    """Append a provider health record. cls must be in ALL_CLASSES (or OK)."""
    if cls not in ALL_CLASSES and cls != "OK":
        return False, "BAD_CLASS: %s (allowed: %s | OK)" % (cls, " ".join(sorted(ALL_CLASSES)))
    if not provider or not model:
        return False, "PROVIDER_MODEL_REQUIRED"
    rec = {
        "provider": provider,
        "model": model,
        "class": cls,
        "detail": detail,
        "source": source,
        "ts": _now(),
    }
    if task_id:
        rec["task_id"] = task_id
    p = health_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return True, "recorded"


# --- pre-flight check -------------------------------------------------------

def _resolved_models() -> dict[str, str]:
    """{agent: model} from the live environment via models/resolve.py. Fail-closed."""
    if not _RES_OK:
        raise RuntimeError("resolve engine unavailable: %s" % _RES_ERR)
    cfg = {}
    try:
        cfg = json.loads(Path("opencode.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    script = Path("framework/models/profiles.sh")
    text = script.read_text(encoding="utf-8") if script.exists() else ""
    pf = _res.preflight(cfg, os.environ, text)
    if pf.get("failures"):
        raise RuntimeError("model resolution failures: %s" % ", ".join(pf["failures"]))
    agents = pf["agents"]
    return {name: info["model"] for name, info in agents.items() if info.get("model")}


def check(window_min: int | None = None) -> dict:
    """Pre-flight verdict. Returns a report dict; caller maps to exit code."""
    window = window_min if window_min is not None else int(
        os.environ.get("PROVIDER_HEALTH_WINDOW_MIN", DEFAULT_WINDOW_MIN))

    try:
        models = _resolved_models()
    except RuntimeError as e:
        return {"status": "blocked", "reason": str(e), "models": {}}
    if not models:
        return {"status": "not_applicable", "reason": "no models resolved", "models": {}}

    inv = _res.inventory(timeout=8)
    if not inv.get("ok"):
        return {"status": "blocked",
                "reason": "inventory unavailable (cannot verify provider health): %s" % inv.get("note", ""),
                "models": models}

    inventory_models = set(inv.get("models") or [])
    records = load_records()
    problems: list[dict] = []
    seen: set[str] = set()
    for agent, model in models.items():
        if model in seen:
            continue
        seen.add(model)
        entry = {"agent": agent, "model": model, "in_inventory": model in inventory_models}
        if model not in inventory_models:
            entry["problem"] = "MODEL_UNAVAILABLE: not in `opencode models` inventory"
            entry["blocking"] = True
            problems.append(entry)
            continue
        blocking = latest_blocking_for_model(records, model, window)
        if blocking:
            entry["problem"] = "%s: %s" % (blocking.get("class"),
                                           (blocking.get("detail") or blocking.get("source") or "")[:160])
            entry["blocking"] = True
            entry["recorded_at"] = blocking.get("ts")
            problems.append(entry)
            continue
        entry["blocking"] = False
        recent = latest_for_model(records, model, window)
        if recent:
            entry["last_class"] = recent.get("class")
    if problems:
        return {"status": "fail", "window_min": window, "problems": problems, "models": models}
    return {"status": "pass", "window_min": window, "problems": [], "models": models}


# --- selftest ---------------------------------------------------------------

def _selftest() -> int:
    res: list[bool] = []

    def t(name, ok, detail=""):
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, " - " + detail if detail else ""))
        res.append(ok)

    # S1 classify: the exact observed OpenRouter credit-wall error
    cls, rule = classify("Insufficient credits. This account never purchased credits. "
                         "Make sure your key is on the correct account or org, and if so, "
                         "purchase more at https://openrouter.ai/settings/credits")
    t("S1 classify observed credit error -> QUOTA_FAILURE", cls == "QUOTA_FAILURE", str(cls))

    # S2 classify: auth, model, timeout, network
    t("S2a classify 401 -> AUTH_FAILURE", classify("401 Unauthorized: invalid API key")[0] == "AUTH_FAILURE")
    t("S2b classify model 404 -> MODEL_UNAVAILABLE", classify("model openrouter/x not found")[0] == "MODEL_UNAVAILABLE")
    t("S2c classify timeout -> PROVIDER_TIMEOUT", classify("request timed out after 30s")[0] == "PROVIDER_TIMEOUT")
    t("S2d classify network -> PROVIDER_NETWORK_FAILURE", classify("ECONNREFUSED fetch failed")[0] == "PROVIDER_NETWORK_FAILURE")
    t("S2e classify noise -> None", classify("all good here")[0] is None)

    # S3 record->read roundtrip on a temp ledger
    with tempfile.TemporaryDirectory() as td:
        old = os.environ.get("PROVIDER_HEALTH_FILE")
        os.environ["PROVIDER_HEALTH_FILE"] = str(Path(td) / "health.jsonl")
        try:
            ok, msg = record("openrouter", "opencode/big-pickle", "QUOTA_FAILURE",
                             detail="Insufficient credits", source="selftest")
            t("S3a record accepted", ok and msg == "recorded", msg)
            ok2, msg2 = record("openrouter", "opencode/big-pickle", "NOT_A_CLASS",
                               detail="x", source="selftest")
            t("S3b bad class rejected", not ok2 and msg2.startswith("BAD_CLASS"), msg2)
            recs = load_records()
            t("S3c load roundtrip", len(recs) == 1 and recs[0]["class"] == "QUOTA_FAILURE")
            latest = latest_for_model(recs, "opencode/big-pickle", 5)
            t("S3d latest within window", latest is not None and latest["class"] == "QUOTA_FAILURE")

            # S3e-S3i pin the window rule. The former assertion
            # ("zero window excludes") is deliberately gone: it encoded the
            # behaviour this patch removes. A persistent failure must NOT expire.
            q0 = latest_blocking_for_model(recs, "opencode/big-pickle", 0)
            t("S3e QUOTA_FAILURE ignores the window entirely",
              q0 is not None and q0["class"] == "QUOTA_FAILURE")

            timeout_only = [{"provider": "openrouter", "model": "m-timeout",
                             "class": "PROVIDER_TIMEOUT", "detail": "", "source": "selftest",
                             "ts": _now()}]
            t("S3f PROVIDER_TIMEOUT expires outside the window",
              latest_blocking_for_model(timeout_only, "m-timeout", 0) is None)

            recs.append({"provider": "openrouter", "model": "opencode/big-pickle",
                         "class": "OK", "detail": "", "source": "selftest", "ts": _now()})
            t("S3g a later OK record clears the persistent block",
              latest_blocking_for_model(recs, "opencode/big-pickle", 0) is None)

            same = [
                {"provider": "p", "model": "m", "class": "QUOTA_FAILURE",
                 "detail": "", "source": "selftest", "ts": "2026-09-30T00:00:00Z"},
                {"provider": "p", "model": "m", "class": "OK",
                 "detail": "", "source": "selftest", "ts": "2026-09-30T00:00:00Z"},
            ]
            t("S3h same-second tie: later OK wins",
              latest_blocking_for_model(same, "m", 100000) is None)
            t("S3i same-second tie: later failure wins",
              latest_blocking_for_model(list(reversed(same)), "m", 100000) is not None)
        finally:
            if old is None:
                os.environ.pop("PROVIDER_HEALTH_FILE", None)
            else:
                os.environ["PROVIDER_HEALTH_FILE"] = old

    # S4 classify is first-match-ordered: auth key error beats quota
    cls4, _ = classify("401: insufficient credits on this key")
    t("S4 first-match order (401 -> AUTH_FAILURE)", cls4 == "AUTH_FAILURE", str(cls4))

    return 0 if all(res) else 1


# --- main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="healthcheck", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_classify = sub.add_parser("classify", help="map error text to a failure class")
    p_classify.add_argument("--error", required=True, help="raw error text")

    p_record = sub.add_parser("record", help="append a provider health record")
    p_record.add_argument("--provider", required=True)
    p_record.add_argument("--model", required=True)
    p_record.add_argument("--class", dest="cls", required=True)
    p_record.add_argument("--detail", default="")
    p_record.add_argument("--source", default="manual")
    p_record.add_argument("--task-id", default="")

    sub.add_parser("check", help="pre-flight verdict: pass|fail|blocked|not_applicable")
    sub.add_parser("resolve", help="print per-agent model resolution (fail-closed)")
    sub.add_parser("inventory", help="query `opencode models` (ground truth)")
    sub.add_parser("selftest", help="behavioral self-test (no network)")

    args = ap.parse_args()

    if args.cmd == "classify":
        cls, rule = classify(args.error)
        print(json.dumps({"class": cls, "matched_rule": rule}))
        return 0

    if args.cmd == "record":
        ok, msg = record(args.provider, args.model, args.cls, args.detail, args.source, args.task_id)
        print(msg)
        return 0 if ok else 1

    if args.cmd == "check":
        report = check()
        print(json.dumps(report, indent=2))
        return {"pass": 0, "fail": 1, "blocked": 2, "not_applicable": 4}[report["status"]]

    if args.cmd == "resolve":
        try:
            models = _resolved_models()
        except RuntimeError as e:
            print("blocked: %s" % e)
            return 2
        for agent, model in sorted(models.items()):
            print("%-20s %s" % (agent, model))
        return 0

    if args.cmd == "inventory":
        inv = _res.inventory(timeout=10)
        print(json.dumps(inv, indent=2))
        return 0 if inv.get("ok") else 2

    if args.cmd == "selftest":
        return _selftest()

    return 3


if __name__ == "__main__":
    sys.exit(main())
