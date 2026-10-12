#!/usr/bin/env python3
"""Negative-path and contract tests for framework/standalone_check.py.

The exit-0 path is proved by running the guard itself: it builds the wheel, installs it into a
throwaway venv, binds the reference application with `framework init`, and runs
`validate --profile app`. That is deliberate, expensive evidence and it lives with the guard.
These tests pin the cheap, deterministic half the guard must never lose - it refuses to proceed
whenever it cannot produce that evidence:

  - exit 2  an incomplete reference application is refused, not silently trimmed
  - exit 2  an unknown flag is refused with usage
  - exit 2  a --wheel that does not exist is refused
  - the guard reaches the wheel step only when the reference application is complete
  - _parse accepts --keep / --wheel PATH / --wheel=PATH and rejects everything else

ROOT is redirected onto a synthetic tree so the real repository is never staged and no wheel is
built. The module global is restored in a finally block.

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

# The reference application the guard stages: the `--profile app` self-fixture (plan 4.1).
DIRS = ("src", "tests", ".planning/contracts")
FILES = ("package.json", "vite.config.ts", "playwright.config.ts",
         "tsconfig.json", "components.json", "index.html")
OPTIONAL = ".gitattributes"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok)))
    suffix = f"   [{detail}]" if detail and not ok else ""
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{suffix}")


def build_root(base: Path, *, omit: str = "") -> Path:
    """Synthetic framework root holding the reference application. `omit` drops one required
    entry so the guard must refuse rather than trim the surface."""
    root = base / "root"
    root.mkdir(parents=True)
    for name in (*DIRS, *FILES, OPTIONAL):
        if name == omit:
            continue
        target = root / name
        if name in DIRS:
            target.mkdir(parents=True)
        else:
            target.write_text("stub\n", encoding="utf-8")
    return root


def stage(root: Path, scaffold: Path) -> tuple[list[str], list[str]]:
    original = standalone_check.ROOT
    standalone_check.ROOT = root
    try:
        scaffold.mkdir(parents=True, exist_ok=True)
        return standalone_check._stage(scaffold)
    finally:
        standalone_check.ROOT = original


def run_main(root: Path, argv: list[str]) -> tuple[int, str]:
    original = standalone_check.ROOT
    standalone_check.ROOT = root
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = standalone_check.main(argv)
    finally:
        standalone_check.ROOT = original
    return code, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="standalone-guard-"))
    try:
        print("standalone_check v2 contract")

        complete = build_root(tmp / "ok")
        staged, missing = stage(complete, tmp / "ok" / "app")
        check("complete reference application stages with nothing missing",
              missing == [], f"missing={missing}")
        check("the framework tree is never staged",
              "framework" not in staged and ".opencode" not in staged, f"staged={staged}")

        hole = build_root(tmp / "hole", omit="tests")
        _, missing = stage(hole, tmp / "hole" / "app")
        check("a missing required entry is reported, not trimmed",
              missing == ["tests"], f"missing={missing}")

        # Exit 2: incomplete reference application, refused before any build.
        code, out = run_main(hole, [])
        check("incomplete reference application -> exit 2 (BLOCKED)",
              code == 2, f"exit={code} out={out!r}")
        check("BLOCKED names the missing entry",
              "BLOCKED" in out and "tests" in out, f"out={out!r}")

        # Exit 2: unknown flag -> usage on stderr.
        code, out = run_main(complete, ["--bogus"])
        check("unknown flag -> exit 2 with usage",
              code == 2 and "usage: framework standalone" in out, f"exit={code}")

        # Exit 0: --help.
        code, out = run_main(complete, ["--help"])
        check("--help -> exit 0 and prints usage",
              code == 0 and "usage: framework standalone" in out, f"exit={code}")

        # Exit 2: complete fixture, --wheel that does not exist (reaches the wheel step).
        code, out = run_main(complete, ["--wheel", "no-such-wheel.whl"])
        check("missing --wheel -> exit 2 (BLOCKED)",
              code == 2 and "wheel not found" in out, f"exit={code} out={out!r}")

        for argv, want in ((["--keep"], (True, None)),
                           (["--wheel", "w.whl"], (False, "w.whl")),
                           (["--wheel=w.whl"], (False, "w.whl")),
                           (["--keep", "--wheel=w.whl"], (True, "w.whl"))):
            check(f"_parse({argv}) -> {want}", standalone_check._parse(argv) == want)
        for argv in (["--wheel"], ["--nope"], ["positional"]):
            check(f"_parse({argv}) -> None", standalone_check._parse(argv) is None)

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
