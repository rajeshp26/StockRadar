#!/usr/bin/env python3
"""The gate scope contract: which paths this gate judges, and who judges the rest.

WHY THIS EXISTS
===============
G4 is repo-scoped by design ("does this language appear in the tree?"). In a repository
that is BOTH the framework's home and an application, that made the framework gate judge
the application: measured here, 1,637 of 1,764 budgeted lint findings and 2,379 of 2,429
collected tests belonged to `backend/` -- app code with its own CI, its own ruff/mypy/pytest
config, and integration tests that need Supabase/Firebase credentials this machine does not
have.

The result is the worst of both worlds: the gate either goes red for debt the framework does
not own, or it masks that debt in a budget so loose it stops ratcheting anything. Neither
tells you whether the framework is checked.

So the gate gets an explicit, reviewed scope:

    framework/gates/scope.json
    {
      "schema": 1,
      "owned": ["framework"],
      "delegated": [
        {"path": "backend", "tools": ["ruff", "pytest"],
         "authority": {"file": ".github/workflows/ci.yml",
                       "requires": ["ruff-action", "pytest tests/"]},
         "reason": "..."}
      ]
    }

* `owned`      -- paths this gate runs its tools over. `"."` means the whole tree.
* `delegated`  -- paths judged somewhere else, naming the authority AND the commands that
                  authority runs. Those tokens are re-verified against the authority file on
                  every run (see `verify`), because a delegation nobody re-checks is a
                  suppression list with better manners.
* everything else -- reported as judged by nobody, with a file count, every run. Not silent,
                  not fatal: it is a statement about ownership, not a claim of correctness.

A delegation disclaims a path WHOLESALE -- that code is somebody else's. Which of this
gate's tools that somebody actually runs is a separate question, reported as a gap, because
"they lint it" is not "they type-check it".

DEFAULT (no scope.json) is every path, whole tree. Absence must never read as "narrower
scope", so a missing file scans MORE, not less. An unreadable or invalid file is BLOCKED
(exit 2): it cannot be read, so it must not be guessed at.

Exit codes: 0 ok, 1 a delegation is void (authority file or token gone), 2 BLOCKED.

Usage:
    python3 framework/tools/gate_scope.py check [--root PATH]
    python3 framework/tools/gate_scope.py paths
    python3 framework/tools/gate_scope.py delegated [--tool ruff]
    python3 framework/tools/gate_scope.py count [--tool ruff]
    python3 framework/tools/gate_scope.py unjudged
    python3 framework/tools/gate_scope.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCHEMA = 1
SCOPE_RELPATH = Path("framework") / "gates" / "scope.json"

# Tools this contract can talk about. A tool name outside this set in scope.json is a typo
# that would otherwise silently match nothing.
TOOLS = ("ruff", "pytest", "mypy", "bandit")

# The sentinel for "the whole repository". Returned when there is no contract at all, so
# that "no scope file" and "owned: ['.']" behave identically: scan everything.
WHOLE_TREE = "."

# Directories never walked when counting files. Mirrors the gates' COMMON_PRUNE and, for
# dot-directories, pytest's own `norecursedirs = [".*"]` convention: runtime state and
# caches are not source. `.lifecycle`/`.planning` are state roots, not code.
PRUNE = {
    ".git", "node_modules", ".venv", "venv", "venv_wsl", "site-packages",
    "dist-packages", "__pycache__", ".tox", "build", "dist", "target", ".mypy_cache",
    ".ruff_cache", ".pytest_cache",
}


class Blocked(Exception):
    """The scope could not be read or is internally invalid (exit 2). Never a pass."""


# ── loading ────────────────────────────────────────────────────────────────────

def scope_path(root: Path) -> Path:
    return root / SCOPE_RELPATH


def load(root: Path) -> dict | None:
    """Return the parsed scope, or None when no scope file exists (whole tree).

    Unreadable / invalid raises Blocked. The distinction matters: "no file" is the
    documented, stricter default, while "I cannot read the file you wrote" must never be
    silently interpreted as either scope or no-scope.
    """
    p = scope_path(root)
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Blocked(f"{SCOPE_RELPATH} is unreadable ({e}); refusing to guess which paths "
                      "this gate owns") from e
    if not isinstance(doc, dict):
        raise Blocked(f"{SCOPE_RELPATH} must be a JSON object")
    if doc.get("schema") != SCHEMA:
        raise Blocked(f"{SCOPE_RELPATH} has schema {doc.get('schema')!r}, expected {SCHEMA}")

    owned = doc.get("owned", [])
    if not isinstance(owned, list) or not all(isinstance(x, str) for x in owned):
        raise Blocked(f"{SCOPE_RELPATH}: 'owned' must be a list of paths")
    if not owned:
        raise Blocked(f"{SCOPE_RELPATH} declares no owned paths. This gate would scan "
                      "nothing and could only pass vacuously; either name what it owns or "
                      "delete the file (no file = the whole tree).")
    if WHOLE_TREE in owned and len(owned) > 1:
        raise Blocked(f"{SCOPE_RELPATH}: '.' already means the whole tree; listing it "
                      "alongside other paths is ambiguous about intent")

    delegated_ = doc.get("delegated", [])
    if not isinstance(delegated_, list):
        raise Blocked(f"{SCOPE_RELPATH}: 'delegated' must be a list")

    seen: set[str] = set()
    for entry in delegated_:
        if not isinstance(entry, dict):
            raise Blocked(f"{SCOPE_RELPATH}: every 'delegated' entry must be an object")
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise Blocked(f"{SCOPE_RELPATH}: a delegated entry has no 'path'")
        if path in seen:
            raise Blocked(f"{SCOPE_RELPATH}: duplicate delegated path {path!r}")
        seen.add(path)
        if inside(path, [_norm(o) for o in owned]):
            raise Blocked(f"{SCOPE_RELPATH}: {path!r} is both owned and delegated")
        tools = entry.get("tools")
        if not isinstance(tools, list) or not tools:
            raise Blocked(f"{SCOPE_RELPATH}: delegated {path!r} names no tools")
        unknown = [t for t in tools if t not in TOOLS]
        if unknown:
            raise Blocked(f"{SCOPE_RELPATH}: delegated {path!r} names unknown tool(s) "
                          f"{unknown}; known tools are {list(TOOLS)}")
        auth = entry.get("authority")
        if not isinstance(auth, dict) or not auth.get("file") or not auth.get("requires"):
            raise Blocked(f"{SCOPE_RELPATH}: delegated {path!r} must name authority.file and "
                          "authority.requires (the commands that authority actually runs)")
    return doc


def _norm(p: str) -> str:
    p = p.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/") or WHOLE_TREE


def owned_paths(root: Path) -> list[str]:
    """Paths this gate judges. No contract at all means the whole tree."""
    doc = load(root)
    if doc is None:
        return [WHOLE_TREE]
    return [_norm(p) for p in doc.get("owned", [])]


def delegated(root: Path, tool: str | None = None) -> list[dict]:
    doc = load(root)
    if doc is None:
        return []
    out = []
    for entry in doc.get("delegated", []):
        if tool is None or tool in entry.get("tools", []):
            out.append(entry)
    return out


# ── analysis ──────────────────────────────────────────────────────────────────

def inside(rel: str, paths: list[str]) -> bool:
    rel = _norm(rel)
    if WHOLE_TREE in paths:
        return True
    return any(rel == p or rel.startswith(p + "/") for p in paths)


def python_files(root: Path) -> list[str]:
    """Every project .py file, repo-relative POSIX, pruned like the gates prune."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE and not d.startswith("."))
        for name in filenames:
            if name.endswith(".py"):
                out.append(_norm(str((Path(dirpath) / name).relative_to(root))))
    return sorted(out)


