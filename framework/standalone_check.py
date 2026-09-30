#!/usr/bin/env python3
"""Prove the framework stands alone: validate it in a scaffold holding only its own surface.

A green validate.py in a working project is not evidence of distribution. The host app's
files, its root .gitignore, and accumulated .planning state can each mask a missing
dependency or a hardcoded path, so the only run that can fail on them is one that has none
of them. That is the run this performs.

Exit codes: 0 standalone | 1 not standalone | 2 scaffold incomplete or unusable.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_TIMEOUT_S = 1800

REQUIRED = ("framework", ".opencode", ".lifecycle", "opencode.json", "AGENTS.md")
OPTIONAL = (".gitattributes",)

_IGNORED = shutil.ignore_patterns(".manifest", "__pycache__", "*.pyc", "node_modules")


def _stage(scaffold: Path) -> tuple[list[str], list[str]]:
    staged, missing = [], []
    for name in REQUIRED:
        src = ROOT / name
        if not src.exists():
            missing.append(name)
        elif src.is_dir():
            shutil.copytree(src, scaffold / name, ignore=_IGNORED)
            staged.append(name)
        else:
            shutil.copy2(src, scaffold / name)
            staged.append(name)
    for name in OPTIONAL:
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, scaffold / name)
            staged.append(name)
    return staged, missing


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="standalone-"))
    scaffold = tmp / "scaffold"
    scaffold.mkdir()
    try:
        staged, missing = _stage(scaffold)
        if missing:
            print("BLOCKED: framework surface incomplete: " + ", ".join(sorted(missing)))
            return 2
        subprocess.run(["git", "init", "-q"], cwd=scaffold, check=False)
        print("scaffold: " + ", ".join(staged))
        try:
            r = subprocess.run([sys.executable, "framework/validate.py",
                                "--profile", "framework"], cwd=scaffold,
                               capture_output=True, text=True, timeout=VALIDATE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            print(f"BLOCKED: validate.py exceeded {VALIDATE_TIMEOUT_S}s in a bare scaffold")
            return 2
        body = [ln for ln in r.stdout.splitlines() if ln.strip()]
        for ln in body[-2:]:
            print("  " + ln.strip())
        if r.returncode != 0:
            for ln in body:
                if ln.strip().startswith("FAIL"):
                    print("  " + ln.strip())
            print("NOT STANDALONE: framework needs something it does not declare")
            return 1
        print("STANDALONE: framework validates holding only its own surface")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
