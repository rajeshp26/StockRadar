"""Tests for framework/plan/plan_lint.py (DID-016).

Written as plain pytest functions so `pytest` actually collects them (several older suites in
this repo use custom runners that pytest never sees).
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("plan_lint_under_test", HERE / "plan_lint.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

CASES = sorted((HERE / "eval" / "cases").glob("*.md"))


def _expected(path):
    first = path.read_text(encoding="utf-8").splitlines()[0]
    spec = first.split("expect:", 1)[1].replace("-->", "").strip()
    return set() if spec == "-" else set(spec.split(","))


@pytest.mark.parametrize("case", CASES, ids=[c.stem for c in CASES])
def test_eval_case_fires_exactly_the_expected_rules(case):
    rows = pl.lint(str(case), str(ROOT), str(ROOT / ".planning"))
    fired = {r["rule"] for r in rows if r["severity"] == "ERROR"}
    assert fired == _expected(case), rows


def test_good_plan_has_no_findings_at_all():
    rows = pl.lint(str(HERE / "eval/cases/good_full.md"), str(ROOT), str(ROOT / ".planning"))
    assert rows == []


def test_parser_matches_g_entry_block_and_inline_forms():
    keys = pl.parse_plan("a:\n  - one\n  - two\nb: [x, y]\nc: scalar\n")
    assert keys["a"]["items"] == ["one", "two"]
    assert keys["b"]["items"] == ["x", "y"] and keys["b"]["inline"]
    assert keys["c"]["scalar"] == "scalar"


def test_inline_list_stops_at_first_bracket_like_the_gate():
    keys = pl.parse_plan("acceptance_criteria: [AC-1 [unit] text, AC-2 [e2e] more]\n")
    assert keys["acceptance_criteria"]["items"] == ["AC-1 [unit"]


def test_crlf_plan_gives_same_verdict(tmp_path):
    src = (HERE / "eval/cases/good_full.md").read_text(encoding="utf-8")
    p = tmp_path / "crlf.md"
    p.write_bytes(src.replace("\n", "\r\n").encode("utf-8"))
    assert pl.lint(str(p), str(ROOT), str(ROOT / ".planning")) == []


def test_stamp_then_edit_is_detected(tmp_path):
    p = tmp_path / "p.md"
    p.write_text("status: approved\ntitle: t\n", encoding="utf-8")
    pl.stamp(str(p))
    assert pl.parse_plan(p.read_text())["approval_hash"]["scalar"]
    assert not [r for r in pl.lint(str(p), str(ROOT), str(tmp_path)) if r["rule"] == "PL08"]
    p.write_text(p.read_text() + "\nextra line\n", encoding="utf-8")
    assert [r for r in pl.lint(str(p), str(ROOT), str(tmp_path)) if r["rule"] == "PL08"]


def test_dependency_cycle_and_unresolved(tmp_path):
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "A.md").write_text("depends_on:\n  - B\n", encoding="utf-8")
    (plans / "B.md").write_text("depends_on:\n  - A\n", encoding="utf-8")
    (plans / "C.md").write_text("depends_on:\n  - NOPE\n", encoding="utf-8")
    cyc = [r for r in pl.lint(str(plans / "A.md"), str(tmp_path), str(tmp_path))
           if r["rule"] == "PL07"]
    assert any("cycle" in r["message"] for r in cyc)
    unres = [r for r in pl.lint(str(plans / "C.md"), str(tmp_path), str(tmp_path))
             if r["rule"] == "PL07"]
    assert any("does not resolve" in r["message"] for r in unres)


def test_negated_mock_phrase_is_allowed_but_real_mock_is_not():
    assert not pl.MOCK.search("verified against the real database with no mocking")
    assert pl.MOCK.search("verified against a mocked repository")


def test_vague_with_anchor_passes_vague_without_anchor_fails(tmp_path):
    base = ("status: approved\nacceptance_criteria:\n  - AC-1 [e2e] %s\n")
    for text, should_fail in (("the page works correctly", True),
                              ("the page works correctly and shows 12 rows", False)):
        p = tmp_path / "p.md"
        p.write_text(base % text, encoding="utf-8")
        rows = pl.lint(str(p), str(ROOT), str(tmp_path))
        assert bool([r for r in rows if r["rule"] == "PL01" and r["severity"] == "ERROR"]) \
            == should_fail


def test_cli_exit_codes(tmp_path):
    script = str(HERE / "plan_lint.py")
    ok = subprocess.run([sys.executable, script, str(HERE / "eval/cases/good_full.md"),
                         "--root", str(ROOT)], capture_output=True, text=True)
    bad = subprocess.run([sys.executable, script, str(HERE / "eval/cases/vague_ac.md"),
                          "--root", str(ROOT)], capture_output=True, text=True)
    gone = subprocess.run([sys.executable, script, str(tmp_path / "missing.md")],
                          capture_output=True, text=True)
    assert (ok.returncode, bad.returncode, gone.returncode) == (0, 1, 2)
