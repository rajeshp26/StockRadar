#!/usr/bin/env python3
"""
orphan-check.py — mechanical check of the eleven orphan classes in
FEATURE_DEVELOPMENT_LIFECYCLE.md v1.1 §8.4.

Consumed by G3.5, G7 and G8. Emits counts in the ledger format those
checklists expect. Exits non-zero if any class is non-zero.

Usage:
    orphan-check.py features/<FEATURE-ID>/trace.yml [--json]

Dependencies: PyYAML only.
"""
import sys, json, argparse

try:
    import yaml
except ImportError:
    sys.stderr.write("orphan-check: PyYAML required (pip install pyyaml)\n")
    sys.exit(2)

CLASSES = [
    "orphan_acceptance", "orphan_requirement", "orphan_scenario", "orphan_test", "orphan_component",
    "orphan_contract", "orphan_code", "orphan_impact", "orphan_state",
    "orphan_risk", "stale_baseline",
]

LABEL = {
    "orphan_acceptance": "orphan acceptance",
    "orphan_requirement": "orphan requirement",
    "orphan_scenario":    "orphan scenario",
    "orphan_test":        "orphan test",
    "orphan_component":   "orphan component",
    "orphan_contract":    "orphan contract",
    "orphan_code":        "orphan code",
    "orphan_impact":      "orphan impact",
    "orphan_state":       "orphan state",
    "orphan_risk":        "orphan risk",
    "stale_baseline":     "stale baseline",
}

HIGH_RISK = {"high", "critical"}


def _d(t, k):
    v = t.get(k) or {}
    return v if isinstance(v, dict) else {}


def _l(t, k):
    v = t.get(k) or []
    return v if isinstance(v, list) else []


