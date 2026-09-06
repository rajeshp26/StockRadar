#!/usr/bin/env python3
"""Code Intelligence Adapter — capability interface, never tool names.

Priority ladder. Record which tier answered.
  1 native   GSD / OpenCode capability (codebase map, graphify)
  2 repo     LSP references and definitions
  3 provider CodeGraph via MCP
  4 fallback grep plus path conventions

Tier 3 is preferred for a capability only when measurement on THIS repository shows it
materially beats tiers 1-2. Record that measurement as a decision. The framework must remain
functional with the provider absent, degrading to tier 4 with a logged warning.
"""
import argparse
import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path

MANIFEST = Path("framework/.manifest/code_intel.json")
CAPABILITIES = ["symbol_search", "relationships", "impact", "affected_tests",
                "freshness", "reindex", "edit_context", "locate"]

# Candidate provider CLIs, probed in order. Names deliberately live in ONE place.
# The OMO harness installs CodeGraph under ~/.omo/codegraph/bin (node CLI). Probe
# PATH installs by name first, the harness location second.
_OMO_CG = os.path.expanduser(os.path.join("~", ".omo", "codegraph", "bin",
                                          "codegraph.cmd" if os.name == "nt" else "codegraph"))
PROVIDERS = [
    {"bin": "codegraph",      "probe": ["status"]},
    {"bin": _OMO_CG,          "probe": ["status"]},
    {"bin": "code-graph-mcp", "probe": ["health-check"]},
    {"bin": "symgraph",       "probe": ["status"]},
]


def _has(b): return shutil.which(b) is not None


def _run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def resolve() -> dict:
    """Resolve each capability to a tier. Written once at install, revalidated at session start."""
    native = _has("gsd")
    provider = next((p for p in PROVIDERS if _has(p["bin"])), None)
    if provider:
        rc, _ = _run([provider["bin"]] + provider["probe"])
        if rc != 0:
            provider = None

    res = {}
    for cap in CAPABILITIES:
        if provider:
            res[cap] = {"tier": 3, "via": provider["bin"]}
        elif cap in ("relationships", "locate") and _has("rg"):
            res[cap] = {"tier": 2, "via": "lsp-or-ripgrep"}
        else:
            res[cap] = {"tier": 4, "via": "grep",
                        "warning": f"{cap} degraded to search fallback"}
    m = {"provider": provider["bin"] if provider else None,
         "native_gsd": native, "capabilities": res}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))
    return m


def manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else resolve()


def tier(cap: str) -> int:
    return manifest()["capabilities"].get(cap, {}).get("tier", 4)


def _provider() -> str | None:
    return manifest().get("provider")


def _grep(pattern: str) -> str:
    tool = "rg" if _has("rg") else "grep"
    args = [tool, "-n", pattern, "."] if tool == "rg" else [tool, "-rn", pattern, "."]
    _, out = _run(args)
    return "\n".join(out.splitlines()[:60])


def locate(symbol: str) -> str:
    p = _provider()
    if p:
        rc, out = _run([p, "query", symbol])
        if rc == 0 and out:
            return out.splitlines()[0]
    return (_grep(f"(def|class|function|const|fn) +{symbol.split('.')[-1]}") or "unresolved").splitlines()[0] if _grep(f"{symbol.split('.')[-1]}") else "unresolved"


def impact(symbol: str | None, task: str | None) -> dict:
    """Blast radius. Returns tier so callers know how much to trust it."""
    p, t = _provider(), tier("impact")
    if p and symbol:
        for sub in (["impact", symbol], ["callers", symbol]):
            rc, out = _run([p] + sub)
            if rc == 0 and out:
                return {"tier": t, "via": p, "result": out[:4000]}
    target = symbol or (task or "")
    return {"tier": 4, "via": "grep", "result": _grep(target) if target else "",
            "warning": "search fallback; treat as incomplete"}


# Framework bookkeeping is not source. Gates write verdicts into project state, so including
# those paths makes the gate analyse its own footprint and report UNKNOWN_IMPACT on a clean tree.
_NON_SOURCE = ("/.planning/", "/.gsd/", "/.opencode/", "framework/telemetry/")


def _is_source(path: str) -> bool:
    q = "/" + path.lstrip("./")
    return not any(m in q for m in _NON_SOURCE) and not q.startswith("/.git/")


def changed_source() -> list[str]:
    """Changed source files, CWD-relative.

    `--relative` matters: without it git reports repo-root-relative paths, which never match
    project-relative paths when the project sits in a subdirectory of a larger repo.
    """
    raw = set(_run(["git", "diff", "--name-only", "--relative", "HEAD"])[1].splitlines())
    raw |= set(_run(["git", "ls-files", "--others", "--exclude-standard"])[1].splitlines())
    return sorted(f for f in raw if f and _is_source(f) and Path(f).exists())


