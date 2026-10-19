#!/usr/bin/env python3
"""Emit a single, git-apply-able patch that wires the ``ui-designer`` agent into the repo.

WHY THIS SCRIPT EXISTS
======================
The edits it emits touch enforcement-plane paths (``opencode.json`` and
``framework/opencode/**``). Agents cannot edit those paths, so this script is the
agent-side half of the change: it computes the exact edits and writes them as a unified
diff that a HUMAN applies with ``git apply``.

This script NEVER modifies the repository. It writes exactly two files under
``docs/designer-agent/``::

    ui-designer.patch     the patch
    PATCH-SUMMARY.md      per-file description + apply/verify commands

THE EDITS
=========
A. two files (the repo's two-part agent shape, see check [30] in ``framework/validate.py``):
   ``.lifecycle/agents/ui-designer.md``            the portable charter (single source)
   ``framework/opencode/agents/ui-designer.md``    thin pointer to that charter +
   OpenCode runtime bindings. The pointer body is copied from
   ``docs/designer-agent/ui-designer.md``.
B. ``opencode.json`` - append the ``"ui-designer"`` entry to the top-level ``"agent"``
   object (keeps every existing entry byte-for-byte; the entry is appended last, so the
   diff is a single hunk). Carries ``model``/``temperature``/``_model_rationale``, which
   check [20] asserts for every name in ``EXPECTED``.
C. 9 workflow files - ``./.opencode/skills/`` -> ``./.planning/skills/`` (25 sites).
   ``.opencode/**`` is an edit-deny plane path and is not a configured skill root, so the
   findings were being written where neither the agent nor the loader could use them.
D. ``sketch-wrap-up.md`` / ``spike-wrap-up.md`` / ``help/modes/full.md`` - replace the
   plane-locked ``AGENTS.md`` write and the false "auto-load" claim with "emit a routing
   suggestion; the findings are consumed by explicit glob".
E. ``framework/validate.py`` - add ``ui-designer`` to check [30] ``_ROLES30`` and check
   [1] ``EXPECTED`` so both invariants cover the new role.

WHEN TO RUN IT
==============
Against a CLEAN checkout, i.e. before the patch is applied. It derives the OLD side from
the working tree, so re-running after applying fails loudly - it reports
``ui-designer is already registered - the patch is applied`` (or, if only part of the patch
landed, a path-fix anchor that is already consumed) instead of emitting a patch that no
longer applies. That loud failure is the intended post-apply behaviour.

METHOD
======
Original and modified copies are staged in two temp trees (``a/`` and ``b/``) and diffed
with ``git diff --no-index`` so hunk generation and line endings are git's, not ours. A
self-check then re-applies every generated hunk in memory and asserts the result equals
the intended modified content before anything is written.

Run::

    python framework/tools/emit_designer_agent_patch.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "docs" / "designer-agent"
PATCH_PATH = OUT_DIR / "ui-designer.patch"
SUMMARY_PATH = OUT_DIR / "PATCH-SUMMARY.md"

# New files, staged source -> destination. The repo's agent shape is two-part
# (.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md:111; enforced by framework/validate.py:2814-2828):
# a portable charter under .lifecycle/agents/, and a thin pointer under
# framework/opencode/agents/ whose body is the pointer line.
NEW_FILES = {
    "docs/designer-agent/charter-ui-designer.md": ".lifecycle/agents/ui-designer.md",
    "docs/designer-agent/ui-designer.md": "framework/opencode/agents/ui-designer.md",
}

CONFIG = "opencode.json"

PATH_FIX_FILES = [
    "framework/opencode/gsd-core/workflows/sketch-wrap-up.md",
    "framework/opencode/gsd-core/workflows/spike-wrap-up.md",
    "framework/opencode/gsd-core/workflows/ui-phase.md",
    "framework/opencode/gsd-core/workflows/plan-phase.md",
    "framework/opencode/gsd-core/workflows/discuss-phase.md",
    "framework/opencode/gsd-core/workflows/new-project.md",
    "framework/opencode/gsd-core/workflows/sketch.md",
    "framework/opencode/gsd-core/workflows/spike.md",
    "framework/opencode/gsd-core/workflows/help/modes/full.md",
]

OLD_ROOT = "./.opencode/skills/"
NEW_ROOT = "./.planning/skills/"
EXPECTED_PATH_FIX_COUNT = 25

# --------------------------------------------------------------------------------------
# B. the opencode.json agent entry (verified against sibling entries)
# --------------------------------------------------------------------------------------

UI_DESIGNER_ENTRY = {
    "description": (
        "Designs UI and produces 2-3 throwaway HTML mockup variants for human approval, "
        "grounded in design/skills. Foreground only."
    ),
    "mode": "subagent",
    "permission": {
        "edit": {
            "*": "deny",
            ".planning/**": "allow",
            ".opencode/**": "deny",
            "opencode.json": "deny",
            "AGENTS.md": "deny",
            "framework.config.json": "deny",
            "framework/opencode/**": "deny",
            "framework/plan/**": "deny",
            "framework/testing/**": "deny",
            "framework/security/**": "deny",
        },
        "task": {"*": "deny"},
        "bash": {
            "*": "deny",
            "git status*": "allow",
            "git diff*": "allow",
            "git log*": "allow",
            "git show*": "allow",
        },
    },
    # Required by framework/validate.py check [20] (lines 1521-1526) for every name in
    # EXPECTED: a structurally resolvable `model`, a non-empty `_model_rationale`, and an
    # explicit `temperature`. `security-auditor` is the precedent for an auxiliary agent
    # that is outside resolve.AGENTS but still carries all three. The model id is not
    # profile-driven (resolve.py only knows the seven lifecycle roles), so it is pinned
    # to the same id every other entry uses. Temperature sits at 0.3 - researcher's
    # breadth value - because variants are throwaway and human-reviewed: exploration
    # variance is absorbed by the approval gate.
    "model": "opencode/big-pickle",
    "temperature": 0.3,
    "_model_rationale": (
        "Variant generation rewards breadth: every variant is throwaway and human-reviewed, "
        "so exploration variance is cheap to absorb while a homogenised shortlist costs the "
        "project a genuinely different direction."
    ),
}

# --------------------------------------------------------------------------------------
# D. prose fixes in the wrap-up workflows
# --------------------------------------------------------------------------------------

_SKETCH_STEP_OLD = '''<step name="update_claude_md">
## Update Project AGENTS.md

Add an auto-load routing line:

```
- **Sketch findings for [project]** (design decisions, CSS patterns, visual direction) \u2192 `Skill("sketch-findings-[project-dir-name]")`
```

If this routing line already exists (append mode), leave it as-is.
</step>'''

_SKETCH_STEP_NEW = '''<step name="suggest_routing_line">
## Suggest a Routing Line (do NOT edit AGENTS.md)

`AGENTS.md` is an enforcement-plane file - agents cannot write it. Do not attempt to.

Instead, print this suggestion in the completion report so the human can add it if wanted:

```
- **Sketch findings for [project]** (design decisions, CSS patterns, visual direction) \u2192 read `./.planning/skills/sketch-findings-[project-dir-name]/SKILL.md`
```

This is optional: consumers find the findings by explicit glob (`ui-phase.md:37`,
`plan-phase.md:560-561`, `discuss-phase.md:253-254`), not by the skill loader.
</step>'''

_SPIKE_STEP_OLD = '''<step name="update_claude_md">
## Update Project AGENTS.md

Add an auto-load routing line to the project's AGENTS.md (create the file if it doesn't exist):

```
- **Spike findings for [project]** (implementation patterns, constraints, gotchas) \u2192 `Skill("spike-findings-[project-dir-name]")`
```

If this routing line already exists (append mode), leave it as-is.
</step>'''

_SPIKE_STEP_NEW = '''<step name="suggest_routing_line">
## Suggest a Routing Line (do NOT edit AGENTS.md)

`AGENTS.md` is an enforcement-plane file - agents cannot write it. Do not attempt to.

Instead, print this suggestion in the completion report so the human can add it if wanted:

```
- **Spike findings for [project]** (implementation patterns, constraints, gotchas) \u2192 read `./.planning/skills/spike-findings-[project-dir-name]/SKILL.md`
```

This is optional: consumers find the findings by explicit glob (`sketch.md:135`,
`spike.md:136`), not by the skill loader.
</step>'''

PROSE_FIXES: dict[str, list[tuple[int, str, str]]] = {
    "framework/opencode/gsd-core/workflows/sketch-wrap-up.md": [
        (1, _SKETCH_STEP_OLD, _SKETCH_STEP_NEW),
        (1, "**AGENTS.md:** routing line added",
         "**AGENTS.md:** not modified (enforcement-plane file) - routing suggestion below"),
        (1, "The sketch-findings skill will auto-load when building the UI.",
         "The findings are read by explicit glob (`./.planning/skills/sketch-findings-*/SKILL.md`); "
         "they do not auto-load."),
        (1, "- [ ] Project AGENTS.md has auto-load routing line",
         "- [ ] Routing-line suggestion presented (AGENTS.md not modified - enforcement-plane file)"),
    ],
    "framework/opencode/gsd-core/workflows/spike-wrap-up.md": [
        (1, _SPIKE_STEP_OLD, _SPIKE_STEP_NEW),
        (1, "**AGENTS.md:** routing line added",
         "**AGENTS.md:** not modified (enforcement-plane file) - routing suggestion below"),
        (1, "The spike-findings skill will auto-load in future build conversations.",
         "The findings are read by explicit glob (`./.planning/skills/spike-findings-*/SKILL.md`); "
         "they do not auto-load."),
        (1, "- [ ] Project AGENTS.md has auto-load routing line",
         "- [ ] Routing-line suggestion presented (AGENTS.md not modified - enforcement-plane file)"),
    ],
    "framework/opencode/gsd-core/workflows/help/modes/full.md": [
        (2, "- Adds auto-load routing line to project AGENTS.md",
         "- Prints a routing-line suggestion for the human (AGENTS.md is enforcement-plane; not edited)"),
    ],
    # Land the new role in the executable single-source check, in the same change as the
    # charter and the pointer. Without this the [30] invariant silently stops covering the
    # agent it was written for. framework/validate.py is not a plane file, so this edit is
    # agent-legal; it rides in the patch only to keep the change atomic.
    "framework/validate.py": [
        (1,
         '_ROLES30 = ["architect", "implementer", "planner", "researcher",\n'
         '            "reviewer", "team-lead", "verifier"]',
         '_ROLES30 = ["architect", "implementer", "planner", "researcher",\n'
         '            "reviewer", "team-lead", "verifier", "ui-designer"]'),
    ],
}


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def _text(rel: str) -> str:
    """Read a repo-relative file as text with line endings preserved exactly."""
    with (REPO / rel).open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _find_object_close(s: str, open_idx: int) -> int:
    """Index of the ``}`` that closes the object whose ``{`` is at ``open_idx``."""
    depth = 0
    i = open_idx
    while i < len(s):
        c = s[i]
        if c == '"':
            i += 1
            while i < len(s):
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == '"':
                    break
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise SystemExit("open_brace: unbalanced braces from offset %d" % open_idx)


def _insert_agent_entry(s: str) -> str:
    matches = list(re.finditer(r'"agent"\s*:\s*\{', s))
    if len(matches) != 1:
        raise SystemExit(
            'opencode.json: expected exactly one top-level "agent" object, found %d'
            % len(matches)
        )
    open_idx = s.index("{", matches[0].start())
    close_idx = _find_object_close(s, open_idx)

    j = close_idx - 1
    while j > open_idx and s[j] in " \t\r\n":
        j -= 1
    if s[j] != "}":
        raise SystemExit(
            "opencode.json: unexpected agent-block shape (last non-space char %r)" % s[j]
        )

    entry = '"ui-designer": ' + json.dumps(UI_DESIGNER_ENTRY, indent=2)
    entry = "\n".join(("    " + ln) if ln else ln for ln in entry.split("\n"))

    return s[:j] + "},\n" + entry + "\n  }" + s[close_idx + 1:]


def build_modified() -> dict[str, str]:
    """Map repo-relative path -> intended new content (line endings preserved)."""
    modified: dict[str, str] = {}

    # --- B: opencode.json -------------------------------------------------------------
    original = _text("opencode.json")
    # Post-apply guard: on a clean checkout the agent is absent. If it is already present
    # the patch has been applied, and emitting a patch from that baseline would produce one
    # that no longer applies. Fail with the real cause rather than a downstream assertion
    # that reads as if an unrelated agent were tampered with.
    if "ui-designer" in json.loads(original).get("agent", {}):
        raise SystemExit(
            "opencode.json: ui-designer is already registered - the patch is applied. "
            "Regenerate from a clean checkout."
        )
    updated = _insert_agent_entry(original)
    if updated == original:
        raise SystemExit("opencode.json: insertion produced no change")

    # Hard checks: the result must parse, must add exactly one agent, and must keep the
    # other top-level keys and existing agent entries byte-identical in value.
    before = json.loads(original)
    after = json.loads(updated)
    if "ui-designer" not in after.get("agent", {}):
        raise SystemExit("opencode.json: ui-designer entry missing after insertion")
    expected_agent_keys = set(before["agent"]) | {"ui-designer"}
    if set(after["agent"]) != expected_agent_keys:
        raise SystemExit(
            "opencode.json: agent key set changed unexpectedly: %s"
            % sorted(set(after["agent"]) ^ expected_agent_keys)
        )
    for key in before:
        if key == "agent":
            continue
        if after.get(key) != before[key]:
            raise SystemExit("opencode.json: top-level key %r changed" % key)
    for key, value in before["agent"].items():
        if after["agent"][key] != value:
            raise SystemExit("opencode.json: agent %r changed" % key)

    # --- C: the path fix --------------------------------------------------------------
    total = 0
    for rel in PATH_FIX_FILES:
        text = _text(rel)
        count = text.count(OLD_ROOT)
        if count == 0:
            raise SystemExit("%s: no %r occurrence found" % (rel, OLD_ROOT))
        total += count
        modified[rel] = text.replace(OLD_ROOT, NEW_ROOT)
    if total != EXPECTED_PATH_FIX_COUNT:
        raise SystemExit(
            "path fix: expected %d occurrences, found %d"
            % (EXPECTED_PATH_FIX_COUNT, total)
        )

    # --- D: prose fixes ---------------------------------------------------------------
    for rel, pairs in PROSE_FIXES.items():
        text = modified.get(rel, _text(rel))
        for expected, old, new in pairs:
            found = text.count(old)
            if found != expected:
                raise SystemExit(
                    "%s: expected %d match(es) for %r, found %d"
                    % (rel, expected, old[:70], found)
                )
            text = text.replace(old, new)
        modified[rel] = text

    # keep opencode.json last in the diff for readability
    modified["opencode.json"] = updated
    return modified


# --------------------------------------------------------------------------------------
# patch generation via git diff --no-index over two staged trees
# --------------------------------------------------------------------------------------

def _swap_prefixed(name: str, want: str) -> str:
    """Map a temp-tree path (``OLD/...`` or ``NEW/...``) to its repo-relative a/ or b/ form."""
    if name == "/dev/null":
        return name
    for tmp in ("OLD/", "NEW/"):
        if name.startswith(tmp):
            return want + name[len(tmp):]
    return name


def _rewrite_prefixes(lines: list[str]) -> list[str]:
    """Turn ``--no-prefix`` output over the OLD/NEW trees into a standard a/ b/ patch."""
    out = []
    for ln in lines:
        nl = "\n" if ln.endswith("\n") else ""
        body = ln[:-1] if nl else ln
        if body.startswith("diff --git "):
            rest = body[len("diff --git "):]
            parts = rest.split(" ")
            if len(parts) == 2:
                body = "diff --git %s %s" % (
                    _swap_prefixed(parts[0], "a/"),
                    _swap_prefixed(parts[1], "b/"),
                )
        elif body.startswith("--- "):
            body = "--- " + _swap_prefixed(body[4:], "a/")
        elif body.startswith("+++ "):
            body = "+++ " + _swap_prefixed(body[4:], "b/")
        out.append(body + nl)
    return out


def generate_patch(modified: dict[str, str], new_files: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory(prefix="ui-designer-patch-") as td:
        root = Path(td)
        a_dir, b_dir = root / "OLD", root / "NEW"

        for rel in modified:
            (a_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            with (a_dir / rel).open("w", encoding="utf-8", newline="") as fh:
                fh.write(_text(rel))

        for rel, text in modified.items():
            (b_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            with (b_dir / rel).open("w", encoding="utf-8", newline="") as fh:
                fh.write(text)

        for dest, text in new_files.items():
            (b_dir / dest).parent.mkdir(parents=True, exist_ok=True)
            with (b_dir / dest).open("w", encoding="utf-8", newline="") as fh:
                fh.write(text)

        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff", "--no-prefix", "OLD", "NEW"],
            cwd=str(root),
            capture_output=True,
        )
        if proc.returncode not in (0, 1):
            raise SystemExit(
                "git diff --no-index failed: %s" % proc.stderr.decode("utf-8", "replace").strip()
            )
        stdout = proc.stdout.decode("utf-8")
        if not stdout.strip():
            raise SystemExit("git diff --no-index produced no output")

        return "".join(_rewrite_prefixes(stdout.splitlines(keepends=True)))


# --------------------------------------------------------------------------------------
# self-check: re-apply every hunk in memory and compare to the intended content
# --------------------------------------------------------------------------------------

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch: str) -> list[dict]:
    files: list[dict] = []
    cur: dict | None = None
    hunk: dict | None = None
    for ln in patch.splitlines(keepends=True):
        if ln.startswith("diff --git "):
            cur, hunk = {"path": None, "is_new": False, "hunks": []}, None
            files.append(cur)
            continue
        if cur is None:
            continue
        if ln.startswith("new file mode"):
            cur["is_new"] = True
        elif ln.startswith("+++ "):
            p = ln[4:].rstrip("\r\n")
            cur["path"] = p[2:] if p.startswith("b/") else p
        elif ln.startswith("@@"):
            m = _HUNK_RE.match(ln)
            if not m:
                raise SystemExit("unparsable hunk header: %r" % ln[:60])
            hunk = {
                "old_start": int(m.group(1)),
                "lines": [],
            }
            cur["hunks"].append(hunk)
        elif hunk is not None:
            if ln.startswith("\\"):
                continue
            if ln in ("\n", "\r\n"):
                ln = " " + ln
            hunk["lines"].append(ln)
    return files


def apply_hunks(original: str, hunks: list[dict]) -> str:
    src = original.splitlines(keepends=True)
    out: list[str] = []
    pos = 0
    for h in hunks:
        start = max(h["old_start"] - 1, 0)
        if start < pos:
            raise SystemExit("hunk overlap in self-check (start=%d pos=%d)" % (start, pos))
        out.extend(src[pos:start])
        pos = start
        for ln in h["lines"]:
            tag, body = ln[:1], ln[1:]
            if tag == " ":
                if pos >= len(src) or src[pos] != body:
                    raise SystemExit(
                        "context mismatch: file has %r, patch expects %r"
                        % (src[pos] if pos < len(src) else None, body)
                    )
                out.append(body)
                pos += 1
            elif tag == "-":
                if pos >= len(src) or src[pos] != body:
                    raise SystemExit(
                        "deletion mismatch: file has %r, patch expects %r"
                        % (src[pos] if pos < len(src) else None, body)
                    )
                pos += 1
            elif tag == "+":
                out.append(body)
            else:
                raise SystemExit("unexpected hunk line %r" % ln[:40])
    out.extend(src[pos:])
    return "".join(out)


def self_check(patch: str, modified: dict[str, str], new_files: dict[str, str]) -> list[str]:
    expected = dict(modified)
    expected.update(new_files)
    for f in parse_patch(patch):
        rel = f["path"]
        if rel not in expected:
            raise SystemExit("self-check: patch touches unexpected path %r" % rel)
        original = "" if f["is_new"] else _text(rel)
        got = apply_hunks(original, f["hunks"])
        if got != expected[rel]:
            raise SystemExit("self-check FAILED: rebuilt %s != intended" % rel)
    covered = sorted(f["path"] for f in parse_patch(patch))
    if covered != sorted(expected):
        missing = set(expected) - set(covered)
        raise SystemExit("self-check: patch does not cover %s" % sorted(missing))
    return covered


# --------------------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------------------

def write_summary(files: list[str], patch: str, modified: dict[str, str]) -> None:
    path_fix_rows = []
    for rel in PATH_FIX_FILES:
        n = _text(rel).count(OLD_ROOT)
        path_fix_rows.append("| `%s` | %d |" % (rel, n))
    prose_rows = []
    for rel, pairs in PROSE_FIXES.items():
        prose_rows.append("| `%s` | %d |" % (rel, len(pairs)))

    body = f"""# ui-designer wiring patch

Generated by `framework/tools/emit_designer_agent_patch.py`. Regenerate with:

```bash
python framework/tools/emit_designer_agent_patch.py
```

Patch file: `docs/designer-agent/ui-designer.patch`
Patch touches {len(files)} paths.

## Apply

```bash
git apply --verbose docs/designer-agent/ui-designer.patch
```

Preview without applying:

```bash
git apply --stat docs/designer-agent/ui-designer.patch
git apply --check docs/designer-agent/ui-designer.patch
```

## What it changes

| # | Path | Change |
|---|---|---|
| A | `.lifecycle/agents/ui-designer.md` | new file — the portable charter (single source) |
| A | `framework/opencode/agents/ui-designer.md` | new file — thin pointer to the charter + runtime bindings |
| B | `opencode.json` | appends the `"ui-designer"` entry to the top-level `"agent"` object |
| C | 9 workflow files | `./.opencode/skills/` -> `./.planning/skills/` (25 sites) |
| D | `sketch-wrap-up.md`, `spike-wrap-up.md`, `help/modes/full.md` | drop the plane-locked `AGENTS.md` write + the false "auto-load" claim |
| E | `framework/validate.py` | adds `ui-designer` to check [1] `EXPECTED` and check [30] `_ROLES30` |

Part A is two files on purpose. `framework/validate.py:2814-2828` (check [30],
DID-013 PR-E) requires every core role to have a portable charter under
`.lifecycle/agents/` **and** a thin pointer under `framework/opencode/agents/` whose body is
exactly ``Read `.lifecycle/agents/<role>.md` and act only within that charter.`` Part E adds
`ui-designer` to that executable check so the new role is bound by the same single-source
invariant as the existing seven, instead of sitting silently outside it.

### C - path fix, per file

| File | Occurrences |
|---|---|
{chr(10).join(path_fix_rows)}

## D - prose fixes (semantic - review before accepting)

| Path | Replacements |
|---|---|
{chr(10).join(prose_rows)}

`AGENTS.md` is an enforcement-plane file (`opencode.json` `edit: deny`), so the wrap-up
step that appended a routing line to it could never succeed for an agent. The patch replaces
that step with "print the suggestion in the completion report". The findings are still found
by the consumers, because they locate them by explicit glob, not by the skill loader.

**Decision: D is kept.** The `AGENTS.md` write is guaranteed to fail — `AGENTS.md` is an
enforcement-plane edit-deny path (`opencode.json:26`), so a workflow step instructing an agent
to write it is a defect, not a preference. Removing it also removes the false "auto-load"
claim: `.opencode/skills/` is neither writable nor a configured skill root, so nothing
auto-loads; consumers already locate findings by explicit glob (`ui-phase.md:37`,
`plan-phase.md:560-561`, `discuss-phase.md:253-254`), which the corrected prose states.

If you would rather keep the `AGENTS.md` write (accepting that it always errors), apply only
the A/B/C/E hunks and drop the D hunks (`framework/opencode/gsd-core/workflows/sketch-wrap-up.md`
and `spike-wrap-up.md` prose, plus `help/modes/full.md` wording). The two are semantically
independent.

## After applying

1. Restart the OpenCode session so `opencode.json` is re-read.
2. Confirm `ui-designer` appears in the spawnable subagent list and can call `question()`
   (see `docs/designer-agent/AGENT-REGISTRATION.md` §3). This is the open item U6.
3. `python framework/validate.py` — check `[30] Charter single-source conformance` must pass,
   now covering `ui-designer`.
4. `python framework/security/check_enforcement_plane.py` must exit 0.
5. `git status` should show exactly the paths in the table above.

## Hunk counts

| Path | Hunks |
|---|---|
"""
    for f in parse_patch(patch):
        body += "| `%s` | %d |\n" % (f["path"], len(f["hunks"]))

    (REPO / "docs" / "designer-agent" / "PATCH-SUMMARY.md").write_text(
        body, encoding="utf-8", newline=""
    )


# --------------------------------------------------------------------------------------

def main() -> int:
    new_files = {dest: _text(src) for src, dest in NEW_FILES.items()}
    modified = build_modified()
    patch = generate_patch(modified, new_files)
    files = self_check(patch, modified, new_files)

    out = REPO / "docs" / "designer-agent" / "ui-designer.patch"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8", newline="")
    write_summary(files, patch, modified)

    added = sum(len(f["hunks"]) for f in parse_patch(patch))
    print("wrote %s (%d bytes)" % (out, len(patch)))
    print("wrote %s" % (out.parent / "PATCH-SUMMARY.md"))
    print("paths: %d, hunks: %d, self-check: OK" % (len(files), added))
    for rel in files:
        print("  - %s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
