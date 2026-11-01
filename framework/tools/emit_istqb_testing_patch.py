#!/usr/bin/env python3
"""Emit the istqb-testing integration patch for the enforcement plane.

WHY THIS EXISTS
===============
The `istqb-testing` skill package (routing.json + router.py + SKILL.md + 18 references) must be
vendored under `framework/opencode/skills/`, which is an enforcement-plane path: agent edits are
denied. The framework's own rule (AGENTS.md, design doc section 9.1) is to deliver a plane change
as an applyable change set for a human to land, never to write the plane from an agent.

This patch:

    A. framework/opencode/skills/istqb-testing/**   NEW skill tree (SKILL.md, router.py,
                                                    routing.json, ATTRIBUTION.md, references/*)
    B. framework/opencode/skill-routing.md          routing row + implementer/verifier/reviewer checks
    C. framework/opencode/skill-integration-matrix.md  role bindings + evidence row
    D. framework/opencode/agents/team-lead.md       capability-matrix row
    E. framework/opencode/agents/verifier.md        "Test design (ISTQB)" procedure section

Emits `.planning/patches/istqb-testing-integration.patch`.

INVARIANTS ASSERTED (pre-apply proof, because the patch is the deliverable)
===========================================================================
- every anchor occurs exactly once after line-ending normalization (no ambiguity)
- replacements are reversible: undoing them restores the original byte-for-byte
- each existing file's own line endings are preserved
- the emitted hunks, re-applied from the @@ offset, reproduce the post-image exactly
- post-image: skill frontmatter name matches its directory
- post-image: every reference in routing.json exists on disk
- post-image: the router, executed from the post-image tree, routes the documented examples
- post-image: every skill routed in skill-routing.md resolves on a configured root

Usage:
    python3 framework/tools/emit_istqb_testing_patch.py [--source DIR] [--out PATH]

SINGLE USE, against the PRE-PATCH tree. Every edit is anchored on text this patch removes, so a
second run on an already-patched tree fails loudly ("anchor occurs 0 times") instead of
producing a no-op or a duplicate row. The emitted patch is the reviewable change set; the
SC06 rule in `framework/tools/skill_coverage.py` was made as a separate edit and is not part of
it, so review `git diff` alongside this file, never this file alone.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_REL = "framework/opencode/skills/istqb-testing"
DEFAULT_SOURCE = Path(r"C:\Users\rajes\AppData\Local\Temp\opencode\istqb_extract\istqb-testing")
DEFAULT_OUT = REPO / ".planning" / "patches" / "istqb-testing-integration.patch"

# Files copied verbatim from the source package. skill.yaml is deliberately excluded: framework
# skills carry no skill.yaml (validate.py globs */SKILL.md), and the design-skills patch deleted
# the one muse-style skill.yaml that ever existed here. ATTRIBUTION.md is kept for provenance.
SKILL_FILES = [
    "SKILL.md",
    "router.py",
    "routing.json",
    "ATTRIBUTION.md",
] + ["references/" + p.name for p in sorted((DEFAULT_SOURCE / "references").glob("*.md"))]

# Anchored edits to existing plane files: path -> [(anchor, replacement), ...]
EDITS: dict[str, list[tuple[str, str]]] = {}

EDITS["framework/opencode/skill-routing.md"] = [
    (
        "| Unit tests required | `unit-test-authoring` | Implementer | Any business logic verification |\n",
        "| Unit tests required | `unit-test-authoring` | Implementer | Any business logic verification |\n"
        "| Test design technique, coverage claim, risk-based regression scope, defect report, test plan or work-product review, ISTQB exam prep | `istqb-testing` | Verifier / Implementer / Reviewer | Choosing a technique or stating coverage, selecting regression scope, writing a defect report, planning or reporting testing, reviewing a work product |\n",
    ),
    (
        "- [ ] `unit-test-authoring` for business logic\n",
        "- [ ] `unit-test-authoring` for business logic\n"
        "- [ ] `istqb-testing` when choosing a test technique, stating coverage, or writing a defect report\n",
    ),
    (
        "- [ ] Verify test adequacy via `unit-test-authoring` standards\n",
        "- [ ] Verify test adequacy via `unit-test-authoring` standards\n"
        "- [ ] `istqb-testing` when judging test adequacy by technique and coverage, not by pass count\n",
    ),
    (
        "- [ ] `browser-verification` for visible behavior\n",
        "- [ ] `browser-verification` for visible behavior\n"
        "- [ ] `istqb-testing` when choosing a test technique or stating a coverage claim\n",
    ),
]

EDITS["framework/opencode/skill-integration-matrix.md"] = [
    (
        "| implementer | load ALL skills named by Team Lead / Planner; apple-ui + frontend-react for any UI work; designmotion-design when a UI surface introduces or changes a pattern/system; unit-test-authoring for business logic; karpathy-guidelines per its routing condition (skill-routing.md:24) | skill-routing.md:75-78 |",
        "| implementer | load ALL skills named by Team Lead / Planner; apple-ui + frontend-react for any UI work; designmotion-design when a UI surface introduces or changes a pattern/system; unit-test-authoring for business logic; istqb-testing when choosing a test technique, stating coverage, or writing a defect report; karpathy-guidelines per its routing condition (skill-routing.md:24) | skill-routing.md:75-78 |",
    ),
    (
        "| reviewer | verify implementation vs architecture; contract compliance; required-skills-used; unit-test-authoring adequacy standards | skill-routing.md:80-84 |",
        "| reviewer | verify implementation vs architecture; contract compliance; required-skills-used; unit-test-authoring adequacy standards; istqb-testing when judging test adequacy by technique and coverage | skill-routing.md:80-84 |",
    ),
    (
        "| verifier | performance-testing when material; browser-verification for visible behavior; name applicable evidence class per requirement shape | skill-routing.md:86-89; evidence.md:1-19 |",
        "| verifier | performance-testing when material; browser-verification for visible behavior; istqb-testing when choosing a technique or stating a coverage claim; name applicable evidence class per requirement shape | skill-routing.md:86-89; evidence.md:1-19 |",
    ),
    (
        "| unit test | business rule produces a value | G4 |\n",
        "| unit test | business rule produces a value | G4 |\n"
        "| test design technique + coverage claim (istqb-testing router output) | a suite must be adequate, not merely green | G4 / G17 |\n",
    ),
]

EDITS["framework/opencode/agents/team-lead.md"] = [
    (
        "| Unit test authoring | yes/no | `unit-test-authoring` |\n",
        "| Unit test authoring | yes/no | `unit-test-authoring` |\n"
        "| Test design (ISTQB) | yes/no | `istqb-testing` |\n",
    ),
]

EDITS["framework/opencode/agents/verifier.md"] = [
    (
        "## Frontend and browser verification\n",
        "## Test design (ISTQB)\n"
        "\n"
        "Load the `istqb-testing` skill when you choose a test technique, state a coverage claim,\n"
        "select regression scope, write a defect report, plan or report testing, or review a work\n"
        "product. Run its deterministic router first, from the repository root:\n"
        "\n"
        "    python3 framework/opencode/skills/istqb-testing/router.py --task \"<the task text>\"\n"
        "\n"
        "Load the returned `primary` reference before designing; load an additional reference only\n"
        "if the task needs that part. `fallback: true` means the task text was too vague to route:\n"
        "clarify it rather than defaulting to `fundamentals.md`. Name the technique and the coverage\n"
        "achieved in the verification artifact; a test list with neither is not finished.\n"
        "\n"
        "## Frontend and browser verification\n",
    ),
]

# Inserted into SKILL.md so the vendored copy is runnable from the repository root. The upstream
# text tells the agent to run `python3 router.py` from inside the package, which is not the cwd
# of an agent working in the repo.
SKILL_MD_ANCHOR = '    python3 router.py --task "your task text here"\n'
SKILL_MD_ADDITION = (
    "\n"
    "From the repository root (this package is vendored at `framework/opencode/skills/istqb-testing/`):\n"
    "\n"
    '    python3 framework/opencode/skills/istqb-testing/router.py --task "your task text here"\n'
)

SKILL_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
SKILL_NAME = re.compile(r"^name:\s*(\S+)", re.M)


def read_exact(path: Path) -> str:
    """Read preserving line endings (read_text would normalize CRLF away)."""
    return path.read_bytes().decode("utf-8")


def style_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def apply_edits(rel: str, text: str, pairs: list[tuple[str, str]]) -> str:
    style = style_of(text)
    current = text
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
    if restored != text:
        raise SystemExit(f"{rel}: replacement is not reversible - more changed than intended")
    return current


def build(source: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Return (existing-file post-images, new-file contents)."""
    built: dict[str, dict] = {}
    for rel, pairs in EDITS.items():
        path = REPO / rel
        if not path.exists():
            raise SystemExit(f"{rel}: target does not exist")
        original = read_exact(path)
        built[rel] = {
            "original": original,
            "updated": apply_edits(rel, original, pairs),
            "style": style_of(original),
        }

    new_files: dict[str, str] = {}
    for name in SKILL_FILES:
        src = source / name
        if not src.exists():
            raise SystemExit(f"source package is missing {src}")
        text = src.read_bytes().decode("utf-8")
        text = text.replace("\r\n", "\n")
        # Upstream routing.json has no trailing newline. Vendored files carry one (repo
        # convention, .gitattributes eol=lf); without it git emits a "\ No newline" marker
        # the hunk replay cannot reproduce.
        if not text.endswith("\n"):
            text += "\n"
        rel = f"{SKILL_REL}/{name}"
        if name == "SKILL.md":
            hits = text.count(SKILL_MD_ANCHOR)
            if hits != 1:
                raise SystemExit(f"SKILL.md: router anchor occurs {hits} times, expected 1")
            text = text.replace(SKILL_MD_ANCHOR, SKILL_MD_ANCHOR + SKILL_MD_ADDITION)
        new_files[rel] = text
    return built, new_files


