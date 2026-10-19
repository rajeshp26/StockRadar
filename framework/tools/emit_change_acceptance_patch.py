#!/usr/bin/env python3
"""Emit the *enforcement* patch for the two change-acceptance bindings.

RELATIONSHIP TO THE FIRST PATCH
===============================
The first patch added the two policy blocks themselves and was APPLIED on 2026-10-19:

    A. "Prompt shape (Goal / Context / Validation)" -> delegation-protocol.md
    B. "Merge acceptance tiers"                     -> agents/team-lead.md

Those two edits are deliberately NOT in this script. They are already part of the working
tree, so re-running an emitter that still carried them would insert a SECOND copy of each
section - the anchor would still match exactly once and nothing would catch the duplicate.

WHAT THIS PATCH ADDS
====================
Both blocks are instruction-level: nothing executable fails if a later edit deletes them.
This patch closes that gap, plus wires the merge tier into the one workflow step that
actually asks the question:

    C. gsd-ship/SKILL.md   bind the tier table to the workflow's `optional_review` step,
                           so the Skip/Self/Request review choice is decided, not asked.
    D. validate.py [9]     assert the delegation-protocol carries the prompt shape
    E. validate.py [8]     assert team-lead carries the merge acceptance tiers

WHY (C) IS A SKILL NOTE AND NOT AN EDIT TO ``ship.md``
=====================================================
``framework/opencode/gsd-core/workflows/ship.md`` is vendored GSD-core: it carries upstream
issue references (#2589, #1950, ADR-2008) and the repo already tracks local upstream
divergence separately in ``gsd-core-upstream.patch`` (which patches ``bin/install.js``).
Adding local policy to the vendored workflow creates a divergence the next upstream pull
must rebase. The local wrapper skill is where this repo's policy about that workflow
belongs - the same pattern used for the ``ui-designer`` executor note on ``gsd-sketch``.

WHY (D)/(E) ARE A PATCH AND NOT A DIRECT EDIT
=============================================
``framework/validate.py`` is NOT enforcement-plane, but it currently carries uncommitted
work from a concurrent session (the claims-ledger isolation work in suites 22/24/26/28).
Editing it now would mix two authors' in-flight changes. A patch lets the human apply this
hunk after that session commits - and the emitter re-reads the file, so regenerate it
against the committed tree immediately before applying.

Emits ``docs/change-acceptance/change-acceptance-enforcement.patch``.

INVARIANTS ASSERTED
===================
- every anchor occurs exactly once in its file (no accidental ambiguity)
- every edit is a pure insertion: zero removal lines in the whole diff
- inserted table rows carry the same pipe count as their table's column count
- line-ending style is detected per file and preserved
- the emitted hunks, re-applied independently, reproduce the intended post-image exactly
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "change-acceptance" / "change-acceptance-enforcement.patch"

SHIP_NOTE = """<runtime_note>
**Merge review is decided by the change class, not asked.** The workflow's `optional_review`
step offers Skip / Self-review / Request review. Answer it from the merge acceptance tiers in
`framework/opencode/agents/team-lead.md` - read the tier from the actual diff and re-derive it
like impact; a lower tier never overrides a higher one:

- tier 1 -> Skip or Self-review. CI green plus the recorded verifier evidence is the acceptance.
- tier 2 -> Request review. An identity that did not author the change reviews before merge.
- tier 3 -> do not merge until the security or H2 human gate is recorded.
- tier 4 -> do not merge here. G8 part B hands a recommendation to H3, which decides.

An identity never merges or certifies its own work at tier 2 or above.

