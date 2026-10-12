#!/usr/bin/env python3
"""Architecture design checklist checker.

Three jobs, in order of how easily each is faked:

1. STRUCTURE. Rejects folklore. An item must be a judgement question that no gate could
   assert, must trace to a retro id, and must justify why it is not executable. "Validate
   inputs" is a gate; it does not belong here. The ceiling is enforced — adding a 13th item
   requires retiring one, because an unbounded checklist dilutes the items that matter.

2. DISPOSITION. Loading the checklist is not compliance. The Architect returns a per-item
   verdict with the fields that verdict requires. "reviewed" is rejected outright: it is the
   checklist equivalent of a test that exists but never ran.

3. LIFECYCLE. Items are not permanent. `promote` lists items whose condition has become
   machine-checkable. `expire` lists items dispositioned expiry_cycles times without ever
   changing a design — decoration, retired.

Exit codes:
  0  checklist structurally valid; dispositions complete if a task was named
  1  structural violation, or a disposition is invalid
  2  BLOCKED — cannot evaluate (pyyaml missing)
  3  disposition OWED but absent for the named task
  4  NOT_APPLICABLE — no checklist present
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

CHECKLIST = Path("framework/architecture/design_checklist.yaml")
OK, VIOLATION, BLOCKED, OWED, NA = 0, 1, 2, 3, 4

# An item claiming to need judgement while reading like a grep pattern is folklore. These
# markers indicate a condition a gate could assert — which makes the checklist the wrong home.
EXECUTABLE_SMELL = [
    "must not import", "use tailwind", "no inline", "exit code", "returns 4",
    "package.json", "must be present in", "forbidden alternate",
]


# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework.adapters.gsd_state import root as _gsd_state_root


def _state_root() -> Path:
    """Delegate to the single source of GSD state-root resolution."""
    return _gsd_state_root()


def disposition_dir() -> Path:
    return _state_root() / "retro" / "checklist"


def load_checklist():
    try:
        import yaml
    except ImportError:
        print("BLOCKED: pyyaml missing; cannot evaluate checklist", file=sys.stderr)
        sys.exit(BLOCKED)
    if not CHECKLIST.exists():
        return None
    return yaml.safe_load(CHECKLIST.read_text()) or {}


def check_structure(doc) -> list[str]:
    errs = []
    items = doc.get("items") or []
    ceiling = doc.get("max_items", 12)
    if len(items) > ceiling:
        errs.append(f"{len(items)} items exceeds max_items={ceiling} — retire one before adding "
                    f"another; an unbounded checklist dilutes the items that matter")
    seen = set()
    for it in items:
        iid = it.get("id", "<no id>")
        if iid in seen:
            errs.append(f"{iid}: duplicate id")
        seen.add(iid)
        for field in ("question", "why", "judgement_because", "retro_id"):
            if not str(it.get(field, "")).strip():
                errs.append(f"{iid}: missing required field '{field}'")
        if "cycles_without_effect" not in it:
            errs.append(f"{iid}: missing cycles_without_effect — lifecycle cannot be tracked")
        q = str(it.get("question", "")).lower()
        for smell in EXECUTABLE_SMELL:
            if smell in q:
                errs.append(f"{iid}: question reads like an executable condition "
                            f"('{smell}') — belongs in a gate or a declared rule, not here")
                break
        if q and "?" not in q:
            errs.append(f"{iid}: not phrased as a question — checklist items prompt judgement, "
                        f"they do not state rules")
    return errs


def read_dispositions(task: str) -> dict | None:
    d = disposition_dir()
    f = d / f"{task}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: {f} is not valid JSON: {e}", file=sys.stderr)
        return {}


def check_dispositions(doc, task: str) -> tuple[int, list[str]]:
    items = {it["id"]: it for it in (doc.get("items") or [])}
    disp = read_dispositions(task)
    if disp is None:
        return OWED, [
            f"disposition OWED for task {task} and not found.",
            f"Write {disposition_dir()}/{task}.json with one verdict per item:",
            '  {"task":"%s","dispositions":[{"id":"ACD-001","verdict":"applied",'
            '"changed":"..."}]}' % task,
            "Allowed verdicts: " + ", ".join(doc.get("dispositions", {})),
        ]
    errs = []
    given = {d.get("id"): d for d in (disp.get("dispositions") or [])}
    allowed = doc.get("dispositions", {})

    for iid in items:
        if iid not in given:
            errs.append(f"{iid}: no disposition — a silently skipped item is a gap, not a pass")
            continue
        d = given[iid]
        v = d.get("verdict", "")
        if v not in allowed:
            extra = " ('reviewed' is not a verdict — it is the checklist equivalent of a test " \
                    "that exists but never ran)" if v == "reviewed" else ""
            errs.append(f"{iid}: verdict '{v}' not in {sorted(allowed)}{extra}")
            continue
        for req in allowed[v].get("requires", []):
            if not str(d.get(req, "")).strip():
                errs.append(f"{iid}: verdict '{v}' requires field '{req}'")

    unknown = [i for i in given if i not in items]
    for u in unknown:
        errs.append(f"{u}: disposition for an item not in the checklist")
    return (VIOLATION if errs else OK), errs


def lifecycle(doc, effects: dict[str, int]) -> dict:
    """effects: item id -> number of times it was dispositioned 'applied' (i.e. changed a design)."""
    expiry = doc.get("expiry_cycles", 6)
    promote, expire, keep = [], [], []
    for it in doc.get("items") or []:
        iid = it["id"]
        cwe = int(it.get("cycles_without_effect", 0))
        if effects.get(iid, 0) > 0:
            keep.append({"id": iid, "reason": "changed a design at least once"})
        elif cwe >= expiry:
            expire.append({"id": iid, "cycles_without_effect": cwe,
                           "reason": f"dispositioned {cwe} times without ever changing a design "
                                     f"— decoration, retire it"})
        else:
            keep.append({"id": iid, "cycles_without_effect": cwe,
                         "reason": f"{expiry - cwe} cycles before expiry review"})
        if str(it.get("graduated_to", "")).strip():
            promote.append({"id": iid, "graduated_to": it["graduated_to"],
                            "reason": "condition is now machine-checkable — remove from "
                                      "checklist, the gate owns it"})
    return {"promote": promote, "expire": expire, "keep": keep, "expiry_cycles": expiry}


def tally_effects() -> dict[str, int]:
    """Count 'applied' verdicts per item across all recorded dispositions.

    Files are read in TIMESTAMP order, not filename order. Sorting lexicographically would let
    a stale disposition override a newer one, retiring an item whose most recent cycle DID
    change a design.
    """
    d = disposition_dir()
    if not d.exists():
        return {}
    files = sorted(d.glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name))
    out: dict[str, int] = {}
    for f in files:
        try:
            doc = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        for e in doc.get("dispositions") or []:
            if e.get("verdict") == "applied":
                out[e.get("id", "?")] = out.get(e.get("id", "?"), 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Architecture design checklist checker")
    ap.add_argument("command", choices=["structure", "dispositions", "lifecycle", "show"])
    ap.add_argument("--task", default="", help="task id whose dispositions to verify")
    a = ap.parse_args()

    doc = load_checklist()
    if doc is None:
        print(json.dumps({"status": "not_applicable", "reason": f"{CHECKLIST} absent"}, indent=2))
        return NA

    if a.command == "show":
        print(json.dumps({"scope": doc.get("scope"), "version": doc.get("version"),
                          "items": [{"id": i["id"], "question": " ".join(i["question"].split())}
                                    for i in doc.get("items") or []],
                          "dispositions": doc.get("dispositions")}, indent=2))
        return OK

    if a.command == "structure":
        errs = check_structure(doc)
        print(json.dumps({"status": "invalid" if errs else "valid",
                          "items": len(doc.get("items") or []),
                          "errors": errs}, indent=2))
        return VIOLATION if errs else OK

    if a.command == "lifecycle":
        print(json.dumps(lifecycle(doc, tally_effects()), indent=2))
        return OK

    if not a.task:
        print("ERROR: --task required for dispositions", file=sys.stderr)
        return VIOLATION
    rc, errs = check_dispositions(doc, a.task)
    print(json.dumps({"status": {OK: "complete", VIOLATION: "invalid", OWED: "owed"}[rc],
                      "task": a.task, "errors": errs}, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
