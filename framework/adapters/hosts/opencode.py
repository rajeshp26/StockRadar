#!/usr/bin/env python3
"""OpenCode host backend. The only fully implemented host in v1.

Detect, never assume. Current docs specify PLURAL config subdirectories (agents/, skills/,
tools/, plugins/, commands/); older versions and many published configs use singular. The
plugin loader globs {plugin,plugins}, so both are written. The `skills` config key is an
ARRAY of paths, not an object — the object form is silently ignored, so no skill loads.
The per-agent `tools` field is deprecated in favour of `permission`.
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

PAIRS = [("agents", "agent"), ("skills", "skill"), ("tools", "tool"),
         ("plugins", "plugin"), ("commands", "command")]


def detect_version():
    if not shutil.which("opencode"):
        return None
    try:
        return subprocess.run(["opencode", "--version"], capture_output=True,
                              text=True, timeout=15).stdout.strip() or None
    except Exception:
        return None


def dir_naming() -> dict:
    """Naming actually present per subdirectory, preferring what exists on disk."""
    out = {}
    for base in (Path(".opencode"), Path.home() / ".config/opencode"):
        for plural, singular in PAIRS:
            if (base / plural).is_dir():
                out.setdefault(plural, plural)
            elif (base / singular).is_dir():
                out.setdefault(plural, singular)
    for plural, _ in PAIRS:
        out.setdefault(plural, plural)   # docs default
    return out


def agent_def_format() -> dict:
    return {
        "kind": "markdown_with_yaml_frontmatter",
        "location": f".opencode/{dir_naming()['agents']}/<name>.md",
        "frontmatter_keys": ["description", "mode", "model", "temperature", "permission"],
        "mode_values": ["primary", "subagent", "all"],
        "body": "portable — instructions move to any host unchanged",
    }


def permission_map() -> dict:
    """Framework intent -> OpenCode permission keys. Enforced by the host."""
    return {
        "enforcement": "enforced",
        "schema": "v2_pattern_objects",
        "keys": ["read", "edit", "glob", "grep", "list", "bash", "task",
                 "external_directory", "lsp", "skill", "webfetch"],
        "intents": {
            "cannot_edit_code": {"edit": "deny"},
            "cannot_delegate": {"task": "deny"},
            "can_delegate": {"task": "allow"},
            "bash_allowlist": {"bash": {"*": "ask", "<pattern>": "allow"}},
            "no_network": {"webfetch": "deny"},
        },
        "tools_field": "deprecated_use_permission",
    }


def plugin_paths() -> list:
    """Write BOTH; the loader globs {plugin,plugins} and versions disagree."""
    return [".opencode/plugin/telemetry.ts", ".opencode/plugins/telemetry.ts"]


def capabilities() -> dict:
    return {
        "permission_enforcement": "enforced",
        "subagent_delegation": "task_tool_with_glob_patterns",
        "star_topology_enforceable": True,
        "custom_tools": "typescript_under_.opencode/tool[s]",
        "plugins": "typescript_under_.opencode/plugin[s]",
        "context_middleware": None,
        "context_builder_mode": "agent_invoked_tool",
        "skills_config_shape": "array_of_paths",
        "session_log": "prunes_tool_output_and_autocompacts",
        "compaction_hazard": "gate evidence can vanish mid-task; persist to state immediately",
        "compaction_overrides": ["OPENCODE_DISABLE_AUTOCOMPACT", "OPENCODE_DISABLE_PRUNE"],
        "config_precedence": ["remote .well-known/opencode", "global ~/.config/opencode",
                              "OPENCODE_CONFIG", "project opencode.json", ".opencode dirs",
                              "OPENCODE_CONFIG_CONTENT", "managed"],
    }
