#!/usr/bin/env python
"""The repository's task runner.

One entry point per operation, so "how do I run the checks" has exactly one
answer, and it is the same answer in a terminal, in a runbook and in CI.

    python tasks.py            # check: lint changed files, then the unit suite
    python tasks.py lint       # ruff over files changed vs HEAD
    python tasks.py lint-all   # ruff over everything (reports baseline debt)
    python tasks.py test       # unit suite, no live stack required
    python tasks.py db-check   # contract tests against the live stack
    python tasks.py migrate <file.sql>   # apply one migration, idempotently

Why a Python script and not a Makefile: `make`, `just` and `nox` are all absent
from this project's supported environment (`Get-Command make` finds nothing), so
a Makefile would be a gate nobody can execute - the exact defect this file
closes. Python is already a hard requirement.

Gate policy, stated so it can be argued with:

* `lint` is scoped to files changed against HEAD. The repository has ~1750
  pre-existing ruff findings; a whole-tree lint gate would be permanently red and
  therefore ignored. Scoping is a ratchet: new code must be clean, existing debt
  is not fixed opportunistically inside unrelated work.
* `test` runs the whole unit suite. It is currently red on ~92 pre-existing
  failures. If `tests/known_failures.txt` exists, those node ids are deselected
  and reported as quarantine, so the gate fails only on new breakage. That file
  is deliberately absent until someone decides to quarantine: hiding 92 failures
  is a decision, not a default.
* `db-check` is separate because it needs a live stack. It is never folded into
  `check`, so a machine without the database still has a usable lint/test gate.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
QUARANTINE = BACKEND / "tests" / "known_failures.txt"


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> int:
    """Run one command from backend/, echoing it so the log shows what judged what."""
    print(f"\n$ {' '.join(argv)}", flush=True)
    merged = {**os.environ, **(env or {})}
    return subprocess.run(argv, cwd=BACKEND, env=merged).returncode


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        # Empty stdout from a failed git call means "unknown", never "nothing changed".
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def changed_python_files() -> list[str]:
    """Python files changed against HEAD, including untracked ones, as backend-relative paths."""
    paths = set(_git("diff", "--name-only", "--diff-filter=ACMR", "HEAD"))
    paths.update(_git("ls-files", "--others", "--exclude-standard"))
    files = []
    for path in sorted(paths):
        if not path.endswith(".py") or not path.startswith("backend/"):
            continue
        if (ROOT / path).is_file():
            files.append(str((ROOT / path).relative_to(BACKEND)))
    return files


def lint() -> int:
    files = changed_python_files()
    if not files:
        print("lint: no changed Python files")
        return 0
    print(f"lint: {len(files)} changed file(s)")
    return _run([sys.executable, "-m", "ruff", "check", *files])


def lint_all() -> int:
    """Whole-tree lint. Reports the pre-existing baseline; not part of `check`."""
    return _run([sys.executable, "-m", "ruff", "check", "."])


def _quarantine_args() -> list[str]:
    if not QUARANTINE.exists():
        return []
    ids = [
        line.strip()
        for line in QUARANTINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    print(f"test: quarantining {len(ids)} known failure(s) from {QUARANTINE.name}")
    args: list[str] = []
    for node_id in ids:
        args += ["--deselect", node_id]
    return args


def test() -> int:
    return _run(
        [sys.executable, "-m", "pytest", "-m", "not integration", "-q", *_quarantine_args()]
    )


def db_check() -> int:
    """Contract tests that only the running stack can prove."""
    return _run(
        [sys.executable, "-m", "pytest", "-m", "integration", "-q"],
        env={"RUN_INTEGRATION_TESTS": "1"},
    )


def migrate(name: str) -> int:
    if not name:
        print("usage: python tasks.py migrate <migration-file.sql>", file=sys.stderr)
        return 2
    return _run([sys.executable, "scripts/apply_sql_migration.py", name])


def check() -> int:
    code = lint()
    if code != 0:
        # Lint before tests: a lint failure takes seconds, the suite takes ~17 min.
        print("\ncheck: lint failed, tests not run", file=sys.stderr)
        return code
    code = test()
    print(f"\ncheck: {'PASS' if code == 0 else 'FAIL'}")
    return code


COMMANDS = {
    "check": check,
    "lint": lint,
    "lint-all": lint_all,
    "test": test,
    "db-check": db_check,
}


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    if command == "migrate":
        return migrate(argv[2] if len(argv) > 2 else "")
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"unknown task {command!r}; one of {sorted(COMMANDS)} or 'migrate'",
              file=sys.stderr)
        return 2
    return handler()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