def files_for(root: Path, tool: str) -> list[str]:
    """Python files this gate would judge with `tool` (the contract is python-scoped)."""
    if tool not in TOOLS:
        raise Blocked(f"unknown tool {tool!r}; known tools are {list(TOOLS)}")
    return [f for f in python_files(root) if inside(f, owned_paths(root))]


def unjudged(root: Path) -> dict[str, int]:
    """{top-level dir: python file count} for files in no owned and no delegated path.

    Delegation disclaims a path wholesale -- it is somebody else's code. Which of this
    gate's tools that somebody actually runs is `delegation_gaps()`, a different question:
    "they lint it" is not "they type-check it".
    """
    covered = owned_paths(root) + [_norm(e["path"]) for e in delegated(root)]
    buckets: dict[str, int] = {}
    for f in python_files(root):
        if inside(f, covered):
            continue
        top = f.split("/", 1)[0] if "/" in f else "<root files>"
        buckets[top] = buckets.get(top, 0) + 1
    return buckets


def delegation_gaps(root: Path) -> list[dict]:
    """Per delegated path: which of this gate's tools no named authority runs there.

    This is the honest half of a delegation. `backend` delegated for ruff+pytest is still
    not type-checked or security-scanned by anyone we can name, and that gap has to be
    visible -- otherwise delegating one dimension reads as delegating all of them.
    """
    out = []
    for entry in delegated(root):
        missing = [t for t in TOOLS if t not in entry.get("tools", [])]
        if missing:
            out.append({"path": entry["path"], "tools": missing,
                        "authority": entry["authority"]["file"]})
    return out