def generate(built: dict[str, dict], new_files: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory(prefix="istqb-patch-") as td:
        root = Path(td)
        (root / "OLD").mkdir()
        for rel, info in built.items():
            old_target = root / "OLD" / rel
            old_target.parent.mkdir(parents=True, exist_ok=True)
            old_target.write_text(info["original"], encoding="utf-8", newline="")
            new_target = root / "NEW" / rel
            new_target.parent.mkdir(parents=True, exist_ok=True)
            new_target.write_text(info["updated"], encoding="utf-8", newline="")
        for rel, text in new_files.items():
            new_target = root / "NEW" / rel
            new_target.parent.mkdir(parents=True, exist_ok=True)
            new_target.write_text(text, encoding="utf-8", newline="")

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
            if body.startswith("diff --git "):
                m = re.match(r"diff --git (?:OLD|NEW)/(\S+) (?:NEW|OLD)/(\S+)$", body)
                if not m or m.group(1) != m.group(2):
                    raise SystemExit(f"unexpected diff header: {body[:100]!r}")
                body = f"diff --git a/{m.group(1)} b/{m.group(2)}"
            elif body.startswith("--- OLD/"):
                body = "--- a/" + body[len("--- OLD/"):]
            elif body.startswith("--- NEW/"):
                body = "--- /dev/null" if body == "--- NEW/" + body[len("--- NEW/"):] else body
            elif body.startswith("+++ NEW/"):
                body = "+++ b/" + body[len("+++ NEW/"):]
            elif body.startswith("+++ OLD/"):
                body = "+++ b/" + body[len("+++ OLD/"):]
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
            files.setdefault(path, {"hunks": [], "new": False})
            cur = None
        elif ln.startswith("new file mode"):
            files[path]["new"] = True
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
    style = style_of(original) if original else "\n"
    for hunk in hunks:
        # A new file's hunk is `@@ -0,0 +1,N @@`: there is no old line 0, so it starts at 1
        # against an empty source. Treating it as 0 makes the ordering guard fire.
        start = hunk["start"] if hunk["start"] > 0 else 1
        if pos > start - 1:
            raise SystemExit("hunk fidelity: hunks out of order")
        out.extend(src[pos:start - 1])
        pos = start - 1
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


def routed_skills(routing_text: str) -> set[str]:
    names: set[str] = set()
    for line in routing_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        names |= set(re.findall(r"`([A-Za-z0-9][A-Za-z0-9-]*)`", cells[1]))
    return names


def verify_post_image(built: dict[str, dict], new_files: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="istqb-verify-") as td:
        root = Path(td)
        # Materialise the post-image for the new skill tree only (edits are text-verified above).
        for rel, text in new_files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")

        skill_md = root / SKILL_REL / "SKILL.md"
        front = SKILL_FRONTMATTER.match(skill_md.read_text(encoding="utf-8"))
        if not front:
            raise SystemExit("post-image: SKILL.md has no parseable frontmatter")
        name = SKILL_NAME.search(front.group(1))
        if not name or name.group(1) != skill_md.parent.name:
            raise SystemExit(
                "post-image: skill name/directory mismatch: %s" %
                (name.group(1) if name else "<missing>")
            )

        routing = json.loads((root / SKILL_REL / "routing.json").read_text(encoding="utf-8"))
        missing = []
        refs = {r["reference"] for r in routing["rules"]} | {routing["fallback"]["reference"]}
        for ref in sorted(refs):
            if not (root / SKILL_REL / ref).exists():
                missing.append(ref)
        if missing:
            raise SystemExit(f"post-image: routing.json names references that do not exist: {missing}")

        # Teeth: a deliberately broken reference MUST be detected.
        probe = [r for r in refs if r not in missing]
        if not probe:
            raise SystemExit("post-image: reference existence check read nothing")

        router = root / SKILL_REL / "router.py"
        cases = {
            "design pairwise tests for checkout config": "references/ta-test-design-data.md",
            "choose regression tests after a discount change": "references/ta-risk-based-testing.md",
            "explain regression testing": "references/sdlc.md",
            "minimise this decision table and check the checksum": "references/ta-test-design-rule.md",
        }
        for task, expected in cases.items():
            proc = subprocess.run(
                [sys.executable, str(router), "--task", task],
                capture_output=True, text=True, encoding="utf-8",
            )
            if proc.returncode != 0:
                raise SystemExit(f"post-image: router failed for {task!r}: {proc.stderr[:200]}")
            got = json.loads(proc.stdout)["primary"]
            if got != expected:
                raise SystemExit(
                    f"post-image: router misroute for {task!r}: got {got}, want {expected}"
                )

        fallback = subprocess.run(
            [sys.executable, str(router), "--task", "unrelated xyzzy plugh"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if not json.loads(fallback.stdout).get("fallback"):
            raise SystemExit("post-image: router did not mark an unmatched task as fallback")

        # Every skill routed in the post-image router resolves on a configured root.
        cfg = json.loads((REPO / "opencode.json").read_text(encoding="utf-8"))
        roots = (cfg.get("skills") or {}).get("paths") or ["framework/opencode/skills"]
        found: set[str] = set()
        for root_rel in roots:
            base = REPO / root_rel
            if not base.is_dir():
                raise SystemExit(f"post-image: configured skills path missing: {root_rel}")
            for skill_md_path in base.glob("*/SKILL.md"):
                text = skill_md_path.read_text(encoding="utf-8")
                m = SKILL_FRONTMATTER.match(text)
                if m:
                    n = SKILL_NAME.search(m.group(1))
                    if n:
                        found.add(n.group(1))
        found.add("istqb-testing")  # arrives with this patch
        routed = routed_skills(built["framework/opencode/skill-routing.md"]["updated"])
        unresolved = sorted(n for n in routed if n not in found)
        if unresolved:
            raise SystemExit(f"post-image: routed skills resolve nowhere: {unresolved}")

        print(
            f"post-image check: skill frontmatter OK, {len(refs)} references present, "
            f"{len(cases)} routes correct + fallback, {len(routed)} routed skills all resolve"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    source = Path(args.source)
    if not (source / "SKILL.md").exists():
        raise SystemExit(f"source package not found at {source}")

    built, new_files = build(source)
    patch = generate(built, new_files)
    files = parse(patch)
    expected = set(built) | set(new_files)
    if set(files) != expected:
        raise SystemExit(f"patch touches {sorted(files)}, expected {sorted(expected)}")

    removed = added = 0
    for rel, info in files.items():
        if rel in new_files:
            if not info["new"]:
                raise SystemExit(f"{rel}: intended new file is not marked new")
            rebuilt = apply_hunks("", info["hunks"])
            if rebuilt != new_files[rel]:
                raise SystemExit(f"self-check FAILED: rebuilt new file {rel} != intended")
        else:
            spec = built[rel]
            rebuilt = apply_hunks(spec["original"], info["hunks"])
            if rebuilt != spec["updated"]:
                raise SystemExit(f"self-check FAILED: rebuilt {rel} != intended post-image")
        body = [l for h in info["hunks"] for l in h["lines"]]
        removed += sum(1 for l in body if l.startswith("-"))
        added += sum(1 for l in body if l.startswith("+"))

    verify_post_image(built, new_files)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8", newline="")
    print(f"wrote {out} ({len(patch)} bytes)")
    print(
        f"files: {len(files)} ({len(new_files)} new), "
        f"hunks: {sum(len(v['hunks']) for v in files.values())}, "
        f"removed: {removed}, added: {added}, self-check: OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
