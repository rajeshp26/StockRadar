#!/usr/bin/env python3
"""Execution context. The canonical runtime identity behind evidence provenance.

Every claim's evidence names a runtime; until now that name was a free-form string nobody
could verify. The execution context makes the binding checkable: `record` pins the current
host, resolved model and provider under an RT- id in <state_root>/contexts/execution.jsonl,
and claims/ledger.py refuses an RT- reference that does not resolve. "A claim names the
runtime it was verified under" stops being prose and becomes a check.

Records are append-only, one row per pinned run. A corrected binding is a new row, never an
edit; analyse reports duplicate ids as invalid rather than guessing which one wins.

Exit codes:
  0  record/current/resolve/path/analyse ok
  1  record/resolve: model resolution failed (nothing bindable) | analyse: invalid rows
  3  analyse/current: context file empty or missing (nothing to conclude -- never a pass)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_ID_RE = re.compile(r"^RT-\d+$")


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Execution context ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    sub.add_parser("current")
    sub.add_parser("resolve")
    sub.add_parser("analyse")
    sub.add_parser("path")
    a = ap.parse_args()

    if a.cmd == "path":
        print(context_path()); sys.exit(0)
    if a.cmd == "resolve":
        print(json.dumps(_bind(), indent=2)); sys.exit(0)
    if a.cmd == "record":
        rid = record()
        print(json.dumps({"runtime_id": rid})); sys.exit(0)
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