def verify(root: Path) -> list[str]:
    """Prove each delegation still describes reality. Returns human-readable problems."""
    problems: list[str] = []
    for entry in delegated(root):
        path = entry["path"]
        auth = entry["authority"]
        auth_file = root / _norm(auth["file"])
        where = f"{SCOPE_RELPATH}: delegated {path!r} -> {auth['file']}"
        if not auth_file.is_file():
            problems.append(f"{where}: the authority file does not exist")
            continue
        try:
            text = auth_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            problems.append(f"{where}: the authority file cannot be read ({e})")
            continue
        for token in auth["requires"]:
            if token not in text:
                problems.append(
                    f"{where}: claims it runs {token!r}, but {auth['file']} no longer "
                    "contains it. The delegation is void -- either the authority stopped "
                    "checking this, or the token changed. Fix the claim or bring the path "
                    "back into 'owned'."
                )
        if not (root / _norm(path)).exists():
            problems.append(f"{where}: the delegated path {path!r} no longer exists "
                            "(stale entry -- remove it, or it will keep claiming coverage)")
    return problems


def summary_line(root: Path) -> str:
    """One line for the gate's own output, so scope is never silent."""
    owned = owned_paths(root)
    parts = ["owned: whole tree" if WHOLE_TREE in owned
             else f"owned: {', '.join(owned)}"]
    for e in delegated(root):
        gaps = [t for t in TOOLS if t not in e.get("tools", [])]
        tail = f" (no authority runs {', '.join(gaps)})" if gaps else ""
        parts.append(f"delegated {e['path']} -> {e['authority']['file']} "
                     f"[{'+'.join(e['tools'])}]{tail}")
    nj = unjudged(root)
    if nj:
        who = ", ".join(f"{d} ({n})" for d, n in sorted(nj.items()))
        parts.append(f"judged by nobody: {who}")
    return "; ".join(parts)


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    try:
        doc = load(root)
        problems = verify(root)
        owned = owned_paths(root)
    except Blocked as e:
        print(f"[scope] BLOCKED: {e}", file=sys.stderr)
        return 2
    if doc is None:
        print("[scope] no framework/gates/scope.json: the whole tree is in scope")
        return 0
    print(f"[scope] owned: {'whole tree' if WHOLE_TREE in owned else ', '.join(owned)}")
    for entry in delegated(root):
        auth = entry["authority"]
        gaps = [t for t in TOOLS if t not in entry.get("tools", [])]
        tail = f" (no authority runs {', '.join(gaps)})" if gaps else ""
        print(f"[scope] delegated: {entry['path']} -> {auth['file']} "
              f"[{'+'.join(entry['tools'])}]{tail} "
              f"[verified: {', '.join(auth['requires'])}]")
    nj = unjudged(root)
    if nj:
        who = ", ".join(f"{d} ({n})" for d, n in sorted(nj.items()))
        print(f"[scope] judged by nobody: {who}")
    if problems:
        for p in problems:
            print(f"[scope] FAIL {p}", file=sys.stderr)
        return 1
    return 0


