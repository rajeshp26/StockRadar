#!/usr/bin/env python3
"""sync_to_agentic.py - one-way mirror of the framework tree into the agentic-lifecycle repo.

WHY
---
StockerPro is the development home. `agentic-lifecycle` is the published
distribution repository: it is a *pruned projection* of StockerPro (the same
tree with the application directories removed). This tool regenerates that
projection deterministically and then proves the result by running the
framework suites in BOTH repositories.

MODEL (decided 2026-10-13): one-way artifact.
  StockerPro  --(this tool)-->  agentic-lifecycle
Nothing is pulled back. Anything edited directly in agentic-lifecycle inside
scope will be overwritten on the next run - by design.

SCOPE
-----
Default scope is the framework surface: `framework/`, `opencode.json`,
`AGENTS.md`. StockerPro's `framework/` and agentic's `framework/` are the same
git tree, so this can never carry application code. Widen with --include (e.g.
--include .lifecycle) or narrow with --exclude. The application-only
top-level directories (backend, web, mobile, ...) are a hard guard, never scope.

The tool copies COMMITTED blobs (git cat-file blob <rev>:<path>), which are
line-ending normalised by .gitattributes. This is the transfer that was proven
byte-for-byte identical in the DID-016/017 port; it handles empty files and
BOMs correctly. Never copy working-tree bytes - unconverted CRLF fakes a diff.

USAGE
-----
  python framework/tools/sync_to_agentic.py --check     # dry run, report only
  python framework/tools/sync_to_agentic.py             # apply + verify both repos
  python framework/tools/sync_to_agentic.py --no-verify # apply only
  python framework/tools/sync_to_agentic.py --commit    # apply, then commit in agentic

The target repo is taken from --agentic, else $AGENTIC_LIFECYCLE_REPO, else a
few sibling defaults. This tool never pushes; pushing stays a human action.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The application-only top-level entries. These exist in StockerPro and must
# NEVER be mirrored into the distribution repo. Guard, not scope.
APP_ONLY = {".idx", "backend", "mobile", "web"}

# The framework surface mirrored by default. StockerPro's `framework/` and
# agentic's `framework/` are the SAME tree (verified), so it can never carry
# application code; opencode.json + AGENTS.md are the root framework files.
# `.lifecycle/agents` carries the agent charters that the thin pointers in
# framework/opencode/agents/ resolve to. The advisory design-skill corpus the
# ui-designer agent reads now lives at framework/design/skills, so it travels
# with `framework` and needs no separate entry.
INCLUDE_DEFAULT = ["framework", "opencode.json", "AGENTS.md", ".lifecycle/agents"]

# Paths the distribution repo owns itself, or that carry application content.
# `docs/` is excluded because StockerPro holds ~90 *application* design docs
# that are not part of the distribution - mirroring the directory would leak
# them. `.github` has divergent CI; `.gitignore`/`pyproject.toml` are the
# distribution repo's own config. The sync tool itself stays source-side: its
# job is to publish FROM StockerPro, so it does not belong in the artifact.
#
# `framework/quality/baseline.json` is per-repository STATE, not mechanism. It
# records the findings of one repository's code; mirroring it would hand the
# target a budget sized for someone else's debt, which is worse than no budget
# at all (it silently permits findings that do not exist there). The module and
# the README are mirrored; each repo generates its own baseline with
# `python3 framework/tools/lint_budget.py update --allow-increase --reason ...`.
#
# `framework/gates/scope.json` is the same class of thing: it names THIS
# repository's layout, the authorities inside it, and the tokens that prove those
# authorities still run what is claimed. Mirrored to a repo without a `backend/`
# it would either fail (stale path) or, worse, describe a boundary that does not
# exist. The mechanism (`gate_scope.py`, the gate, the README) is mirrored; the
# contract is drawn per repository.
EXCLUDE_DEFAULT = [
    ".gitignore", "pyproject.toml", ".github", ".planning",
    "framework/tools/sync_to_agentic.py",
    "framework/quality/baseline.json",
    "framework/gates/scope.json",
]

AGENTIC_CANDIDATES = (
    os.environ.get("AGENTIC_LIFECYCLE_REPO", ""),
    r"C:\Project\agentic-lifecycle",
    str(REPO_ROOT.parent / "agentic-lifecycle"),
    str(REPO_ROOT.parent.parent / "agentic-lifecycle"),
)

VERIFY_COMMANDS = (
    (["python", "-m", "pytest", "framework/plan", "framework/testing", "-q"], "pytest framework/plan framework/testing"),
    (["python", "framework/validate.py", "--profile", "framework"], "validate --profile framework"),
    (["python", "framework/security/check_enforcement_plane.py"], "check_enforcement_plane"),
)


# --------------------------------------------------------------------------- #
# git helpers
# --------------------------------------------------------------------------- #

def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def ls_tree(repo: Path, rev: str) -> dict[str, str]:
    """Map repo-relative path -> blob sha for every file in rev."""
    r = git(repo, "ls-tree", "-r", rev)
    if r.returncode != 0:
        sys.exit("error: git ls-tree failed in %s: %s" % (repo, r.stderr.strip()))
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        meta, _, path = line.partition("\t")
        out[path] = meta.split()[2]
    return out


def blob(repo: Path, rev: str, path: str) -> bytes:
    r = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", "%s:%s" % (rev, path)],
        capture_output=True,
    )
    if r.returncode != 0:
        sys.exit("error: cannot read %s:%s" % (rev, path))
    return r.stdout


def worktree_blob_hash(repo: Path, path: str) -> str | None:
    """Hash a working-tree file the way a commit would store it (clean filters)."""
    if not (repo / path).is_file():
        return None
    r = git(repo, "hash-object", "--path=%s" % path, path)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def top(path: str) -> str:
    return path.split("/", 1)[0]


# --------------------------------------------------------------------------- #
# scope + diff
# --------------------------------------------------------------------------- #

def resolve_agentic(explicit: str | None) -> Path:
    if explicit:
        candidates = (explicit,)
    else:
        candidates = AGENTIC_CANDIDATES
    for c in candidates:
        if c and (Path(c) / ".git").exists():
            return Path(c).resolve()
    sys.exit(
        "error: could not locate the agentic-lifecycle clone.\n"
        "       pass --agentic PATH or set AGENTIC_LIFECYCLE_REPO."
    )


def in_scope(path: str, include, exclude) -> bool:
    """Prefix-scoped membership: a path is in scope if it is (under) an include
    entry and not (under) an exclude entry."""
    if any(path == e or path.startswith(e + "/") for e in exclude):
        return False
    return any(path == s or path.startswith(s + "/") for s in include)


def compute_scope(stock, agentic, include, exclude):
    include = sorted(set(INCLUDE_DEFAULT) | set(include))
    exclude = sorted(set(EXCLUDE_DEFAULT) | set(exclude))

    guard = {top(s) for s in include} & APP_ONLY
    if guard:
        sys.exit("REFUSING: application-only paths would enter scope: %s" % sorted(guard))

    stock_top = {top(p) for p in stock}
    agentic_top = {top(p) for p in agentic}
    shared = stock_top & agentic_top

    desired = {p: s for p, s in stock.items() if in_scope(p, include, exclude)}
    agentic_paths = set(agentic)
    included_tops = {top(s) for s in include}
    out_of_scope = sorted(t for t in shared if t not in included_tops)
    return (include, exclude, desired, agentic_paths,
            sorted(stock_top - agentic_top), sorted(agentic_top - stock_top), out_of_scope)


def compute_changes(agentic, desired, include, exclude, agentic_paths):
    changes = []  # (kind, path)
    for p in sorted(desired):
        have = worktree_blob_hash(agentic, p)
        if have is None:
            changes.append(("add", p))
        elif have != desired[p]:
            changes.append(("mod", p))
    for p in sorted(agentic_paths):
        if in_scope(p, include, exclude) and p not in desired and (agentic / p).is_file():
            changes.append(("del", p))
    return changes


def apply_changes(stock, agentic, changes, rev):
    written = deleted = 0
    for kind, p in changes:
        dst = agentic / p
        if kind in ("add", "mod"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob(stock, rev, p))
            written += 1
        else:
            dst.unlink()
            deleted += 1
    return written, deleted


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #

def verify(repo: Path) -> list[tuple[str, bool, int]]:
    """Run the verification commands in `repo` and report what failed.

    A verification step that can fail without naming the check is a defect in the
    instrument: it turns a 15-minute run into an unattributable exit code. MEASURED
    (2026-11-11): this function printed only the last line of output, so
    `validate --profile framework exit=1` in the source repo could not be diagnosed
    at all -- the failing check's name had been discarded. So a failure now prints
    the lines that look like failures and persists the full output to a log whose
    path is named, while a pass still costs exactly one line.
    """
    env = dict(os.environ, PYTHONUTF8="1")
    results = []
    log_dir = None
    for argv, label in VERIFY_COMMANDS:
        r = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        passed = r.returncode == 0
        results.append((label, passed, r.returncode))
        text = r.stdout or ""
        if r.stderr:
            text = text + "\n" + r.stderr if text else r.stderr
        if passed:
            tail = text.strip().splitlines()
            if tail:
                print("    %s" % tail[-1].strip()[:110])
            continue

        print("    FAILED: %s (exit=%d)" % (label, r.returncode))
        for line in _failure_lines(text):
            print("      %s" % line.strip()[:160])
        if log_dir is None:
            log_dir = Path(tempfile.mkdtemp(prefix="sync-verify-"))
        log = log_dir / ("%s.log" % "".join(
            c if c.isalnum() else "-" for c in label).strip("-"))
        log.write_text(text, encoding="utf-8")
        print("      full output: %s" % log)
    return results


def _failure_lines(text: str, limit: int = 20) -> list[str]:
    """The lines worth reading when a verification command fails.

    Prefers lines that name a verdict (`FAIL`, `FAILURE(S)`, `BLOCKED`, a traceback,
    an error) over a bare tail: the failing check is what the reader needs, and the
    tail of a 900-line validator run is a summary, not a cause. Falls back to the
    tail when nothing matches, so an unlabelled crash is still shown.
    """
    lines = text.splitlines()
    marked = [ln for ln in lines
              if any(m in ln for m in ("FAIL", "FAILURE", "BLOCKED", "Traceback",
                                       "Error", "error:", "ERROR"))]
    return marked[:limit] if marked else lines[-limit:]



def print_report(repo: Path, results: list[tuple[str, bool, int]]) -> bool:
    ok = all(passed for _, passed, _ in results)
    for label, passed, code in results:
        print("    [%s] %-34s exit=%d" % ("PASS" if passed else "FAIL", label, code))
    return ok


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Mirror StockerPro's framework tree into agentic-lifecycle.")
    ap.add_argument("--stock", default=str(REPO_ROOT), help="source repo (default: this repo)")
    ap.add_argument("--agentic", default=None, help="target clone (default: $AGENTIC_LIFECYCLE_REPO or siblings)")
    ap.add_argument("--rev", default="HEAD", help="source revision to mirror (default HEAD)")
    ap.add_argument("--include", action="append", default=[], help="top-level path to ADD to scope (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="top-level path to REMOVE from scope (repeatable)")
    ap.add_argument("--check", action="store_true", help="dry run: report changes, write nothing")
    ap.add_argument("--no-verify", action="store_true", help="skip running the suites")
    ap.add_argument("--commit", action="store_true", help="commit in agentic after applying (never pushes)")
    args = ap.parse_args()

    stock = Path(args.stock).resolve()
    agentic = resolve_agentic(args.agentic)
    if stock == agentic:
        sys.exit("error: source and target are the same repository")

    stock_tree = ls_tree(stock, args.rev)
    agentic_tree = ls_tree(agentic, "HEAD")

    include, exclude, desired, agentic_paths, app_only, agentic_only, out_of_scope = compute_scope(
        stock_tree, agentic_tree, args.include, args.exclude)

    print("source : %s @ %s" % (stock, args.rev))
    print("target : %s" % agentic)
    print("scope  : %s  ->  %d files" % (", ".join(include), len(desired)))
    print("excluded (target-owned/app): %s" % ", ".join(exclude))
    if app_only:
        print("excluded (application-only): %s" % ", ".join(app_only))
    if out_of_scope:
        print("shared but out of scope:     %s" % ", ".join(out_of_scope))
    if agentic_only:
        print("target-only (untouched):     %s" % ", ".join(agentic_only))
    print()

    changes = compute_changes(agentic, desired, include, exclude, agentic_paths)

    if not changes:
        print("in sync: 0 files to change")
    else:
        counts = {k: sum(1 for c, _ in changes if c == k) for k in ("add", "mod", "del")}
        print("changes: %d add, %d mod, %d del" % (counts["add"], counts["mod"], counts["del"]))
        for kind, p in changes[:60]:
            print("  %-4s %s" % (kind, p))
        if len(changes) > 60:
            print("  ... and %d more" % (len(changes) - 60))
    print()

    if args.check:
        if changes:
            print("DRY RUN - nothing written. Re-run without --check to apply.")
            return 1
        print("DRY RUN - already in sync.")
        return 0

    if changes:
        written, deleted = apply_changes(stock, agentic, changes, args.rev)
        print("applied: %d files written, %d deleted" % (written, deleted))
        status = git(agentic, "status", "--porcelain")
        print("agentic working tree now:")
        for line in status.stdout.splitlines()[:40]:
            print("  " + line)
        print()

    ok = True
    if not args.no_verify:
        for label, repo in (("StockerPro (source)", stock), ("agentic-lifecycle (target)", agentic)):
            print("verify %s:" % label)
            ok = print_report(repo, verify(repo)) and ok
        print()

    if args.commit and changes:
        ident = git(stock, "config", "user.name").stdout.strip()
        email = git(stock, "config", "user.email").stdout.strip()
        r = git(agentic, "add", "-A")
        if r.returncode == 0:
            r = git(agentic, "-c", "user.name=%s" % ident, "-c", "user.email=%s" % email,
                    "commit", "-m", "chore(framework): sync from StockerPro")
        print("commit: %s" % ("ok" if r.returncode == 0 else r.stderr.strip()))
        print()

    if changes and not args.commit:
        print("next: push the source yourself, then publish the target:")
        print("  git -C \"%s\" push origin main" % stock)
        print("  git -C \"%s\" add -A && git -C \"%s\" commit -m \"chore(framework): sync from StockerPro\"" % (agentic, agentic))
        print("  git -C \"%s\" push origin main" % agentic)

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
