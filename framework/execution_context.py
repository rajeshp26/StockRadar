#!/usr/bin/env python3
"""Execution context. The canonical runtime identity behind evidence provenance.

Every claim's evidence names a runtime; until now that name was a free-form string nobody
could verify. The execution context makes the binding checkable: `record` pins the current
host, resolved model and provider under an RT- id in <state_root>/contexts/execution.jsonl,
and claims/ledger.py refuses an RT- reference that does not resolve. "A claim names the
runtime it was verified under" stops being prose and becomes a check.

The command environment behind a probe is a second, orthogonal binding: `record-env` pins
the interpreter that actually ran (path + version), the working directory, the git commit
and dirty state, and the OS under an ENV- id in <state_root>/contexts/environments.jsonl,
and `check-env` compares a recorded row against the canonical declaration for its scope in
framework/execution_context.yaml. This is the DBeta incident axis: a probe run under the
global interpreter while the canonical backend runtime is the venv.

Records are append-only, one row per pinned run. A corrected binding is a new row, never an
edit; analyse reports duplicate ids as invalid rather than guessing which one wins.

Exit codes:
  0  record/current/resolve/path/analyse ok | record-env ok | check-env match
  1  record/resolve: model resolution failed (nothing bindable) | analyse: invalid rows
     | check-env: mismatch, or a named ENV- id that does not resolve
  3  analyse/current: context file empty or missing (nothing to conclude -- never a pass)
     | check-env: no canonical declaration for the scope, or no recorded ENV- row
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_ID_RE = re.compile(r"^RT-\d+$")
ENV_ID_RE = re.compile(r"^ENV-\d+$")


def _state_root() -> Path:
    """Resolve the GSD state root exactly the way the rest of the framework does."""
    try:
        r = subprocess.run(["python3", "framework/adapters/gsd_state.py", "state-root"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return Path(".planning")


def context_path() -> Path:
    return _state_root() / "contexts" / "execution.jsonl"


def load() -> list[dict]:
    p = context_path()
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN: execution context line {i} is not valid JSON -- skipped", file=sys.stderr)
    return out


def environments_path() -> Path:
    return _state_root() / "contexts" / "environments.jsonl"


def load_envs() -> list[dict]:
    p = environments_path()
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN: environments line {i} is not valid JSON -- skipped", file=sys.stderr)
    return out


def _bind() -> dict:
    """Resolve what THIS run is executing under; exits 1 if nothing bindable.

    Provider is taken from the resolved default model id (the prefix before '/',
    e.g. 'opencode' in 'opencode/big-pickle'); a model id with no prefix falls back
    to the detected host name so the binding always names a real boundary.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from adapters import host as _host
    from models import resolve as _resolve

    host_name, host_mod = _host.resolve()
    try:
        cfg = json.loads(Path("opencode.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    config = {"model": cfg.get("model"), "small_model": cfg.get("small_model")}

    profiles_path = Path(__file__).parent / "models" / "profiles.sh"
    try:
        profiles_text = profiles_path.read_text(encoding="utf-8")
    except OSError:
        profiles_text = ""
    realized = _resolve.realized_profiles(profiles_text, os.environ)
    resolved = _resolve.resolve_all(config, os.environ, realized)

    model, source = resolved.get("team-lead", ("", "error"))
    small, small_source = resolved.get("small", ("", "error"))
    if not model or source == "error":
        print(json.dumps({"error": "no bindable model", "source": source,
                          "hint": "config-default resolution failed; g12 requires a resolvable model"}),
              file=sys.stderr)
        sys.exit(1)
    provider = model.split("/", 1)[0] if "/" in model else host_name
    return {
        "host": host_name,
        "host_version": host_mod.detect_version() or "unknown",
        "provider": provider,
        "model": model,
        "resolved_by": source,
        "small_model": small if small and small_source != "error" else "",
        "session_id": os.environ.get("OC_SESSION_ID") or os.environ.get("OPENCODE_SESSION_ID") or "",
    }


def _next_runtime_id(rows: list[dict]) -> str:
    highest = 0
    for r in rows:
        m = re.match(r"^RT-(\d+)$", str(r.get("runtime_id") or ""))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"RT-{highest + 1:04d}"


def record() -> str:
    ctx = _bind()
    rows = load()
    ctx["runtime_id"] = _next_runtime_id(rows)
    ctx["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    p = context_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(ctx, sort_keys=True) + "\n")
    return ctx["runtime_id"]


def _next_env_id(rows: list[dict]) -> str:
    highest = 0
    for r in rows:
        m = re.match(r"^ENV-(\d+)$", str(r.get("env_id") or ""))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"ENV-{highest + 1:04d}"


def _git_state() -> tuple[str, bool]:
    """(commit, dirty) for the current tree; ('', False) when git is unavailable."""
    try:
        c = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=15)
        commit = c.stdout.strip() if c.returncode == 0 else ""
        d = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, timeout=15)
        dirty = d.returncode == 0 and bool(d.stdout.strip())
        return commit, dirty
    except Exception:
        return "", False


def record_env(scope: str = "default") -> str:
    """Pin the command environment THIS run executes under as an ENV- row.

    The DBeta incident axis: a probe run under the global interpreter while the
    canonical backend runtime is the venv. record-env captures the interpreter that
    actually ran (path + version), the working directory, the git commit and dirty
    state, and the OS, so check-env can compare it against the canonical declaration
    for the scope.
    """
    commit, dirty = _git_state()
    row = {
        "env_id": _next_env_id(load_envs()),
        "scope": scope,
        "interpreter_path": sys.executable,
        "interpreter_version": platform.python_version(),
        "cwd": os.getcwd(),
        "git_commit": commit,
        "git_dirty": dirty,
        "os": sys.platform,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    p = environments_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row["env_id"]


def current() -> dict:
    rows = load()
    if not rows:
        return {"status": "none", "note": "no execution context recorded -- nothing to show"}
    return rows[-1]


def analyse() -> dict:
    rows = load()
    if not rows:
        return {"status": "empty", "entries": 0, "invalid": [], "runtimes": []}
    invalid = []
    seen: dict[str, int] = {}
    for idx, r in enumerate(rows):
        problems = []
        rid = r.get("runtime_id")
        if not rid or not RUNTIME_ID_RE.match(str(rid)):
            problems.append("CONTEXT_BAD_ID")
        if not r.get("host"):
            problems.append("CONTEXT_NO_HOST")
        if not r.get("provider"):
            problems.append("CONTEXT_NO_PROVIDER")
        if not r.get("model"):
            problems.append("CONTEXT_NO_MODEL")
        if not r.get("created_at"):
            problems.append("CONTEXT_NO_CREATED_AT")
        seen[str(rid)] = seen.get(str(rid), 0) + 1
        if problems:
            invalid.append({"index": idx + 1, "runtime_id": rid, "problems": problems})
    duplicates = [rid for rid, n in seen.items() if n > 1]
    if duplicates:
        invalid.append({"runtime_id": "?", "problems": ["CONTEXT_DUPLICATE_ID"], "duplicates": duplicates})
    return {"status": "invalid" if invalid else "ok", "entries": len(rows),
            "invalid": invalid, "runtimes": [r.get("runtime_id") for r in rows]}


def _canonical_scopes() -> dict:
    """Canonical env declarations per scope from framework/execution_context.yaml.

    An absent file or scope is 'no canonical declaration' -- check-env exits 3
    (nothing to conclude), never a pass. An absent YAML parser is a hard BLOCKED,
    not a pass: a missing parser must not read as 'no canonical declaration'.
    """
    p = Path("framework/execution_context.yaml")
    if not p.exists():
        return {}
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "BLOCKED: PyYAML is required to read framework/execution_context.yaml. "
            "An absent parser must not read as 'no canonical declaration'."
        )
    data = yaml.safe_load(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {}
    scopes = data.get("scopes")
    return scopes if isinstance(scopes, dict) else {}


def _interpreter_matches(canonical: str, recorded: str) -> bool:
    """Bare names compare by basename (python == python.exe); paths resolve
    against the repo root and compare case-insensitively on Windows."""
    if "/" not in canonical and "\\" not in canonical:
        return (os.path.splitext(os.path.basename(recorded))[0].lower()
                == os.path.splitext(canonical)[0].lower())
    return os.path.normcase(os.path.abspath(canonical)) == os.path.normcase(os.path.abspath(recorded))


def check_env(scope: str, env_id: str | None = None) -> dict:
    """Compare a recorded ENV- row against the canonical declaration for a scope.

    Status -> exit: match 0, mismatch 1, env_unknown 1, no_canonical 3,
    no_recorded 3. Only fields the canonical declares are compared; a declared
    field missing from the recorded row is a mismatch.
    """
    scopes = _canonical_scopes()
    canonical = scopes.get(scope)
    if not isinstance(canonical, dict):
        return {"status": "no_canonical", "scope": scope,
                "note": f"no canonical declaration for scope '{scope}' in framework/execution_context.yaml"}

    rows = load_envs()
    if env_id:
        row = next((r for r in rows if r.get("env_id") == env_id), None)
        if row is None:
            return {"status": "env_unknown", "scope": scope, "env_id": env_id,
                    "note": f"no recorded ENV- row with id {env_id}"}
    else:
        if not rows:
            return {"status": "no_recorded", "scope": scope,
                    "note": "no recorded ENV- row to compare -- nothing to conclude"}
        row = rows[-1]
        env_id = row.get("env_id")

    compared: dict[str, bool] = {}
    mismatches: list[str] = []
    for field, expected in canonical.items():
        actual = row.get("interpreter_path" if field == "interpreter" else field)
        if field == "interpreter":
            ok = isinstance(actual, str) and _interpreter_matches(str(expected), actual)
        elif field == "cwd":
            ok = isinstance(actual, str) and (
                os.path.normcase(os.path.abspath(str(expected)))
                == os.path.normcase(os.path.abspath(actual)))
        elif field == "os":
            ok = actual == expected
        elif field == "git_dirty":
            ok = actual is expected
        else:
            ok = actual == expected
        compared[field] = bool(ok)
        if not ok:
            mismatches.append(field)

    if mismatches:
        return {"status": "mismatch", "scope": scope, "env_id": env_id,
                "match": False, "mismatches": mismatches, "compared": compared}
    return {"status": "match", "scope": scope, "env_id": env_id,
            "match": True, "compared": compared}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Execution context ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    sub.add_parser("current")
    sub.add_parser("resolve")
    sub.add_parser("analyse")
    sub.add_parser("path")
    sub.add_parser("record-env").add_argument("--scope", default="default")
    _ce = sub.add_parser("check-env")
    _ce.add_argument("--scope", required=True)
    _ce.add_argument("--env", default=None)
    a = ap.parse_args()

    if a.cmd == "path":
        print(context_path()); sys.exit(0)
    if a.cmd == "resolve":
        print(json.dumps(_bind(), indent=2)); sys.exit(0)
    if a.cmd == "record":
        rid = record()
        print(json.dumps({"runtime_id": rid})); sys.exit(0)
    if a.cmd == "record-env":
        eid = record_env(a.scope)
        print(json.dumps({"env_id": eid})); sys.exit(0)
    if a.cmd == "check-env":
        out = check_env(a.scope, a.env)
        print(json.dumps(out, indent=2))
        sys.exit({"match": 0, "mismatch": 1, "env_unknown": 1,
                  "no_canonical": 3, "no_recorded": 3}[out["status"]])
    if a.cmd == "current":
        out = current()
        if out.get("status") == "none":
            print(json.dumps(out)); sys.exit(3)
        print(json.dumps(out, indent=2)); sys.exit(0)
    out = analyse()
    print(json.dumps(out, indent=2))
    if out["status"] == "empty":
        sys.exit(3)
    sys.exit(1 if out["invalid"] else 0)
