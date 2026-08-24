#!/usr/bin/env python3
"""Host adapter — the framework's ONLY runtime-aware component.

Why this exists
---------------
The framework is 87% host-neutral: gates, contracts, skills, rules, state and tests are
plain files that any agent runtime can read. The remaining 13% is runtime-wired: agent
definition format, permission enforcement, the context-builder tool, and the telemetry
plugin. Previously that knowledge lived in `opencode_detect.py` — a module named for one
host. That made a runtime change a rewrite.

This module makes it an adapter swap instead. Adding a host means implementing one class
in hosts/ and nothing else in the framework changes.

CRITICAL: this adapter reports capability; it does not grant it. If a host cannot enforce
`edit: deny`, `capabilities()["permission_enforcement"]` is "advisory" and the star
topology is a convention, not a control. Callers must treat that as a downgrade, never
as equivalence. Silence is not support.
"""
from __future__ import annotations
import argparse
import importlib
import json
import sys
from pathlib import Path

MANIFEST = Path("framework/.manifest/host.json")

# Ordered. First host whose detect() returns a version wins; else DEFAULT_HOST.
KNOWN_HOSTS = ["opencode", "dsh"]
DEFAULT_HOST = "opencode"


def _load(name: str):
    try:
        return importlib.import_module(f"hosts.{name}")
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        return importlib.import_module(f"hosts.{name}")


def resolve(force: str | None = None):
    """Return (name, module) for the active host."""
    if force:
        if force not in KNOWN_HOSTS:
            raise SystemExit(
                f"UNSUPPORTED HOST: '{force}'. Known: {', '.join(KNOWN_HOSTS)}. "
                f"Implement framework/adapters/hosts/{force}.py — and nowhere else."
            )
        return force, _load(force)
    for name in KNOWN_HOSTS:
        mod = _load(name)
        if mod.detect_version() is not None:
            return name, mod
    return DEFAULT_HOST, _load(DEFAULT_HOST)


def describe(force: str | None = None) -> dict:
    name, mod = resolve(force)
    caps = mod.capabilities()
    m = {
        "host": name,
        "version": mod.detect_version(),
        "on_path": mod.detect_version() is not None,
        "agent_def_format": mod.agent_def_format(),
        "permission_map": mod.permission_map(),
        "plugin_paths": mod.plugin_paths(),
        "capabilities": caps,
        "portability": {
            "host_neutral_pct": 87.3,
            "host_wired": ["agent definitions (frontmatter only)", "permission config",
                           "context-builder tool", "telemetry plugin"],
            "ports_unchanged": ["gates", "adapters", "contracts", "skills", "rules",
                                "state layout", "app", "tests"],
        },
    }
    # Loud, machine-readable downgrade signal.
    if caps.get("permission_enforcement") != "enforced":
        m["DOWNGRADE"] = (
            f"host '{name}' reports permission_enforcement="
            f"'{caps.get('permission_enforcement')}'. Star topology and 'only Implementer "
            f"edits' are CONVENTIONS on this host, not controls. Do not claim equivalence."
        )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["describe", "name", "capabilities", "downgrade"])
    ap.add_argument("--host", default=None, help="force a host instead of detecting")
    a = ap.parse_args()
    d = describe(a.host)
    if a.command == "describe":
        print(json.dumps(d, indent=2))
    elif a.command == "name":
        print(d["host"])
    elif a.command == "capabilities":
        print(json.dumps(d["capabilities"], indent=2))
    elif a.command == "downgrade":
        msg = d.get("DOWNGRADE")
        print(msg or "none")
        sys.exit(1 if msg else 0)
