#!/usr/bin/env python3
"""Verify the enforcement plane is consistent across its representations:

  - framework/security/enforcement_plane.yaml   canonical source
  - opencode.json permission.edit deny blocks   top-level + team-lead + implementer
  - AGENTS.md generated fence

The top-level permission.edit is mandatory: it governs any agent whose
agent-scoped permission set carries no edit rule (e.g. a plugin-defined
primary), so its plane denies are required, not optional.

Exit codes: 0 consistent | 1 mismatch (details printed) | 3 unverifiable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework import locate as _locate

ROOT = _locate.app_root()  # the app repo root (config-driven)
PLANE = _locate.framework_root() / "security" / "enforcement_plane.yaml"
CONFIG = ROOT / "opencode.json"
AGENTS = ROOT / "AGENTS.md"

FENCE_BEGIN = "<!-- enforcement-plane: begin -->"
FENCE_END = "<!-- enforcement-plane: end -->"
AGENT_NAMES = ("team-lead", "implementer")


def check_edit_block(label: str, edit: object, plane: list[str]) -> bool:
    """Assert one permission.edit block denies every plane path as trailing rules."""
    ok = True
    if not isinstance(edit, dict):
        print(f"FAIL: {label} permission.edit is not an object")
        return False
    allowed = {k for k, v in edit.items() if v in ("allow", "ask")}
    denied = [k for k, v in edit.items() if k != "*" and v == "deny"]
    overlap = sorted(allowed & set(plane))
    if overlap:
        print(f"FAIL: {label} allows/asks plane paths: {overlap}")
        ok = False
    missing = [p for p in plane if p not in denied]
    if missing:
        print(f"FAIL: {label} lacks deny for plane paths: {missing}")
        ok = False
    keys = [k for k in edit if k != "*"]
    trailing = []
    for k in reversed(keys):
        if k in plane:
            trailing.append(k)
        else:
            break
    trailing.reverse()
    if trailing != plane:
        print(f"FAIL: {label} plane denies are not the trailing rules in canonical order")
        ok = False
    return ok


def get_plane() -> list[dict[str, str]] | None:
    if not PLANE.exists():
        print(f"UNVERIFIABLE: canonical plane missing: {PLANE}")
        return None
    docs = yaml.safe_load(PLANE.read_text(encoding="utf-8"))
    entries = docs.get("paths") if isinstance(docs, dict) else None
    if not isinstance(entries, list) or not entries:
        print(f"UNVERIFIABLE: non-empty 'paths' list required: {PLANE}")
        return None
    return entries


def main() -> int:
    entries = get_plane()
    if entries is None:
        return 3
    plane = [e["path"] for e in entries]
    if len(plane) != len(set(plane)):
        print("FAIL: duplicate paths in canonical plane")
        return 1

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ok = True

    # The top-level permission.edit governs any agent whose agent-scoped
    # permission set carries no edit rule (e.g. a plugin-defined primary).
    # It is the block that actually resolved the runtime probes, so it is
    # required, not optional.
    if not check_edit_block("top-level", cfg["permission"].get("edit"), plane):
        ok = False
    for name in AGENT_NAMES:
        if not check_edit_block(name, cfg["agent"][name]["permission"]["edit"], plane):
            ok = False

    md = AGENTS.read_text(encoding="utf-8")
    if FENCE_BEGIN not in md or FENCE_END not in md:
        print("FAIL: AGENTS.md missing enforcement-plane fence markers")
        ok = False
    else:
        start = md.index(FENCE_BEGIN) + len(FENCE_BEGIN)
        end = md.index(FENCE_END)
        fence = [line.strip() for line in md[start:end].splitlines() if line.strip()]
        expected = [f"{e['path']:<20}{e.get('note', '')}" for e in entries]
        if fence != expected:
            print("FAIL: AGENTS.md fence differs from canonical")
            for have, want in zip(fence, expected):
                if have != want:
                    print(f"  fence:    {have!r}")
                    print(f"  expected: {want!r}")
            ok = False

    if ok:
        print(f"OK: enforcement plane consistent ({len(plane)} paths)")
        return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"check failed: {exc}", file=sys.stderr)
        sys.exit(1)