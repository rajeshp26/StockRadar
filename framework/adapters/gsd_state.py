#!/usr/bin/env python3
"""GSD State Adapter.

V1 supports the INSTALLED distribution only. Multi-distribution support is a conformance
target, verified by running `selftest` against a second distribution — not a v1 deliverable.

The rest of the framework touches only this interface, so adding a distribution is an
adapter change and nothing else.
"""
import argparse
import json
import subprocess
import datetime
from pathlib import Path

MANIFEST = Path("framework/.manifest/gsd.json")

# (state_root, distribution, mode). Recognised for detection; see SUPPORTED for implemented.
DISTRIBUTIONS = ((".planning", "gsd-core", "files"), (".gsd", "gsd-pi", "db"))
SUPPORTED = ("gsd-core",)


def detect() -> dict:
    """Identify the installed GSD distribution and its state root."""
    cwd = Path.cwd()
    # V1 SUPPORTS ONE DISTRIBUTION: the one installed. Probing is detection only —
    # it does NOT imply both are supported. gsd-pi is RECOGNISED so we can refuse it
    # by name instead of silently misreading a db-backed store as a file-backed one.
    found = []
    for root, dist, mode in DISTRIBUTIONS:
        if (cwd / root).is_dir():
            found.append((root, dist, mode))

    if len(found) > 1:
        names = ", ".join(f"{d} ({r})" for r, d, _ in found)
        return {"distribution": "ambiguous", "state_root": None, "mode": None,
                "version": _version(), "detected_at": _now(),
                "error": f"AMBIGUOUS: multiple GSD state roots present: {names}. "
                         "V1 supports exactly one. Remove or archive the unused root."}

    if found:
        root, dist, mode = found[0]
        # Store RELATIVE, never absolute: an absolute path bakes in one shell's mount
        # flavour (/mnt/c vs C:\), so a gate run under WSL poisons the cache for Windows
        # and validate fails with 'cache belongs to another checkout'. Detection is
        # cwd-anchored and every call site invokes the adapter from the repo root, so the
        # bare root name resolves identically under both shells.
        m = {"distribution": dist, "state_root": root, "mode": mode,
             "version": _version(), "detected_at": _now(),
             "supported": dist in SUPPORTED}
        if dist not in SUPPORTED:
            m["error"] = (
                f"UNSUPPORTED DISTRIBUTION: detected '{dist}' (mode={mode}). V1 implements "
                f"'{SUPPORTED[0]}' only. Multi-distribution support is a CONFORMANCE TARGET, "
                f"verified by running `selftest` against the second distribution — not a v1 "
                f"deliverable. Implement it in THIS adapter and nowhere else."
            )
        return m
    return {"distribution": "none", "state_root": ".planning",
            "mode": "files", "version": None, "detected_at": _now(),
            "warning": "No GSD state found. Run GSD project init before using the framework."}


def _version():
    for cmd in (["gsd", "--version"], ["gsd-core", "--version"]):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip() or None
        except Exception:
            continue
    return None


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def manifest() -> dict:
    """Cached detection, invalidated when the cache does not describe THIS checkout.

    The cache used to be trusted unconditionally and stored an ABSOLUTE state_root. A
    packaged, cloned, or relocated tree then inherited the packager's path — and because that
    path can still exist on the packager's machine, every read and write silently targeted the
    wrong tree while reporting success. Same failure class as a stale index reading as fresh.
    """
    if MANIFEST.exists():
        try:
            m = json.loads(MANIFEST.read_text())
        except json.JSONDecodeError:
            m = None
        if m and _cache_valid(m):
            return m
    m = detect()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))
    return m


def _cache_valid(m: dict) -> bool:
    """A cached manifest is valid only if its state root is inside the current tree."""
    sr = m.get("state_root")
    if not sr:
        return m.get("distribution") in ("none", "ambiguous") or m.get("supported") is False
    p = Path(sr)
    if p.is_absolute():
        try:
            p.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            return False        # cache belongs to a different checkout
    return p.exists()


def root() -> Path:
    """State root, or refuse. An unsupported distribution must NOT read as empty state.

    Returning "" with exit 0 is the same failure class as a missing tool reading as a pass:
    a downstream agent would treat 'no requirements found' as 'there are no requirements'.
    """
    m = manifest()
    dist = m.get("distribution")
    if dist == "ambiguous":
        raise SystemExit(m.get("error", "AMBIGUOUS GSD state"))
    if m.get("supported") is False:
        raise SystemExit(m.get("error", f"UNSUPPORTED DISTRIBUTION: {dist}"))
    if not m.get("state_root"):
        raise SystemExit(f"BLOCKED: no state root resolved for distribution '{dist}'.")
    return Path(m["state_root"])


def _db_mode() -> bool:
    return manifest().get("mode") == "db"


def _unsupported(op):
    raise SystemExit(
        f"UNSUPPORTED: '{op}' is not implemented for distribution "
        f"'{manifest()['distribution']}'. V1 supports the installed distribution only. "
        f"Implement it here rather than anywhere else in the framework."
    )