This binding lives in the wrapper skill and not in `gsd-core/workflows/ship.md`: that file is
vendored GSD-core, and local divergence from upstream is a rebase cost paid on every pull.
</runtime_note>"""

# validate.py - suite [8] (human gates): the tiers bind H1/H2/H3 to the merge decision.
MERGE_TIER_CHECK = '''
# The merge tiers bind the H1/H2/H3 line to the *merge* decision (the /gsd-ship review
# prompt). Without them that question has no framework answer and is settled by
# preference. Instruction-level: this asserts the policy is present, not that an
# agent followed it.
_tl_mg = Path("framework/opencode/agents/team-lead.md").read_text(encoding="utf-8")
check("team-lead defines merge acceptance tiers",
      "Merge acceptance tiers" in _tl_mg and "never a self-merge" in _tl_mg,
      "which classes need independent review or an H gate before merge is policy, not preference")'''

# validate.py - suite [9] (rules loaded): the shape makes the contract fields authorable.
PROMPT_SHAPE_CHECK = '''
# The prompt shape is what makes the contract fields authorable: a prompt missing Goal,
# Context or Validation is not ready to dispatch. Without this the rule file can lose the
# shape silently and "a vague prompt" regains no shape to fail against.
_dp_shape = Path("framework/opencode/rules/delegation-protocol.md").read_text(encoding="utf-8")
check("delegation-protocol carries the prompt shape",
      "Prompt shape (Goal / Context / Validation)" in _dp_shape
      and "not ready to dispatch" in _dp_shape,
      "a delegation prompt with no Validation is not ready to dispatch")'''

# (path, [(anchor, replacement, expected_pipe_count_or_None)])
# A single-line anchor keeps the match line-ending agnostic; the replacement ends with
# that same anchor line, so the diff is a pure insertion at the anchor.
EDITS: list[tuple[str, list[tuple[str, str, int | None]]]] = [
    (
        "framework/opencode/skills/gsd-ship/SKILL.md",
        [(
            "Execute the ship workflow from @C:/Project/StockerPro/StockerPro/framework/opencode/gsd-core/workflows/ship.md end-to-end.",
            "Execute the ship workflow from @C:/Project/StockerPro/StockerPro/framework/opencode/gsd-core/workflows/ship.md end-to-end.\n\n" + SHIP_NOTE,
            None,
        )],
    ),
    (
        "framework/validate.py",
        [
            (
                'check("browser missing driver is unverifiable", "report_unverifiable" in prof)',
                'check("browser missing driver is unverifiable", "report_unverifiable" in prof)' + MERGE_TIER_CHECK,
                None,
            ),
            (
                'check("do-not-invoke rule present", "merely because it exists" in ag)',
                'check("do-not-invoke rule present", "merely because it exists" in ag)' + PROMPT_SHAPE_CHECK,
                None,
            ),
        ],
    ),
]


def style_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def inserted_lines(anchor: str, replacement: str, rel: str) -> list[str]:
    """Lines the replacement adds to the anchor (a real line diff, not a string diff)."""
    a, b = anchor.split("\n"), replacement.split("\n")
    opcodes = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    out: list[str] = []
    for tag, i1, _i2, j1, j2 in opcodes:
        if tag == "insert":
            out.extend(b[j1:j2])
        elif tag in ("replace", "delete"):
            raise SystemExit(f"{rel}: not a pure insertion - {tag} at anchor line {i1}")
    if not out:
        raise SystemExit(f"{rel}: replacement inserts nothing")
    return out


def build() -> dict[str, dict]:
    """repo-relative path -> {original, post-image, inserted lines, pipe expectations}"""
    built: dict[str, dict] = {}
    for rel, pairs in EDITS:
        original = (REPO / rel).read_text(encoding="utf-8")
        style = style_of(original)
        current = original
        inserted: list[str] = []
        pipes: list[int | None] = []
        for anchor, replacement, expect in pairs:
            old = anchor.replace("\n", style)
            new = replacement.replace("\n", style)
            hits = current.count(old)
            if hits != 1:
                raise SystemExit(f"{rel}: anchor occurs {hits} times, expected exactly 1")
            if new == old:
                raise SystemExit(f"{rel}: replacement equals anchor")
            added = inserted_lines(anchor, replacement, rel)
            current = current.replace(old, new)
            inserted.extend(line.rstrip("\r") for line in added)
            pipes.extend([expect] * len(added))
        restored = current
        for anchor, replacement, _ in reversed(pairs):
            restored = restored.replace(
                replacement.replace("\n", style), anchor.replace("\n", style)
            )
        if restored != original:
            raise SystemExit(f"{rel}: insertion is not reversible - more changed than intended")
        built[rel] = {
            "original": original,
            "updated": current,
            "inserted": inserted,
            "pipes": pipes,
        }
    return built


def generate(built: dict[str, dict]) -> str:
    with tempfile.TemporaryDirectory(prefix="change-acceptance-enf-") as td:
        root = Path(td)
        for side in ("OLD", "NEW"):
            (root / side).mkdir()
        for rel, info in built.items():
            for side, payload in (("OLD", info["original"]), ("NEW", info["updated"])):
                target = root / side / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(payload, encoding="utf-8", newline="")
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff",
             "--no-prefix", "OLD", "NEW"],
            cwd=root, capture_output=True, text=True,
        )
        if proc.returncode not in (0, 1):
            raise SystemExit("git diff failed: %s" % (proc.stderr or proc.stdout)[:400])
        if not proc.stdout.strip():
            raise SystemExit("git diff produced empty stdout (empty output is a failure)")
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
    files: dict[str, dict] = {}
    path, cur = None, None
    for ln in patch.splitlines():
        if ln.startswith("diff --git "):
            path = ln.split(" ")[2][2:]
            files.setdefault(path, {"hunks": []})
            cur = None
        elif ln.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+", ln)
            if not m:
                raise SystemExit(f"unparsable hunk header: {ln[:60]!r}")
            cur = {"start": int(m.group(1)), "lines": []}
            files[path]["hunks"].append(cur)
        elif cur is not None and ln[:1] in (" ", "+", "-"):
            cur["lines"].append(ln)
    if not files:
        raise SystemExit("patch contains no files")
    return files


def apply_hunks(original: str, hunks: list[dict]) -> str:
    """Rebuild the post-image from context/+/- lines - independent hunk fidelity check."""
    out: list[str] = []
    src = original.splitlines(keepends=True)
    pos = 0
    style = style_of(original)
    for hunk in hunks:
        start = hunk["start"] if hunk["start"] > 0 else 0
        if pos > start - 1:
            raise SystemExit("hunk fidelity: hunks out of order")
        out.extend(src[pos:(start - 1) if start else 0])
        pos = max(start - 1, 0)
        for ln in hunk["lines"]:
            tag, body = ln[:1], ln[1:].rstrip("\r\n")
            if tag not in (" ", "+", "-"):
                raise SystemExit(f"unexpected hunk line {ln[:40]!r}")
            if tag == "+":
                out.append(body + style)
                continue
            if pos + 1 > len(src) or src[pos].rstrip("\r\n") != body:
                raise SystemExit(f"hunk fidelity: context mismatch at {body[:60]!r}")
            if tag == "-":
                pos += 1
            else:
                out.append(src[pos])
                pos += 1
    out.extend(src[pos:])
    return "".join(out)


def main() -> int:
    built = build()
    patch = generate(built)
    files = parse(patch)

    if set(files) != set(built):
        raise SystemExit(f"patch touches {sorted(files)}, expected {sorted(built)}")

    total_removed = total_added = 0
    for rel, info in files.items():
        spec = built[rel]
        original, updated = spec["original"], spec["updated"]
        body = [l for h in info["hunks"] for l in h["lines"]]
        removals = [l[1:] for l in body if l.startswith("-")]
        additions = [l[1:].rstrip("\r") for l in body if l.startswith("+")]
        if removals:
            raise SystemExit(f"{rel}: expected a pure insertion, found removals: {removals!r}")
        if additions != spec["inserted"]:
            raise SystemExit(
                f"{rel}: added lines differ from intended insertion.\n"
                f"  actual:   {additions!r}\n  intended: {spec['inserted']!r}"
            )
        for line, expect in zip(spec["inserted"], spec["pipes"]):
            if line.startswith("|") and expect is not None and line.count("|") != expect:
                raise SystemExit(
                    f"{rel}: table row has {line.count('|')} pipes, table needs {expect}: {line[:70]!r}"
                )
        rebuilt = apply_hunks(original, info["hunks"])
        if rebuilt != updated:
            raise SystemExit(f"self-check FAILED: rebuilt {rel} != intended post-image")
        total_removed += len(removals)
        total_added += len(additions)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patch, encoding="utf-8", newline="")
    print(f"wrote {OUT} ({len(patch)} bytes)")
    print(
        f"files: {len(files)}, hunks: {sum(len(v['hunks']) for v in files.values())}, "
        f"removed: {total_removed}, added: {total_added}, self-check: OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
