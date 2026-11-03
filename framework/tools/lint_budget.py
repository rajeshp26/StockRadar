#!/usr/bin/env python3
"""Static-analysis budget: a ratchet, not a sweep.

WHY THIS EXISTS
===============
G4 required every detected language to run at least one static-analysis tool. That bar
is right, but it was the only gate with no way to live alongside existing debt, so on
any repository with history it could never pass. This framework already settled that
question once, for the frontend stack (``framework/frontend/stack_check.py``):

    "1. Ratchet, not sweep. Only files changed by the current task are judged. A
     brownfield repo ..."

and it ships ``framework/frontend/baseline.json`` to do it. G4 simply never got the
same treatment. This module is that treatment, for static analysis.

THE MODEL
=========
A committed budget records how many findings exist per ``(file, rule)``, together with
the exact tool version that produced them. Then:

  * a finding NOT covered by the budget is NEW  -> exit 1, the gate fails
  * a finding covered by the budget is DEBT     -> reported, non-blocking
  * fewer findings than the budget is SHRINKAGE -> reported, and ``update`` locks it in
  * ``update`` refuses to raise the total unless a human passes ``--allow-increase``
    with a ``--reason``

The last rule is what makes it a ratchet rather than a set of exclusions. A frozen
exclusion list rots silently; a budget that can only shrink is a standing obligation.

Why key on counts per ``(file, rule)`` and not on changed files? A new rule violation
can be introduced in a file the diff does not list (generated code, a file touched
earlier in the branch, a config change). Counting is scope-free: it catches new debt
anywhere, and it cannot be satisfied by editing a file back and forth.

Why pin the tool version? Findings are a function of the linter. An upgraded ruff that
adds a rule would otherwise "create" hundreds of findings and read as a developer's
mistake. Pinning turns that into a deliberate, reviewable baseline refresh.

Exit codes (framework/gates/EXIT_CODES.md vocabulary):
  0  no new findings
  1  new findings (or a refused budget increase)
  2  BLOCKED - tool missing, budget unreadable, or tool version drift

Usage:
    python3 framework/tools/lint_budget.py check  [--tool ruff]
    python3 framework/tools/lint_budget.py report
    python3 framework/tools/lint_budget.py update --reason "..." [--allow-increase]
    python3 framework/tools/lint_budget.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
DEFAULT_BUDGET = Path("framework") / "quality" / "baseline.json"


class Blocked(Exception):
    """Something prevented a judgement (exit 2). Never a pass."""


# ── tool adapters ──────────────────────────────────────────────────────────────
# One adapter per tool. Adding mypy/bandit later means adding an entry here; the
# budget format, the comparison and the exit-code contract stay unchanged.

def _ruff_version(binary: str) -> str:
    r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise Blocked(f"cannot read {binary} --version: {r.stderr.strip()[:200]}")
    return out


def _ruff_findings(binary: str, root: Path) -> tuple[int, list[dict]]:
    """Run ruff over the whole tree and return (exit, parsed findings).

    ruff exits 1 when it finds anything; that is a normal result, not an error. Exit 2
    means ruff itself failed (bad config, crashed), which must not be mistaken for
    "no findings".
    """
    r = subprocess.run(
        [binary, "check", ".", "--output-format=json"],
        cwd=str(root), capture_output=True, text=True, timeout=900,
    )
    if r.returncode not in (0, 1):
        raise Blocked(f"ruff check failed to run (exit {r.returncode}): "
                      f"{(r.stderr or r.stdout).strip()[:300]}")
    try:
        findings = json.loads(r.stdout or "[]")
    except json.JSONDecodeError as e:
        raise Blocked(f"ruff output was not JSON ({e}); refusing to guess") from e
    if not isinstance(findings, list):
        raise Blocked("ruff output was not a JSON list; refusing to guess")
    return r.returncode, findings


TOOLS = {
    "ruff": {"version": _ruff_version, "findings": _ruff_findings, "binary": "ruff"},
}


# ── analysis ───────────────────────────────────────────────────────────────────

def _canon_path(value: str) -> str:
    """Canonicalise a path so Windows and WSL spellings of the same file agree.

    Measured problem this fixes: the baseline was written by Windows Python (``python`` ->
    ``C:\\repo``) while the gate runs it under WSL Python (``python3`` -> ``/mnt/c/repo``).
    ruff is a Windows PE in both cases, so it reports ``C:\\repo\\a.py`` in both; the two
    interpreters then disagreed about whether that was inside the root, every key missed,
    and a clean tree reported 1,764 new findings AND 1,764 improvements at once.

    Canonical form: forward slashes, lowercase drive letter, ``/mnt/<d>/x`` folded to
    ``<d>:/x``, no duplicate or trailing slashes, compared case-insensitively (Windows
    paths are case-insensitive and a baseline keyed on case would be host-specific).
    """
    p = value.replace("\\", "/")
    m = re.match(r"^/?mnt/([a-zA-Z])/(.*)$", p)
    if m:
        p = f"{m.group(1).lower()}:/{m.group(2)}"
    p = re.sub(r"/+", "/", p)
    if len(p) > 2 and p[1] == ":":
        p = p[0].lower() + p[1:]
    return p.rstrip("/")


def relative_name(filename: str, root: Path) -> str:
    """Repo-relative POSIX path, so a budget key is portable across hosts.

    ruff reports absolute paths in the host's own form (``C:\\x\\y.py`` under Windows,
    ``/mnt/c/x/y.py`` under WSL). A budget keyed on either would be machine-specific.
    """
    name = _canon_path(str(filename))
    base = _canon_path(str(root))
    if base and name.lower().startswith(base.lower() + "/"):
        return name[len(base) + 1:]
    if base and name.lower() == base.lower():
        return "."
    return name


def counts_from(findings: list[dict], root: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for f in findings:
        name = relative_name(str(f.get("filename", "")), root)
        code = str(f.get("code") or f.get("name") or "UNKNOWN")
        counts.setdefault(name, {})
        counts[name][code] = counts[name].get(code, 0) + 1
    return counts


def total_of(counts: dict[str, dict[str, int]]) -> int:
    return sum(n for per_file in counts.values() for n in per_file.values())


def compare(current: dict[str, dict[str, int]],
            budget: dict[str, dict[str, int]]) -> tuple[dict, dict]:
    """Return (new, removed) as {file: {rule: delta}}.

    new     - more occurrences of a rule in a file than the budget allows
    removed - fewer occurrences than the budget records (shrinkage to lock in)
    """
    new: dict[str, dict[str, int]] = {}
    removed: dict[str, dict[str, int]] = {}
    for name, per_file in current.items():
        for code, n in per_file.items():
            allowed = budget.get(name, {}).get(code, 0)
            if n > allowed:
                new.setdefault(name, {})[code] = n - allowed
    for name, per_file in budget.items():
        for code, n in per_file.items():
            have = current.get(name, {}).get(code, 0)
            if have < n:
                removed.setdefault(name, {})[code] = n - have
    return new, removed


def load_budget(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # An unreadable budget is not "empty": that would silently turn every existing
        # finding into a new one, or worse, hide a corrupt baseline.
        raise Blocked(f"budget {path} is not valid JSON ({e})") from e
    if not isinstance(data, dict) or not isinstance(data.get("counts", {}), dict):
        raise Blocked(f"budget {path} is not schema {SCHEMA}")
    if data.get("schema") != SCHEMA:
        raise Blocked(f"budget {path} has schema {data.get('schema')!r}, expected {SCHEMA}")
    return data


def write_budget(path: Path, tool: str, version: str,
                 counts: dict[str, dict[str, int]]) -> None:
    payload = {
        "schema": SCHEMA,
        "tool": tool,
        "tool_version": version,
        "generated_at": _now(),
        "total": total_of(counts),
        "counts": counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # sort_keys + fixed separators: the budget is reviewed in diffs, so it must be byte
    # stable for an unchanged tree. A budget that reorders on every run is unreviewable.
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(path)


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summarise_delta(delta: dict, limit: int = 10) -> list[str]:
    rows = []
    for name in sorted(delta):
        for code in sorted(delta[name]):
            rows.append(f"{name}: {delta[name][code]} x {code}")
    return rows[:limit]


# ── commands ───────────────────────────────────────────────────────────────────

def _root(args) -> Path:
    if args.root:
        return Path(args.root).resolve()
    cwd = Path.cwd()
    if (cwd / "framework").is_dir():
        return cwd
    return Path(__file__).resolve().parents[2]


def _budget_path(args) -> Path:
    p = Path(args.budget) if args.budget else DEFAULT_BUDGET
    return p if p.is_absolute() else _root(args) / p


def _gather(args, tool: str):
    adapter = TOOLS[tool]
    binary = args.tool_bin or shutil.which(adapter["binary"])
    if not binary:
        raise Blocked(
            f"{adapter['binary']} not found on PATH. Install it (framework/quality/README.md) "
            "or this gate cannot judge static analysis -- a missing tool is never a pass."
        )
    root = _root(args)
    version = adapter["version"](binary)
    _rc, findings = adapter["findings"](binary, root)
    return root, version, findings, counts_from(findings, root)


def cmd_check(args) -> int:
    tool = args.tool
    root, version, findings, current = _gather(args, tool)
    path = _budget_path(args)
    budget_doc = load_budget(path)

    budget_version = budget_doc.get("tool_version")
    if budget_doc and budget_version and budget_version != version:
        raise Blocked(
            f"budget was produced by {budget_version!r} but {tool} is {version!r}. "
            "Findings are a function of the linter, so the budget cannot be compared "
            "across versions. Refresh it deliberately:\n"
            f"  python3 framework/tools/lint_budget.py update --reason \"upgrade to {version}\""
        )

    budget_counts = budget_doc.get("counts", {})
    new, removed = compare(current, budget_counts)
    total, budgeted = total_of(current), total_of(budget_counts)

    print(f"[lint_budget] {tool} {version}: {total} finding(s), budget {budgeted} "
          f"-> {len(new)} file(s) with new findings, {len(removed)} file(s) improved")

    if new:
        print(f"[lint_budget] NEW finding(s) not covered by the budget ({path}):")
        shown = _summarise_delta(new, limit=args.max_samples)
        for row in shown:
            print("  " + row)
        remaining = sum(len(v) for v in new.values()) - len(shown)
        if remaining > 0:
            print(f"  ... and {remaining} more (file, rule) pair(s)")
        # Point at the actual source lines: a count is not actionable without them.
        print("[lint_budget] offending locations (first few):")
        new_keys = {(name, code) for name in new for code in new[name]}
        printed = 0
        for f in findings:
            key = (relative_name(str(f.get("filename", "")), root),
                   str(f.get("code") or f.get("name") or "UNKNOWN"))
            if key not in new_keys:
                continue
            loc = f.get("location") or {}
            print(f"  {key[0]}:{loc.get('row', '?')}:{loc.get('column', '?')}: "
                  f"{key[1]} {f.get('message', '')}")
            printed += 1
            if printed >= args.max_samples:
                break
        print("[lint_budget] fix them, or record a deliberate baseline update with a reason:")
        print("  python3 framework/tools/lint_budget.py update --reason \"...\"")
        return 1

    if removed:
        lost = sum(v for per in removed.values() for v in per.values())
        print(f"[lint_budget] budget shrank by {lost} finding(s) - lock it in so the "
              "ratchet cannot spring back:")
        print("  python3 framework/tools/lint_budget.py update --reason \"burndown\"")
    return 0


def cmd_report(args) -> int:
    tool = args.tool
    root, version, findings, current = _gather(args, tool)
    path = _budget_path(args)
    budget_doc = load_budget(path)
    budgeted = total_of(budget_doc.get("counts", {}))
    total = total_of(current)

    print(f"[lint_budget] tool      {tool} {version}")
    print(f"[lint_budget] root      {root}")
    print(f"[lint_budget] budget    {path} (schema {budget_doc.get('schema', 'absent')})")
    print(f"[lint_budget] baseline  {budgeted} finding(s), generated "
          f"{budget_doc.get('generated_at', 'n/a')}")
    print(f"[lint_budget] current   {total} finding(s)")

    if not current:
        print("[lint_budget] nothing to report: the tree is clean")
        return 0

    by_rule: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for name, per_file in current.items():
        for code, n in per_file.items():
            by_rule[code] = by_rule.get(code, 0) + n
            by_file[name] = by_file.get(name, 0) + n

    print("[lint_budget] top rules:")
    for code, n in sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
        print(f"  {n:6d}  {code}")
    print("[lint_budget] heaviest files:")
    for name, n in sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
        print(f"  {n:6d}  {name}")
    return 0


def cmd_update(args) -> int:
    if not args.reason:
        print("REFUSING: a budget change needs --reason. A baseline with no stated "
              "reason is an exclusion list nobody can review.", file=sys.stderr)
        return 1
    tool = args.tool
    _root_dir, version, _findings, current = _gather(args, tool)
    path = _budget_path(args)
    old = load_budget(path)
    old_total = total_of(old.get("counts", {}))
    new_total = total_of(current)

    if old and new_total > old_total and not args.allow_increase:
        print(f"REFUSING: budget would grow {old_total} -> {new_total} "
              f"(+{new_total - old_total}). A ratchet that can be raised on demand is "
              "not a ratchet.", file=sys.stderr)
        new, _removed = compare(current, old.get("counts", {}))
        for row in _summarise_delta(new, limit=25):
            print("  new: " + row, file=sys.stderr)
        print("Fix them, or pass --allow-increase with the reason this is unavoidable.",
              file=sys.stderr)
        return 1

    write_budget(path, tool, version, current)
    verb = "adopted" if not old else ("raised" if new_total > old_total else "recorded")
    print(f"[lint_budget] {verb} baseline: {old_total} -> {new_total} finding(s)")
    print(f"[lint_budget] wrote {path}")
    print(f"[lint_budget] reason: {args.reason}")
    return 0


# ── self-test ──────────────────────────────────────────────────────────────────

def _self_test() -> int:
    """Prove the comparison rules, not just the happy path.

    Every case below is falsifiable: if compare()/load_budget()/write_budget() lost the
    behaviour it names, the case fails. No subprocess, no real linter -- the logic under
    test is pure, and a self-test that needed ruff installed would skip on exactly the
    hosts where the budget matters most.
    """
    import tempfile

    cases: list[tuple[str, callable]] = []

    def case(fn):
        cases.append((fn.__name__, fn))
        return fn

    @case
    def new_finding_is_detected():
        new, removed = compare({"a.py": {"E1": 2}}, {"a.py": {"E1": 1}})
        assert new == {"a.py": {"E1": 1}}, new
        assert removed == {}, removed

    @case
    def budgeted_finding_is_not_new():
        new, removed = compare({"a.py": {"E1": 3}}, {"a.py": {"E1": 3}})
        assert new == {} and removed == {}, (new, removed)

    @case
    def file_absent_from_budget_is_entirely_new():
        new, _ = compare({"new.py": {"E1": 1}}, {})
        assert new == {"new.py": {"E1": 1}}, new

    @case
    def shrinkage_is_reported():
        _new, removed = compare({}, {"a.py": {"E1": 4}})
        assert removed == {"a.py": {"E1": 4}}, removed

    @case
    def rule_change_in_same_file_is_new_not_neutral():
        new, _removed = compare({"a.py": {"E2": 1}}, {"a.py": {"E1": 1}})
        assert new == {"a.py": {"E2": 1}}, new

    @case
    def counts_are_per_file_not_global():
        new, _removed = compare({"a.py": {"E1": 2}, "b.py": {"E1": 0}},
                                {"a.py": {"E1": 1}, "b.py": {"E1": 1}})
        assert new == {"a.py": {"E1": 1}}, new

    @case
    def paths_are_normalised_to_repo_relative_posix():
        root = Path("C:/repo")
        assert relative_name(r"C:\repo\pkg\m.py", root) == "pkg/m.py"
        assert relative_name("C:/repo/pkg/m.py", root) == "pkg/m.py"

    @case
    def windows_and_wsl_spellings_of_the_same_path_agree():
        # The regression that made a clean tree report 1764 new findings: baseline written
        # by Windows python, check run by WSL python3, ruff reporting "C:\\repo\\a.py".
        win_root = Path("C:/repo")
        wsl_root = Path("/mnt/c/repo")
        for root in (win_root, wsl_root):
            assert relative_name(r"C:\repo\a.py", root) == "a.py", root
            assert relative_name("/mnt/c/repo/a.py", root) == "a.py", root
            assert relative_name("c:/REPO/a.py", root) == "a.py", root

    @case
    def path_outside_the_root_is_left_absolute_not_silently_trimmed():
        assert relative_name("/other/place/a.py", Path("/mnt/c/repo")) == "/other/place/a.py"

    @case
    def corrupt_budget_blocks_instead_of_reading_empty():
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.json"
            p.write_text("{not json", encoding="utf-8")
            try:
                load_budget(p)
            except Blocked:
                pass
            else:
                raise AssertionError("corrupt budget was accepted")

    @case
    def wrong_schema_blocks():
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.json"
            p.write_text(json.dumps({"schema": 999, "counts": {}}), encoding="utf-8")
            try:
                load_budget(p)
            except Blocked:
                pass
            else:
                raise AssertionError("wrong schema was accepted")

    @case
    def missing_budget_reads_as_empty_not_error():
        with tempfile.TemporaryDirectory() as td:
            assert load_budget(Path(td) / "absent.json") == {}

    @case
    def write_is_byte_stable_for_same_input():
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.json"
            counts = {"z.py": {"E2": 1, "E1": 2}, "a.py": {"F1": 1}}
            write_budget(p, "ruff", "ruff 1.2.3", counts)
            one = p.read_bytes()
            write_budget(p, "ruff", "ruff 1.2.3", counts)
            two = p.read_bytes()
            assert one == two, "budget bytes changed for identical input"
            doc = json.loads(one.decode("utf-8"))
            assert doc["total"] == 4, doc
            assert list(doc["counts"]) == ["a.py", "z.py"], list(doc["counts"])

    failed = 0
    for name, fn in cases:
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - a self-test reports, it does not crash
            print(f"  FAIL  {name}: {e}")
            failed += 1
        else:
            print(f"  PASS  {name}")
    print(f"selftest: {len(cases) - failed}/{len(cases)} pass")
    return 0 if failed == 0 else 1


# ── entry point ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?", choices=["check", "update", "report"])
    ap.add_argument("--tool", default="ruff", choices=sorted(TOOLS))
    ap.add_argument("--root", default=None, help="repo root (default: cwd)")
    ap.add_argument("--budget", default=None,
                    help=f"budget path (default: {DEFAULT_BUDGET.as_posix()})")
    ap.add_argument("--tool-bin", default=None,
                    help="explicit linter binary, bypassing PATH lookup")
    ap.add_argument("--reason", default=None, help="why the budget is changing (update)")
    ap.add_argument("--allow-increase", action="store_true",
                    help="permit the total to grow (update); requires --reason")
    ap.add_argument("--max-samples", type=int, default=15)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.command:
        ap.print_help()
        return 2

    try:
        return {"check": cmd_check, "update": cmd_update, "report": cmd_report}[args.command](args)
    except Blocked as e:
        print(f"[lint_budget] BLOCKED {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
