#!/usr/bin/env python3
"""Propagate the canonical enforcement plane (framework/security/enforcement_plane.yaml)
into opencode.json (permission.edit deny blocks: top-level, team-lead, implementer) and
AGENTS.md (generated fence). Conservative: only mirrors the YAML, never invents rules.

Human-run (or human-audited) after editing the canonical file. Then run
check_enforcement_plane.py - it must exit 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLANE = ROOT / "framework" / "security" / "enforcement_plane.yaml"
CONFIG = ROOT / "opencode.json"
AGENTS = ROOT / "AGENTS.md"

FENCE_BEGIN = "<!-- enforcement-plane: begin -->"
FENCE_END = "<!-- enforcement-plane: end -->"

AGENT_NAMES = ("team-lead", "implementer")


def load_plane() -> list[dict[str, str]]:
    docs = yaml.safe_load(PLANE.read_text(encoding="utf-8"))
    entries = docs.get("paths") if isinstance(docs, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"non-empty 'paths' list required: {PLANE}")
    seen: set[str] = set()
    for entry in entries:
        path = entry.get("path")
        if not path or not isinstance(path, str):
            raise ValueError(f"each plane entry needs a non-empty 'path': {PLANE}")
        if path in seen:
            raise ValueError(f"duplicate plane path: {path}")
        seen.add(path)
    return entries


def _rebuild_edit(edit: object, plane: list[str], label: str) -> dict:
    """Return a permission.edit object with every plane path denied as trailing
    rules - the invariant check_enforcement_plane.py asserts. Accepts a scalar
    '*' base rule (the top-level default before the plane fix)."""
    if isinstance(edit, str):
        edit = {"*": edit}
    if not isinstance(edit, dict):
        raise ValueError(f"{label} permission.edit must be a scalar or object")
    base = edit.get("*")
    if base is None:
        raise ValueError(f"{label} permission.edit needs a '*' base rule")
    kept = {k: v for k, v in edit.items() if k != "*" and k not in plane}
    rebuild = {"*": base, **kept}
    for path in plane:
        rebuild[path] = "deny"
    return rebuild


def sync_config(entries: list[dict[str, str]], cfg: dict) -> None:
    plane = [e["path"] for e in entries]
    cfg["permission"]["edit"] = _rebuild_edit(
        cfg["permission"].get("edit"), plane, "top-level"
    )
    for name in AGENT_NAMES:
        agent = cfg["agent"].get(name)
        if agent is None:
            raise ValueError(f"agent {name!r} missing in opencode.json")
        agent["permission"]["edit"] = _rebuild_edit(
            agent["permission"]["edit"], plane, f"agent {name!r}"
        )


def sync_agents_md(entries: list[dict[str, str]], text: str) -> str:
    fence = "\n".join(f"    {e['path']:<20}{e.get('note', '')}" for e in entries)
    block = f"{FENCE_BEGIN}\n{fence}\n{FENCE_END}"
    if FENCE_BEGIN not in text or FENCE_END not in text:
        raise ValueError("AGENTS.md: enforcement-plane fence markers missing")
    start = text.index(FENCE_BEGIN)
    end = text.index(FENCE_END) + len(FENCE_END)
    return text[:start] + block + text[end:]


def main() -> int:
    entries = load_plane()
    raw = CONFIG.read_text(encoding="utf-8")
    before = json.loads(raw)
    after = json.loads(raw)
    sync_config(entries, after)
    if before != after:
        CONFIG.write_text(
            json.dumps(after, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        json.loads(CONFIG.read_text(encoding="utf-8"))  # round-trip guard, fail loudly
        print("opencode.json updated")
    else:
        print("opencode.json already consistent")

    text = AGENTS.read_text(encoding="utf-8")
    updated = sync_agents_md(entries, text)
    if updated != text:
        AGENTS.write_text(updated, encoding="utf-8")
        print("AGENTS.md fence updated")
    else:
        print("AGENTS.md already consistent")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        sys.exit(1)