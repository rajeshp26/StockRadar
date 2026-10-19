#!/usr/bin/env python3
"""Emit the routing patch that makes the ``ui-designer`` agent discoverable.

WHY THIS EXISTS
===============
``opencode.json`` registers the agent and the charter defines it, but nothing in the
delegation contracts *routes* to it. ``framework/opencode/skill-routing.md`` states that
"Every delegation must consult this matrix before selecting skills", and its only UI row
routes to the Implementer:

    | UI change | `apple-ui` + `frontend-react` | Implementer | ... |   (skill-routing.md:21)

So a delegator following the contract would never select ``ui-designer``. This patch adds
the missing bindings, following how ``security-auditor`` is wired (a routing row plus
matrix rows):

    A. skill-routing.md               condition -> skill -> agent row
    B. skill-integration-matrix.md 1  role -> mandatory skills row
    C. skill-integration-matrix.md 3  artifact -> owner -> gate row
    D. gsd-sketch/SKILL.md            runtime note naming the delegate (bidirectional link)

All three target files sit under ``framework/opencode/**`` - enforcement-plane, edit-deny -
so the edits are emitted as a patch a HUMAN applies with ``git apply``, like the two before
it. This script NEVER modifies the repository.

Emits ``docs/designer-agent/ui-designer-routing.patch``.

INVARIANTS ASSERTED
===================
- every anchor occurs exactly once in its file (no accidental ambiguity)
- every edit is a pure insertion: zero removal lines in the whole diff
- inserted table rows carry the same pipe count as their table's column count
- line-ending style is detected per file and preserved (skill-*.md are CRLF,
  gsd-sketch/SKILL.md is LF - mixing them would corrupt the working tree)
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
OUT = REPO / "docs" / "designer-agent" / "ui-designer-routing.patch"

# (path, [(anchor, replacement, expected_pipe_count_or_None)])
# A pipe count applies to every inserted line that starts with "|"; None skips it.
EDITS: list[tuple[str, list[tuple[str, str, int | None]]]] = [
    (
        "framework/opencode/skill-routing.md",
        [(
            "| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |",
            "| Design direction for a UI surface is undecided (2-3 comparable mockups before a plan) | `gsd-sketch` + `frontend-react` + `apple-ui` | ui-designer | Before a screen/layout direction enters a plan; the human approval selects the variant |\n"
            "| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |",
            5,
        )],
    ),
    (
        "framework/opencode/skill-integration-matrix.md",
        [
            (
                "| security-auditor | security-audit for a scoped audit of a security-sensitive diff; technical-validation for material unknowns | skill-routing.md |",
                "| security-auditor | security-audit for a scoped audit of a security-sensitive diff; technical-validation for material unknowns | skill-routing.md |\n"
                "| ui-designer | gsd-sketch to drive variant generation; frontend-react + apple-ui as stack and design-language baseline; design/skills/ corpus as advisory craft only | skill-routing.md |",
                4,
            ),
            (
                "| audit run dir (findings.json + coverage-ledger.json) | security-auditor | reviewer, verifier | G-SANDBOX (execution), G18 (artifacts) |",
                "| audit run dir (findings.json + coverage-ledger.json) | security-auditor | reviewer, verifier | G-SANDBOX (execution), G18 (artifacts) |\n"
                "| sketch deliverables (.planning/sketches/<sketch>/ : variants, render evidence, DECISION-SHEET.md) | ui-designer | team-lead, planner, implementer | none (human approval only; not a gate outcome) |",
                5,
            ),
        ],
    ),
    (
        "framework/opencode/skills/gsd-sketch/SKILL.md",
        [(
            "<runtime_note>\n"
            "**Copilot (VS Code):** Use `vscode_askquestions` wherever this workflow calls `question`.\n"
            "</runtime_note>",
            "<runtime_note>\n"
            "**Copilot (VS Code):** Use `vscode_askquestions` wherever this workflow calls `question`.\n"
            "\n"
            "**Executor:** this workflow runs in the current session, or is delegated by team-lead to the\n"
            "`ui-designer` subagent (charter `.lifecycle/agents/ui-designer.md`), which drives this same\n"
            "workflow and stops at its human-approval gate. Neither case implements application code.\n"
            "</runtime_note>",
            None,
        )],
    ),
]


def style_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def inserted_lines(anchor: str, replacement: str, rel: str) -> list[str]:
    """Lines the replacement adds to the anchor.

    A real line diff, not a string difference: skill-integration-matrix.md carries two
    different tables (3-column and 4-column), so the pipe count each inserted row must
    match belongs to the pair that inserted it, not to the file.
    """
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
            # anchors are authored with \n; translate to the file's own style so CRLF
            # files match byte-for-byte instead of failing on \r
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
        # round-trip: undoing every insertion must restore the original byte-for-byte
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
    with tempfile.TemporaryDirectory(prefix="ui-designer-routing-") as td:
        root = Path(td)
        for side in ("OLD", "NEW"):
            (root / side).mkdir()
        for rel, info in built.items():
            for side, payload in (("OLD", info["original"]), ("NEW", info["updated"])):
                target = root / side / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                # newline="" keeps the file's own line endings untouched
                target.write_text(payload, encoding="utf-8", newline="")
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff",
             "--no-prefix", "OLD", "NEW"],
            cwd=root, capture_output=True, text=True,
        )
        # 1 = differences found; anything else means the diff itself failed
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
    """Split the diff into per-path hunks, keeping each hunk's source offset.

    The offset matters: a hunk whose context starts at line 20 must not be matched
    against line 0 of the original - that mismatch is what the fidelity check raises
    if the @@ header is skipped.
    """
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
        # the diff's added lines must be exactly the lines this script intended to insert
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
