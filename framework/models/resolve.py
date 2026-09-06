#!/usr/bin/env python3
"""Model resolution engine for the StockerPro agentic framework.

The runtime truth is: OC_MODEL_<AGENT> env vars (set by sourcing a profile, by
the user, or not at all) plus the opencode.json model fallbacks.  A sourced
profile is detected by matching its full export set against the environment.

Per agent, resolution is:
  env set, matches active profile cell      -> (model, "profile")
  env set, structurally valid, no profile   -> (model, "override")
  env set but empty or malformed            -> ("", "error")   FAIL CLOSED
  env unset                                 -> (config model, "default")
  env unset and no config model             -> ("", "error")   FAIL CLOSED
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

AGENTS = [
    "team-lead",
    "researcher",
    "architect",
    "planner",
    "implementer",
    "reviewer",
    "verifier",
]

# OC_MODEL_* variable per agent. Kept in lockstep with AGENTS.
ENV_BY_AGENT: Dict[str, str] = {
    "team-lead": "OC_MODEL_LEAD",
    "researcher": "OC_MODEL_RESEARCH",
    "architect": "OC_MODEL_ARCHITECT",
    "planner": "OC_MODEL_PLANNER",
    "implementer": "OC_MODEL_IMPLEMENT",
    "reviewer": "OC_MODEL_REVIEW",
    "verifier": "OC_MODEL_VERIFY",
}

SMALL_ENV = "OC_MODEL_SMALL"

# The nine variables a sourced profile exports, in _p argument order.
PROFILE_VARS = [
    "OC_MODEL_DEFAULT",
    "OC_MODEL_SMALL",
    "OC_MODEL_LEAD",
    "OC_MODEL_RESEARCH",
    "OC_MODEL_ARCHITECT",
    "OC_MODEL_PLANNER",
    "OC_MODEL_IMPLEMENT",
    "OC_MODEL_REVIEW",
    "OC_MODEL_VERIFY",
]

# The nine _p argument roles, in argument order.  arg1 = default model,
# arg2 = small model, args 3..9 = the seven agents in AGENTS order.
_ROLES = ["default", "small"] + AGENTS

# A model id acceptable from config, env override, or realized profile cell.
STRUCTURAL_OK = re.compile(r"^[A-Za-z0-9_./:~-]+$")

# A raw profile cell: $BIG / ${OC_BIG:-...} / plain id.
DEP_REF = re.compile(r"^(\$[A-Za-z_][A-Za-z0-9_]*|\$\{[^}]*\}|[A-Za-z0-9_./:~-]+)$")

# A bare variable reference inside a cell: $BIG
_REF = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")

# case-label lines: "  baseline)" / "  reset|off)" (the `*)` catch-all never matches).
_CASE_LABEL = re.compile(r"(?m)^\s*([A-Za-z0-9_|]+)\)\s*$")

# a full 9-arg _p call (the nine roles above, in order).
_PROFILE_CALL = re.compile(
    r'_p\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"'
    r'\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"'
)

# VAR="${ENV:-default}" | VAR="$ENV" | VAR="literal"
_ASSIGN = re.compile(
    r'(?m)^([A-Za-z_][A-Za-z0-9_]*)=\"'
    r'(?:\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)|([^"$]*))\"\s*$'
)

MISSING = "<<missing>>"


def structural_ok(model: Optional[str]) -> bool:
    """True iff the value is a structurally safe model id."""
    return bool(model) and bool(STRUCTURAL_OK.match(model))


def dep_ok(value: Optional[str]) -> bool:
    """True iff a raw profile cell is a var reference or a plain model id."""
    return bool(value) and bool(DEP_REF.match(value))


def parse_profile_script(text: str) -> Dict[str, Dict[str, str]]:
    """Parse profiles.sh -> {profile: {role: raw_cell}}.

    Profile names come from `case` labels; each label's first following `_p`
    call supplies the nine role cells.  A label with no well-formed call (or a
    call with no label) is absent from the result -- callers treat absence as
    a failure to map the profile.
    """
    labels = [(m.group(1).split("|")[0], m.start()) for m in _CASE_LABEL.finditer(text)]
    profiles: Dict[str, Dict[str, str]] = {}
    for m in _PROFILE_CALL.finditer(text):
        preceding = [name for name, pos in labels if pos <= m.start()]
        if not preceding:
            continue
        profiles[preceding[-1]] = dict(zip(_ROLES, m.groups()))
    return profiles


def _realize_vars(text: str, environ: Dict[str, str]) -> Dict[str, str]:
    """Evaluate top-level VAR=\"...\" assignments (BIG/MID/SML) against environ."""
    var_map: Dict[str, str] = {}
    for m in _ASSIGN.finditer(text):
        name, env1, default, env2, literal = m.groups()
        if env1 is not None:
            var_map[name] = environ.get(env1) or default or MISSING
        elif env2 is not None:
            var_map[name] = environ.get(env2) or MISSING
        else:
            var_map[name] = literal if literal else MISSING
    return var_map


