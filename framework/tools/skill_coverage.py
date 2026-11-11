#!/usr/bin/env python3
"""Skill coverage -- do the skills a plan NEEDS actually get NAMED?

WHY THIS EXISTS
===============
Two different claims were being confused, and only one of them was checked:

  resolution   the skill exists, parses, and is reachable by name      <- validate.py (green)
  selection    a task actually requires it, so an agent must load it  <- nothing

Resolution alone is how a skill lies around: `apple-ui` resolves, so every check is green,
while a plan that touches `web/src/**` never names it and the implementer is never told to
load the design system. The routing table said the row was mandatory; no machine read it.

This module closes the selection gap at the only place it can be closed *before* work starts:
the plan. `g_skill_coverage.sh` runs it from `g_entry.sh` block 4c, and g_entry refuses
dispatch on errors, so a plan that implies a skill but omits it cannot be dispatched.

It is deliberately NOT a rule inside plan_lint.py. The lint judges plan *shape* and is pure
stdlib; this needs the configured skills roots and the Capability Matrix to answer a
different question. Composition at g_entry keeps both with one dispatch verdict and one
`framework/plan/lint_mode` switch, which is what the plan lint already shares.

`--required-skills` is the single parser for `required_skills:` in the repository. A plan
repeats that key once per task, so every consumer must aggregate across blocks; a shell
`sed` range silently keeps only the first, which made G-SKILL-USE verify one task and pass.

RULES
=====
  SC01 ERROR  a `required_skills` entry names a skill no configured root provides (phantom)
  SC02 ERROR  the plan touches UI paths but omits `apple-ui` or `frontend-react`
              (skill-routing.md row 24: UI change -> apple-ui + frontend-react, unconditional)
  SC03 ERROR  the plan creates a NEW UI surface but omits `designmotion-design`
              (row 22: a new surface introduces a pattern/system by definition)
  SC04 WARN   the plan declares code files but has no `required_skills` at all
  SC05 WARN   a required skill resolves but no routing row names it (loadable, unrouted)
  SC06 ERROR  the plan touches test files but omits `istqb-testing` (the technique layer)
  SC07 ERROR  the plan declares `AC-n [tag]` criteria whose evidence class owns skills the
              plan does not require (e.g. `[e2e]` -> `system-test-authoring`)

SC02/SC03/SC06/SC07 are the ones with teeth: they are the difference between "the skill
resolves" and "the skill was required". All clear by naming the skill, or by not making the
claim that routes to it.

SC07 is the DERIVED half of routing. CM04 checks the Capability Matrix's DECLARED rows
(`apple-ui: yes` must be named), but a plan's acceptance criteria route to skills through the
evidence table without ever passing through the matrix. `evidence_classes.yaml` says an
`[e2e]` criterion is owned by `system-test-authoring`; before SC07 nothing read that column,
so a plan could claim a real-stack criterion and never require the skill that authors it.

WHAT THIS DOES NOT PROVE
========================
It proves the plan REQUIRED the skill. It cannot prove the agent READ it -- that is the
reviewer's check against the handoff's `skills_loaded`, and a claim, not a gate verdict.

Exit: 0 no findings | 1 errors | 2 BLOCKED (config unreadable)
Usage:
  python3 framework/tools/skill_coverage.py PLAN.md [--root DIR] [--json]
  python3 framework/tools/skill_coverage.py PLAN.md --required-skills
  python3 framework/tools/skill_coverage.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

CONFIG = "opencode.json"
ROUTING = "framework/opencode/skill-routing.md"
TEAM_LEAD = "framework/opencode/agents/team-lead.md"
MATRIX_NAME = "CAPABILITY-MATRIX.yaml"

# Repo root, resolved from this file so --self-test works from any cwd.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The UI skill set, keyed to the routing rows that mandate it. Keep in sync with
# skill-routing.md:22-24 -- SC02/SC03 cite these rows in their messages.
UI_ALWAYS = ("apple-ui", "frontend-react")     # row 24, unconditional for a UI change
UI_NEW_SURFACE = ("designmotion-design",)      # row 22, when the surface is new
UI_ROWS = "skill-routing.md:22-24"

UI_PREFIXES = ("web/src/", "web/app/", "mobile/lib/", "web/pages/")
UI_EXTS = (".tsx", ".jsx", ".css", ".scss", ".sass", ".html", ".dart", ".vue", ".svelte")
CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".sh", ".dart", ".css", ".md")

# The testing skill set, keyed to the routing row that mandates it. Keep in sync with
# skill-routing.md:13 -- SC06 cites that row in its message. A test file is the observable
# signal that a task is testing work; the skill is the technique layer over it.
TEST_SKILL = "istqb-testing"
TEST_ROW = "skill-routing.md:19"

# SC07 -- the DERIVED half of skill routing. The tag -> skills mapping is read from the
# canonical evidence table, never copied here: `framework/verifier/evidence.py` is its only
# reader and a second copy is the exact defect this framework is closing.
EVIDENCE_REL = "framework/verifier/evidence.py"
# `AC-1 [e2e] ...` in list form and in a flow/inline block both match; only the tag is read.
AC_TAG_RE = re.compile(r"\bAC-\d+\s*\[([A-Za-z0-9-]+)\]", re.I)
# Exact path SEGMENTS, never substrings: "latest/" contains "test/", and a substring rule would
# demand a testing skill for a directory that has nothing to do with tests.
TEST_DIR_SEGMENTS = ("tests", "test", "__tests__", "e2e", "playwright", "spec")
TEST_NAME_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.py$|^conftest\.py$|.*\.(test|spec)\.[cm]?[jt]sx?$)", re.I)

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
ITEM_RE = re.compile(r"^[ \t]*-[ \t]+(.*)$")
SPLIT_RE = re.compile(r"[,\s]+")


def _clean(item):
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'`":
        item = item[1:-1]
    return item.strip()


def collect_lists(text, key):
    """Every value of `key` anywhere in the plan, in order.

    A plan repeats `required_skills:` once per task, so this aggregates instead of letting the
    last occurrence win (the top-level-dict parser in plan_lint.py keeps only one). Supports
    `key: [a, b]`, `key: a, b`, and `key:` followed by `- a` items.
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
            out.extend(_clean(x) for x in SPLIT_RE.split(rest) if _clean(x))
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


