#!/usr/bin/env python3
"""Evidence classes -- the canonical derivation from an acceptance-criterion tag to a
verification method, its gates, its skills and whether it exercises the real stack.

WHY THIS EXISTS
===============
The chain impact -> criterion -> skill -> gate -> evidence had five nodes and no artifact
carrying the decision between them. The evidence-tag vocabulary was copied four times with
no canonical copy (``plan_lint.EVIDENCE_TAGS``, ``plan_lint.REAL_TAGS``,
``evidence_level.REAL_STACK_TAGS``, ``system_test_lint.REAL_TAGS``), so a plan could declare
``AC-1 [e2e]`` and nothing downstream ever asked whether that criterion had evidence.

``framework/verifier/evidence_classes.yaml`` is the canonical table; this module is its only
reader. ``matrix.py`` derives a verification matrix from it, ``route.py`` turns that matrix
into a gate set, and ``validate.py`` proves the legacy copies still equal it -- so the
duplication is checked, not merely regretted.

WHAT THIS DOES NOT PROVE
========================
It proves a tag RESOLVES to a method, gates and skills. It does not prove the method ran or
that the evidence is any good. ``matrix.py check`` judges existence and freshness; quality is
review.

Usage (library):
    from evidence import load_table, parse_criteria, derive_rows, derive_impact
Exit: this module is a library. ``python3 evidence.py --self-test`` runs its checks.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

TABLE_REL = os.path.join("framework", "verifier", "evidence_classes.yaml")
SCOPES = ("local", "component", "cross_component", "system")
IMPACT_KEYS = ("contract_change", "data_change", "public_api_change")

_HERE = os.path.dirname(os.path.abspath(__file__))
_FRAMEWORK = os.path.dirname(_HERE)

CRIT_RE = re.compile(r"^(AC-\d+)\s+\[([A-Za-z0-9-]+)\]\s+(.*)$", re.I)
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
ITEM_RE = re.compile(r"^[ \t]*-[ \t]+(.*)$")
IMPACT_RE = re.compile(r"^(?:impact|scope):[ \t]*([A-Za-z_]+)[ \t]*$", re.I)
FLAG_RE = re.compile(r"^(contract_change|data_change|public_api_change):[ \t]*(true|false)[ \t]*$", re.I)

_PLAN_LINT = None


class TableError(Exception):
    """The table is absent, unparsable, or structurally wrong. Never a silent default."""


# ---------------------------------------------------------------- table
def load_table(root="."):
    """Return {tag: {method, gates, skills, real_stack}} from the canonical table.

    Raises TableError when pyyaml is missing, the file is absent, or a row is incomplete.
    A missing table must not degrade to an empty one: an empty table would make every tag
    unknown, and an unknown tag is a plan error, not a configuration default.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise TableError("pyyaml unavailable; cannot read %s" % TABLE_REL) from exc

    path = os.path.join(root, TABLE_REL)
    if not os.path.isfile(path):
        raise TableError("evidence class table missing: %s" % TABLE_REL)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, ValueError) as exc:
        raise TableError("evidence class table unreadable: %s" % exc) from exc

    classes = data.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise TableError("%s declares no `classes:` map" % TABLE_REL)

    table = {}
    for tag, spec in classes.items():
        if not isinstance(spec, dict):
            raise TableError("class %r is not a mapping" % tag)
        missing = [k for k in ("method", "real_stack") if k not in spec]
        if missing:
            raise TableError("class %r missing %s" % (tag, ", ".join(missing)))
        gates = spec.get("gates") or []
        skills = spec.get("skills") or []
        if not isinstance(gates, list) or not isinstance(skills, list):
            raise TableError("class %r: gates and skills must be lists" % tag)
        table[str(tag).lower()] = {
            "method": str(spec["method"]),
            "gates": [str(g) for g in gates],
            "skills": [str(s) for s in skills],
            "real_stack": bool(spec["real_stack"]),
        }
    return table


def real_stack_tags(table):
    return sorted(t for t, spec in table.items() if spec["real_stack"])


# ---------------------------------------------------------------- plan parsing
def _clean(item):
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
        item = item[1:-1]
    return item.strip()


