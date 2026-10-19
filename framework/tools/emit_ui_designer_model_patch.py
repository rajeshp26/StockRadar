#!/usr/bin/env python3
"""Emit the follow-up plane patch that completes the ui-designer agent entry.

Why this exists: the first patch (`ui-designer.patch`) registered `ui-designer` in
`opencode.json`, but it omitted the three fields the repo's own validator requires of every
registered agent:

    framework/validate.py:1521-1526 (check [20]) asserts, for each name in EXPECTED:
      - a structurally resolvable `model`
      - a non-empty `_model_rationale`
      - an explicit `temperature`

`opencode.json` is an edit-deny enforcement-plane file, so the fields cannot be written by an
agent - they are emitted as a patch for a human to apply, exactly like the first one.

Emits `docs/designer-agent/ui-designer-model.patch`, verified by `git apply --check`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "designer-agent" / "ui-designer-model.patch"
TARGET = "opencode.json"

# The exact tail of the ui-designer entry. `"mcp": {` anchors it, so the string below
# identifies one location in the file.
_OLD = """          "git show*": "allow"
        }
      }
    }
  },
  "mcp": {"""

_NEW = """          "git show*": "allow"
        }
      },
      "model": "opencode/big-pickle",
      "temperature": 0.3,
      "_model_rationale": "Variant generation rewards breadth: every variant is throwaway and human-reviewed, so exploration variance is cheap to absorb while a homogenised shortlist costs the project a genuinely different direction."
    }
  },
  "mcp": {"""


def build() -> tuple[str, str]:
    original = (REPO / TARGET).read_text(encoding="utf-8")
    if original.count(_OLD) != 1:
        raise SystemExit(
            "expected exactly 1 anchor for the ui-designer entry, found %d"
            % original.count(_OLD)
        )
    updated = original.replace(_OLD, _NEW)

    # --- the delta must be surgical -------------------------------------------------
    before = json.loads(original)
    after = json.loads(updated)
    if before.keys() != after.keys():
        raise SystemExit("opencode.json: top-level key set changed")
    if set(before["agent"]) != set(after["agent"]):
        raise SystemExit("opencode.json: agent key set changed")
    for key in before:
        if key == "agent":
            continue
        if before[key] != after[key]:
            raise SystemExit("opencode.json: top-level key %r changed" % key)
    for name, value in before["agent"].items():
        entry = after["agent"][name]
        if name == "ui-designer":
            continue
        if entry != value:
            raise SystemExit("opencode.json: unrelated agent %r changed" % name)

    ui = after["agent"]["ui-designer"]
    for field in ("model", "temperature", "_model_rationale"):
        if field not in ui:
            raise SystemExit("ui-designer: %r still missing" % field)
    if ui["permission"] != before["agent"]["ui-designer"]["permission"]:
        raise SystemExit("ui-designer: permission envelope must not change")
    if ui["description"] != before["agent"]["ui-designer"]["description"]:
        raise SystemExit("ui-designer: description must not change")

    # the inserted fields must be the ONLY textual difference
    if updated.replace(_NEW, _OLD) != original:
        raise SystemExit("opencode.json: more changed than the intended delta")
    return original, updated


def generate(original: str, updated: str) -> str:
    with tempfile.TemporaryDirectory(prefix="ui-designer-model-") as td:
        root = Path(td)
        for side in ("OLD", "NEW"):
            (root / side).mkdir()
        (root / "OLD" / TARGET).write_text(original, encoding="utf-8", newline="")
        (root / "NEW" / TARGET).write_text(updated, encoding="utf-8", newline="")
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff",
             "--no-prefix", "OLD", "NEW"],
            cwd=root, capture_output=True, text=True,
        )
        # 1 = differences found; anything else means the diff itself failed
        if proc.returncode not in (0, 1):
            raise SystemExit("git diff failed: %s" % (proc.stderr or proc.stdout)[:400])
        if not proc.stdout.strip():
            raise SystemExit("git diff produced no output (stdout empty = failure)")
        # rewrite OLD/... NEW/... to a/... b/... (git diff --no-index leaves those prefixes)
        lines = []
        for ln in proc.stdout.splitlines(keepends=True):
            nl = "\n" if ln.endswith("\n") else ""
            body = ln[:-1] if nl else ln
            if body.startswith("diff --git OLD/"):
                body = body.replace("diff --git OLD/", "diff --git a/", 1)
                body = body.replace(" NEW/", " b/", 1)
            elif body.startswith("--- OLD/"):
                body = "--- a/" + body[len("--- OLD/"):]
            elif body.startswith("+++ NEW/"):
                body = "+++ b/" + body[len("+++ NEW/"):]
            lines.append(body + nl)
        return "".join(lines)


def parse(patch: str) -> dict:
    """Split a unified diff into paths and hunks, keeping each hunk's source offset.

    The offset matters: a hunk whose context begins at line 437 must not be matched
    against line 0 of the original. Losing it is exactly the mismatch the fidelity
    check raises, so the @@ header is parsed, not skipped.
    """
    path, is_new, hunks, cur = None, False, [], None
    for ln in patch.splitlines():
        if ln.startswith("diff --git "):
            path = ln.split(" ")[2][2:]
            is_new, cur = False, None
        elif ln.startswith("new file mode"):
            is_new = True
        elif ln.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+", ln)
            if not m:
                raise SystemExit("unparsable hunk header: %r" % ln[:60])
            cur = {"start": int(m.group(1)), "lines": []}
            hunks.append(cur)
        elif cur is not None and (not ln[:1] or ln[:1] in " +-"):
            if ln.startswith("--- ") or ln.startswith("+++ ") or ln.startswith("diff --"):
                continue
            cur["lines"].append(ln)
    if not hunks:
        raise SystemExit("patch contains no hunks")
    return {"path": path, "is_new": is_new, "hunks": hunks}


def apply_hunks(original: str, hunks: list[dict]) -> str:
    """Rebuild the post-image from context/+/- lines (independent hunk fidelity check)."""
    out, pos = [], 0
    src = original.splitlines(keepends=True)
    for hunk in hunks:
        start = hunk["start"] if hunk["start"] > 0 else 0
        if pos > start - 1:
            raise SystemExit("hunk fidelity: hunks are out of order")
        out.extend(src[pos:start - 1 if start else 0])
        pos = max(start - 1, 0)
        for ln in hunk["lines"]:
            tag, body = ln[:1], ln[1:]
            if tag not in (" ", "", "+", "-"):
                raise SystemExit("unexpected hunk line %r" % ln[:40])
            body = body.rstrip("\n")
            if tag == "+" :
                out.append(body + "\n")
                continue
            if pos + 1 > len(src) or src[pos].rstrip("\n") != body:
                raise SystemExit("hunk fidelity: mismatch at %r" % body[:60])
            if tag == "-":
                pos += 1
            else:
                out.append(src[pos])
                pos += 1
    out.extend(src[pos:])
    return "".join(out)


def main() -> int:
    original, updated = build()
    patch = generate(original, updated)
    f = parse(patch)
    if f["path"] != TARGET:
        raise SystemExit("patch touches %r, expected %r" % (f["path"], TARGET))
    if f["is_new"]:
        raise SystemExit("target must not be a new file")
    body = [l for h in f["hunks"] for l in h["lines"]]
    rebuilt = apply_hunks(original, f["hunks"])
    if rebuilt != updated:
        raise SystemExit("self-check FAILED: rebuilt opencode.json != intended")
    # The delta rewrites exactly one line (the permission closer gains a comma) and adds
    # the three required fields. Removing the old permission-close line is the only edit,
    # so the only legal removal is that line itself; anything else means git diff picked
    # up a change outside the anchor.
    removals = [l[1:] for l in body if l.startswith("-")]
    additions = [l[1:] for l in body if l.startswith("+")]
    if removals != ["      }"]:
        raise SystemExit("unexpected removals: %r" % removals)
    if len(additions) != 4:
        raise SystemExit("expected 4 added lines, got %d" % len(additions))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patch, encoding="utf-8", newline="")
    print("wrote %s (%d bytes)" % (OUT, len(patch)))
    print("hunks: %d, removed: %d, added: %d, self-check: OK"
          % (len(f["hunks"]), len(removals), len(additions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
