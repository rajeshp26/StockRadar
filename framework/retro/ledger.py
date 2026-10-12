#!/usr/bin/env python3
"""Retro ledger. Append-only record of defect escapes and the framework changes they caused.

Two jobs the individual retrospective cannot do:

1. RECURRENCE. The same (injection_phase, defect_class, escaped_checkpoint) appearing twice
   means the first fix did not work. A framework that files the same finding repeatedly is
   generating paperwork, not learning. Second occurrence escalates to human.

2. UNVERIFIED FIXES. A retro that recommends a change and never lands it is a wish. Every
   entry carries `fix_landed` and `fix_verified_by` (a command + exit code). An entry with a
   recommendation and no landed fix past its due date is reported as debt.

TWO SIGNATURES, NOT ONE
-----------------------
`signature()` is the CLASS key: structural shape only, no site, no task id, no prose. It is
what aggregation and trend counts use.

`signature_instance()` is the CLASS key PLUS `defect_site`. It is what recurrence is judged
on. The class key alone produces false recurrences: two unrelated findings that share a
class and an escaped checkpoint collide even though they are in different files and were
fixed independently. Recurrence means "this gap, in this place, came back" — not "this
shape of gap was seen twice anywhere".

`defect_site` is the field that separates the two. It is a judgement, and a wrong one
merges two sites or splits one; it is recorded explicitly rather than inferred from prose.

IMMUTABLE AMENDMENTS
--------------------
The ledger has no close command and never rewrites history. A correction is a new row
carrying `supersedes: <task_id>`; `resolve_amendments()` folds amendments at read time.
An amendment that claims `fix_landed` must carry `fix_verified_by` — a metadata-only
backfill (adding `defect_site` or a `counterfactual`) needs no proof, because it asserts
nothing about a fix.

Exit codes:
  0  ledger consistent
  1  recurrence detected at or beyond threshold, or a fix claimed without verification
  3  ledger empty or unreadable (nothing to conclude — never a pass)
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

RECURRENCE_THRESHOLD = 2   # 2nd occurrence of the same signature escalates

# Closed vocabulary for counterfactual.gap_type. An uncontrolled value means the
# retrospective did not choose a fix tier, which is the unfalsifiable outcome the
# subsystem exists to prevent. "accepted" is a deliberate non-fix and must say so.
CONTROLLED_GAP_TYPES = {
    "routing", "validation", "gate_routing", "skill_rule", "agent_instruction",
    "declared_rule", "design_checklist", "unmapped_combination", "accepted",
}

# Fields an amendment row may carry. Everything else in the ledger is immutable
# (injected_at, defect_class, primary_gap, fix_target, routing_gaps, containment_misses).
AMENDABLE = ("fix_landed", "fix_verified_by", "note", "defect_site", "counterfactual")

# Phase at which a defect reaching here means every checkpoint passed it.
PRODUCTION_PHASES = {"production", "security"}

# Transitional: sites for rows written before `defect_site` existed, transcribed from
# each entry's own recommendation. Delete once every row carries the field itself.
_BACKFILL_SITES = {
    "FRAMEWORK-VALIDATE-REG": "framework/validate.py",
    "EXT-CRITIQUE-01": "framework/adapters/gsd_state.py",
    "EXT-CRITIQUE-02": "framework/adapters/gsd_state.py",
    "EXT-CRITIQUE-03": "framework/gates/g_entry.sh",
    "EXT-CRITIQUE-05": ".lifecycle",
    "EXT-CRITIQUE-07": "framework/contracts/validator.py",
    "TELEMETRY-RCA": "framework/opencode/plugin/telemetry.ts",
    "PRICE-HISTORY-COMPRESSOR": "shared/price_rows.py",
}


# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework.adapters.gsd_state import root as _gsd_state_root


def _state_root() -> Path:
    """Delegate to the single source of GSD state-root resolution."""
    return _gsd_state_root()


def ledger_path() -> Path:
    return _state_root() / "retro" / "ledger.jsonl"


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
            print(f"WARN: ledger line {i} is not valid JSON — skipped", file=sys.stderr)
    return out


def signature(e: dict) -> str:
    """CLASS key: what makes two escapes the same KIND of gap.

    Deliberately excludes the task id, the site, and the human-written description: the
    same structural gap in different words is still the same gap, and matching on prose
    would let a rephrase hide a recurrence. This is the aggregation key — do NOT use it
    to judge recurrence; that is `signature_instance`.
    """
    return "|".join([
        e.get("injected_at", "?"),
        e.get("defect_class", "?"),
        (e.get("primary_gap") or "?"),
        ",".join(sorted(e.get("routing_gaps", []) + e.get("containment_misses", []))) or "?",
    ])


def _site_of(e: dict) -> str:
    """The site this defect lived in, or '?' when it is not recorded.

    Prefers the explicit field; falls back to the pre-`defect_site` transcription table
    so a ledger that has not been backfilled yet still reports sane instance keys.
    """
    site = e.get("defect_site")
    if isinstance(site, str) and site.strip():
        return site.strip()
    return _BACKFILL_SITES.get(e.get("task_id", ""), "?")


def signature_instance(e: dict) -> str:
    """CLASS key + site. The key recurrence is judged on.

    Two findings in different files are two instances even when the class key matches;
    the class key alone would report them as the same gap recurring.
    """
    return signature(e) + "| " + _site_of(e)


def _open_debt(e: dict) -> bool:
    """True when THIS entry still owes a fix.

    Per-entry, not per-class: one entry of a recurring shape being resolved does not
    resolve the other. A group-level predicate kept G7 red forever once any shape had
    ever recurred, because the ledger has no close command.
    """
    if e.get("fix_target") == "none_human_judgement":
        return False
    return not bool(e.get("fix_landed"))


def checkpoint_pressure(entries: list[dict]) -> dict:
    """How many findings escaped past each checkpoint, and across how many sites.

    A count alone is ambiguous: 7 escapes is a systemic routing problem if all 7 came
    from one broken place, and noise if they came from 7 unrelated ones. Reporting
    both numbers separates those. This is a SIGNAL, never a gate input — it orders
    attention, it does not pass or fail anything.
    """
    occ: Counter = Counter()
    sites: dict[str, set] = defaultdict(set)
    for e in entries:
        for cp in list(e.get("routing_gaps", [])) + list(e.get("containment_misses", [])):
            occ[cp] += 1
            sites[cp].add(_site_of(e))
    return {cp: {"occurrences": n, "distinct_sites": len(sites[cp])}
            for cp, n in sorted(occ.items(), key=lambda kv: (-kv[1], kv[0]))}


def _counterfactual_ok(e: dict) -> tuple[bool, str]:
    """Whether a production finding declares a controlled fix tier."""
    cf = e.get("counterfactual")
    if not isinstance(cf, dict) or not cf:
        return False, "no counterfactual"
    gt = cf.get("gap_type")
    if gt not in CONTROLLED_GAP_TYPES:
        return False, "uncontrolled gap_type: %r" % (gt,)
    if not cf.get("earliest_prevention_point"):
        return False, "no earliest_prevention_point"
    return True, ""


def resolve_amendments(entries: list[dict]) -> list[dict]:
    """Fold supersession rows into the entries they amend.

    History is never mutated: an amendment is an ordinary row that also names
    `supersedes`. Amendment rows are dropped from the returned list so every consumer
    sees one logical entry per original row.
    """
    amend = {a["supersedes"]: a for a in entries if a.get("supersedes")}
    out = []
    for e in entries:
        if e.get("supersedes"):
            continue
        a = amend.get(e.get("task_id"))
        merged = dict(e)
        if a:
            for k in AMENDABLE:
                if k in a:
                    merged[k] = a[k]
            merged["amended_at"] = a.get("recorded_at")
        out.append(merged)
    return out


def supersede(target: str, fields: dict) -> str:
    """Append an immutable amendment to `target`. Never rewrites the original row."""
    unknown = [k for k in fields if k not in AMENDABLE]
    if unknown:
        print(json.dumps({"error": "field not amendable", "fields": sorted(unknown),
                          "amendable": list(AMENDABLE)}), file=sys.stderr)
        sys.exit(1)
    if fields.get("fix_landed") and not fields.get("fix_verified_by"):
        print(json.dumps({"error": "fix_landed requires fix_verified_by"}), file=sys.stderr)
        sys.exit(1)
    known = {e.get("task_id") for e in load()}
    if target not in known:
        print(json.dumps({"error": "unknown target", "task_id": target}), file=sys.stderr)
        sys.exit(1)
    row = {
        "task_id": "AMEND-" + target,
        "supersedes": target,
        "kind": "amendment",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    row.update(fields)
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return str(p)


def append(entry: dict) -> str:
    required = ["task_id", "injected_at", "caught_at", "defect_class", "primary_gap",
                "fix_target", "fix_landed"]
    missing = [k for k in required if k not in entry]
    if missing:
        print(json.dumps({"error": "incomplete retro entry", "missing": missing}),
              file=sys.stderr)
        sys.exit(1)
    if entry["fix_target"] != "none_human_judgement" and not entry.get("fix_landed"):
        entry.setdefault("debt_opened", date.today().isoformat())
    # A defect that reached production passed every checkpoint. Its escape therefore has
    # to name the control that was missing and the tier it belonged to, from the closed
    # vocabulary — not a paragraph about being more careful.
    if entry.get("caught_at") in PRODUCTION_PHASES or \
            str(entry.get("defect_class", "")).startswith("security"):
        ok, why = _counterfactual_ok(entry)
        if not ok:
            print(json.dumps({"error": "production finding needs a controlled counterfactual",
                              "detail": why,
                              "gap_types": sorted(CONTROLLED_GAP_TYPES)}), file=sys.stderr)
            sys.exit(1)
    entry["signature"] = signature(entry)
    entry["signature_instance"] = signature_instance(entry)
    if not entry.get("defect_site"):
        entry["defect_site"] = _site_of(entry)
    entry.setdefault("recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"))

    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return str(p)


def analyse() -> dict:
    raw = load()
    if not raw:
        return {"status": "empty", "entries": 0,
                "note": "no retrospectives recorded — nothing to conclude"}
    entries = resolve_amendments(raw)

    # Recurrence must mean "the gap is still open", not "history exists". The ledger is
    # append-only and has no close command, so without a resolved predicate any signature
    # that ever recurred keeps G7 red permanently.
    by_inst: dict[str, list[dict]] = {}
    for e in entries:
        by_inst.setdefault(signature_instance(e), []).append(e)
    recurring = {s: len(g) for s, g in by_inst.items()
                 if len(g) >= RECURRENCE_THRESHOLD and any(_open_debt(e) for e in g)}

    by_target = Counter(e.get("fix_target", "?") for e in entries)
    by_phase = Counter(e.get("injected_at", "?") for e in entries)
    by_gap = Counter(e.get("primary_gap", "?") for e in entries)

    # A fix claimed as landed must name how it was proven.
    unverified = [{"task_id": e.get("task_id"), "fix_target": e.get("fix_target")}
                  for e in entries
                  if e.get("fix_landed") and not e.get("fix_verified_by")]

    open_debt = [{"task_id": e.get("task_id"), "fix_target": e.get("fix_target"),
                  "opened": e.get("debt_opened"), "defect_site": _site_of(e)}
                 for e in entries if _open_debt(e)]

    # Recurrence detail: which tasks, so the escalation is actionable rather than a count.
    detail = defaultdict(list)
    for e in entries:
        s = signature_instance(e)
        if s in recurring:
            detail[s].append({"task_id": e.get("task_id"),
                              "fix_target": e.get("fix_target"),
                              "fix_landed": e.get("fix_landed"),
                              "defect_site": _site_of(e),
                              "recorded_at": e.get("recorded_at")})

    judgement_rate = by_target.get("none_human_judgement", 0) / len(entries)

    return {
        "status": "recurrence" if recurring else ("unverified_fix" if unverified else "ok"),
        "entries": len(entries),
        "recurring_signatures": [
            {"signature": s, "occurrences": n, "history": detail[s]}
            for s, n in sorted(recurring.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "unverified_fixes": unverified,
        "open_fix_debt": open_debt,
        "checkpoint_pressure": checkpoint_pressure(entries),
        "by_injection_phase": dict(by_phase),
        "by_primary_gap": dict(by_gap),
        "by_fix_target": dict(by_target),
        # High judgement rate is a signal, not a failure: it can mean the framework has
        # reached the limit of what checks can express. Reported so the trend is visible.
        "human_judgement_rate": round(judgement_rate, 3),
        "escalate": bool(recurring) or bool(unverified),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Retro ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyse")
    sub.add_parser("path")
    ad = sub.add_parser("append")
    ad.add_argument("--json", default="")
    ad.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    sp = sub.add_parser("supersede", help="append an immutable amendment to an existing entry")
    sp.add_argument("--target", required=True, help="task_id of the entry to amend")
    sp.add_argument("--json", default="")
    sp.add_argument("--patch-file", default="",
                    help="read the amendment fields from a file (PowerShell-safe)")
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "") or getattr(a, "patch_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    if a.cmd in ("append", "supersede") and not getattr(a, "json", ""):
        ap.error("--json or --json-file is required for %s" % a.cmd)

    if a.cmd == "path":
        print(ledger_path()); sys.exit(0)
    if a.cmd == "append":
        try:
            entry = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"}), file=sys.stderr); sys.exit(1)
        print(append(entry)); sys.exit(0)
    if a.cmd == "supersede":
        try:
            fields = json.loads(a.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"bad json: {e}"}), file=sys.stderr); sys.exit(1)
        if not isinstance(fields, dict):
            print(json.dumps({"error": "amendment payload must be an object"}), file=sys.stderr)
            sys.exit(1)
        print(supersede(a.target, fields)); sys.exit(0)

    out = analyse()
    print(json.dumps(out, indent=2))
    if out["status"] == "empty":
        sys.exit(3)
    sys.exit(1 if out["escalate"] else 0)