def check(trace):
    """Return {class: [offending ids]} for all eleven §8.4 classes."""
    f = {c: [] for c in CLASSES}

    use_cases = _d(trace, "use_cases")
    stories   = _d(trace, "stories")
    design    = _d(trace, "design")
    contracts = _d(trace, "contracts")
    units     = _d(trace, "units")
    tests     = _d(trace, "tests")
    nfrs      = _d(trace, "nfrs")
    scenarios = _d(trace, "scenarios")
    states    = _d(trace, "states")
    baselines = _d(trace, "baselines")
    impacts   = _l(trace, "impacted_paths")

    # --- sets used by several classes -------------------------------------
    ac_with_design = set()
    for des in design.values():
        for ac in (des or {}).get("satisfies", []) or []:
            ac_with_design.add(ac)

    ac_with_test, nfr_with_test, contract_with_test = set(), set(), set()
    for tid, t in tests.items():
        for cov in (t or {}).get("covers", []) or []:
            if cov.startswith("AC-"):
                ac_with_test.add(cov)
            elif cov.startswith("NFR-"):
                nfr_with_test.add(cov)
            elif cov.startswith(("IFC-", "EVT-")):
                contract_with_test.add(cov)

    all_ac = set()
    for st in stories.values():
        for ac in (st or {}).get("criteria", []) or []:
            all_ac.add(ac)

    # 0. orphan acceptance -- every AC must link to at least one SCN
    #    via stories criteria (bidirectional: SCN->AC exists, AC->SCN check)
    ac_to_stories = {}
    for st_id, st in stories.items():
        for ac in (st or {}).get("criteria", []) or []:
            ac_to_stories.setdefault(ac, []).append(st_id)
    for ac, st_ids in sorted(ac_to_stories.items()):
        has_scn = any(
            bool((stories[sid] or {}).get("scenarios"))
            for sid in st_ids
        )
        if not has_scn:
            f["orphan_acceptance"].append(ac)

    # 1. orphan requirement — AC/NFR with no design element AND no test case
    for ac in sorted(all_ac):
        if ac not in ac_with_design and ac not in ac_with_test:
            f["orphan_requirement"].append(ac)
    for nid, n in nfrs.items():
        has_design = bool((n or {}).get("design"))
        has_test = nid in nfr_with_test or bool((n or {}).get("conditions"))
        if not has_design and not has_test:
            f["orphan_requirement"].append(nid)

    # 2. orphan scenario — SCN with no AC and no recorded deferral
    scn_with_ac = set()
    for st in stories.values():
        for s in (st or {}).get("scenarios", []) or []:
            scn_with_ac.add(s)
    for sid, s in scenarios.items():
        s = s or {}
        if s.get("criteria") or s.get("acceptance") or sid in scn_with_ac:
            continue
        if s.get("deferred") and s.get("deferral_reason"):
            continue
        f["orphan_scenario"].append(sid)

    # 3. orphan test — covers no AC, NFR or contract
    for tid, t in tests.items():
        cov = (t or {}).get("covers", []) or []
        if not any(c.startswith(("AC-", "NFR-", "IFC-", "EVT-")) for c in cov):
            f["orphan_test"].append(tid)

    # 4. orphan component — CMP allocated to no UC
    allocated = set()
    for uc in use_cases.values():
        for c in (uc or {}).get("components", []) or []:
            allocated.add(c)
    declared = set(_d(trace, "components").keys())
    for des in design.values():
        c = (des or {}).get("component")
        if c:
            declared.add(c)
    for con in contracts.values():
        con = con or {}
        if con.get("owner"):
            declared.add(con["owner"])
        for c in con.get("consumers", []) or []:
            declared.add(c)
    for cmp_id in sorted(declared):
        if cmp_id not in allocated:
            f["orphan_component"].append(cmp_id)

    # 5. orphan contract — no consumer, or no owner
    for cid, c in contracts.items():
        c = c or {}
        owner = c.get("owner") or c.get("publisher")
        consumers = c.get("consumers") or c.get("subscribers") or []
        if not owner or not consumers:
            f["orphan_contract"].append(cid)

    # 6. orphan code — changed file with no IMP and no AC (hardening H8: an
    #    IMP that satisfies no AC-* is still orphan code)
    imp_with_ac = {}
    for u in units.values():
        p = (u or {}).get("path")
        if p:
            imp_with_ac[p] = [x for x in ((u or {}).get("satisfies") or [])
                              if isinstance(x, str) and x.startswith("AC-")]
    for path in _l(trace, "changed_files"):
        acs = imp_with_ac.get(path)
        if acs is None:
            f["orphan_code"].append(path)
        elif not acs:
            f["orphan_code"].append(f"{path} (IMP satisfies no AC-*)")
    for uid, u in units.items():
        u = u or {}
        if not u.get("satisfies") and not u.get("tests"):
            linked = any(uid in ((d or {}).get("units") or []) for d in design.values())
            if not linked:
                f["orphan_code"].append(uid)

    # 7. orphan impact — impacted path with no selected regression test
    for i, imp in enumerate(impacts):
        imp = imp or {}
        if not imp.get("regression"):
            f["orphan_impact"].append(imp.get("changed", f"impacted_paths[{i}]"))

    # 8. orphan state — no owner, or more than one owner
    for sid, s in states.items():
        s = s or {}
        owner = s.get("owner")
        owners = owner if isinstance(owner, list) else ([owner] if owner else [])
        if len(owners) != 1:
            f["orphan_state"].append(sid)

    # 9. orphan risk — SCN with no priority score, with a band that
    #    contradicts the config.yml formula, or high/critical with no F15
    #    case (hardening H6)
    st_ids = {t for t, v in tests.items() if t.startswith("ST-")}
    for sid, s in scenarios.items():
        s = s or {}
        prio = s.get("priority") or {}
        if not all(k in prio for k in ("likelihood", "impact", "detectability")):
            f["orphan_risk"].append(sid)
            continue
        pri = prio.get("priority")
        if pri is None:
            pri = prio["likelihood"] * prio["impact"] * (6 - prio["detectability"])
        declared = prio.get("band")
        computed = _band(pri)
        if declared and declared != computed:
            f["orphan_risk"].append(f"{sid} (band {declared}, formula {computed})")
            continue
        band = computed
        if band in HIGH_RISK:
            cases = s.get("cases", []) or []
            if not any(c in st_ids or c.startswith("ST-") for c in cases):
                f["orphan_risk"].append(sid)

    # 10. stale baseline — AC/NFR on a superseded baseline with gates unreopened
    superseded = {b for b, v in baselines.items()
                  if ((v or {}).get("status") == "superseded")}
    reopened = set()
    for ch in _l(trace, "changes"):
        ch = ch or {}
        if ch.get("gates_reopened"):
            el = ch.get("changed")
            if el:
                reopened.add(el)
    for st in stories.values():
        for ac in (st or {}).get("criteria", []) or []:
            bl = (_d(trace, "element_baselines").get(ac) or {})
            if isinstance(bl, str):
                bl = {"baseline": bl}
            if bl.get("baseline") in superseded and ac not in reopened:
                f["stale_baseline"].append(ac)
    for nid, n in nfrs.items():
        if (n or {}).get("baseline") in superseded and nid not in reopened:
            f["stale_baseline"].append(nid)

    for c in CLASSES:
        f[c] = sorted(set(f[c]))
    return f


def _band(p):
    if p <= 20:
        return "low"
    if p <= 45:
        return "medium"
    if p <= 80:
        return "high"
    return "critical"


def main():
    ap = argparse.ArgumentParser(description="§8.4 orphan check")
    ap.add_argument("trace", help="path to features/<ID>/trace.yml")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    a = ap.parse_args()

    try:
        with open(a.trace) as fh:
            trace = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        sys.stderr.write(f"orphan-check: not found: {a.trace}\n")
        return 2
    except yaml.YAMLError as e:
        sys.stderr.write(f"orphan-check: unparseable YAML: {e}\n")
        return 2

    findings = check(trace)
    total = sum(len(v) for v in findings.values())
    feature = trace.get("feature", "<unknown>")

    if a.json:
        print(json.dumps({"feature": feature, "total": total,
                          "counts": {c: len(v) for c, v in findings.items()},
                          "findings": findings}, indent=2))
    else:
        print(f"orphan check — {feature}")
        print(f"trace: {a.trace}")
        print("")
        for c in CLASSES:
            n = len(findings[c])
            print(f"  {LABEL[c]:<20} {n}")
            for item in findings[c]:
                print(f"      - {item}")
        print("")
        print(f"  total orphans: {total}")
        print("")
        print("ledger line (§9.1):")
        print("  orphan counts: " + ", ".join(
            f"{LABEL[c].replace('orphan ', '')} {len(findings[c])}" for c in CLASSES))

    if total:
        sys.stderr.write(f"orphan-check: FAIL — {total} orphan(s); "
                         "§8.4 blocks G3.5, G7 and G8\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
