#!/usr/bin/env python3
"""Import third-party design skills into the repo's advisory skill corpus.

Why this exists
---------------
The repo hosts a corpus of third-party UI/design skills that the `ui-designer`
agent reads as *advisory* material. Those skills live OUTSIDE the enforcement
plane (AGENTS.md "enforcement plane" fence; framework/security/enforcement_plane.yaml)
so that agents may read them, and they are never treated as authoritative:
AGENTS.md > agent definition > skill content (untrusted-input-boundary.md).

Precedence of truth:
  - Imported skill content is ADVISORY, never a rule, evidence, or contract.
  - The corpus is intentionally outside `framework/opencode/skills` (a plane path
    agents cannot edit) and outside `opencode.json`'s configured `skills.paths`.

Usage
-----
  python framework/tools/import_design_skills.py \
      --source <dir-of-skill-dirs> \
      --dest framework/design/skills \
      [--exclude write-swift,animate-expo] \
      [--only prototype,break-ui] \
      [--license MIT] \
      [--license-file <path-to-LICENSE>]

A "skill directory" is any directory containing a SKILL.md. The importer copies
each such directory verbatim into <dest>/<name>/ and (re)writes <dest>/ATTRIBUTION.md.

Idempotent: an existing destination skill directory is replaced.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ADVISORY_NOTICE = """# Imported design skills (advisory)

This directory contains third-party UI/design skills imported by
`framework/tools/import_design_skills.py`.

- They are **advisory only**. Precedence is:
  `AGENTS.md > agent definition > skill content`.
- They are **discoverable**: `opencode.json` lists this directory in `skills.paths`, so a
  role may load one by name. Discoverable is not mandatory - `framework/opencode/skill-routing.md`
  decides which skills a task *must* load, and only `apple-ui`, `frontend-react` and
  `designmotion-design` hold UI slots there.
- They are **not** rules, contracts, or verification evidence. G5/G6 still decide visual
  conformance and browser evidence.
- Some entries carry upstream pointers that do not exist here (`settigation-code`,
  `practical-ui`, `muse.*` connectors, `/opt/muse/...`). Treat those as inapplicable, not as
  files to go looking for; the repo-real targets are `frontend-react` for implementation and
  `uiux-design-foundations` for principles.
- See `ATTRIBUTION.md` for source and license.
- To add/refresh skills, re-run the importer (see its module docstring; it rewrites this file).
"""


def discover_skill_dirs(source: Path) -> list[Path]:
    """Return every directory under *source* that contains a SKILL.md."""
    return sorted({skill_md.parent for skill_md in source.rglob("SKILL.md")})


def copy_skill(skill: Path, dest: Path) -> list[str]:
    """Copy one skill directory verbatim; return its relative file list."""
    target = dest / skill.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(skill, target)
    return sorted(
        p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import design skills (advisory corpus).")
    parser.add_argument("--source", required=True, help="Directory containing skill dirs.")
    parser.add_argument("--dest", default="framework/design/skills", help="Corpus destination.")
    parser.add_argument("--only", default="", help="Comma list; import only these names.")
    parser.add_argument("--exclude", default="", help="Comma list; skip these names.")
    parser.add_argument("--license", default="MIT", help="SPDX id recorded in attribution.")
    parser.add_argument("--license-file", default="", help="Optional LICENSE file to copy.")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    dest = Path(args.dest)
    if not source.is_dir():
        print(f"SOURCE_NOT_FOUND: {source}", file=sys.stderr)
        return 2

    discovered = discover_skill_dirs(source)
    if not discovered:
        print(f"NO_SKILLS_FOUND: no SKILL.md under {source}", file=sys.stderr)
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    exclude = {s.strip() for s in args.exclude.split(",") if s.strip()}
    selected = [s for s in discovered if s.name not in exclude]
    if only:
        selected = [s for s in selected if s.name in only]
    if not selected:
        print("NO_SKILLS_SELECTED after --only/--exclude filters", file=sys.stderr)
        return 2

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text(ADVISORY_NOTICE, encoding="utf-8")

    lines = [
        "# Attribution",
        "",
        f"Source: {source}",
        f"License: {args.license}",
        "",
        "Imported design skills are advisory only (see README.md).",
        "",
    ]
    for skill in selected:
        files = copy_skill(skill, dest)
        print(f"imported {skill.name}: {len(files)} file(s)")
        lines.append(f"## {skill.name}")
        lines.extend(f"- {skill.name}/{f}" for f in files)
        lines.append("")

    if args.license_file:
        lic = Path(args.license_file)
        if lic.is_file():
            shutil.copy2(lic, dest / "LICENSE")
            print(f"copied license: {lic} -> {dest / 'LICENSE'}")
        else:
            print(f"LICENSE_FILE_NOT_FOUND: {lic}", file=sys.stderr)
            return 2

    (dest / "ATTRIBUTION.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {dest / 'ATTRIBUTION.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
