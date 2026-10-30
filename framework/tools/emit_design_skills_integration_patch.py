#!/usr/bin/env python3
"""Emit the design-skills integration patch for the enforcement plane.

WHY THIS EXISTS
===============
`designmotion-design` was added under `framework/opencode/skills/` but nothing routes to it,
`apple-ui` / `frontend-react` cross-link to nothing, and the imported craft corpus is invisible
because `design/skills` is not in `skills.paths`. The previous attempt wrote a literal git diff
into `framework/opencode/skills/ROUTES.md` instead of applying one, and that file duplicated
`framework/opencode/skill-routing.md`, the authoritative router.

This patch finishes the integration:

    A. opencode.json                          skills.paths += design/skills (discoverable)
    B. skill-routing.md                       designmotion row, advisory-corpus row, precedence
    C. skill-integration-matrix.md            role bindings, route, verification method
    D. apple-ui/SKILL.md                      pairing + precedence pointer
    E. frontend-react/SKILL.md                behaviour-layer pointer
    F. designmotion-design/SKILL.md           repo-real pointers (no muse, no phantom skills)
    G. designmotion-design/skill.yaml       DELETED (muse metadata, says include_in_prompt:false)
    H. ROUTES.md                            DELETED (corrupted diff, duplicate router)

Every target is plane-locked (edit-deny), so this script NEVER modifies the repository; it writes
a patch a HUMAN applies with `git apply`.

Emits `docs/designer-agent/design-skills-integration.patch`.

INVARIANTS ASSERTED
===================
- every anchor occurs exactly once after line-ending normalization (no ambiguity)
- replacements are reversible: undoing them restores the original byte-for-byte
- each file's own line endings are preserved (CRLF files are detected from bytes, not read_text,
  which would normalize them away)
- the emitted hunks, re-applied independently from the @@ offset, reproduce the post-image exactly
- every `diff --git` header is `a/<path> b/<path>` with both sides naming the same path
- deletions are real deletions (no post-image), not empty files
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "designer-agent" / "design-skills-integration.patch"

# path -> list of (anchor, replacement), or None for "delete this file"
EDITS: dict[str, list[tuple[str, str]] | None] = {}

EDITS["opencode.json"] = [(
    '  "skills": {\n'
    '    "paths": [\n'
    '      "framework/opencode/skills"\n'
    '    ]\n'
    '  },',
    '  "skills": {\n'
    '    "paths": [\n'
    '      "framework/opencode/skills",\n'
    '      "design/skills"\n'
    '    ]\n'
    '  },',
)]

EDITS["framework/opencode/skill-routing.md"] = [
    (
        "| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |",
        "| UI surface introduces or changes a pattern/system (screen, form, table, navigation, feedback surface, overlay, motion) | `designmotion-design` + `apple-ui` | Implementer / Reviewer | State coverage, feedback timing, failure modes, component-system choice; `apple-ui` still wins on finance tokens, motion values and data-viz |\n"
        "| Design craft reference outside the finance design system (CSS effect, named UX law, animation recipe, library comparison) | `design/skills/` corpus (advisory): `ania-kubow-design` for CSS, `uiux-design-foundations` for principles | any role, on demand | Read-only craft reference, never mandatory and never evidence (AGENTS.md > agent definition > skill content) |\n"
        "| UI change | `apple-ui` + `frontend-react` | Implementer | Components, styling, animation, icons, finance dashboard design |",
    ),
    (
        "## Skill dependency chain",
        "## UI design precedence\n"
        "\n"
        "Load the union: a finance UI task loads `apple-ui` + `frontend-react`, plus\n"
        "`designmotion-design` when the surface's behaviour is new or under review. Precedence\n"
        "resolves conflicts only; it never suppresses loading.\n"
        "\n"
        "- `apple-ui` wins on finance visual tokens, motion values and data visualization.\n"
        "- `designmotion-design` wins on interaction behaviour (state coverage, feedback timing,\n"
        "  failure modes, component-system choice) where `apple-ui` is silent.\n"
        "- If both specify the same thing, `apple-ui` wins and the plan records the conflict.\n"
        "- `design/skills/` (imported craft corpus) is advisory: load it on demand, never as a rule\n"
        "  and never as evidence (AGENTS.md > agent definition > skill content).\n"
        "- `frontend-react` is the implementation stack and does not by itself decide design; it\n"
        "  pairs with `apple-ui` for finance surfaces.\n"
        "\n"
        "## Skill dependency chain",
    ),
    (
        "- [ ] Do not skip required skills",
        "- [ ] `designmotion-design` when a UI surface introduces or changes a pattern/system\n"
        "- [ ] Do not skip required skills",
    ),
]

EDITS["framework/opencode/skill-integration-matrix.md"] = [
    (
        "| implementer | load ALL skills named by Team Lead / Planner; apple-ui + frontend-react for any UI work; unit-test-authoring for business logic; karpathy-guidelines per its routing condition (skill-routing.md:24) | skill-routing.md:75-78 |",
        "| implementer | load ALL skills named by Team Lead / Planner; apple-ui + frontend-react for any UI work; designmotion-design when a UI surface introduces or changes a pattern/system; unit-test-authoring for business logic; karpathy-guidelines per its routing condition (skill-routing.md:24) | skill-routing.md:75-78 |",
    ),
    (
        "| ui-designer | gsd-sketch to drive variant generation; frontend-react + apple-ui as stack and design-language baseline; design/skills/ corpus as advisory craft only | skill-routing.md |",
        "| ui-designer | gsd-sketch to drive variant generation; frontend-react + apple-ui as stack and design-language baseline; designmotion-design for pattern behaviour (states, feedback timing, failure modes); design/skills/ corpus as advisory craft only | skill-routing.md |",
    ),
    (
        "## 2. Skill dependency route",
        "Imported craft corpus: `design/skills/` is listed in `skills.paths` so its 17 skills are\n"
        "loadable by name, but it is **advisory** - never a mandatory binding, never evidence\n"
        "(`design/skills/README.md`). Only `apple-ui`, `frontend-react` and `designmotion-design`\n"
        "hold UI slots above.\n"
        "\n"
        "## 2. Skill dependency route",
    ),
    (
        "       |- apple-ui + frontend-react (UI work) -> implementer",
        "       |- apple-ui + frontend-react (+ designmotion-design when the pattern/system is new) -> implementer",
    ),
    (
        "- G-EXEC: gate created, executed, exit code recorded.",
        "- G-EXEC: gate created, executed, exit code recorded.\n"
        "- Routing resolution: `framework/validate.py` asserts every configured `skills.paths`\n"
        "  entry exists and is populated, every skill's `name` matches its directory, no name is\n"
        "  declared by two roots, and every skill named in `skill-routing.md` resolves on a\n"
        "  configured path.",
    ),
]

EDITS["framework/opencode/skills/apple-ui/SKILL.md"] = [(
    "> One sentence: **near-black canvas + purple-soul glass, used only where layers overlap and budgeted like the GPU cost it is; every directional signal is color *and* a shape, verified at its worst case, not its average case.**",
    "> One sentence: **near-black canvas + purple-soul glass, used only where layers overlap and budgeted like the GPU cost it is; every directional signal is color *and* a shape, verified at its worst case, not its average case.**\n"
    "\n"
    "**Pairing:** implement with `frontend-react`; for interaction behaviour (state coverage,\n"
    "feedback timing, failure modes, component-system choice) load `designmotion-design` too. This\n"
    "skill owns finance visual tokens, motion values and data-viz; `designmotion-design` owns\n"
    "behaviour where this skill is silent. Advisory craft references live in `design/skills/`.\n"
    "Routing: `framework/opencode/skill-routing.md`.",
)]

EDITS["framework/opencode/skills/frontend-react/SKILL.md"] = [(
    "This skill covers the implementation stack only. The design system for this repo (dark glass finance UI: tokens in `tokens.css`, component/pattern/data-viz specs, accessibility and motion rules) lives in `apple-ui` — load it together with this skill on every UI task. It is a mandatory pairing, not an option.",
    "This skill covers the implementation stack only. The design system for this repo (dark glass finance UI: tokens in `tokens.css`, component/pattern/data-viz specs, accessibility and motion rules) lives in `apple-ui` — load it together with this skill on every UI task. It is a mandatory pairing, not an option.\n"
    "\n"
    "Interaction behaviour (state coverage, feedback timing, failure modes, component-system choice)\n"
    "is covered by `designmotion-design`; load it when the surface introduces or changes a pattern.\n"
    "Advisory CSS/animation craft references live in `design/skills/` and are read on demand, never\n"
    "mandatory. Routing precedence: `framework/opencode/skill-routing.md`.",
)]

EDITS["framework/opencode/skills/designmotion-design/SKILL.md"] = [
    (
        "Apply UX pattern system rules from designmotionhq when you build or review a user interface. Use this skill when you need to decide what system a component belongs to, which states it must cover, how fast it must respond, and how it should fail. Use it for screens, forms, tables, navigation, feedback surfaces, overlays, and motion. When you need a pure CSS effect with copy-paste code, use the ania-kubow-design skill instead. When you need a JavaScript or React implementation, use the settigation-code skill instead. When you need a general principle or a named UX law, use the uiux-design-foundations skill instead. When you need a checkable guideline value, use the practical-ui skill instead.",
        "Apply UX pattern system rules from designmotionhq when you build or review a user interface. Use this skill when you need to decide what system a component belongs to, which states it must cover, how fast it must respond, and how it should fail. Use it for screens, forms, tables, navigation, feedback surfaces, overlays, and motion. For pure CSS effects and copy-paste snippets use `design/skills/ania-kubow-design`; for React implementation in this repo use `frontend-react`; for general principles and named UX laws use `design/skills/uiux-design-foundations`. This repository has no `settigation-code` or `practical-ui` skill — do not send a reader looking for either.\n"
        "\n"
        "**In this repository:** `apple-ui` owns finance visual tokens, motion values and data-viz and\n"
        "wins on those; this skill owns interaction behaviour and wins where `apple-ui` is silent.\n"
        "Implement with `frontend-react`. Precedence and mandatory routing:\n"
        "`framework/opencode/skill-routing.md`.",
    ),
    (
        "- Do not duplicate sister skills. When a topic overlaps, keep the system rules here and point to the sister skill for its layer: pure CSS effects to ania-kubow-design, JavaScript and React implementations to settigation-code, principles and laws to uiux-design-foundations, and guideline values to practical-ui.",
        "- Do not duplicate sister skills. When a topic overlaps, keep the system rules here and point to the sister skill for its layer: pure CSS effects to `design/skills/ania-kubow-design`, React implementation to `frontend-react`, principles and laws to `design/skills/uiux-design-foundations`, and checkable finance guideline values to `apple-ui`.",
    ),
    (
        "## Available connectors\n"
        "\n"
        "- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.\n"
        "- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.",
        "## Where this fits in this repository\n"
        "\n"
        "- Sister skills are repo paths, not upstream names: `apple-ui` (finance design system),\n"
        "  `frontend-react` (implementation stack), `browser-verification` (visible-behaviour\n"
        "  evidence), and the advisory craft corpus in `design/skills/` (including\n"
        "  `ania-kubow-design` and `uiux-design-foundations`).\n"
        "- The `muse.*` connector tools and `/opt/muse/...` paths this skill was extracted with do\n"
        "  not exist in this repository. Do not call them; use the repo tools named above.",
    ),
]

EDITS["framework/opencode/skills/designmotion-design/skill.yaml"] = None
EDITS["framework/opencode/skills/ROUTES.md"] = None


def read_exact(path: Path) -> str:
    """Read preserving line endings (read_text would normalize CRLF away)."""
    return path.read_bytes().decode("utf-8")


def style_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


_SKILL_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
_SKILL_NAME = re.compile(r"^name:\s*(\S+)", re.M)


def _routed_skills(routing_text: str) -> set[str]:
    """Skill names in the `Required Skill` column. Same parse validate.py uses."""
    names: set[str] = set()
    for line in routing_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        names |= set(re.findall(r"`([A-Za-z0-9][A-Za-z0-9-]*)`", cells[1]))
    return names


def _unresolved(routing_text: str, found: set[str]) -> list[str]:
    return sorted(n for n in _routed_skills(routing_text) if n not in found)


def verify_target(built: dict[str, dict]) -> None:
    """Prove the POST-IMAGE state, not the working tree: the patch is the deliverable.

    validate.py is authoritative *after* a human applies the patch; this is the pre-apply
    equivalent so a staged plane change is never handed over unverified.
    """
    import json

    cfg = json.loads(built["opencode.json"]["updated"])
    roots = cfg["skills"]["paths"]
    found: dict[str, list[str]] = {}
    for root in roots:
        base = REPO / root
        if not base.is_dir():
            raise SystemExit(f"target check: configured skills path does not exist: {root}")
        skill_files = sorted(base.glob("*/SKILL.md"))
        if not skill_files:
            raise SystemExit(f"target check: configured skills path is empty: {root}")
        for skill_md in skill_files:
            text = skill_md.read_text(encoding="utf-8")
            front = _SKILL_FRONTMATTER.match(text)
            if not front:
                raise SystemExit(f"target check: no parseable frontmatter: {skill_md}")
            name = _SKILL_NAME.search(front.group(1))
            if not name or name.group(1) != skill_md.parent.name:
                raise SystemExit(
                    f"target check: name/directory mismatch: {skill_md} says "
                    f"{name.group(1) if name else '<missing>'}"
                )
            found.setdefault(skill_md.parent.name, []).append(str(skill_md))

    dupes = sorted(n for n, paths in found.items() if len(paths) > 1)
    if dupes:
        raise SystemExit(f"target check: skill name declared by two roots: {dupes}")

    routed = _unresolved(built["framework/opencode/skill-routing.md"]["updated"], set(found))
    if routed:
        raise SystemExit(f"target check: routed skills resolve nowhere: {routed}")

    # Teeth: a row naming a skill that does not exist MUST be reported, otherwise the check
    # above is only ever green because it read nothing.
    if not _unresolved("| c | `not-a-real-skill` | agent | when |\n", set(found)):
        raise SystemExit("target check: resolution check cannot detect a missing skill")

    print(
        f"target check: {len(found)} skills across {len(roots)} roots; "
        f"{len(_routed_skills(built['framework/opencode/skill-routing.md']['updated']))} routed, "
        "all resolve"
    )


def build() -> dict[str, dict]:
    """repo-relative path -> {original, updated|None, style}"""
    built: dict[str, dict] = {}
    for rel, pairs in EDITS.items():
        path = REPO / rel
        if not path.exists():
            raise SystemExit(f"{rel}: target does not exist")
        original = read_exact(path)
        style = style_of(original)
        current = original
        if pairs is None:
            built[rel] = {"original": original, "updated": None, "style": style}
            continue
        for anchor, replacement in pairs:
            old = anchor.replace("\n", style)
            new = replacement.replace("\n", style)
            hits = current.count(old)
            if hits != 1:
                raise SystemExit(f"{rel}: anchor occurs {hits} times, expected exactly 1")
            if new == old:
                raise SystemExit(f"{rel}: replacement equals anchor")
            current = current.replace(old, new)
        restored = current
        for anchor, replacement in reversed(pairs):
            restored = restored.replace(
                replacement.replace("\n", style), anchor.replace("\n", style)
            )
        if restored != original:
            raise SystemExit(f"{rel}: replacement is not reversible - more changed than intended")
        built[rel] = {"original": original, "updated": current, "style": style}
    return built


def generate(built: dict[str, dict]) -> str:
    with tempfile.TemporaryDirectory(prefix="design-skills-") as td:
        root = Path(td)
        for rel, info in built.items():
            old_target = root / "OLD" / rel
            old_target.parent.mkdir(parents=True, exist_ok=True)
            old_target.write_text(info["original"], encoding="utf-8", newline="")
            if info["updated"] is not None:
                new_target = root / "NEW" / rel
                new_target.parent.mkdir(parents=True, exist_ok=True)
                new_target.write_text(info["updated"], encoding="utf-8", newline="")
        (root / "NEW").mkdir(exist_ok=True)
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff",
             "--no-prefix", "OLD", "NEW"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="strict",
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
                # git prints a file that exists only in OLD as `OLD/<p> OLD/<p>`, and a
                # modified file as `OLD/<p> NEW/<p>`. Rebuild the header from the pair so a
                # deleted-file header never keeps a stray OLD/ token (git apply tolerates it,
                # patch -p1 and human readers do not).
                m = re.match(r"diff --git OLD/(\S+) (?:NEW|OLD)/(\S+)$", body)
                if not m or m.group(1) != m.group(2):
                    raise SystemExit(f"unexpected diff header: {body[:80]!r}")
                body = f"diff --git a/{m.group(1)} b/{m.group(2)}"
            elif body.startswith("--- OLD/"):
                body = "--- a/" + body[len("--- OLD/"):]
            elif body.startswith("+++ NEW/"):
                body = "+++ b/" + body[len("+++ NEW/"):]
            lines.append(body + nl)
        return "".join(lines)


def parse(patch: str) -> dict[str, dict]:
    files: dict[str, dict] = {}
    path, cur = None, None
    for ln in patch.splitlines():
        if ln.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)$", ln)
            if not m or m.group(1) != m.group(2):
                raise SystemExit(f"malformed diff header: {ln[:80]!r}")
            path = m.group(1)
            files.setdefault(path, {"hunks": [], "deleted": False})
            cur = None
        elif ln.startswith("deleted file mode"):
            files[path]["deleted"] = True
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
                got = src[pos].rstrip("\r\n") if pos + 1 <= len(src) else "<EOF>"
                raise SystemExit(
                    f"hunk fidelity: context mismatch at old line {pos + 1}: "
                    f"expected {body[:60]!r}, found {got[:60]!r}"
                )
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

    removed = added = 0
    for rel, info in files.items():
        spec = built[rel]
        rebuilt = apply_hunks(spec["original"], info["hunks"])
        expected = spec["updated"] if spec["updated"] is not None else ""
        if rebuilt != expected:
            raise SystemExit(f"self-check FAILED: rebuilt {rel} != intended post-image")
        if spec["updated"] is None:
            if not info["deleted"]:
                raise SystemExit(f"{rel}: intended deletion is not marked deleted in the patch")
            if not rebuilt == "":
                raise SystemExit(f"{rel}: deletion left content behind")
        else:
            if info["deleted"]:
                raise SystemExit(f"{rel}: unintended deletion marker")
        body = [l for h in info["hunks"] for l in h["lines"]]
        removed += sum(1 for l in body if l.startswith("-"))
        added += sum(1 for l in body if l.startswith("+"))

    # Post-image proof: the plane is what a human applies, so assert the target state here.
    verify_target(built)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patch, encoding="utf-8", newline="")
    print(f"wrote {OUT} ({len(patch)} bytes)")
    print(
        f"files: {len(files)}, hunks: {sum(len(v['hunks']) for v in files.values())}, "
        f"removed: {removed}, added: {added}, self-check: OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
