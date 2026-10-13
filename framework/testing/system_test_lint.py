#!/usr/bin/env python3
"""System-test lint -- DID-017. Static checks that a test suite is REQUIREMENT-DERIVED,
BLACK-BOX and REAL-STACK, so a green run means something.

Why: tests written by the same agent that wrote the code, against mocks and hand-picked
fixtures, share the code's assumptions and pass while the real system is wrong. This lint
rejects the structural symptoms. It cannot judge whether an assertion is the right one.

Tag grammar (first docstring line of a Python test, or the title string of a JS/TS test):
    AC-2 kind:negative data:acct9-2026-09 shape:mixed_lot  <free text>
  AC-<n>      requirement (acceptance criterion id from the plan)         required
  kind:<k>    positive | negative | boundary | abuse | idempotency | concurrency | regression
  data:<id>   id of an entry in the real-data manifest                    optional
  shape:<id>  real-data shape class this test exercises                   optional

Rules (ERROR unless noted):
  ST01 mocking/stubbing/network interception        ST02 imports or reads application source
  ST03 skipped / xfail / conditional-skip tests     ST04 vacuous test (no real assertion)
  ST05 missing AC tag or kind tag                   ST06 real-data manifest problems
  ST07 plan coverage: positive + break test per real-stack AC   ST08 unresolved scenario matrix
  (WARN) unreferenced manifest shape; orphan AC tag; hand-picked data without data: tag

Stdlib only. Exit 0 no errors | 1 errors | 2 BLOCKED (policy/plan unreadable)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_TAGS = ("integration", "e2e", "browser", "data-invariant")
SKILL = "see skill system-test-authoring"

PY_MOCK = re.compile(
    r"(unittest\.mock|from\s+mock\s+import|import\s+mock\b|pytest_mock|\bmocker\b|MagicMock|"
    r"\bAsyncMock\b|\bmonkeypatch\b|mock\.patch|@patch\s*\(|requests_mock|\bresponses\.(add|activate)|"
    r"httpretty|\brespx\b|\bfreezegun\b|\bfreeze_time\b|\bvcr\b|\bcassette\b)")
JS_MOCK = re.compile(
    r"(jest\.mock|jest\.spyOn|jest\.fn\s*\(|vi\.mock|vi\.fn\s*\(|vi\.spyOn|sinon\.|\bnock\s*\(|"
    r"\bmsw\b|page\.route\s*\(|context\.route\s*\(|route\.fulfill|\.mockResolvedValue|"
    r"\.mockReturnValue|\.mockImplementation)")
PY_SKIP = re.compile(r"(pytest\.skip\s*\(|mark\.skip|mark\.skipif|mark\.xfail|pytest\.xfail|"
                     r"importorskip|unittest\.skip)")
JS_SKIP = re.compile(r"(\b(test|it|describe)\.(skip|fixme|fail)\b|\bxit\s*\(|\bxtest\s*\(|"
                     r"\bxdescribe\s*\(|test\.slow|\.only\s*\()")
JS_TEST = re.compile(r"\b(?:test|it)\s*\(\s*(['\"`])(.*?)\1", re.S)
JS_EXPECT = re.compile(r"\bexpect\s*\(|\bassert[\.\(]")


def _load_plan_lint():
    spec = importlib.util.spec_from_file_location(
        "plan_lint_for_system_tests", os.path.join(HERE, "..", "plan", "plan_lint.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Findings:
    def __init__(self):
        self.rows = []

    def err(self, rule, where, msg):
        self.rows.append({"severity": "ERROR", "rule": rule, "where": where,
                          "message": msg + " (" + SKILL + ")"})

    def warn(self, rule, where, msg):
        self.rows.append({"severity": "WARN", "rule": rule, "where": where,
                          "message": msg + " (" + SKILL + ")"})


class T:
    def __init__(self, path, name, tagtext, body, lang):
        self.path, self.name, self.tagtext, self.body, self.lang = path, name, tagtext, body, lang
        self.acs = re.findall(r"\bAC-\d+\b", tagtext)
        self.kinds = re.findall(r"\bkind:([a-z-]+)", tagtext)
        self.data = re.findall(r"\bdata:([A-Za-z0-9_.-]+)", tagtext)
        self.shapes = re.findall(r"\bshape:([A-Za-z0-9_.-]+)", tagtext)


def load_policy(root):
    p = os.path.join(root, "framework", "testing", "system_test_policy.json")
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_files(root, policy):
    base = os.path.join(root, policy["test_dir"])
    out = []
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x not in ("node_modules", "__pycache__", "data", ".git")]
        for fn in sorted(files):
            if re.match(r"(test_.*\.py|.*_test\.py|.*\.(spec|test)\.(ts|tsx|js|jsx|mjs))$", fn):
                out.append(os.path.join(d, fn))
    return sorted(out)


def discover(root, policy, f):
    tests, texts = [], {}
    for path in test_files(root, policy):
        rel = os.path.relpath(path, root).replace("\\", "/")
        src = open(path, encoding="utf-8-sig", errors="replace").read()
        texts[rel] = src
        if path.endswith(".py"):
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                f.err("ST04", rel, "does not parse: %s" % exc)
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        node.name.startswith("test"):
                    doc = ast.get_docstring(node) or ""
                    seg = ast.get_source_segment(src, node) or ""
                    tests.append(T(rel, node.name, doc.splitlines()[0] if doc else "", seg, "py"))
        else:
            ms = list(JS_TEST.finditer(src))
            for i, m in enumerate(ms):
                end = ms[i + 1].start() if i + 1 < len(ms) else len(src)
                tests.append(T(rel, m.group(2), m.group(2), src[m.start():end], "js"))
    return tests, texts


def _py_vacuous(t):
    try:
        node = ast.parse(t.body.lstrip()).body[0]
    except (SyntaxError, IndexError):
        return False
    has_real = False
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            tst = n.test
            if isinstance(tst, ast.Constant):
                continue
            if isinstance(tst, ast.Compare) and len(tst.ops) == 1 and \
                    ast.dump(tst.left) == ast.dump(tst.comparators[0]):
                continue
            has_real = True
        elif isinstance(n, ast.With):
            for item in n.items:
                if "raises" in ast.dump(item.context_expr):
                    has_real = True
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                n.func.attr.startswith("assert"):
            has_real = True
    return not has_real


def check_files(tests, texts, policy, f):
    forbidden = tuple(policy.get("forbidden_imports", []))
    for rel, src in texts.items():
        mock = PY_MOCK if rel.endswith(".py") else JS_MOCK
        skip = PY_SKIP if rel.endswith(".py") else JS_SKIP
        for m in mock.finditer(src):
            f.err("ST01", rel, "mocking/stubbing/interception (%r): a mocked test proves the "
                  "mock, not the system. Call the real stack" % m.group(0))
            break
        for m in skip.finditer(src):
            f.err("ST03", rel, "skip/xfail/only (%r): a skipped test is not a pass; if the "
                  "stack is down the harness reports UNVERIFIABLE" % m.group(0))
            break
        if rel.endswith(".py"):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                mods = []
                if isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    mods = [n.module]
                for mod in mods:
                    if mod.split(".")[0] in forbidden:
                        f.err("ST02", rel, "imports application code %r: system tests are "
                              "black-box; drive the running system through its interfaces" % mod)
            if re.search(r"open\([^)]*['\"][^'\"]*\b(" + "|".join(map(re.escape, forbidden)) +
                         r")/", src) if forbidden else False:
                f.warn("ST02", rel, "opens a path under application source; black-box tests "
                       "should not read the implementation")
        else:
            for m in re.finditer(r"""(?:from\s+|require\(\s*)['"]((?:\.\./)+|@/)(?:src|backend|app)/""",
                                 src):
                f.err("ST02", rel, "imports application code (%s...)" % m.group(0)[:40])
                break
    for t in tests:
        where = "%s::%s" % (t.path, t.name)
        if t.lang == "py":
            if _py_vacuous(t):
                f.err("ST04", where, "no real assertion (none, constant, or compares a value "
                      "to itself)")
        elif not JS_EXPECT.search(t.body):
            f.err("ST04", where, "no expect()/assert in the test body")
        if not t.acs:
            f.err("ST05", where, "no AC-<n> tag: every test must trace to a requirement")
        allowed = ["positive"] + list(policy.get("break_kinds", []))
        if not t.kinds:
            f.err("ST05", where, "no kind:<k> tag; allowed: %s" % ", ".join(allowed))
        else:
            for k in t.kinds:
                if k not in allowed:
                    f.err("ST05", where, "unknown kind:%s; allowed: %s" % (k, ", ".join(allowed)))


def check_manifest(root, policy, tests, f):
    mp = os.path.join(root, policy["data_manifest"])
    if not os.path.isfile(mp):
        used = [t for t in tests if t.data or t.shapes]
        if used:
            f.err("ST06", policy["data_manifest"], "tests reference data:/shape: tags but the "
                  "manifest does not exist")
        else:
            f.err("ST06", policy["data_manifest"], "no real-data manifest: record where the real "
                  "data came from (source, captured_at, file, sha256, rows, shapes)")
        return {}
    try:
        man = json.load(open(mp, encoding="utf-8-sig"))
    except ValueError as exc:
        f.err("ST06", policy["data_manifest"], "manifest is not valid JSON: %s" % exc)
        return {}
    entries = {e.get("id"): e for e in man.get("datasets", []) if isinstance(e, dict)}
    all_shapes = set()
    for eid, e in entries.items():
        miss = [k for k in ("id", "source", "captured_at", "file", "sha256", "rows", "shapes")
                if not e.get(k) and e.get(k) != 0]
        if miss:
            f.err("ST06", str(eid), "manifest entry missing: %s" % ", ".join(miss))
            continue
        fp = os.path.join(os.path.dirname(mp), e["file"])
        if not os.path.isfile(fp):
            f.err("ST06", str(eid), "dataset file not found: %s" % e["file"])
        elif sha256_file(fp) != str(e["sha256"]).lower():
            f.err("ST06", str(eid), "dataset file hash differs from the manifest (data changed)")
        all_shapes.update(e.get("shapes") or [])
    used_shapes = set()
    for t in tests:
        for d in t.data:
            if d not in entries:
                f.err("ST06", "%s::%s" % (t.path, t.name), "data:%s is not in the manifest" % d)
        used_shapes.update(t.shapes)
    for s in sorted(all_shapes - used_shapes):
        f.warn("ST06", "shape:%s" % s, "real-data shape exists in the manifest but no test "
               "exercises it")
    for t in tests:
        for s in t.shapes:
            if s not in all_shapes:
                f.err("ST06", "%s::%s" % (t.path, t.name), "shape:%s is not declared in the "
                      "manifest" % s)
    return entries


def plan_acs(plan_path):
    pl = _load_plan_lint()
    text = open(plan_path, encoding="utf-8-sig").read()
    keys = pl.parse_plan(text)
    out = {}
    for raw in keys.get("acceptance_criteria", {"items": []})["items"]:
        m = re.match(r"^(AC-\d+)\s+\[([A-Za-z0-9-]+)\]\s+(.*)$", raw)
        if m:
            out[m.group(1)] = (m.group(2).lower(), m.group(3))
    return out, keys


def check_coverage(tests, policy, plan_path, f):
    acs, _keys = plan_acs(plan_path)
    need = {a: v for a, v in acs.items() if v[0] in REAL_TAGS}
    breaks = set(policy.get("break_kinds", []))
    mins = policy.get("min_per_ac", {"positive": 1, "break": 1})
    for a in need:
        mine = [t for t in tests if a in t.acs]
        pos = [t for t in mine if "positive" in t.kinds]
        brk = [t for t in mine if breaks & set(t.kinds)]
        if len(pos) < mins.get("positive", 1):
            f.err("ST07", a, "no positive system test (kind:positive) traces to this "
                  "real-stack criterion")
        if len(brk) < mins.get("break", 1):
            f.err("ST07", a, "no break-it test (%s) traces to this criterion; a suite that "
                  "only confirms the happy path cannot find defects" % "/".join(sorted(breaks)))
    for t in tests:
        for a in t.acs:
            if a not in acs:
                f.warn("ST07", "%s::%s" % (t.path, t.name), "%s is not a criterion of this plan" % a)
    return need


def check_matrix(matrix_path, tests, f):
    names = {t.name for t in tests}
    n_rows = 0
    for ln in open(matrix_path, encoding="utf-8-sig").read().replace("\r", "").split("\n"):
        if not re.match(r"^\|\s*M-\d+", ln):
            continue
        n_rows += 1
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        mid, res = cells[0], cells[-1] if len(cells) >= 4 else ""
        m = re.match(r"^test:(\S+)$", res)
        if m:
            if m.group(1) not in names:
                f.err("ST08", mid, "resolution names test %s which does not exist" % m.group(1))
        elif re.match(r"^NA:\s*(.+)$", res, re.I):
            if len(res.split(":", 1)[1].split()) < 4:
                f.err("ST08", mid, "NA needs a reason of at least four words")
        else:
            f.err("ST08", mid, "unresolved: write the test and put test:<name>, or NA: <reason>")
    if n_rows == 0:
        f.err("ST08", matrix_path, "matrix has no rows")


def run_lint(root, plan=None, matrix=None):
    policy = load_policy(root)
    f = Findings()
    tests, texts = discover(root, policy, f)
    if not tests:
        f.err("ST00", policy["test_dir"], "no system tests found; write them from the "
              "requirements (skill system-test-authoring) before implementation")
        return f.rows, tests, policy
    check_files(tests, texts, policy, f)
    check_manifest(root, policy, tests, f)
    if len(tests) < policy.get("min_total_tests", 1):
        f.err("ST07", "suite", "only %d test(s); policy minimum is %d" %
              (len(tests), policy["min_total_tests"]))
    if plan:
        check_coverage(tests, policy, plan, f)
    if matrix:
        check_matrix(matrix, tests, f)
    return f.rows, tests, policy


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--plan")
    ap.add_argument("--matrix")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        rows, _t, _p = run_lint(a.root, a.plan, a.matrix)
    except (OSError, ValueError, KeyError) as exc:
        print("[system_test_lint] BLOCKED %s" % exc)
        return 2
    errs = [r for r in rows if r["severity"] == "ERROR"]
    if a.json:
        print(json.dumps({"errors": len(errs), "findings": rows}, indent=1))
    else:
        for r in rows:
            print("[system_test_lint] %s %s %s: %s" % (r["severity"], r["rule"], r["where"],
                                                       r["message"]))
        print("[system_test_lint] %d error(s), %d warning(s)" % (len(errs), len(rows) - len(errs)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