def realize_cell(cell: str, var_map: Dict[str, str]) -> str:
    """Resolve one raw cell ($BIG etc.) to a concrete model id, or MISSING."""
    m = _REF.match(cell or "")
    if m:
        return var_map.get(m.group(1)) or MISSING
    return cell if structural_ok(cell) else MISSING


def realized_profiles(text: str, environ: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """{profile: {role: model_id-or-MISSING}} with $VAR refs resolved."""
    var_map = _realize_vars(text, environ)
    return {
        name: {role: realize_cell(cell, var_map) for role, cell in cells.items()}
        for name, cells in parse_profile_script(text).items()
    }


def active_profile(environ: Dict[str, str], realized: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Profile whose full export set matches the environment, else None.

    Matching compares all nine OC_MODEL_* vars against the profile's realized
    cells; an unrealized (MISSING) cell expects the var to be unset/empty.
    The first match in file order wins.
    """
    for name in [n for n in realized if n != "reset"]:
        cells = realized[name]
        for var, role in zip(PROFILE_VARS, _ROLES):
            env_val = environ.get(var) or ""
            cell = cells.get(role)
            cell_val = "" if cell in (None, MISSING) else cell
            if env_val != cell_val:
                break
        else:
            return name
    return None


def _resolve_one(env_val: Optional[str], profile_cell: Optional[str], config_default: Optional[str]) -> Tuple[str, str]:
    """Resolve a single agent/small slot. Returns (model, source)."""
    if env_val is not None:
        if env_val == "":
            return ("", "error")
        if not structural_ok(env_val):
            return ("", "error")
        if profile_cell not in (None, MISSING) and env_val == profile_cell:
            return (env_val, "profile")
        return (env_val, "override")
    if config_default and structural_ok(config_default):
        return (config_default, "default")
    return ("", "error")


def resolve_all(
    config: Dict[str, Optional[str]],
    environ: Dict[str, str],
    realized: Dict[str, Dict[str, str]],
) -> Dict[str, Tuple[str, str]]:
    """Resolve every agent plus the small model -> {name: (model, source)}."""
    active = active_profile(environ, realized)
    prof = realized.get(active) if active else None
    out: Dict[str, Tuple[str, str]] = {}
    for agent in AGENTS:
        out[agent] = _resolve_one(
            environ.get(ENV_BY_AGENT[agent]),
            prof.get(agent) if prof else None,
            config.get("model"),
        )
    out["small"] = _resolve_one(
        environ.get(SMALL_ENV),
        prof.get("small") if prof else None,
        config.get("small_model"),
    )
    return out


def inventory(timeout: int = 10) -> Dict[str, object]:
    """Query `opencode models` for the ground-truth model inventory.

    Never raises. Returns {"ok": bool, "models": [str], "note": str}.
    ok=False means the CLI is unavailable or failed; callers must treat the
    inventory as unverifiable, never as empty-but-trusted.
    """
    try:
        proc = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "models": [], "note": "opencode CLI not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "models": [], "note": "opencode models timed out after %ds" % timeout}
    if proc.returncode != 0:
        return {
            "ok": False,
            "models": [],
            "note": "opencode models exited %d: %s" % (proc.returncode, proc.stderr.strip()[:200]),
        }
    models = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return {"ok": True, "models": models, "note": ""}


def preflight(
    config: Dict[str, Optional[str]],
    environ: Dict[str, str],
    profile_script_text: str,
) -> Dict[str, object]:
    """One-shot resolution answer used by validate.py --models and telemetry.

    Returns:
      agents:          {agent: {"model": str, "source": str}} plus "small"
      failures:        [name, ...] that resolved to error ([] == fail-closed ok)
      active_profile:  detected sourced profile, or None
      top_level / small_model: the opencode.json fallbacks
      profiles:        realized cells per profile (for S5/S6 diagnostics)
    """
    realized = realized_profiles(profile_script_text, environ)
    active = active_profile(environ, realized)
    resolved = resolve_all(config, environ, realized)
    failures = [a for a, (model, source) in resolved.items() if source == "error"]
    return {
        "agents": {a: {"model": m, "source": s} for a, (m, s) in resolved.items()},
        "failures": failures,
        "active_profile": active,
        "top_level": config.get("model"),
        "small_model": config.get("small_model"),
        "profiles": realized,
    }


def main() -> int:
    """Self-test: core scenarios without touching the network."""
    results: List[bool] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print("[{}] {}{}".format("PASS" if ok else "FAIL", name, " - " + detail if detail else ""))
        results.append(ok)

    cfg = {"model": "opencode/big-pickle", "small_model": "opencode/big-pickle"}
    script = (
        'BIG="${OC_BIG:-opencode/big-pickle}"\n'
        'MID="${OC_MID:-opencode/big-pickle}"\n'
        'SML="${OC_SML:-opencode/big-pickle}"\n'
        'case "${1:-}" in\n'
        '  baseline)\n'
        '    _p "$BIG" "$SML" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG" "$BIG" ;;\n'
        '  tiered)\n'
        '    _p "$MID" "$SML" "$SML" "$MID" "$BIG" "$SML" "$BIG" "$BIG" "$SML" ;;\n'
        '  cheap)\n'
        '    _p "$SML" "$SML" "$SML" "$SML" "$MID" "$SML" "$MID" "$MID" "$SML" ;;\n'
        '  broken)\n'
        '    _p "$BIG" "$BIG" ;;\n'
        'esac\n'
    )
    tiers = {
        "OC_BIG": "opencode/big-pickle",
        "OC_MID": "anthropic/claude-4-5-sonnet",
        "OC_SML": "x-ai/grok-4-fast",
    }

    # S1: no env -> config defaults, no failures
    pf = preflight(cfg, {}, script)
    ok = pf["failures"] == [] and all(a["source"] == "default" for a in pf["agents"].values())
    check("S1 no env -> defaults", ok)

    # S2: all agent envs set, matching no profile -> override everywhere
    env2 = {v: "anthropic/claude-4-5-sonnet" for v in ENV_BY_AGENT.values()}
    env2[SMALL_ENV] = "opencode/big-pickle"
    pf2 = preflight(cfg, env2, script)
    ok = all(a["source"] == "override" for a in pf2["agents"].values()) and pf2["failures"] == []
    check("S2 env overrides (no profile matched)", ok)

    # S3: single env -> that override, rest default
    pf3 = preflight(cfg, {"OC_MODEL_IMPLEMENT": "anthropic/claude-4-5-sonnet"}, script)
    ok = (pf3["agents"]["implementer"] == {"model": "anthropic/claude-4-5-sonnet", "source": "override"}
          and pf3["agents"]["team-lead"]["source"] == "default")
    check("S3 single env override", ok)

    # S4: set-but-empty override -> error, never inherit
    pf4 = preflight(cfg, {"OC_MODEL_LEAD": ""}, script)
    ok = pf4["agents"]["team-lead"] == {"model": "", "source": "error"}
    check("S4 empty override fails closed", ok)

    # S4b: malformed override -> error
    pf5 = preflight(cfg, {"OC_MODEL_LEAD": "bad;rm -rf /"}, script)
    ok = pf5["agents"]["team-lead"]["source"] == "error"
    check("S4b malformed override fails closed", ok)

    # S5: every profile maps all seven agents (realized, non-MISSING)
    realized = realized_profiles(script, tiers)
    ok = set(realized) == {"baseline", "tiered", "cheap"} and all(
        all(cells.get(a) != MISSING for a in AGENTS) for cells in realized.values()
    )
    check("S5 profiles map all seven agents", ok)

    # S5b: malformed call has no profile entry -> detectable, never inherited
    ok = "broken" not in realized
    check("S5b malformed profile absent", ok)

    # S6: raw profile cells are var refs or literals only
    ok = all(dep_ok(cell) for cells in parse_profile_script(script).values() for cell in cells.values())
    check("S6 profile refs structural", ok)

    # S7: sourcing tiered (with distinct BIG/MID/SML) is detected and attributed
    tiered_env = {
        "OC_MODEL_DEFAULT": "anthropic/claude-4-5-sonnet",
        "OC_MODEL_SMALL": "x-ai/grok-4-fast",
        "OC_MODEL_LEAD": "x-ai/grok-4-fast",
        "OC_MODEL_RESEARCH": "anthropic/claude-4-5-sonnet",
        "OC_MODEL_ARCHITECT": "opencode/big-pickle",
        "OC_MODEL_PLANNER": "x-ai/grok-4-fast",
        "OC_MODEL_IMPLEMENT": "opencode/big-pickle",
        "OC_MODEL_REVIEW": "opencode/big-pickle",
        "OC_MODEL_VERIFY": "x-ai/grok-4-fast",
    }
    tiered_env.update(tiers)
    pf7 = preflight(cfg, tiered_env, script)
    ok = (pf7["active_profile"] == "tiered"
          and pf7["agents"]["implementer"] == {"model": "opencode/big-pickle", "source": "profile"}
          and pf7["agents"]["team-lead"] == {"model": "x-ai/grok-4-fast", "source": "profile"})
    check("S7 sourced profile attributed as profile", ok)

    # S8: a manual tweak on top of a sourced profile -> override, no false profile
    tweak_env = dict(tiered_env)
    tweak_env["OC_MODEL_PLANNER"] = "opencode/big-pickle"
    pf8 = preflight(cfg, tweak_env, script)
    ok = (pf8["active_profile"] is None
          and pf8["agents"]["planner"]["source"] == "override"
          and pf8["agents"]["implementer"]["source"] == "override")
    check("S8 tweak breaks profile match -> override", ok)

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())