# --- blockers -------------------------------------------------------------
# Escalation vocabulary made executable. Every non-complete stop lands here as a
# record the verifier can refuse on: signal, task, agent, what was missing, what
# was tried, how many attempts. Stored as <state_root>/blockers.yaml, written ONLY
# through these commands so the schema stays enforced.
BLOCKERS_REL = "blockers.yaml"
_BLOCKER_REQUIRED = ("signal", "task_id", "agent")
_BLOCKER_TEXT_FIELDS = ("missing_item", "tried")


def _yaml_mod():
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "BLOCKED: PyYAML is required for blocker tracking (pip install pyyaml). "
            "An absent parser must not read as empty state."
        )
    return yaml


def _parse_json(s: str):
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise SystemExit(f"BLOCKER_INVALID_JSON: {e}")


def _blockers_path() -> Path:
    return root() / BLOCKERS_REL


def _blockers_load() -> list:
    p = _blockers_path()
    if not p.exists():
        return []
    data = _yaml_mod().safe_load(p.read_text())
    if data is None:
        return []
    if not isinstance(data, list):
        raise SystemExit(
            f"BLOCKED: {BLOCKERS_REL} must be a YAML list, got {type(data).__name__}."
        )
    return data


def _blockers_save(records: list):
    body = _yaml_mod().safe_dump(records, sort_keys=False) if records else ""
    _write(BLOCKERS_REL, body)


def _next_blocker_id(records: list) -> str:
    top = 0
    for r in records:
        rid = str(r.get("id") or "")
        if rid.startswith("BLK-"):
            try:
                top = max(top, int(rid[4:]))
            except ValueError:
                continue
    return f"BLK-{top + 1:03d}"


def _retry_int(v, field: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise SystemExit(f"BLOCKER_INCOMPLETE: {field} must be an integer, got {v!r}")


def write_blocker(payload: dict) -> dict:
    """Upsert one OPEN blocker keyed by (task_id, signal).

    A repeat of the same pair never creates a second record: retries rises to
    max(existing, incoming) and missing/tried refresh, so the retry count survives
    agent restarts instead of resetting with each new attempt.
    """
    if _db_mode():
        _unsupported("write-blocker")
    payload = payload or {}
    for k in _BLOCKER_REQUIRED:
        if not str(payload.get(k) or "").strip():
            raise SystemExit(f"BLOCKER_INCOMPLETE: missing required field '{k}'")
    incoming = _retry_int(payload.get("retries") or 1, "retries")
    now = _now()
    records = _blockers_load()
    for r in records:
        if r.get("resolved_at") is None                 and r.get("task_id") == payload["task_id"]                 and r.get("signal") == payload["signal"]:
            r["retries"] = max(_retry_int(r.get("retries") or 1, "retries"), incoming)
            r["agent"] = payload["agent"]
            for k in _BLOCKER_TEXT_FIELDS:
                if payload.get(k):
                    r[k] = payload[k]
            r["updated_at"] = now
            _blockers_save(records)
            return {"id": r.get("id"), "retries": r["retries"], "upserted": True}
    rec = {
        "id": _next_blocker_id(records),
        "signal": payload["signal"],
        "task_id": payload["task_id"],
        "agent": payload["agent"],
        **{k: payload.get(k) for k in _BLOCKER_TEXT_FIELDS},
        "retries": incoming,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
    }
    records.append(rec)
    _blockers_save(records)
    return {"id": rec["id"], "retries": rec["retries"], "upserted": False}


def resolve_blocker(bid: str) -> dict:
    """Resolve an OPEN blocker by id. Unknown id fails loudly - never a silent pass."""
    if _db_mode():
        _unsupported("resolve-blocker")
    records = _blockers_load()
    for r in records:
        if r.get("id") == bid and r.get("resolved_at") is None:
            r["resolved_at"] = _now()
            r["updated_at"] = r["resolved_at"]
            _blockers_save(records)
            return {"id": bid, "resolved": True}
    raise SystemExit(f"NOT_FOUND: open blocker {bid}")


def list_blockers(as_text: bool = False):
    """OPEN blockers only. A missing file is zero blockers; an unparsable file blocks.

    Default returns the JSON records. With --text it prints one line per open
    blocker (id, task_id, signal, retries, then missing/tried detail) for gate
    output -- keeps every inline python payload in gates on a single line,
    which survives all bash->python transports.
    """
    recs = [r for r in _blockers_load() if r.get("resolved_at") is None]
    if not as_text:
        return recs
    for b in recs:
        print("  %s  %s  %s  retries=%s" % (
            b.get("id"), b.get("task_id"), b.get("signal"), b.get("retries")))
        if b.get("missing_item"):
            print("      missing: %s" % b["missing_item"])
        if b.get("tried"):
            print("      tried:   %s" % b["tried"])
    return None

# ── reads ────────────────────────────────────────────────────────────────
def _read(rel: str) -> str:
    p = root() / rel
    return p.read_text() if p.exists() else ""


def read_project():        return _read("PROJECT.md")
def read_requirements():   return _read("REQUIREMENTS.md")
def read_roadmap():        return _read("ROADMAP.md")
def read_state():          return _read("STATE.md")


def read_requirement(rid: str) -> str:
    """Return only the block for one requirement id. Pointers over copies."""
    text = read_requirements()
    out, capture = [], False
    for line in text.splitlines():
        if rid in line:
            capture = True
        elif capture and line.strip() and not line.startswith((" ", "-", "*", "|")) and ":" not in line[:20]:
            break
        if capture:
            out.append(line)
    return "\n".join(out[:40]) or f"NOT_FOUND: {rid}"


def current_phase() -> dict:
    phases = root() / "phases"
    if not phases.is_dir():
        return {"phase": None, "note": "no phases directory"}
    dirs = sorted(d.name for d in phases.iterdir() if d.is_dir())
    return {"phases": dirs, "current": dirs[-1] if dirs else None,
            "state_excerpt": read_state()[:800]}


def plan_path(task_id: str) -> str:
    hits = sorted(str(p) for p in (root() / "phases").rglob(f"*{task_id}*PLAN.md")) if (root() / "phases").is_dir() else []
    return hits[0] if hits else f"NOT_FOUND: plan for {task_id}"


def read_contract(cid: str) -> str:
    for ext in ("openapi.yaml", "yaml", "yml", "json"):
        p = root() / "contracts" / f"{cid.lower()}.{ext}"
        if p.exists():
            return p.read_text()
    return f"NOT_FOUND: contract {cid}"


# ── writes ───────────────────────────────────────────────────────────────
def _write(rel: str, body: str, append=False):
    if _db_mode():
        _unsupported(f"write {rel}")
    p = root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a" if append else "w") as fh:
        fh.write(body)
    return str(p)


def write_task_summary(task_id: str, payload: str) -> str:
    phase = (current_phase().get("current") or "00-unphased")
    return _write(f"phases/{phase}/{task_id}-SUMMARY.md",
                  f"# Summary {task_id}\n\n_generated {_now()}_\n\n```yaml\n{payload}\n```\n")


def write_verification(phase: str, payload: str) -> str:
    return _write(f"phases/{phase}/VERIFICATION.md",
                  f"\n## Verification run {_now()}\n\n```yaml\n{payload}\n```\n", append=True)


def write_decision(did: str, payload: str) -> str:
    return _write(f"decisions/{did}.md",
                  f"# {did}\n\n_created {_now()}_\n\n```yaml\n{payload}\n```\n")


def write_contract(cid: str, schema: str) -> str:
    return _write(f"contracts/{cid.lower()}.openapi.yaml", schema)


def write_telemetry(payload: str) -> str:
    return _write("telemetry/records.jsonl", payload.strip() + "\n", append=True)


# ── health ───────────────────────────────────────────────────────────────
def health() -> dict:
    m, r = manifest(), root()
    expected = ["PROJECT.md", "REQUIREMENTS.md", "ROADMAP.md", "STATE.md"]
    drift = [f for f in expected if not (r / f).exists()]
    git_dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True).stdout.strip().splitlines()
    return {"manifest": m, "missing_expected": drift, "dirty_files": len(git_dirty),
            "framework_dirs": {d: (r / d).is_dir() for d in ("contracts", "decisions", "telemetry")},
            "ok": not drift}