def _is_ui_path(path):
    low = path.replace("\\", "/").lower()
    if low.endswith(UI_EXTS):
        return True
    return low.startswith(UI_PREFIXES)


def _is_code_path(path):
    return path.replace("\\", "/").lower().endswith(CODE_EXTS)


def _is_test_path(path):
    """True when the path is a test artefact. Segment-exact, so 'latest/' is not a test dir."""
    p = path.replace("\\", "/").lower().strip()
    while p.startswith("./"):
        p = p[2:]
    segs = [s for s in p.split("/") if s]
    if not segs:
        return False
    if any(s in TEST_DIR_SEGMENTS for s in segs[:-1]):
        return True
    return bool(TEST_NAME_RE.match(segs[-1]))


def find(severity, rule, where, message):
    return {"severity": severity, "rule": rule, "where": where, "message": message}


def check(text, skills, routed, exists, tag_skills=None):
    """Pure check. `skills` = loadable names, `routed` = names a routing row mentions,
    `exists(path)` = does this repo-relative path exist on disk,
    `tag_skills` = {evidence tag: [skills that own it]} from the canonical table."""
    rows = []
    required = collect_lists(text, "required_skills")
    files = [p for p in collect_lists(text, "files_or_components") if "/" in p or "." in p]
    names = {n for n in required if re.match(r"^[A-Za-z0-9][A-Za-z0-9-]*$", n)}

    for name in sorted(names - skills):
        rows.append(find(
            "ERROR", "SC01", "required_skills",
            "'%s' resolves on no configured skills path, so the task would require a skill "
            "that cannot be loaded" % name))

    ui = [p for p in files if _is_ui_path(p)]
    new_ui = [p for p in ui if not exists(p)]
    if ui:
        missing = [s for s in UI_ALWAYS if s not in names]
        if missing:
            rows.append(find(
                "ERROR", "SC02", "required_skills",
                "plan touches UI files (%s) but does not require %s; %s is unconditional for a "
                "UI change" % (", ".join(ui[:3]), " + ".join(missing), UI_ROWS)))
        if new_ui:
            missing = [s for s in UI_NEW_SURFACE if s not in names]
            if missing:
                rows.append(find(
                    "ERROR", "SC03", "required_skills",
                    "plan creates a new UI surface (%s) but does not require %s; a new surface "
                    "introduces a pattern system, so %s applies -- name the skill or move the "
                    "surface to an existing component" % (", ".join(new_ui[:3]),
                                                          " + ".join(missing), UI_ROWS)))
    elif ui == [] and any(p for p in files if _is_code_path(p)) and not required:
        rows.append(find(
            "WARN", "SC04", "required_skills",
            "plan declares code files but no required_skills block; nothing tells the "
            "implementer which skills to load"))

    for name in sorted(names & skills - routed):
        rows.append(find(
            "WARN", "SC05", "required_skills",
            "'%s' is loadable but no routing row names it; a loadable skill nobody routes is "
            "selected only by chance" % name))

    # SC06 -- the testing half of the same defect. A plan that writes or changes a test is
    # testing work, and the technique layer (which technique, what coverage, what to leave out)
    # lives in `istqb-testing`. Naming it is the only point where the requirement can be forced
    # before dispatch: the skill has a routing row, so without this rule the row is a claim
    # nobody reads, exactly as the UI rows were before SC02/SC03.
    tests = [p for p in files if _is_test_path(p)]
    if tests and TEST_SKILL not in names:
        rows.append(find(
            "ERROR", "SC06", "required_skills",
            "plan touches test files (%s) but does not require %s; %s is the technique layer "
            "for any test a task writes or changes" % (", ".join(tests[:3]), TEST_SKILL,
                                                       TEST_ROW)))

    # SC07 -- derived skill routing. An acceptance criterion's evidence tag names the skills
    # that own that evidence class, and nothing read that column: a plan could declare
    # `AC-1 [e2e]` and never require `system-test-authoring`. CM04 covers the DECLARED matrix
    # rows only, so this is the half with no mechanism. Table-owned, not code-owned: adding a
    # skill to a class in evidence_classes.yaml widens this check with no code change.
    if tag_skills:
        declared_tags = {m.group(1).lower() for m in AC_TAG_RE.finditer(text)}
        for tag in sorted(declared_tags & set(tag_skills)):
            # Only loadable skills are demanded: a table naming a phantom skill is a table
            # defect, and validate.py owns that check. Blaming the plan for it would send the
            # implementer to fix a file they did not write.
            missing = [s for s in tag_skills[tag] if s in skills and s not in names]
            if missing:
                rows.append(find(
                    "ERROR", "SC07", "required_skills",
                    "plan declares [%s] criteria but does not require %s; %s owns the evidence "
                    "for a [%s] criterion" % (tag, " + ".join(missing), EVIDENCE_REL, tag)))
    return rows