def collect_list(text, key):
    """Every value of ``key`` anywhere in the plan, in order.

    A plan repeats keys once per task block, so this aggregates instead of letting the last
    occurrence win. Supports ``key: [a, b]``, ``key: a, b`` and ``key:`` + ``- a`` items.
    """
    out = []
    lines = text.replace("\r", "").split("\n")
    i = 0
    while i < len(lines):
        m = KEY_RE.match(lines[i])
        if not m or m.group(1) != key:
            i += 1
            continue
        rest = m.group(2).strip()
        if rest.startswith("["):
            inner = re.match(r"^\[([^\]]*)\]", rest)
            if inner:
                out.extend(_clean(x) for x in inner.group(1).split(",") if _clean(x))
        elif rest:
            out.extend(_clean(x) for x in re.split(r"[,\s]+", rest) if _clean(x))
        else:
            j = i + 1
            while j < len(lines):
                im = ITEM_RE.match(lines[j])
                if im:
                    item = _clean(im.group(1))
                    if item:
                        out.append(item)
                elif lines[j].strip():
                    break
                j += 1
            i = j - 1
        i += 1
    return out


def parse_criteria(text):
    """Return (criteria, inline_form).

    Each criterion is {id, tag, text}; a malformed item carries ``malformed: True`` so the
    caller can report it instead of silently dropping the requirement.
    """
    lines = text.replace("\r", "").split("\n")
    items = []
    inline = False
    for i, line in enumerate(lines):
        m = re.match(r"^acceptance_criteria:[ \t]*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith("["):
            inline = True
            inner = re.match(r"^\[([^\]]*)\]", rest)
            if inner:
                items.extend(_clean(x) for x in inner.group(1).split(",") if _clean(x))
            continue
        if rest:
            items.append(_clean(rest))
            continue
        j = i + 1
        while j < len(lines):
            im = ITEM_RE.match(lines[j])
            if im:
                items.append(_clean(im.group(1)))
            elif lines[j].strip():
                break
            j += 1
        break

    criteria = []
    for raw in items:
        m = CRIT_RE.match(raw)
        if m:
            criteria.append({
                "id": m.group(1).upper(),
                "tag": m.group(2).lower(),
                "text": m.group(3).strip(),
            })
        else:
            criteria.append({"id": None, "tag": None, "text": raw, "malformed": True})
    return criteria, inline


def parse_impact(text):
    """Declared impact flags. Absent keys stay absent; the caller decides the fallback."""
    out = {}
    for line in text.replace("\r", "").split("\n"):
        m = IMPACT_RE.match(line)
        if m and m.group(1).lower() in SCOPES:
            out["scope"] = m.group(1).lower()
            out["basis"] = "declared"
        f = FLAG_RE.match(line)
        if f:
            out[f.group(1).lower()] = f.group(2).lower() == "true"
    return out


def derive_impact(text, files):
    """Impact scope, declared or mechanically derived from the declared file breadth.

    A derived scope is RECORDED with the rule that produced it (`basis`), never omitted:
    the defect this module exists for is a routing input nobody wrote down. Derivation is
    deliberately conservative -- two top-level directories is cross_component, a contract or
    public-API change is at least cross_component -- because under-routing is the failure
    that hides work, while over-routing only costs a gate run.
    """
    impact = parse_impact(text)
    paths = [f for f in files if "/" in f or "\\" in f]
    tops = {p.replace("\\", "/").split("/")[0] for p in paths if p.replace("\\", "/").split("/")[0]}
    if "scope" not in impact:
        if len(tops) >= 2:
            scope = "cross_component"
        elif len(tops) == 1:
            scope = "component"
        else:
            scope = "local"
        impact["scope"] = scope
        impact["basis"] = "derived(top_dirs=%d)" % len(tops)

    if impact.get("public_api_change") or impact.get("contract_change"):
        if SCOPES.index(impact["scope"]) < SCOPES.index("cross_component"):
            impact["scope"] = "cross_component"
            impact["basis"] += "+public_api"
    if impact.get("data_change") and impact["scope"] != "system":
        impact["scope"] = "system"
        impact["basis"] += "+data_change"
    return impact


def derive_rows(criteria, table):
    """Return (rows, errors). Rows are the matrix body; errors block emission."""
    rows, errors = [], []
    seen = set()
    for c in criteria:
        if c.get("malformed"):
            errors.append("criterion lacks '<AC-n> [evidence-tag]' prefix: %r"
                          % c["text"][:70])
            continue
        if c["id"] in seen:
            errors.append("%s: duplicate criterion id" % c["id"])
            continue
        seen.add(c["id"])
        spec = table.get(c["tag"])
        if spec is None:
            errors.append("%s: unknown evidence tag [%s]; allowed: %s"
                          % (c["id"], c["tag"], ", ".join(sorted(table))))
            continue
        rows.append({
            "id": c["id"],
            "text": c["text"],
            "tag": c["tag"],
            "method": spec["method"],
            "gates": list(spec["gates"]),
            "skills": list(spec["skills"]),
            "real_stack": spec["real_stack"],
            "status": "pending",
            "evidence": None,
        })
    return rows, errors


# ---------------------------------------------------------------- plan digest
def plan_digest(text):
    """Hash the plan content the way ``plan_lint --stamp`` does.

    Re-stamping rewrites ``approval_hash`` and ``status``, which must not invalidate an
    otherwise-correct matrix. Importing the lint's digest is deliberate: a second
    implementation would be a fifth copy of a decision, which is the defect being fixed.
    """
    global _PLAN_LINT
    if _PLAN_LINT is None:
        path = os.path.join(_FRAMEWORK, "plan", "plan_lint.py")
        if not os.path.isfile(path):
            raise TableError("plan_lint.py missing; cannot bind the matrix to the plan")
        spec = importlib.util.spec_from_file_location("_fw_plan_lint", path)
        if spec is None or spec.loader is None:  # pragma: no cover - import guard
            raise TableError("plan_lint.py unimportable")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PLAN_LINT = mod
    return _PLAN_LINT.approval_digest(text)


# ---------------------------------------------------------------- self-test
def _self_test():
    failures = []

    def eq(name, got, want):
        if got != want:
            failures.append("%s: got %r want %r" % (name, got, want))

    table = {
        "e2e": {"method": "system_test", "gates": ["g17"], "skills": ["system-test-authoring"],
                "real_stack": True},
        "unit": {"method": "unit_test", "gates": ["g4"], "skills": [], "real_stack": False},
    }
    text = "\n".join([
        "acceptance_criteria:",
        "  - AC-1 [e2e] the portfolio page renders four periods from Supabase",
        "  - AC-2 [unit] the parser returns 4 for an empty ledger",
        "files_or_components:",
        "  - web/src/app/portfolio/page.tsx",
        "  - backend/portfolio/service.py",
    ])
    criteria, inline = parse_criteria(text)
    eq("criterion count", len(criteria), 2)
    eq("inline form", inline, False)
    eq("first tag", criteria[0]["tag"], "e2e")
    eq("second id", criteria[1]["id"], "AC-2")

    rows, errors = derive_rows(criteria, table)
    eq("derive errors", errors, [])
    eq("row gates", rows[0]["gates"], ["g17"])
    eq("row status", rows[0]["status"], "pending")
    eq("row real_stack", rows[0]["real_stack"], True)

    _, bad = derive_rows([{"id": "AC-9", "tag": "vibes", "text": "x"}], table)
    eq("unknown tag is an error", len(bad), 1)

    impact = derive_impact(text, collect_list(text, "files_or_components"))
    eq("derived scope", impact["scope"], "cross_component")
    eq("derived basis", impact["basis"], "derived(top_dirs=2)")

    declared = derive_impact("impact: local\nfiles_or_components:\n  - a/b.py\n  - c/d.py\n",
                             ["a/b.py", "c/d.py"])
    eq("declared scope wins", declared["scope"], "local")
    eq("declared basis", declared["basis"], "declared")

    api = derive_impact("impact: component\npublic_api_change: true\n", [])
    eq("public api forces cross_component", api["scope"], "cross_component")

    if failures:
        for f in failures:
            print("FAIL " + f)
        return 1
    print("evidence self-test: PASS")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(__doc__)
    sys.exit(0)
