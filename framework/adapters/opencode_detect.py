#!/usr/bin/env python3
"""DEPRECATED shim — superseded by framework/adapters/host.py.

Host knowledge moved behind a runtime-neutral interface so a runtime change is an adapter
swap rather than a rewrite. This shim preserves the old output shape for anything still
calling it. New code MUST use host.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework import locate as _locate
import host as _host                                    # noqa: E402
from hosts import opencode as _oc                       # noqa: E402


def version():
    return _oc.detect_version()


def dir_naming():
    return _oc.dir_naming()


def detect():
    """Legacy shape, sourced from the host adapter. Do not extend."""
    caps = _oc.capabilities()
    pm = _oc.permission_map()
    m = {
        "version": version(),
        "dir_naming": dir_naming(),
        "permission_schema": pm["schema"],
        "permission_keys_pattern_capable": pm["keys"],
        "tools_field": pm["tools_field"],
        "subagent_depth_note": "star topology keeps depth at 1; all subagents deny task",
        "compaction": {"auto_default": True, "prune_default": True,
                       "hazard": caps["compaction_hazard"],
                       "overrides": caps["compaction_overrides"]},
        "config_precedence": caps["config_precedence"],
        "DEPRECATED": "use framework/adapters/host.py; this shim will be removed",
    }
    p = _locate.manifest_dir() / "opencode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, indent=2))
    _host.describe()          # keep host.json fresh too
    return m


if __name__ == "__main__":
    print(json.dumps(detect(), indent=2))