# ---------------------------------------------------------------- adapters (disk)
class ConfigMissing(OSError):
    """The skills system is not configured in this root.

    Distinct from "config exists but is unreadable": an isolated fixture root (a temp copy
    with framework/ but no opencode.json) has nothing to enforce, which is NOT_APPLICABLE,
    whereas a corrupt config is BLOCKED. Collapsing the two made a fixture fail as if the
    plan were bad.
    """


def load_roots(root="."):
    cfg_path = os.path.join(root, CONFIG)
    if not os.path.isfile(cfg_path):
        raise ConfigMissing("no %s in this root; the skills system is not configured here"
                            % CONFIG)
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    paths = ((cfg.get("skills") or {}).get("paths") or []) or ["framework/opencode/skills"]
    roots = []
    for rel in paths:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            raise OSError("configured skills path does not exist: %s" % rel)
        roots.append(base)
    return roots


def load_skills(roots):
    names = {}
    for base in roots:
        for entry in sorted(os.listdir(base)):
            skill_md = os.path.join(base, entry, "SKILL.md")
            if os.path.isfile(skill_md):
                names[entry] = skill_md
    return names


def load_routed(root="."):
    path = os.path.join(root, ROUTING)
    if not os.path.isfile(path):
        return set()
    routed = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            routed |= set(re.findall(r"`([A-Za-z0-9][A-Za-z0-9-]*)`", cells[1]))
    return routed


# ---------------------------------------------------------------- capability matrix
# The matrix instance is a YAML file next to the plan. The DIMENSION LIST is not duplicated
# here: it is read from the Capability Matrix table in team-lead.md, which is the one place
# that declares which capabilities exist. A hard-coded second list would drift from the doc
# the moment a row is added, and the drift would be invisible.
def parse_schema(text):
    """Return the skill names the Capability Matrix table declares, in order.

    Pure, so a test can feed it the real document plus a hypothetical row and prove that a
    new row widens the check -- without editing the plane file that holds the table.
    """
    schema = []
    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].lower() == "dimension":
            continue
        if re.fullmatch(r"[-: ]+", cells[0]):
            continue
        m = re.search(r"`([A-Za-z0-9][A-Za-z0-9-]*)`", cells[2])
        if m:
            schema.append(m.group(1))
    return schema