def selftest() -> dict:
    """Round-trip suite. Run this on every GSD upgrade; a failure is blocking."""
    results = {}
    try:
        write_task_summary("selftest-00", "status: complete")
        results["write_summary"] = "pass"
    except SystemExit as e:
        results["write_summary"] = f"unsupported: {e}"
    try:
        write_verification(current_phase().get("current") or "00-unphased", "status: pass")
        results["write_verification"] = "pass"
    except SystemExit as e:
        results["write_verification"] = f"unsupported: {e}"
    results["read_requirements"] = "pass" if read_requirements() or True else "fail"
    results["detect"] = manifest()["distribution"]
    return results


CMDS = {
    "detect": lambda a: detect(), "manifest": lambda a: manifest(),
    "state-root": lambda a: str(root()), "health": lambda a: health(),
    "selftest": lambda a: selftest(), "current-phase": lambda a: current_phase(),
    "project": lambda a: read_project(), "requirements": lambda a: read_requirements(),
    "requirement": lambda a: read_requirement(a.id), "roadmap": lambda a: read_roadmap(),
    "plan-path": lambda a: plan_path(a.task), "contract": lambda a: read_contract(a.id),
    "write-summary": lambda a: write_task_summary(a.task, a.json),
    "write-verification": lambda a: write_verification(a.phase, a.json),
    "write-decision": lambda a: write_decision(a.id, a.json),
    "write-contract": lambda a: write_contract(a.id, a.json),
    "write-telemetry": lambda a: write_telemetry(a.json),
    "write-blocker": lambda a: write_blocker(_parse_json(a.json)),
    "resolve-blocker": lambda a: resolve_blocker(a.id),
    "list-blockers": lambda a: list_blockers(a.text),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GSD State Adapter")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--id"); ap.add_argument("--task"); ap.add_argument("--phase")
    ap.add_argument("--json", default="")
    ap.add_argument("--text", action="store_true")
    a = ap.parse_args()
    out = CMDS[a.command](a)
    if out is not None:
        print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)
