#!/usr/bin/env python3
"""DeepSeek Harness (dsh) host backend — DECLARED, NOT SUPPORTED.

Status: developer preview. Package metadata reads 0.1.0-rc.x with no release/tag behind it,
and the project states there WILL be compatibility-breaking changes. GitHub Issues are
disabled. This file exists so the dsh question is a config decision rather than a fork —
it is deliberately NOT a working backend.

Why dsh is a RUNTIME PEER, not a layer: its agent loop lives in packages/core/agent-loop as
an ordinary plugin, and there is no privileged core to patch — model adapter, tool registry,
session log and loop are all replaceable from config. That is the slot OpenCode occupies in
this framework. "Integrating dsh" is really "migrating off OpenCode."

The one genuine architectural upgrade dsh offers: a live `agent/pre-step` extension point
that can reject a step or rewrite the messages entering it. On OpenCode, Context Builder is
a tool the agent may call. On dsh it could be ENFORCED middleware. That is the strongest
technical argument for migrating, and it is why this stub names it explicitly.

THE BLOCKER IS NOT CONFIG. It is permission equivalence. OpenCode's edit:deny / task:deny /
bash allowlists mechanically enforce the star topology and "only Implementer writes code."
dsh has sandboxes and an approval policy, but equivalence is UNVERIFIED. Until someone
proves it, permission_enforcement is 'unverified' and the topology is a convention.
"""
from __future__ import annotations
import shutil
import subprocess

UNSUPPORTED_REASON = (
    "dsh is a declared-but-unsupported host in v1. It is a runtime PEER to OpenCode, so "
    "adopting it is a migration, not an integration. Blocking items, in order: "
    "(1) permission equivalence for edit/task/bash denial is unverified — without it the "
    "star topology is advisory; (2) the surfaces the framework would depend on most "
    "(agent-loop and agent/pre-step) are the least stable in a preview that promises "
    "breaking changes; (3) telemetry and context-builder need rewrites. "
    "Implement this file — and nothing else in the framework — to add support."
)


def detect_version():
    """Return None unless dsh is BOTH installed and explicitly opted into.

    Detection alone must not silently switch hosts: a developer with dsh installed for
    unrelated benchmarking would otherwise flip the framework onto an unsupported runtime.
    """
    import os
    if os.environ.get("FRAMEWORK_HOST") != "dsh":
        return None
    if not shutil.which("dsh"):
        return None
    try:
        return subprocess.run(["dsh", "--version"], capture_output=True,
                              text=True, timeout=15).stdout.strip() or None
    except Exception:
        return None


def agent_def_format() -> dict:
    return {"kind": "UNSUPPORTED", "reason": UNSUPPORTED_REASON,
            "note": "agent instruction BODIES port verbatim; only frontmatter is host-specific"}


def permission_map() -> dict:
    return {
        "enforcement": "unverified",
        "reason": UNSUPPORTED_REASON,
        "intents": {},
        "required_before_support": [
            "prove edit denial for six of seven agents",
            "prove delegation denial (star topology, depth 1)",
            "prove bash allowlisting for Reviewer (git/grep only)",
        ],
    }


def plugin_paths() -> list:
    return []


def capabilities() -> dict:
    return {
        "permission_enforcement": "unverified",
        "star_topology_enforceable": "unverified",
        "context_middleware": "agent/pre-step (can reject a step or rewrite messages)",
        "context_builder_mode": "could_be_enforced_middleware_not_just_a_tool",
        "session_log": "append_only_reconstructable_supports_resume_fork_replay",
        "compaction_hazard": "lower — log is append-only and reconstructable",
        "handoffs_still_required": (
            "yes. A session log says what happened; a handoff plus a gate exit code is what "
            "a later agent can act on. A transcript is a debugging record, not evidence."
        ),
        "maturity": "developer_preview_breaking_changes_expected",
        "best_use_today": (
            "minimal mode (bash + file editor) as a fixed harness for model comparison — "
            "hold the harness constant, vary the model, read rework rate. Runs alongside "
            "the twenty-task slice without touching delivery."
        ),
    }