def load_schema(root="."):
    """Return the skill names declared as Capability Matrix dimensions, or None if unreadable."""
    path = os.path.join(root, TEAM_LEAD)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig") as fh:
        return parse_schema(fh.read()) or None


def parse_matrix(text):
    """Return (scope, {skill: 'yes'|'no'}) from a CAPABILITY-MATRIX.yaml body.

    The KEY IS THE SKILL ID, not the human-readable dimension label. The schema read from
    team-lead.md is a list of skill IDs (`apple-ui`, `frontend-react`, ...), and CM01/CM03
    compare keys against it directly, so `ui-design-system: yes` does not satisfy the
    `apple-ui` row -- it reports CM01 for the row it was meant to answer plus CM03 for the key
    nobody declares. That is loud rather than silent (the self-test pins it), but the label
    form is the intuitive first mistake, so say it here:

        dimensions:
          apple-ui: yes            # correct: the skill ID
          ui-design-system: yes    # wrong: a label CM01/CM03 will both reject

    Deliberately not a YAML parser: the file has two keys and one flat string map, and
    plan_lint.py is stdlib-only for the same reason (it must run on a clean Windows host).
    """
    scope = "task"
    dims = {}
    in_dims = False
    for raw in text.replace("\r", "").split("\n"):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^scope:[ \t]*([A-Za-z]+)", raw)
        if m:
            scope = m.group(1).lower()
            in_dims = False
            continue
        if re.match(r"^dimensions:[ \t]*$", raw):
            in_dims = True
            continue
        if in_dims:
            m = re.match(r"^[ \t]+([A-Za-z0-9][A-Za-z0-9-]*):[ \t]*(\S+)", raw)
            if m:
                dims[m.group(1)] = m.group(2).lower()
                continue
        if not raw.startswith((" ", "\t")):
            in_dims = False
    return scope, dims


def check_matrix(schema, required, scope, dims, matrix_rel):
    """Pure check: every declared dimension is present, valid, and its 'yes' skills are required."""
    rows = []
    if scope not in ("task", "phase"):
        rows.append(find("ERROR", "CM02", "capability-matrix",
                         "scope must be 'task' or 'phase', got %r" % scope))
    missing = [d for d in schema if d not in dims]
    for d in missing:
        rows.append(find("ERROR", "CM01", "capability-matrix",
                         "declares no verdict for dimension '%s'; every row of the Capability "
                         "Matrix needs an explicit yes or no (%s)" % (d, TEAM_LEAD)))
    for d, v in sorted(dims.items()):
        if d not in schema:
            rows.append(find("WARN", "CM03", "capability-matrix",
                             "dimension '%s' is not a Capability Matrix row; keys must be the "
                             "SKILL ID (e.g. 'apple-ui'), not the dimension label -- typo, or "
                             "add the row to %s first" % (d, TEAM_LEAD)))
        elif v not in ("yes", "no"):
            rows.append(find("ERROR", "CM02", "capability-matrix",
                             "dimension '%s' must be yes or no, got %r" % (d, v)))
    for d, v in sorted(dims.items()):
        # A dimension outside the schema is one mistake (CM03), not two: reporting CM04 as
        # well would double-count a typo and hide which line to fix.
        if v == "yes" and d in schema and d not in required:
            rows.append(find("ERROR", "CM04", "capability-matrix",
                             "matrix says '%s: yes' but no required_skills entry names it; a "
                             "matrix that promises a skill the plan never requires is a "
                             "promise with no mechanism (%s)" % (d, matrix_rel)))
    return rows


