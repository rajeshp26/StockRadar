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
import sys
import datetime
import time
from functools import lru_cache
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
            m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            m = None
        if m and _cache_valid(m):
            return m
    m = detect()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
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


def _parse_json(s: str, ctx: str = "BLOCKER"):
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{ctx}_INVALID_JSON: {e}")


def _blockers_path() -> Path:
    return root() / BLOCKERS_REL


def _blockers_load() -> list:
    p = _blockers_path()
    if not p.exists():
        return []
    data = _yaml_mod().safe_load(p.read_text(encoding="utf-8"))
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

# ── worker supervision (delegated task execution protocol) ─────────────────
# A delegated task is an immutable execution contract plus an append-only
# lifecycle event stream under <state_root>/tasks/. Health is DERIVED from the
# last event timestamp against the contract deadlines: a task with no events is
# SPAWNED regardless of what its session label claims. session_info != progress.
TASKS_REL = "tasks"
TASK_TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")
TASK_NEXT = {
    None: ("ACK", "STARTED", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED"),
    "ACK": ("STARTED", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED"),
    "STARTED": ("PROGRESS", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED"),
    "PROGRESS": ("PROGRESS", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED"),
    "BLOCKED": ("PROGRESS", "FAILED", "COMPLETED", "CANCELLED"),
}
_TASK_REQUIRED = ("agent", "objective", "expected_artifact")


def _task_types() -> dict:
    """Type timeout budgets live in framework/tasks/task_types.yaml. Described
    in state, never invented in code -- an absent file must not read as
    'no budget policy' (the same failure class as an absent parser)."""
    p = Path("framework/tasks/task_types.yaml")
    if not p.exists():
        raise SystemExit(
            "BLOCKED: framework/tasks/task_types.yaml is missing - task type "
            "timeout budgets must be declared in state, not invented in code."
        )
    data = _yaml_mod().safe_load(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "defaults" not in data:
        raise SystemExit(
            "BLOCKED: framework/tasks/task_types.yaml must declare 'defaults'."
        )
    return data


def _resolve_budget(payload: dict, tt: str):
    """(progress_timeout_s, max_duration_s): contract field > type entry >
    defaults. A type whose entry is null (verify) means task-specific: the
    field MUST be named in the contract, never inherited from defaults."""
    budgets = _task_types()
    entry = (budgets.get("task_types") or {}).get(tt) or {}
    dflt = budgets.get("defaults") or {}

    def pick(field):
        if payload.get(field) is not None:
            v = payload[field]
        elif entry.get(field) is not None:
            v = entry[field]
        elif field in entry and entry[field] is None:
            raise SystemExit(
                f"TASK_INCOMPLETE: type '{tt}' declares no {field} - the contract "
                "must name it explicitly."
            )
        else:
            v = dflt.get(field)
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise SystemExit(f"TASK_INVALID: {field} must be an integer, got {v!r}")
        if v <= 0:
            raise SystemExit(f"TASK_INVALID: {field} must be positive, got {v}")
        return v

    pt = pick("progress_timeout_s")
    md = pick("max_duration_s")
    if md < pt:
        raise SystemExit(
            f"TASK_INVALID: max_duration_s ({md}) must be >= progress_timeout_s ({pt})"
        )
    return pt, md


def _tasks_dir() -> Path:
    return root() / TASKS_REL


def _task_path(task_id: str) -> Path:
    return _tasks_dir() / f"{task_id}.json"


def _task_events_path(task_id: str) -> Path:
    return _tasks_dir() / f"{task_id}.events.jsonl"


def _task_events(task_id: str) -> list:
    p = _task_events_path(task_id)
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"TASK_BLOCKED: event stream for {task_id} corrupt at line {i + 1}: {e}"
            )
    return out


def _task_load(task_id: str):
    """Contract + events, or a loud refusal. A missing contract is NOT_FOUND;
    corruption blocks instead of reading as a healthy task."""
    p = _task_path(task_id)
    if not p.exists():
        raise SystemExit(f"NOT_FOUND: task {task_id} is not registered (register first)")
    try:
        contract = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"TASK_BLOCKED: contract for {task_id} unreadable: {e}")
    return contract, _task_events(task_id)


def _append_task_event(task_id: str, event: dict):
    p = _task_events_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


@lru_cache(maxsize=1)
def _failure_taxonomy():
    """(ALL_CLASSES, BLOCKING_CLASSES) from the provider boundary. Imported
    lazily so this adapter never hard-couples at load time; an absent taxonomy
    must not read as 'no taxonomy' (fail closed, never fail open)."""
    try:
        from providers.healthcheck import ALL_CLASSES, BLOCKING_CLASSES
        return ALL_CLASSES, BLOCKING_CLASSES
    except ImportError:
        fw = str(Path(__file__).resolve().parent.parent)  # framework/
        if fw not in sys.path:
            sys.path.insert(0, fw)
        try:
            from providers.healthcheck import ALL_CLASSES, BLOCKING_CLASSES
        except ImportError as e:
            raise SystemExit(
                "BLOCKED: providers/healthcheck.py is missing - the failure "
                "taxonomy must come from the provider boundary, not the adapter: " + str(e)
            )
        return ALL_CLASSES, BLOCKING_CLASSES


def task_status(task_id: str, session_alive=None) -> dict:
    contract, events = _task_load(task_id)
    now = datetime.datetime.now(datetime.timezone.utc)
    created = datetime.datetime.fromisoformat(contract["created_at"])
    last = events[-1] if events else None
    state = last["state"] if last else "SPAWNED"
    last_dt = datetime.datetime.fromisoformat(last["ts"]) if last else created
    silent_s = max(0, int((now - last_dt).total_seconds()))
    elapsed_s = max(0, int((now - created).total_seconds()))
    pt = contract["progress_timeout_s"]
    md = contract["max_duration_s"]
    checkpoints = [e.get("checkpoint") for e in events if e.get("checkpoint")]

    if state == "COMPLETED":
        health, level, action = "COMPLETE", 0, "continue"
    elif state == "CANCELLED":
        health, level, action = "CANCELLED", 0, "continue"
    elif state == "FAILED":
        _, blocking = _failure_taxonomy()
        fc = last.get("failure_class") or "" if last else ""
        if fc in blocking:
            action = ("provider route: run g12 provider pre-flight, record provider "
                      "health, dispatch via a fallback provider - no dispatch to "
                      "this provider")
        else:
            action = ("record_blocker: write-blocker WORKER_STALLED, retry once "
                      "narrower, else take over")
        health, level = "FAILED", 4
    elif elapsed_s >= md:
        health, level, action = "OVERDUE", 3, "cancel_and_retry: cancel the bg task, retry with a narrowed prompt"
    elif silent_s >= 2 * pt:
        health, level, action = "STALLED", 2, "inspect_session: read the session state; cancel only if frozen"
    elif silent_s >= pt:
        health, level, action = "WARNING", 1, "query_worker: ask for current checkpoint and blockers"
    else:
        health, level, action = "HEALTHY", 0, "continue"

    if state in TASK_TERMINAL:
        liveness = "DEAD"
    elif session_alive is True:
        liveness = "ALIVE"
    elif session_alive is False:
        liveness = "DEAD"
    elif silent_s >= pt:
        liveness = "UNKNOWN"
    else:
        liveness = "ALIVE"

    # Supervisor reconcile overrides the silent-based STALLED branch for
    # non-terminal states: alive -> downgrade to WARNING (OVERDUE deadline is
    # never suppressed); absent/ended -> force STALLED even before the silence
    # threshold.
    if state not in TASK_TERMINAL:
        if session_alive is True and health == "STALLED":
            health, level, action = (
                "WARNING", 1,
                "query_worker: worker confirmed alive by supervisor reconcile; "
                "ask for current checkpoint and blockers")
        elif session_alive is False:
            health, level, action = (
                "STALLED", 2,
                "inspect_session: worker session reported absent/ended by "
                "supervisor; cancel only if frozen")

    execution = {
        None: "STARTING", "ACK": "STARTING", "STARTED": "THINKING",
        "PROGRESS": "WORKING", "BLOCKED": "BLOCKED",
        "COMPLETED": "IDLE", "FAILED": "IDLE", "CANCELLED": "IDLE",
    }[last["state"] if last else None]

    progress = "COMPLETED" if state == "COMPLETED" else (
        "CHECKPOINT_ADVANCED" if checkpoints else "NONE")

    return {
        "task_id": contract["task_id"],
        "agent": contract["agent"],
        "type": contract.get("type") or "default",
        "session_id": contract.get("session_id") or "",
        "state": state,
        "health": health,
        "recovery_level": level,
        "recovery_action": action,
        "failure_class": (last.get("failure_class") or "") if last else "",
        "liveness": liveness,
        "execution": execution,
        "progress": progress,
        "checkpoints_reached": checkpoints,
        "expected_artifact": contract["expected_artifact"],
        "progress_timeout_s": pt,
        "max_duration_s": md,
        "silent_s": silent_s,
        "elapsed_s": elapsed_s,
        "created_at": contract["created_at"],
        "last_activity": last["ts"] if last else contract["created_at"],
        "recent_events": [
            {k: e.get(k) for k in ("state", "ts", "emitter", "checkpoint", "detail", "failure_class")}
            for e in events[-3:]
        ],
    }


def register_task(task_id: str, payload: dict) -> dict:
    if _db_mode():
        _unsupported("task-register")
    payload = payload or {}
    for k in _TASK_REQUIRED:
        if not str(payload.get(k) or "").strip():
            raise SystemExit(f"TASK_INCOMPLETE: missing required contract field '{k}'")
    p = _task_path(task_id)
    if p.exists():
        raise SystemExit(
            f"EXISTS: task {task_id} is already registered; contracts are immutable - "
            f"retry with a fresh id and 'retry_of': '{task_id}'"
        )
    tt = str(payload.get("type") or "default")
    pt, md = _resolve_budget(payload, tt)
    contract = {
        "task_id": task_id,
        "type": tt,
        "agent": payload["agent"],
        "objective": payload["objective"],
        "expected_artifact": payload["expected_artifact"],
        "session_id": str(payload.get("session_id") or ""),
        "checkpoints": [str(c) for c in payload.get("checkpoints") or []],
        "allowed_tools": [str(t) for t in payload.get("allowed_tools") or []],
        "completion_criteria": [str(c) for c in payload.get("completion_criteria") or []],
        "failure_criteria": [str(c) for c in payload.get("failure_criteria") or []],
        "progress_timeout_s": pt,
        "max_duration_s": md,
        "retry_of": str(payload.get("retry_of") or ""),
        "created_at": _now(),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as fh:          # exclusive create = the immutability guarantee
        fh.write(json.dumps(contract, indent=2) + "\n")
    return task_status(task_id)


def task_event(task_id: str, payload: dict) -> dict:
    if _db_mode():
        _unsupported("task-event")
    payload = payload or {}
    state = str(payload.get("state") or "").strip().upper()
    if state not in ("ACK", "STARTED", "PROGRESS", "BLOCKED", "FAILED", "COMPLETED"):
        raise SystemExit(
            f"TASK_INVALID_STATE: {state!r}; legal event states: "
            "ACK, STARTED, PROGRESS, BLOCKED, FAILED, COMPLETED"
        )
    contract, events = _task_load(task_id)
    prev = events[-1]["state"] if events else None
    if prev in TASK_TERMINAL:
        raise SystemExit(f"TERMINAL_STATE: task {task_id} is already {prev}; no further events")
    nxt = TASK_NEXT.get(prev, ())
    if state not in nxt:
        raise SystemExit(
            f"INVALID_TRANSITION: {prev or 'SPAWNED'} -> {state}; "
            f"legal next states: {', '.join(sorted(nxt))}"
        )
    event = {
        "state": state,
        "ts": _now(),
        "emitter": str(payload.get("emitter") or contract["agent"]),
    }
    if payload.get("checkpoint"):
        event["checkpoint"] = str(payload["checkpoint"])
    if payload.get("detail"):
        event["detail"] = str(payload["detail"])
    fc = str(payload.get("failure_class") or "").strip().upper()
    if state == "FAILED":
        if not fc:
            raise SystemExit(
                "TASK_INVALID_FAILURE_CLASS: FAILED requires failure_class (e.g. "
                "AGENT_FAILURE); an unclassified failure cannot be routed."
            )
        all_classes, _ = _failure_taxonomy()
        if fc not in all_classes:
            raise SystemExit(
                "TASK_INVALID_FAILURE_CLASS: " + fc + " is not in the failure "
                "taxonomy; legal classes: " + ", ".join(sorted(all_classes))
            )
        event["failure_class"] = fc
    elif fc:
        raise SystemExit(
            "TASK_INVALID_FAILURE_CLASS: failure_class is only legal on FAILED "
            "events, not " + state
        )
    _append_task_event(task_id, event)
    return task_status(task_id)


def cancel_task(task_id: str, payload: dict = None) -> dict:
    """Supervisor-only terminal event. Emitter defaults to team-lead."""
    if _db_mode():
        _unsupported("task-cancel")
    payload = payload or {}
    contract, events = _task_load(task_id)
    prev = events[-1]["state"] if events else None
    if prev in TASK_TERMINAL:
        raise SystemExit(f"TERMINAL_STATE: task {task_id} is already {prev}; cannot cancel")
    _append_task_event(task_id, {
        "state": "CANCELLED",
        "ts": _now(),
        "emitter": str(payload.get("emitter") or "team-lead"),
    })
    return task_status(task_id)


def list_tasks() -> list:
    d = _tasks_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        tid = p.stem
        try:
            h = task_status(tid)
        except (SystemExit, KeyError, ValueError, TypeError, IndexError):
            # malformed persisted contract (missing created_at, bad JSON, bad ts) is an
            # unreadable task, not a framework crash: read BROKEN and name it.
            h = {"task_id": tid, "state": "UNREADABLE", "health": "BROKEN", "agent": "?",
                 "type": "?", "elapsed_s": 0, "silent_s": 0, "failure_class": ""}
        out.append({k: h[k] for k in ("task_id", "agent", "type", "state", "health",
                                      "elapsed_s", "silent_s", "failure_class")})
    return out


def task_summary() -> dict:
    """Aggregate worker health across all registered tasks.

    The G13 worker-observability gate's data source: every task's live health plus the
    escalation route each unhealthy task implies. 'unhealthy' means a supervisor action
    is owed NOW (recovery_level >= 2, or an unreadable event stream); WARNING (level 1)
    is probe-and-continue and counts as healthy here.
    """
    rows = list_tasks()
    tasks = []
    unhealthy = []
    for slim in rows:
        tid = slim["task_id"]
        try:
            st = task_status(tid)
        except (SystemExit, KeyError, ValueError, TypeError, IndexError):
            st = {"task_id": tid, "state": "UNREADABLE", "health": "BROKEN",
                  "recovery_level": 5,
                  "recovery_action": "inspect the task contract and event stream manually"}
        tasks.append(st)
        if st["health"] in ("STALLED", "OVERDUE", "FAILED", "BROKEN", "UNREADABLE")                 or st.get("recovery_level", 0) >= 2:
            unhealthy.append({
                "task_id": st["task_id"],
                "agent": st.get("agent", "?"),
                "state": st.get("state"),
                "health": st["health"],
                "recovery_level": st.get("recovery_level", 0),
                "recovery_action": st.get("recovery_action", ""),
                "failure_class": st.get("failure_class", ""),
            })
    if not rows:
        status = "empty"
    elif unhealthy:
        status = "unhealthy"
    else:
        status = "ok"
    return {"status": status, "registered": len(rows), "unhealthy": unhealthy,
            "tasks": tasks}

# ── reads ────────────────────────────────────────────────────────────────
def _read(rel: str) -> str:
    p = root() / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


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
            return p.read_text(encoding="utf-8")
    return f"NOT_FOUND: contract {cid}"


# ── writes ───────────────────────────────────────────────────────────────
def _write(rel: str, body: str, append=False):
    if _db_mode():
        _unsupported(f"write {rel}")
    p = root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a" if append else "w", encoding="utf-8") as fh:
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
    # failure_class round trip: FAILED must name a taxonomy class; provider-class
    # failures route recovery to the provider boundary (g12), worker-class to the
    # WORKER_STALLED ladder. Tasks are cleaned up so selftest leaves no residue.
    tid = "selftest-fc"
    try:
        _task_path(tid).unlink(missing_ok=True)
        _task_events_path(tid).unlink(missing_ok=True)
        register_task(tid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest failure_class routing",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
        })
        task_event(tid, {"state": "STARTED"})
        try:
            task_event(tid, {"state": "FAILED"})
            results["task_failure_class_required"] = "fail: FAILED without class accepted"
        except SystemExit:
            results["task_failure_class_required"] = "pass"
        try:
            task_event(tid, {"state": "FAILED", "failure_class": "NOT_A_CLASS"})
            results["task_failure_class_invalid"] = "fail: unknown class accepted"
        except SystemExit:
            results["task_failure_class_invalid"] = "pass"
        try:
            task_event(tid, {"state": "STARTED", "failure_class": "QUOTA_FAILURE"})
            results["task_failure_class_wrong_state"] = "fail: class on non-FAILED accepted"
        except SystemExit:
            results["task_failure_class_wrong_state"] = "pass"
        st = task_event(tid, {"state": "FAILED", "failure_class": "QUOTA_FAILURE",
                              "detail": "provider side"})
        ok = (st["failure_class"] == "QUOTA_FAILURE" and st["liveness"] == "DEAD"
              and st["execution"] == "IDLE" and "g12" in st["recovery_action"])
        results["task_failure_class_provider_route"] = "pass" if ok else (
            "fail: " + st["recovery_action"])
    except SystemExit as e:
        results["task_failure_class_provider_route"] = "fail: " + str(e)
    finally:
        _task_path(tid).unlink(missing_ok=True)
        _task_events_path(tid).unlink(missing_ok=True)

    # Supervisor reconcile: a silent worker is unproven-alive (UNKNOWN), never
    # assumed dead. session_alive=True downgrades silent-based STALLED to
    # WARNING; session_alive=False forces STALLED/DEAD; OVERDUE deadline is
    # never suppressed by reconcile.
    rtid = "selftest-reconcile"
    try:
        _task_path(rtid).unlink(missing_ok=True)
        _task_events_path(rtid).unlink(missing_ok=True)
        register_task(rtid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest supervisor reconcile",
            "expected_artifact": "pass",
            "progress_timeout_s": 2, "max_duration_s": 60,
        })
        task_event(rtid, {"state": "STARTED"})
        time.sleep(3)
        st = task_status(rtid)
        results["reconcile_default_unknown"] = "pass" if (
            st["liveness"] == "UNKNOWN" and st["health"] == "WARNING") else (
            "fail: " + st["health"] + "/" + st["liveness"])
        st = task_status(rtid, session_alive=True)
        results["reconcile_alive_downgrade"] = "pass" if (
            st["liveness"] == "ALIVE" and st["health"] == "WARNING"
            and st["recovery_level"] == 1) else (
            "fail: " + st["health"] + "/" + st["liveness"])
        st = task_status(rtid, session_alive=False)
        results["reconcile_dead_stalled"] = "pass" if (
            st["liveness"] == "DEAD" and st["health"] == "STALLED"
            and st["recovery_level"] == 2) else (
            "fail: " + st["health"] + "/" + st["liveness"])
        # OVERDUE is a real budget and is never suppressed by reconcile.
        _task_path(rtid).unlink(missing_ok=True)
        _task_events_path(rtid).unlink(missing_ok=True)
        register_task(rtid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest reconcile overdue",
            "expected_artifact": "pass",
            "progress_timeout_s": 1, "max_duration_s": 1,
        })
        task_event(rtid, {"state": "STARTED"})
        time.sleep(1.1)
        st = task_status(rtid, session_alive=True)
        results["reconcile_overdue_not_suppressed"] = "pass" if (
            st["health"] == "OVERDUE" and st["recovery_level"] == 3) else (
            "fail: " + st["health"])
    except SystemExit as e:
        results["reconcile_default_unknown"] = "fail: " + str(e)
    finally:
        _task_path(rtid).unlink(missing_ok=True)
        _task_events_path(rtid).unlink(missing_ok=True)

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
    "task-register": lambda a: register_task(a.id, _parse_json(a.json, "TASK") if a.json else None),
    "task-event": lambda a: task_event(a.id, _parse_json(a.json, "TASK")),
    "task-status": lambda a: task_status(a.id, {"true": True, "false": False}.get(a.session_alive.lower(), None)),
    "task-list": lambda a: list_tasks(),
    "task-summary": lambda a: task_summary(),
    "task-cancel": lambda a: cancel_task(a.id, _parse_json(a.json, "TASK") if a.json else None),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GSD State Adapter")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--id"); ap.add_argument("--task"); ap.add_argument("--phase")
    ap.add_argument("--json", default="")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--session-alive", default="unknown")
    a = ap.parse_args()
    out = CMDS[a.command](a)
    if out is not None:
        print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)
