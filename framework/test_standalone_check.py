#!/usr/bin/env python3
"""Negative-path tests for framework/standalone_check.py.

The exit-0 path is proved by running the guard itself, which needs a real validate.py
and a full copy of the framework surface. These tests cover the two paths that make the
guard mean anything:

  - exit 2  an incomplete declared surface is refused, not silently trimmed
  - exit 1  a failing validation is reported NOT STANDALONE, never passed vacuously

A guard only ever observed to exit 0 has not been shown to work. The regression pinned
here is the accounting defect: four of five required entries plus the optional entry is
NOT a complete surface. An earlier version compared a count against len(REQUIRED) and
would have proceeded with a hole in the surface.

ROOT is redirected onto a synthetic tree so the real repository is never staged and
validate.py is never really executed. The module global is restored in a finally block.

Exit codes: 0 all checks pass | 1 a check failed.
"""
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import standalone_check

DIRS = ("framework", ".opencode", ".lifecycle")
FILES = ("opencode.json", "AGENTS.md")
OPTIONAL = ".gitattributes"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok)))
    suffix = f"   [{detail}]" if detail and not ok else ""
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{suffix}")


def build_root(base: Path, *, omit: str = "", validate_rc: int | None = None) -> Path:
    """Synthetic framework root. `omit` drops one REQUIRED entry; validate_rc, if given,
    writes a framework/validate.py stub exiting with that code."""
    root = base / "root"
    root.mkdir(parents=True)
    for name in (*DIRS, *FILES, OPTIONAL):
        if name == omit:
            continue
        if name in DIRS:
            (root / name).mkdir()
        else:
            (root / name).write_text("stub\n", encoding="utf-8")
    if validate_rc is not None:
        (root / "framework" / "validate.py").write_text(
            "import sys\n"
            "print('FAIL stub check never satisfied')\n"
            f"sys.exit({validate_rc})\n",
            encoding="utf-8",
        )
    return root


def run_guard(root: Path) -> tuple[int, str]:
    original = standalone_check.ROOT
    standalone_check.ROOT = root
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = standalone_check.main()
    finally:
        standalone_check.ROOT = original
    return code, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="standalone-guard-"))
    try:
        print("standalone_check negative paths")

        # Exit 2: one required entry absent. The optional entry is present, so this
        # also pins that an optional file cannot mask a hole in the required surface.
        code, out = run_guard(build_root(tmp / "a", omit=".lifecycle"))
        check("incomplete required surface -> exit 2 (BLOCKED)", code == 2, f"exit={code} out={out!r}")
        check("BLOCKED names the missing entry", ".lifecycle" in out, f"out={out!r}")
        check("optional entry does not mask a missing required entry", code == 2, f"exit={code}")

        # Exit 1: a complete surface whose validate.py fails must be reported, not passed.
        code, out = run_guard(build_root(tmp / "b", validate_rc=1))
        check("failing validation -> exit 1 (NOT STANDALONE)", code == 1, f"exit={code} out={out!r}")
        check("NOT STANDALONE surfaces the failing check", "FAIL stub check" in out, f"out={out!r}")

        # A complete surface that passes must still be the only path reaching exit 0.
        code, out = run_guard(build_root(tmp / "c", validate_rc=0))
        check("passing validation -> exit 0 (STANDALONE)", code == 0, f"exit={code} out={out!r}")

        failed = [n for n, ok in _results if not ok]
        print(f"\n{len(_results) - len(failed)}/{len(_results)} checks passed")
        if failed:
            print("FAILED: " + "; ".join(failed))
            return 1
        print("STANDALONE-GUARD-TESTS: PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