def cmd_paths(args) -> int:
    try:
        for p in owned_paths(Path(args.root).resolve()):
            print(p)
    except Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_delegated(args) -> int:
    try:
        for entry in delegated(Path(args.root).resolve(), args.tool):
            print(entry["path"])
    except Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_count(args) -> int:
    root = Path(args.root).resolve()
    try:
        print(len(files_for(root, args.tool)))
    except Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_unjudged(args) -> int:
    root = Path(args.root).resolve()
    try:
        print(summary_line(root))
    except Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    return 0


# ── self-test ─────────────────────────────────────────────────────────────────

def _self_test() -> int:
    """Falsifiable cases for the contract rules. No scope file is not a failure mode."""
    import tempfile

    cases: list[tuple[str, callable]] = []

    def case(fn):
        cases.append((fn.__name__, fn))
        return fn

    def write(root: Path, doc) -> None:
        p = scope_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc), encoding="utf-8")

    def minimal(owned=("framework",), delegated_=None) -> dict:
        return {"schema": SCHEMA, "owned": list(owned),
                "delegated": list(delegated_ or [])}

    GOOD_AUTH = {"file": ".github/workflows/ci.yml", "requires": ["ruff"]}

    def delegation(path="backend", tools=("ruff",), auth=None) -> dict:
        return {"path": path, "tools": list(tools), "authority": dict(auth or GOOD_AUTH)}

    def tree(root: Path, dirs=("framework", "backend")) -> None:
        for d in dirs:
            (root / d).mkdir(parents=True, exist_ok=True)
            (root / d / "a.py").write_text("x = 1\n", encoding="utf-8")

    @case
    def absent_scope_means_whole_tree():
        # The strict default: no contract = nothing excluded, nothing unjudged. This must
        # read as MORE scanning, never less, or deleting the file would be a way to shrink
        # the gate's coverage.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            assert load(root) is None
            assert owned_paths(root) == [WHOLE_TREE], owned_paths(root)
            assert files_for(root, "ruff") == ["backend/a.py", "framework/a.py"]
            assert unjudged(root) == {}, unjudged(root)

    @case
    def owned_paths_limit_the_files_a_tool_judges():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            write(root, minimal())
            assert files_for(root, "ruff") == ["framework/a.py"], files_for(root, "ruff")

    @case
    def a_delegated_path_is_disclaimed_wholesale():
        # Delegation is per PATH. The per-tool question is `delegation_gaps`, kept
        # separate because a path judged by somebody else is not this gate's code at all.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            write(root, minimal(delegated_=[delegation(tools=["ruff", "pytest"])]))
            assert unjudged(root) == {}, unjudged(root)
            assert files_for(root, "ruff") == ["framework/a.py"]

    @case
    def delegation_gaps_name_the_tools_nobody_runs():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            write(root, minimal(delegated_=[delegation(tools=["ruff"])]))
            gaps = delegation_gaps(root)
            assert len(gaps) == 1, gaps
            assert gaps[0]["tools"] == ["pytest", "mypy", "bandit"], gaps[0]

    @case
    def a_complete_delegation_reports_no_gap():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            write(root, minimal(delegated_=[delegation(tools=list(TOOLS))]))
            assert delegation_gaps(root) == [], delegation_gaps(root)

    @case
    def paths_neither_owned_nor_delegated_are_reported_not_silent():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root, dirs=("framework", "backend", "app"))
            (root / "loose.py").write_text("x = 1\n", encoding="utf-8")
            write(root, minimal(delegated_=[delegation()]))
            assert unjudged(root) == {"app": 1, "<root files>": 1}, unjudged(root)
            assert "judged by nobody" in summary_line(root)
            assert "app (1)" in summary_line(root)

    @case
    def invalid_json_blocks_and_is_not_read_as_no_scope():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = scope_path(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{not json", encoding="utf-8")
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("unreadable scope was accepted")

    @case
    def empty_owned_list_blocks_instead_of_scanning_nothing():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, minimal(owned=()))
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("empty 'owned' was accepted")

    @case
    def whole_tree_cannot_be_mixed_with_other_paths():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, minimal(owned=(".", "framework")))
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("'.' alongside other paths was accepted")

    @case
    def path_cannot_be_owned_and_delegated_at_once():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, minimal(owned=("backend",), delegated_=[delegation()]))
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("a path was both owned and delegated")

    @case
    def unknown_tool_name_blocks():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, minimal(delegated_=[delegation(tools=["ruff", "ruffx"])]))
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("a typo'd tool name was accepted")

    @case
    def delegation_without_an_authority_blocks():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            entry = delegation()
            entry.pop("authority")
            write(root, minimal(delegated_=[entry]))
            try:
                load(root)
            except Blocked:
                pass
            else:
                raise AssertionError("a delegation with no authority was accepted")

    @case
    def verify_passes_when_the_authority_really_runs_the_token():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "run: ruff check backend\nrun: pytest tests/\n", encoding="utf-8")
            (root / "backend").mkdir()
            entry = delegation(tools=["ruff", "pytest"],
                               auth={"file": ".github/workflows/ci.yml",
                                     "requires": ["ruff check backend", "pytest tests/"]})
            write(root, minimal(delegated_=[entry]))
            assert verify(root) == [], verify(root)

    @case
    def verify_fails_when_the_authority_stopped_running_it():
        # This is the anti-rot rule: the delegation is only as good as the file it names.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "run: pytest tests/\n", encoding="utf-8")
            (root / "backend").mkdir()
            entry = delegation(auth={"file": ".github/workflows/ci.yml",
                                     "requires": ["ruff check backend"]})
            write(root, minimal(delegated_=[entry]))
            problems = verify(root)
            assert problems and "ruff check backend" in problems[0], problems

    @case
    def verify_fails_when_the_authority_file_is_gone():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "backend").mkdir()
            write(root, minimal(delegated_=[delegation()]))
            problems = verify(root)
            assert problems and "does not exist" in problems[0], problems

    @case
    def verify_fails_when_the_delegated_path_is_stale():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("ruff\n", encoding="utf-8")
            write(root, minimal(delegated_=[delegation()]))
            problems = verify(root)
            assert problems and "no longer exists" in problems[0], problems

    @case
    def nesting_is_respected_a_directory_named_like_a_prefix_does_not_match():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ("framework", "frameworkx"):
                (root / d).mkdir()
                (root / d / "a.py").write_text("x = 1\n", encoding="utf-8")
            write(root, minimal())
            got = files_for(root, "ruff")
            assert got == ["framework/a.py"], got

    @case
    def dot_directories_are_state_not_source():
        # `.lifecycle`/`.planning` hold runtime state; ruff does not exclude every dot-dir
        # by default and was counting 5 findings from this repo's state root as debt.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree(root)
            (root / ".lifecycle").mkdir()
            (root / ".lifecycle" / "gen.py").write_text("x = 1\n", encoding="utf-8")
            assert "lifecycle/gen.py" not in " ".join(python_files(root)), python_files(root)

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


# ── entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?",
                    choices=["check", "paths", "delegated", "count", "unjudged"])
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--tool", default="ruff", help="tool name for paths/delegated/count")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.command:
        ap.print_help()
        return 2
    if args.command in ("delegated", "count") and args.tool not in TOOLS:
        print(f"BLOCKED: unknown tool {args.tool!r}; known tools are {list(TOOLS)}",
              file=sys.stderr)
        return 2
    return {
        "check": cmd_check,
        "paths": cmd_paths,
        "delegated": cmd_delegated,
        "count": cmd_count,
        "unjudged": cmd_unjudged,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