_IGNORE_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".next", ".nuxt",
    "dist", "build", "out", "coverage", ".turbo", ".cache", ".parcel-cache",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".hypothesis",
    "vendor", ".pnpm-store", ".yarn", "target",
}


def _iter_test_files(root: Path, pattern: str):
    """Yield paths matching pattern under root, pruning dependency/build dirs.

    A bare Path.rglob over "." descends into node_modules and friends (~10^5
    files), which made affected_tests() run for minutes per changed file and
    hung G2 outright. os.walk lets us prune those subtrees instead of
    filtering after the walk.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for name in fnmatch.filter(filenames, pattern):
            yield Path(dirpath) / name


def _importers(changed: list[str]) -> list[str]:
    """Tests that reference a changed module by import or symbol.

    Filename-stem matching alone misses tests/contract/test_api_004.py for a change to
    auth_service.py — the strongest existing evidence, invisible to a naive glob.
    """
    mods = {Path(c).stem for c in changed if c.endswith(".py")}
    mods |= {Path(c).stem for c in changed if c.endswith((".ts", ".tsx", ".js", ".jsx"))}
    if not mods:
        return []
    hits = []
    roots = [Path("tests"), Path("test"), Path("src"), Path(".")]
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for q in _iter_test_files(root, "*test*"):
            if not q.is_file() or q.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx"):
                continue
            key = str(q)
            if key in seen:
                continue
            seen.add(key)
            try:
                body = q.read_text(errors="ignore")
            except OSError:
                continue
            if any(m in body for m in mods):
                hits.append(key)
        if hits:
            break
    return sorted(hits)


def affected_tests(task: str | None) -> dict:
    p = _provider()
    changed = changed_source()
    if not changed:
        return {"tier": tier("affected_tests"), "via": p or "none", "tests": [],
                "changed": 0, "note": "no source changes"}
    if p:
        rc, out = _run([p, "affected"] + changed[:50])
        if rc == 0 and out:
            return {"tier": tier("affected_tests"), "via": p,
                    "tests": out.splitlines(), "changed": len(changed)}

    # Tier-4 fallback: filename convention PLUS content reference. Content reference is the
    # stronger of the two and catches contract tests that import the changed module.
    guess = set()
    for f in changed:
        stem = Path(f).stem
        guess |= {str(q) for q in _iter_test_files(Path("."), f"*test*{stem}*") if q.is_file()}
    guess |= set(_importers(changed))
    return {"tier": 4, "via": "convention+reference", "tests": sorted(guess)[:40],
            "changed": len(changed),
            "warning": "search fallback; incomplete by construction"}


def freshness() -> dict:
    p = _provider()
    if not p:
        return {"tier": 4, "status": "no_provider",
                "stale": True, "note": "impact results are search-derived"}
    for sub in (["status"], ["health-check"], ["get_index_status"]):
        rc, out = _run([p] + sub)
        if rc == 0:
            stale = any(w in out.lower() for w in ("stale", "pending", "dirty", "outdated"))
            return {"tier": 3, "via": p, "status": out[:600], "stale": stale}
    return {"tier": 3, "via": p, "status": "unknown", "stale": True}


def reindex() -> dict:
    p = _provider()
    if not p:
        return {"ok": True, "note": "no provider; nothing to reindex"}
    for sub in (["sync"], ["incremental-index"], ["index"], ["reindex"]):
        rc, out = _run([p] + sub, timeout=600)
        if rc == 0:
            return {"ok": True, "via": f"{p} {sub[0]}", "out": out[:400]}
    return {"ok": False, "via": p, "note": "reindex failed; treat graph as stale"}


def low_impact_check(symbol: str) -> dict:
    """Three concrete checks. All must hold to treat a change as low impact."""
    imp = impact(symbol, None)
    no_dependents = tier("impact") <= 3 and not imp.get("result")
    grep_clean = not _grep(symbol.split(".")[-1])
    tests = affected_tests(None)
    return {"graph_no_dependents": bool(no_dependents), "repo_search_clean": bool(grep_clean),
            "affected_tests_empty": not tests.get("tests"),
            "verdict": "low_impact" if (no_dependents and grep_clean and not tests.get("tests"))
                       else "expand_context"}


CMDS = {
    "resolve": lambda a: resolve(), "manifest": lambda a: manifest(),
    "tier": lambda a: tier(a.capability), "locate": lambda a: locate(a.symbol),
    "impact": lambda a: impact(a.symbol, a.task),
    "affected-tests": lambda a: affected_tests(a.task),
    "freshness": lambda a: freshness(), "reindex": lambda a: reindex(),
    "low-impact-check": lambda a: low_impact_check(a.symbol),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Code Intelligence Adapter")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--capability", default="impact"); ap.add_argument("--symbol", default="")
    ap.add_argument("--task", default="")
    a = ap.parse_args()
    out = CMDS[a.command](a)
    print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)
