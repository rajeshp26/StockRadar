#!/usr/bin/env python3
"""Build patch text that `git apply` accepts, for the shapes plane emitters need.

Enforcement-plane files may not be written by an agent, so a change to them is delivered as a
patch that is checked (`git apply --check`), applied, and then verified byte-for-byte. Two
shapes cover every plane change so far:

  new_file_patch   a file that does not exist yet (a template, a generated bridge)
  modify_patch     an existing file whose content changes (a config, a plugin body)

`new_file_patch` builds the hunk directly: `git diff --no-index` needs an OLD tree containing
the file, which a new file by definition does not have. `modify_patch` does shell out, because
letting git compute context beats hand-rolling it.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def new_file_patch(rel: str, content: str) -> str:
    """A valid new-file unified diff. Paths are repo-relative and use forward slashes."""
    if not content.endswith("\n"):
        content += "\n"
    body = content.splitlines(keepends=True)
    lines = [
        "diff --git a/%s b/%s\n" % (rel, rel),
        "new file mode 100644\n",
        "--- /dev/null\n",
        "+++ b/%s\n" % rel,
        "@@ -0,0 +1,%d @@\n" % len(body),
    ]
    lines.extend("+" + ln for ln in body)
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines)


def modify_patch(rel: str, old: str, new: str) -> str:
    """A unified diff between two versions of one repo-relative file."""
    with tempfile.TemporaryDirectory(prefix="patch-util-") as td:
        root = Path(td)
        for side, text in (("OLD", old), ("NEW", new)):
            p = root / side / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="")
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff", "--no-prefix",
             "OLD", "NEW"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode not in (0, 1):
            raise SystemExit("git diff failed: " + (proc.stderr or proc.stdout)[:400])
        if not proc.stdout.strip():
            raise SystemExit("git diff produced empty stdout for %s" % rel)

    lines = []
    for ln in proc.stdout.splitlines(keepends=True):
        nl = "\n" if ln.endswith("\n") else ""
        body = ln[:-1] if nl else ln
        if body.startswith("diff --git "):
            body = "diff --git a/%s b/%s" % (rel, rel)
        elif body.startswith("--- OLD/"):
            body = "--- a/" + body[len("--- OLD/"):]
        elif body.startswith("+++ NEW/"):
            body = "+++ b/" + body[len("+++ NEW/"):]
        lines.append(body + nl)
    return "".join(lines)