def load_tag_skills(root="."):
    """{evidence tag: [skills]} from the canonical table, or None when it cannot be read.

    Deliberately an import of the canonical reader rather than a YAML parse here: a second
    reader is a second copy of the decision, and a second copy is what drifted in the first
    place. `evidence.py` is the only module allowed to interpret the table.
    """
    import importlib.util
    path = os.path.join(root, EVIDENCE_REL)
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("_fw_evidence", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        table = mod.load_table(root)
    except Exception:  # noqa: BLE001 - any read failure is "cannot judge", never "clean"
        return None
    return {tag: list(spec_["skills"]) for tag, spec_ in table.items() if spec_["skills"]}


def check_file(plan_path, root="."):
    with open(plan_path, encoding="utf-8-sig") as fh:
        text = fh.read()
    skills = load_skills(load_roots(root))
    routed = load_routed(root)

    def exists(rel):
        return os.path.exists(os.path.join(root, rel.replace("\\", "/")))
    tag_skills = load_tag_skills(root)
    rows = check(text, set(skills), routed, exists, tag_skills)

    # An unreadable evidence table means SC07 could not judge, and "could not judge" is not
    # "clean" -- the same contract CM00 holds for the Capability Matrix schema.
    if tag_skills is None:
        rows.append(find("ERROR", "SC07", "required_skills",
                         "evidence class table unreadable from %s; cannot judge whether the "
                         "skills each acceptance-criterion tag owns were required" % EVIDENCE_REL))

    # Capability matrix: the DECLARED half of routing. SC02/SC03 derive requirements from
    # file scope; the matrix records the ask's own claims, so a matrix that says 'yes' while
    # the plan never requires the skill cannot pass quietly.
    schema = load_schema(root)
    plan_dir = os.path.dirname(os.path.abspath(plan_path))
    matrix_path = os.path.join(plan_dir, MATRIX_NAME)
    if schema is None:
        rows.append(find("ERROR", "CM00", "capability-matrix",
                         "Capability Matrix schema unreadable from %s; cannot judge whether the "
                         "matrix is complete" % TEAM_LEAD))
        return rows
    if not os.path.isfile(matrix_path):
        rows.append(find("WARN", "CM05", "capability-matrix",
                         "no %s next to the plan; the declared routing for this ask is "
                         "unrecorded (derived UI checks still apply)" % MATRIX_NAME))
        return rows

    with open(matrix_path, encoding="utf-8-sig") as fh:
        scope, dims = parse_matrix(fh.read())

    required = set(collect_lists(text, "required_skills"))
    if scope == "phase":
        # A phase-level matrix covers several tasks, so "yes" means "some task in this phase
        # requires it". Union the sibling plans in the same directory rather than failing a
        # matrix that is correctly split across tasks.
        for name in sorted(os.listdir(plan_dir)):
            if not name.endswith("PLAN.md"):
                continue
            if os.path.abspath(os.path.join(plan_dir, name)) == os.path.abspath(plan_path):
                continue
            try:
                with open(os.path.join(plan_dir, name), encoding="utf-8-sig") as fh:
                    required |= set(collect_lists(fh.read(), "required_skills"))
            except (OSError, UnicodeDecodeError):
                rows.append(find("ERROR", "CM06", "capability-matrix",
                                 "phase-scope matrix cannot be checked: sibling plan %s is "
                                 "unreadable" % name))

    rows.extend(check_matrix(schema, required, scope, dims,
                             os.path.relpath(matrix_path, root)))
    return rows


# ---------------------------------------------------------------- self-test
SELFTEST_PLAN_UI = """\
files_or_components:
- web/src/features/portfolio/components/DividendDonut.tsx
- web/src/features/portfolio/components/DividendsTab.tsx
required_skills:
- apple-ui
- frontend-react
- designmotion-design
- unit-test-authoring
"""

SELFTEST_PLAN_BACKEND = """\
files_or_components:
- backend/api/analysis.py
required_skills:
- backend-python
- unit-test-authoring
"""

SELFTEST_PLAN_NONE = """\
files_or_components:
- backend/api/analysis.py
"""


def _selftest():
    skills = {"apple-ui", "frontend-react", "designmotion-design", "backend-python",
              "unit-test-authoring", "istqb-testing", "gsd-sketch", "unrouted-extra",
              "system-test-authoring", "browser-verification", "contract-authoring"}
    routed = {"apple-ui", "frontend-react", "designmotion-design", "backend-python",
              "unit-test-authoring", "istqb-testing", "gsd-sketch", "system-test-authoring",
              "browser-verification", "contract-authoring"}
    # The canonical tag -> skills map, as evidence_classes.yaml declares it. Passed in
    # explicitly so the pure check stays pure and the cases are readable; `check_file`
    # loads the real table through `evidence.load_table`.
    tag_skills = {
        "unit": ["unit-test-authoring"],
        "contract": ["contract-authoring"],
        "static": [],
        "integration": ["system-test-authoring"],
        "e2e": ["system-test-authoring"],
        "browser": ["browser-verification", "system-test-authoring"],
        "data-invariant": ["system-test-authoring"],
        "manual": [],
    }
    existing = {"web/src/features/portfolio/components/DividendsTab.tsx",
                "backend/api/analysis.py"}
    exists = existing.__contains__

    cases = []

    def case(name, text, want_rules, want_sev=None, tags=None):
        got = check(text, skills, routed, exists, tags)
        rules = sorted({r["rule"] for r in got
                        if want_sev is None or r["severity"] == want_sev})
        cases.append((name, rules, sorted(want_rules)))

    # 1. A complete UI plan is clean.
    case("complete UI plan -> clean", SELFTEST_PLAN_UI, [])
    # 2. UI plan missing the design-system skills is an error (row 24).
    case("UI plan without apple-ui -> SC02",
         SELFTEST_PLAN_UI.replace("- apple-ui\n", ""), ["SC02"])
    # 3. A new UI surface without designmotion-design is an error (row 22).
    case("new UI surface without designmotion-design -> SC03",
         SELFTEST_PLAN_UI.replace("- designmotion-design\n", ""), ["SC03"])
    # 4. An existing UI file alone does not demand designmotion-design (no new surface).
    existing_only = """
files_or_components:
- web/src/features/portfolio/components/DividendsTab.tsx
required_skills:
- apple-ui
- frontend-react
"""
    case("existing UI file, no new surface -> clean", existing_only, [])
    # 5. A phantom skill name is an error, not a silent no-op.
    case("phantom skill -> SC01", SELFTEST_PLAN_UI + "- settigation-code\n", ["SC01"])
    # 6. A backend plan is not subject to UI rules.
    case("backend plan -> clean", SELFTEST_PLAN_BACKEND, [])
    # 7. No required_skills at all on a code plan is a warning.
    case("code plan without required_skills -> SC04", SELFTEST_PLAN_NONE, ["SC04"])
    # 8. A loadable but unrouted skill is a warning.
    case("unrouted skill -> SC05",
         SELFTEST_PLAN_BACKEND + "- unrouted-extra\n", ["SC05"])
    # 9. Teeth: strip every skill name and the UI rules must fire, otherwise the check is
    #    green only because it read nothing.
    case("empty required_skills on UI plan -> SC02+SC03",
         "\n".join(ln for ln in SELFTEST_PLAN_UI.split("\n")
                   if not ln.startswith("- apple-ui") and not ln.startswith("- frontend-react")
                   and not ln.startswith("- designmotion-design")),
         ["SC02", "SC03"])

    # 9b-9e. SC06 -- a plan that touches a test is testing work. Both directions are asserted:
    #    naming the skill is clean, omitting it is an error, and a directory that merely looks
    #    like a test dir ("latest/") must NOT be treated as one.
    SELFTEST_PLAN_TEST = """\
files_or_components:
- backend/tests/test_discount.py
- backend/pricing/discount.py
required_skills:
- istqb-testing
- backend-python
"""
    case("test plan with istqb-testing -> clean", SELFTEST_PLAN_TEST, [])
    case("test plan without istqb-testing -> SC06",
         SELFTEST_PLAN_TEST.replace("- istqb-testing\n", ""), ["SC06"])
    case("test_*.py outside a tests dir -> SC06",
         "files_or_components:\n- backend/test_math.py\nrequired_skills:\n- backend-python\n",
         ["SC06"])
    case("'latest/' is not a test dir -> clean",
         "files_or_components:\n- backend/latest/analysis.py\n"
         "required_skills:\n- backend-python\n- unit-test-authoring\n", [])

    # 9f-9j. SC07 -- the DERIVED half of routing. A criterion's evidence tag names the skills
    #    that own that evidence class. Both directions are asserted, plus the multi-skill
    #    class (browser) where naming only one of two is still a gap.
    E2E_PLAN = """\
files_or_components:
- web/e2e/portfolio-performance-realdata.spec.ts
acceptance_criteria:
- AC-1 [e2e] the portfolio page renders four periods from the real database
required_skills:
- system-test-authoring
- istqb-testing
"""
    case("[e2e] criterion with system-test-authoring -> clean", E2E_PLAN, [],
         tags=tag_skills)
    case("[e2e] criterion without system-test-authoring -> SC07",
         E2E_PLAN.replace("- system-test-authoring\n", ""), ["SC07"], tags=tag_skills)
    # No table supplied => no SC07. The rule is table-driven, so a caller that cannot read
    # the table must not silently invent a requirement -- check_file reports SC07 instead.
    case("[e2e] criterion with no table -> no SC07",
         E2E_PLAN.replace("- system-test-authoring\n", ""), [], tags=None)
    case("browser criterion naming only one of its two skills -> SC07",
         "acceptance_criteria:\n- AC-1 [browser] the dashboard renders at 375px\n"
         "required_skills:\n- system-test-authoring\n", ["SC07"], tags=tag_skills)
    case("browser criterion naming both skills -> clean",
         "acceptance_criteria:\n- AC-1 [browser] the dashboard renders at 375px\n"
         "required_skills:\n- system-test-authoring\n- browser-verification\n", [],
         tags=tag_skills)
    case("class owning no skills demands nothing",
         "acceptance_criteria:\n- AC-1 [manual] a human signs off the copy\n"
         "required_skills:\n- backend-python\n", [], tags=tag_skills)

    # 10-12. `required_skills` repeats once per task. Aggregating across blocks is the whole
    # reason --required-skills exists: a parser that keeps only the first block verifies one
    # task and passes the rest unobserved, which is exactly the defect G-SKILL-USE must not
    # inherit from a shell range expression.
    def lcase(name, text, want):
        cases.append((name, collect_lists(text, "required_skills"), want))

    multi = """\
required_skills:
- apple-ui
- frontend-react
files_or_components:
- web/src/App.tsx
required_skills: [designmotion-design]
fragment_or_step:
- step
required_skills: unit-test-authoring, backend-python
"""
    lcase("inline-list plan -> every block aggregated", "required_skills: [a, b]\n", ["a", "b"])
    lcase("repeated blocks -> union, not last-wins", multi,
          ["apple-ui", "frontend-react", "designmotion-design",
           "unit-test-authoring", "backend-python"])
    lcase("no required_skills -> empty", SELFTEST_PLAN_NONE, [])

    # 13. The matrix schema is read from the real team-lead.md, so a row added to that doc
    #     widens the check with no code change. Proven against the ACTUAL document text: the
    #     two rows this repository still needs are appended and must show up as dimensions.
    doc = os.path.join(ROOT_DIR, TEAM_LEAD)
    if not os.path.isfile(doc):
        cases.append(("real Capability Matrix table is writable/readable", "missing", "readable"))
    else:
        with open(doc, encoding="utf-8-sig") as fh:
            base = parse_schema(fh.read())
        # Asserted by NAME, not by exact count. A count breaks on a legitimate ADDITION (which
        # is how a row gets added at all -- the `system-test-authoring` row arrives that way),
        # while a name assertion fails exactly when a depended-on row is deleted. The floor
        # catches a table that was gutted wholesale.
        _matrix_rows = {"apple-ui", "designmotion-design", "istqb-testing", "frontend-react",
                        "backend-python", "unit-test-authoring"}
        cases.append(("every routing-dependent skill is a declared matrix row",
                      sorted(_matrix_rows - set(base)), []))
        cases.append(("the Capability Matrix has not been gutted", len(base) >= 16, True))
        # The claim the plane patch actually makes: both design skills are now dimensions, so
        # CM01 can demand them. Asserted against the real document, so deleting a row turns
        # this red instead of quietly narrowing the matrix check.
        cases.append(("both design skills are declared dimensions",
                      sorted({"apple-ui", "designmotion-design"} & set(base)),
                      ["apple-ui", "designmotion-design"]))
        # istqb-testing joined the matrix with the ISTQB integration patch. Deleting the row
        # must fail here, not pass.
        cases.append(("istqb-testing is a declared dimension",
                      "istqb-testing" in base, True))
        widened = parse_schema(
            "| Dimension | Required? | Skill |\n"
            "|---|---|---|\n"
            "| Frontend implementation | yes/no | `frontend-react` |\n"
            "| UI design system | yes/no | `apple-ui` |\n"
            "| Interaction design | yes/no | `designmotion-design` |\n")
        cases.append(("a new doc row becomes a required dimension",
                      widened, ["frontend-react", "apple-ui", "designmotion-design"]))

    # 14-20. Capability matrix: the DECLARED half. The matrix is the one artifact where an
    # agent writes down which skills it decided it needs, so it is exactly where a silent
    # omission would otherwise live.
    dims_schema = ["frontend-react", "backend-python", "unit-test-authoring"]
    good = {"frontend-react": "yes", "backend-python": "no", "unit-test-authoring": "yes"}

    def mcase(name, schema, required, scope, dims, want):
        got = sorted({r["rule"] for r in check_matrix(schema, set(required), scope, dims, "m")})
        cases.append((name, got, sorted(want)))

    mcase("complete matrix -> clean", dims_schema,
          ["frontend-react", "unit-test-authoring"], "task", good, [])
    mcase("missing dimension -> CM01", dims_schema,
          ["frontend-react", "unit-test-authoring"], "task",
          {k: v for k, v in good.items() if k != "backend-python"}, ["CM01"])
    mcase("yes without required_skills -> CM04", dims_schema,
          ["frontend-react"], "task", good, ["CM04"])
    mcase("non-boolean verdict -> CM02", dims_schema,
          ["frontend-react", "unit-test-authoring"], "task",
          dict(good, **{"backend-python": "maybe"}), ["CM02"])
    mcase("unknown dimension -> CM03", dims_schema,
          ["frontend-react", "unit-test-authoring"], "task",
          dict(good, **{"settigation-code": "yes"}), ["CM03"])
    # The trap: the dimension LABEL is the intuitive key, and the schema holds skill IDs. Keying
    # on the label must answer nothing and be reported twice -- CM01 for the row it meant to
    # answer, CM03 for the key no row declares. A silent pass here would be the whole bug.
    mcase("label used as key -> CM01 + CM03", dims_schema,
          ["frontend-react", "unit-test-authoring"], "task",
          {"ui-design-system": "yes", "backend-python": "no", "unit-test-authoring": "yes"},
          ["CM01", "CM03"])
    mcase("bad scope -> CM02", dims_schema,
          ["frontend-react", "unit-test-authoring"], "team", good, ["CM02"])
    # Teeth: an all-'no' matrix must be clean, so CM04 is proven to read values rather than
    # fire on every row.
    mcase("all-no matrix -> clean", dims_schema, [], "task",
          {"frontend-react": "no", "backend-python": "no", "unit-test-authoring": "no"}, [])

    failed = [(n, g, w) for n, g, w in cases if g != w]
    for name, got, want in cases:
        print("  %s  %s%s" % ("PASS" if got == want else "FAIL", name,
                              "" if got == want else "  got=%s want=%s" % (got, want)))
    print("selftest: %d/%d pass" % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="skill coverage for a plan")
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--required-skills", action="store_true",
                    help="print every required_skills entry, one per line, and exit")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return _selftest()
    if not a.plan:
        print("[skill_coverage] BLOCKED no plan given")
        return 2
    if not os.path.isfile(a.plan):
        print("[skill_coverage] BLOCKED plan not readable: %s" % a.plan)
        return 2
    if a.required_skills:
        # A pure parser: no config, no matrix, no network. It must never fail because a root
        # is unconfigured, or G-SKILL-USE could not tell a bad plan from a bad root.
        try:
            with open(a.plan, encoding="utf-8-sig") as fh:
                for name in collect_lists(fh.read(), "required_skills"):
                    print(name)
        except (OSError, UnicodeDecodeError) as exc:
            print("[skill_coverage] BLOCKED %s" % exc)
            return 2
        return 0
    try:
        rows = check_file(a.plan, a.root)
    except ConfigMissing as exc:
        # No configured skills system here: there is no selection contract to enforce, and
        # this is a non-judgement, not a clean plan. opencode.json is agent-immutable, so an
        # agent cannot manufacture this state to escape the check.
        print("[skill_coverage] NOT_APPLICABLE %s" % exc)
        return 4
    except (OSError, ValueError) as exc:
        print("[skill_coverage] BLOCKED %s" % exc)
        return 2
    errors = [r for r in rows if r["severity"] == "ERROR"]
    if a.json:
        print(json.dumps({"errors": len(errors), "findings": rows}, indent=1))
    else:
        for r in rows:
            print("[skill_coverage] %s %s %s: %s" %
                  (r["severity"], r["rule"], r["where"], r["message"]))
        print("[skill_coverage] %d error(s), %d warning(s)" %
              (len(errors), len(rows) - len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
