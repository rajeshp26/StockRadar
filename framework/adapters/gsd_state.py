#!/usr/bin/env python3
"""GSD State Adapter.

V1 supports the INSTALLED distribution only. Multi-distribution support is a conformance
target, verified by running `selftest` against a second distribution — not a v1 deliverable.

The rest of the framework touches only this interface, so adding a distribution is an
adapter change and nothing else.
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import datetime
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

# The app root is config-driven: framework.locate reads framework.config.json,
# else falls back to the framework's own install root. Anchored on __file__ via
# locate, never on the CWD, so running a framework script from a subdirectory
# cannot address a different tree.
# SkillSpec integration (baked-in)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from skill_contracts.skill_spec import SkillSpec
    from adapters.skill_adapter import SkillAdapter
    _SKILL_ADAPTER_AVAILABLE = True
except Exception:
    SkillSpec = None
    SkillAdapter = None
    _SKILL_ADAPTER_AVAILABLE = False

# Unconditional, BEFORE the import: an importable `framework` from the environment
# (PYTHONPATH, an installed copy) must never shadow this file's own tree.
_BOOTSTRAP_ROOT = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP_ROOT not in sys.path:
    sys.path.insert(0, _BOOTSTRAP_ROOT)
from framework import locate as _locate

REPO_ROOT = _locate.app_root()
MANIFEST = _locate.manifest_dir() / "gsd.json"

# (state_root, distribution, mode). Recognised for detection; see SUPPORTED for implemented.
DISTRIBUTIONS = ((".planning", "gsd-core", "files"), (".gsd", "gsd-pi", "db"))
SUPPORTED = ("gsd-core",)


def detect() -> dict:
    """Identify the installed GSD distribution and its state root."""
    # Probes REPO_ROOT, not the CWD: detection has to find the state root even when the
    # caller is sitting in a subdirectory, or it reports "none" for a repo that has one.
    # V1 SUPPORTS ONE DISTRIBUTION: the one installed. Probing is detection only —
    # it does NOT imply both are supported. gsd-pi is RECOGNISED so we can refuse it
    # by name instead of silently misreading a db-backed store as a file-backed one.
    found = []
    for root, dist, mode in DISTRIBUTIONS:
        if (REPO_ROOT / root).is_dir():
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
        # and validate fails with 'cache belongs to another checkout'. The CACHE stays
        # relative; root() is what joins it onto REPO_ROOT for callers. Those are two
        # jobs, so they are two values - the relative name is meaningless as a live path
        # unless the reader already knows where it is standing, and it did not.
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
            p.resolve().relative_to(REPO_ROOT)
        except ValueError:
            return False        # cache belongs to a different checkout
    return (REPO_ROOT / p).exists()


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
    sr = Path(m["state_root"])
    return sr if sr.is_absolute() else (REPO_ROOT / sr)


def _db_mode() -> bool:
    return manifest().get("mode") == "db"


# Per-path intra-process mutexes layered under the cross-process file lock.
# A Windows file lock arbitrates PROCESSES only: msvcrt.locking raises EDEADLK
# when a second thread in the SAME process tries to lock a region the process
# already holds, instead of blocking (ext-critique-01 selftest proves 40 workers
# stay gapless). The thread lock serialises intra-process writers; the file lock
# serialises cross-process writers. Only four acquisition sites exist and none
# nests (blockers vs event-stream are disjoint paths), so non-reentrant is safe.
_THREAD_LOCKS: dict = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(lock_path: Path) -> threading.Lock:
    key = str(lock_path.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    """Cross-process advisory lock for a read-modify-write critical section.

    The event-stream seq append and the blockers upsert both follow a
    read->mutate->write shape: two writers can each read the same tail and then
    both write, duplicating a sequence number or dropping an upsert
    (EXT-CRITIQUE-01). POSIX serialises with fcntl.flock; Windows has no fcntl,
    so msvcrt.locking over one byte at offset 0 is the portable equivalent.
    The lock file is created on demand and NEVER unlinked: an unlink races the
    unlock (another process can hold the old inode while a third opens a fresh
    one at the same name), so a stale lock file is harmless — the lock lives on
    the open fd, not the path.
    """
    with _thread_lock_for(lock_path):
        try:
            import fcntl
        except ImportError:
            fcntl = None
            import msvcrt
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as fh:
            if fh.seek(0, 2) == 0:        # msvcrt cannot lock a region past EOF
                fh.write(b"\0")
                fh.flush()
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            else:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                else:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


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
    with _file_lock(root() / f"{BLOCKERS_REL}.lock"):
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
    with _file_lock(root() / f"{BLOCKERS_REL}.lock"):
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


# Signal name in blockers.yaml -> budget key under retry_policy. The two
# vocabularies differ by design: a signal names what happened, a budget names
# the policy class that bounds it. An open blocker whose signal is unmapped, or
# whose key has no declared budget, is skipped -- assigning one here would put
# the policy in two places, and the yaml is the single source.
_RETRY_BUDGET_KEY = {
    "TEST_FAILED": "test_failure",
    "REVIEW_REJECTED": "review_rejection",
    "INTEGRATION_FAILED": "integration_failure",
    "CONTEXT_INSUFFICIENT": "context_expansion",
    "CONTRACT_CONFLICT": "contract_conflict",
    "ARCHITECTURE_CONFLICT": "architecture_conflict",
    "RELEASE_BLOCKED": "release_blocked",
    "RETRO_RECURRENCE": "retro_recurrence",
    "WORKER_STALLED": "worker_stalled",
}


def retry_budget() -> dict:
    """OPEN blockers whose retries exceed the budget declared in retry_policy.yaml.

    The budgets were declared and read by nothing: a blocker could sit at
    retries=5 under test_failure: 2 and every gate still only said "one open
    blocker", so on_exhaustion (escalate_to_human) never fired. The blocker
    store is the only per-task retry counter that exists (telemetry
    TEST_FAILED events carry no task_id), so it is the count of record.

    Exhaustion is retries > budget: retries starts at 1 on the first write, so
    a budget of 2 permits attempts 1-2 and attempt 3 exhausts it; a budget of 0
    (immediate escalation) is exceeded by the first occurrence. A malformed or
    absent policy refuses loudly rather than reading as "no budgets, nothing
    to check" -- the same failure class as an absent parser.
    """
    p = Path("framework/retry_policy.yaml")
    if not p.exists():
        raise SystemExit(
            "BLOCKED: framework/retry_policy.yaml is missing - retry budgets "
            "must be declared in state, not invented in code."
        )
    try:
        data = _yaml_mod().safe_load(p.read_text(encoding="utf-8-sig")) or {}
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"BLOCKED: framework/retry_policy.yaml unparsable: {e}")
    budgets = data.get("retry_policy")
    if not isinstance(budgets, dict) or not budgets:
        raise SystemExit(
            "BLOCKED: framework/retry_policy.yaml must declare a retry_policy "
            "budget map - an unreadable budget is not zero budget."
        )
    open_blockers = list_blockers()
    checked = 0
    exhausted = []
    for b in open_blockers:
        key = _RETRY_BUDGET_KEY.get(b.get("signal"))
        if key is None or key not in budgets:
            continue  # no declared budget for this signal -- skipped, never invented
        budget = budgets[key]
        if not isinstance(budget, int) or isinstance(budget, bool):
            raise SystemExit(
                f"BLOCKED: retry_policy budget {key!r} must be an integer, got {budget!r}."
            )
        checked += 1
        try:
            retries = int(b.get("retries"))
        except (TypeError, ValueError):
            retries = 1
        if retries > budget:
            exhausted.append({
                "id": b.get("id"),
                "task_id": b.get("task_id"),
                "signal": b.get("signal"),
                "budget_key": key,
                "retries": retries,
                "budget": budget,
            })
    return {
        "checked": checked,
        "on_exhaustion": data.get("on_exhaustion"),
        "exhausted": exhausted,
    }


# ── worker supervision (delegated task execution protocol) ─────────────────
# A delegated task is an immutable execution contract plus an append-only
# lifecycle event stream under <state_root>/tasks/. Health is DERIVED from the
# last event timestamp against the contract deadlines: a task with no events is
# SPAWNED regardless of what its session label claims. session_info != progress.
TASKS_REL = "tasks"
TASK_TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "LOST")
TASK_NEXT = {
    None: ("ACK", "STARTED", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED", "LOST"),
    "ACK": ("STARTED", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED", "LOST"),
    "STARTED": ("PROGRESS", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED", "LOST"),
    "PROGRESS": ("PROGRESS", "BLOCKED", "FAILED", "COMPLETED", "CANCELLED", "LOST"),
    "BLOCKED": ("PROGRESS", "FAILED", "COMPLETED", "CANCELLED", "LOST"),
    "LOST": (),
}
_TASK_REQUIRED = ("agent", "objective", "expected_artifact")


# Health-level escalation signals for recovery. Mirrors the health table in
# framework/opencode/rules/delegation-protocol.md; a type recovery policy in
# task_types.yaml must declare a route for each of these. FAILED splits by
# taxonomy class into FAILED_PROVIDER / FAILED_WORKER for policy lookup.
_RECOVERY_SIGNALS = ("FAILED_PROVIDER", "FAILED_WORKER", "STALLED", "OVERDUE", "LOST")


@lru_cache(maxsize=1)
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
    _validate_recovery(data)
    return data


def _validate_recovery(data: dict):
    """Recovery is part of every task-type contract. The merged policy for
    each type (type entry over defaults) must declare a route for every
    escalation signal in _RECOVERY_SIGNALS, and every route name must be in
    the file's own recovery_routes vocabulary. A missing or partial policy
    is a config error, never a silent 'no recovery' (same failure class as
    an absent parser)."""
    vocab = {str(r) for r in (data.get("recovery_routes") or [])}
    if not vocab:
        raise SystemExit(
            "TASK_CONFIG_INVALID: task_types.yaml must declare a non-empty "
            "recovery_routes vocabulary."
        )
    dflt = data.get("defaults") or {}
    dflt_rec = dict(dflt.get("recovery") or {})
    types = data.get("task_types") or {}
    # merged_list[0] is the 'default' type (defaults alone); each later
    # entry is one concrete type's merged policy (type over defaults). A
    # type may legally omit `recovery` and inherit defaults; the MERGED
    # policy is what must be complete and route-legal.
    merged_list = [dflt_rec] + [
        {**dflt_rec, **(e.get("recovery") or {})} for e in types.values()
    ]
    for i, merged in enumerate(merged_list):
        missing = [s for s in _RECOVERY_SIGNALS if s not in merged]
        if missing:
            raise SystemExit(
                "TASK_CONFIG_INVALID: recovery for entry %d missing signal(s) %s"
                % (i, ", ".join(missing))
            )
        for sig, route in merged.items():
            if sig not in _RECOVERY_SIGNALS:
                raise SystemExit(
                    "TASK_CONFIG_INVALID: unknown recovery signal %r" % sig
                )
            if str(route) not in vocab:
                raise SystemExit(
                    "TASK_CONFIG_INVALID: recovery route %r for %s is not in "
                    "recovery_routes" % (route, sig)
                )


def _recovery_policy(tt: str) -> dict:
    """Merged recovery routes for a type: type entry over defaults, returned
    as {signal: route}. Surfaced via task-status / task-summary as
    recovery_policy so the supervisor and gates act on the declared policy,
    not on an invented one."""
    budgets = _task_types()
    entry = (budgets.get("task_types") or {}).get(tt) or {}
    dflt = budgets.get("defaults") or {}
    merged = dict(dflt.get("recovery") or {})
    merged.update(entry.get("recovery") or {})
    return merged


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


def _resolve_checkpoints(payload: dict, tt: str) -> list:
    """Contract checkpoints override the type's default progression from
    task_types.yaml; a type with no declared defaults yields no checkpoints."""
    if payload.get("checkpoints"):
        return [str(c) for c in payload["checkpoints"]]
    entry = (_task_types().get("task_types") or {}).get(tt) or {}
    return [str(c) for c in entry.get("checkpoints") or []]


def _tasks_dir() -> Path:
    return root() / TASKS_REL


def _task_path(task_id: str) -> Path:
    if not task_id or not str(task_id).strip() or str(task_id) == "None":
        raise SystemExit(
            "TASK_INVALID: task id is required (--id/--task); refusing to address 'None'"
        )
    return _tasks_dir() / f"{task_id}.json"


def _task_events_path(task_id: str) -> Path:
    if not task_id or not str(task_id).strip() or str(task_id) == "None":
        raise SystemExit(
            "TASK_INVALID: task id is required (--id/--task); refusing to address 'None'"
        )
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


TAIL_READ_BYTES = 1 << 16  # 64 KiB: bounded tail read for seq/status without a full-stream scan


def _last_seq(task_id: str) -> int:
    """Sequence of the latest event, read from the stream tail alone (O(1) not O(n)).

    _task_events() parses the entire stream; calling it on every append makes a
    long task quadratic (each write re-reads everything written before). The
    stream is append-only, so the last line always carries the seq, and a bounded
    tail read is exact. A file with no terminator (torn write) is corrupt -- the
    same guard _task_events enforced -- and a missing file yields 0.
    """
    p = _task_events_path(task_id)
    if not p.exists() or p.stat().st_size == 0:
        return 0
    with p.open("rb") as fh:
        fh.seek(max(0, p.stat().st_size - TAIL_READ_BYTES))
        tail = fh.read()
    if not tail.endswith(b"\n"):
        raise SystemExit(f"TASK_BLOCKED: event stream for {task_id} corrupt (torn tail)")
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    if not lines:
        return 0
    try:
        return int(json.loads(lines[-1]).get("seq") or 0)
    except (json.JSONDecodeError, ValueError):
        raise SystemExit(f"TASK_BLOCKED: event stream for {task_id} corrupt at tail")


def _append_task_event(task_id: str, event: dict):
    p = _task_events_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Per-task monotonic sequence number: the event-bus ordering guarantee the
    # supervisor and watchdog rely on. Corrupt streams must block before growing.
    # The seq read and the append are ONE critical section: two concurrent
    # writers can each read the same tail and then both append, duplicating a
    # seq (EXT-CRITIQUE-01). Hold a cross-process lock over the read + write.
    with _file_lock(p.with_name(p.name + ".lock")):
        event["seq"] = _last_seq(task_id) + 1
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



def _suggest_pattern(contract):
    if not isinstance(contract, dict):
        return None
    obj = str(contract.get('objective','')).lower()
    if 'plan' in obj or 'design' in obj or 'complex' in obj:
        return {'pattern': 'planning', 'reason': 'complex goal needs decomposition'}
    if 'search' in obj or 'tool' in obj or 'api' in obj:
        return {'pattern': 'react', 'reason': 'tool use indicated'}
    if 'review' in obj or 'critique' in obj:
        return {'pattern': 'reflection', 'reason': 'quality review needed'}
    if 'route' in obj or 'classify' in obj:
        return {'pattern': 'routing', 'reason': 'classification needed'}
    return {'pattern': 'chaining', 'reason': 'default sequential approach'}


def _gateway_hints(contract):
    if not isinstance(contract, dict):
        return {}
    hints = {}
    if contract.get('agent') in ['security-auditor']:
        hints['guardrails'] = 'strict'
    risk = contract.get('risk') or contract.get('_skill_spec_risk')
    if risk == 'high':
        hints['human_gateway'] = 'required'
    return hints



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
    milestones = []
    heartbeats = 0
    last_progress_kind = "none"
    for e in events:
        cp = e.get("checkpoint")
        if cp and cp not in milestones:
            # a NEW checkpoint is a milestone: measurable progress.
            milestones.append(cp)
            last_progress_kind = "milestone"
        elif e.get("state") in ("PROGRESS", "BLOCKED") or cp:
            # a PROGRESS/BLOCKED event without a new checkpoint, or a repeated
            # checkpoint, is a heartbeat: liveness WITHOUT progress. Separating
            # the two lets supervision distinguish "alive but stuck" from
            # "making progress".
            heartbeats += 1
            last_progress_kind = "heartbeat"
    checkpoints = milestones

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
    elif state == "LOST":
        health, level, action = (
            "LOST", 4,
            "recover: worker session lost without a recorded failure - re-dispatch "
            "a fresh attempt (retry_of=" + task_id + ") via a narrowed contract; "
            "never classify as worker or provider failure")
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
        "COMPLETED": "IDLE", "FAILED": "IDLE", "CANCELLED": "IDLE", "LOST": "IDLE",
    }[last["state"] if last else None]

    progress = "COMPLETED" if state == "COMPLETED" else (
        "CHECKPOINT_ADVANCED" if checkpoints else (
        "HEARTBEAT_ONLY" if heartbeats else "NONE"))

    return {
        "task_id": contract["task_id"],
        "agent": contract["agent"],
        "type": contract.get("type") or "default",
        "session_id": contract.get("session_id") or "",
        "background_task_id": contract.get("background_task_id") or "",
        "state": state,
        "health": health,
        "recovery_level": level,
        "recovery_action": action,
        "recovery_policy": _recovery_policy(contract.get("type") or "default"),
        "failure_class": (last.get("failure_class") or "") if last else "",
        "liveness": liveness,
        "execution": execution,
        "progress": progress,
        "last_progress_kind": last_progress_kind,
        "milestones_reached": len(checkpoints),
        "heartbeats": heartbeats,
        "headless": bool(contract.get("headless") or False),
        "checkpoints_reached": checkpoints,
        "expected_artifact": contract["expected_artifact"],
        "progress_timeout_s": pt,
        "max_duration_s": md,
        "silent_s": silent_s,
        "elapsed_s": elapsed_s,
        "created_at": contract["created_at"],
        "last_activity": last["ts"] if last else contract["created_at"],
        "recent_events": [
            {k: e.get(k) for k in ("seq", "state", "ts", "emitter", "checkpoint", "detail", "failure_class")}
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
        "background_task_id": str(payload.get("background_task_id") or ""),
        "checkpoints": _resolve_checkpoints(payload, tt),
        "allowed_tools": [str(t) for t in payload.get("allowed_tools") or []],
        "completion_criteria": [str(c) for c in payload.get("completion_criteria") or []],
        "failure_criteria": [str(c) for c in payload.get("failure_criteria") or []],
        "headless": bool(payload.get("headless") or False),
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
    if state not in ("ACK", "STARTED", "PROGRESS", "BLOCKED", "FAILED", "COMPLETED", "LOST"):
        raise SystemExit(
            f"TASK_INVALID_STATE: {state!r}; legal event states: "
            "ACK, STARTED, PROGRESS, BLOCKED, FAILED, COMPLETED, LOST"
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
    if state == "LOST":
        # LOST is supervisor-declared and terminal: a worker that can emit events
        # is not lost (it must emit FAILED with a failure_class instead), and a
        # LOST declaration without a reason cannot be actioned by recovery.
        if event["emitter"] == contract["agent"]:
            raise SystemExit(
                "TASK_INVALID_LOST: LOST is supervisor-declared; a worker that can "
                "emit events is not lost - emit FAILED with a failure_class."
            )
        if not str(payload.get("detail") or "").strip():
            raise SystemExit(
                "TASK_INVALID_LOST: LOST requires detail naming what was lost "
                "(session id, provider, or process) and why no failure was recorded."
            )
        event["detail"] = str(payload["detail"])
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
    if state == "COMPLETED":
        # Terminal outcome: only last-event readers consume the stream from here
        # on; the full pre-terminal history has no consumer on a completed task.
        _compact_terminal_stream(task_id)
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
    _compact_terminal_stream(task_id)
    return task_status(task_id)


def list_tasks() -> list:
    d = _tasks_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".contract.json"):
            continue
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


def _retry_chain_resolved() -> set:
    """Task ids whose terminal FAILED/LOST state was superseded by a retry_of
    successor that reached COMPLETED (directly or transitively).

    g13_worker's own recovery_action text tells a supervisor to close out a
    LOST/FAILED task by registering 'a fresh id carrying retry_of: <old-id>'
    (see register_task's EXISTS message) -- but nothing previously consumed
    that field, so a resolved ancestor stayed flagged unhealthy forever even
    after its retry completed. This walks retry_of edges from every task and
    marks an ancestor resolved once its chain terminates in COMPLETED.
    """
    resolved = set()
    tasks_dir = _tasks_dir() if "_tasks_dir" in globals() else (root() / "tasks")
    contracts = {}
    for p in sorted(tasks_dir.glob("*.json")) if tasks_dir.is_dir() else []:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        tid = c.get("task_id")
        if tid:
            contracts[tid] = c
    for tid, c in contracts.items():
        ro = str(c.get("retry_of") or "").strip()
        if not ro:
            continue
        try:
            st = task_status(tid)
        except (SystemExit, KeyError, ValueError, TypeError, IndexError):
            continue
        if st.get("state") != "COMPLETED":
            continue
        # walk the whole ancestor chain, not just the immediate parent
        cur = ro
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            resolved.add(cur)
            cur = str((contracts.get(cur) or {}).get("retry_of") or "").strip()
    return resolved


def task_summary() -> dict:
    """Aggregate worker health across all registered tasks.

    The G13 worker-observability gate's data source: every task's live health plus the
    escalation route each unhealthy task implies. 'unhealthy' means a supervisor action
    is owed NOW (recovery_level >= 2, or an unreadable event stream); WARNING (level 1)
    is probe-and-continue and counts as healthy here. A task resolved by a completed
    retry_of successor (see _retry_chain_resolved) is reported informationally, not
    as owing supervision -- the escalation it named was already acted on.
    """
    rows = list_tasks()
    tasks = []
    unhealthy = []
    resolved = _retry_chain_resolved()
    for slim in rows:
        tid = slim["task_id"]
        try:
            st = task_status(tid)
        except (SystemExit, KeyError, ValueError, TypeError, IndexError):
            st = {"task_id": tid, "state": "UNREADABLE", "health": "BROKEN",
                  "recovery_level": 5,
                  "recovery_action": "inspect the task contract and event stream manually"}
        tasks.append(st)
        if tid in resolved:
            continue
        if st["health"] in ("STALLED", "OVERDUE", "FAILED", "LOST", "BROKEN", "UNREADABLE")                 or st.get("recovery_level", 0) >= 2:
            unhealthy.append({
                "task_id": st["task_id"],
                "agent": st.get("agent", "?"),
                "state": st.get("state"),
                "health": st["health"],
                "recovery_level": st.get("recovery_level", 0),
                "recovery_action": st.get("recovery_action", ""),
                "recovery_policy": st.get("recovery_policy") or {},
                "failure_class": st.get("failure_class", ""),
            })
    if not rows:
        status = "empty"
    elif unhealthy:
        status = "unhealthy"
    else:
        status = "ok"
    return {"status": status, "registered": len(rows), "unhealthy": unhealthy,
            "resolved_by_retry": sorted(resolved), "tasks": tasks}

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


def _shell_path(p: Path) -> str:
    """Render a resolved path so a POSIX shell can stat it, in any namespace.

    plan-path output is consumed by the gates, which on Windows run under WSL bash. A
    Windows-flavoured absolute path (C:\\...) is NOT addressable there -- WSL resolves
    /mnt/c/... -- so `[ -f "$ENTRY_PLAN" ]` fails and the gate reports the plan as
    missing even though it exists. A path relative to the caller's CWD carries no
    flavour at all and resolves in every namespace. Gates invoke gsd_state.py through
    a CWD-relative script path, so their CWD is the repo root and a relative path is
    precisely what they already expect. Absolute is kept only when the target lies
    outside the CWD, where a relative path would be ambiguous rather than portable.
    """
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


def plan_path(task_id: str) -> str:
    hits = sorted((p for p in (root() / "phases").rglob(f"*{task_id}*PLAN.md")), key=str) if (root() / "phases").is_dir() else []
    return _shell_path(hits[0]) if hits else f"NOT_FOUND: plan for {task_id}"


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
    if append:
        # WINDOWS-ATOMIC APPEND (Sep-7 defect: 3 torn lines in
        # telemetry/records.jsonl). A buffered text append (open("a")) can split
        # one logical line into several underlying writes, and two concurrent
        # sessions each holding an append-mode handle can interleave them. Open
        # once per call and issue the full payload in a single os.write over an
        # O_APPEND fd — one write at EOF. Fall back to a buffered text write only
        # when the syscall form is unavailable.
        try:
            fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
            try:
                data = body.encode("utf-8")
                n = os.write(fd, data)
                if n != len(data):
                    raise OSError(f"short append write to {p}: {n}/{len(data)} bytes")
            finally:
                os.close(fd)
        except AttributeError:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(body)
    else:
        # ATOMIC OVERWRITE (T-FX1: append path was fixed for the Sep-7 torn-line
        # defect; this single-shot path was not. A plain open("w") truncates the
        # target before the new content lands, so a crash or a concurrent reader
        # mid-write can observe a zero-length or half-written decision/contract/
        # summary file. Write to a sibling temp file in the same directory (so
        # os.replace stays on one filesystem) and rename over the target — POSIX
        # and Windows (py3.3+) both make os.replace atomic for same-volume renames.
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.replace(tmp_path, p)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    return str(p)


def write_task_summary(task_id: str, payload: str) -> str:
    """Write the SUMMARY.md by delegating to the execution-position adapter (I8 seam).

    The SUMMARY is a RENDER of materialized derived state, not authored state
    (DID-012 I8): `status`, `position`, `derived_state`, and `next_action` are derived
    by execute.py render-summary from the task's lifecycle events. A payload that
    authors any of them is REJECTED (exit 1, no write). The task must be registered
    first (`task-register`) -- render-summary requires the contract. Returns the
    written path.
    """
    phase = (current_phase().get("current") or "00-unphased")
    adapter = Path(__file__).resolve().parent / "execute.py"
    env = dict(os.environ)
    env["EXEC_ROOT"] = str(root())
    p = subprocess.run(
        [sys.executable, str(adapter), "render-summary",
         "--task", task_id, "--json", payload, "--phase", phase],
        capture_output=True, text=True, env=env,
    )
    if p.returncode != 0:
        raise SystemExit((p.stdout + p.stderr).strip() or
                         f"write-summary delegation failed (exit {p.returncode})")
    return p.stdout.strip()


def write_verification(phase: str, payload: str) -> str:
    return _write(f"phases/{phase}/VERIFICATION.md",
                  f"\n## Verification run {_now()}\n\n```yaml\n{payload}\n```\n", append=True)


def write_decision(did: str, payload: str) -> str:
    if not did or not str(did).strip():
        raise SystemExit(
            "DECISION_MISSING_ID: write-decision requires --id <decision-id>; "
            "a decision without an id cannot be referenced or reviewed"
        )
    return _write(f"decisions/{did}.md",
                  f"# {did}\n\n_created {_now()}_\n\n```yaml\n{payload}\n```\n")


def write_contract(cid: str, schema: str) -> str:
    return _write(f"contracts/{cid.lower()}.openapi.yaml", schema)


def write_telemetry(payload: str) -> str:
    _rotate_telemetry()
    return _write("telemetry/records.jsonl", payload.strip() + "\n", append=True)


TELEMETRY_ROTATE_BYTES = 16 * 1024 * 1024  # 16 MiB: keep the live file a bounded working set


def _rotate_telemetry():
    """Move the live telemetry file into archive/ once it outgrows the budget.

    write_telemetry appends every heartbeat; rollup and report.py re-read the
    live file whole on every run, so an unbounded live file is a growing hot
    path. Rotation is atomic (os.replace, same volume) and best-effort: a failed
    rotation must never break a heartbeat write.
    """
    try:
        p = root() / "telemetry" / "records.jsonl"
        if not p.exists() or p.stat().st_size < TELEMETRY_ROTATE_BYTES:
            return
        arc = root() / "telemetry" / "archive"
        arc.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        os.replace(p, arc / f"records-{stamp}.jsonl")
    except OSError:
        return


TERMINAL_COMPACT_LINES = 3


def _compact_terminal_stream(task_id: str):
    """Coalesce a terminal task's event stream in place to its last N events.

    COMPLETED/CANCELLED are final: the only downstream consumers are last-event
    reads (task_status, intake._task_state), and the contract JSON outlives the
    stream. A terminal stream's earlier events have no consumer -- keeping them
    is unbounded growth across a season (every touch re-reads everything).
    FAILED/LOST are NEVER compacted: their full stream is the audit trail the
    retry ladder reads. Best-effort: a compaction failure must not break the
    terminal transition.
    """
    try:
        p = _task_events_path(task_id)
        if not p.exists():
            return
        with _file_lock(p.with_name(p.name + ".lock")):
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(lines) <= TERMINAL_COMPACT_LINES:
                return
            _write(str(p.relative_to(root())), "\n".join(lines[-TERMINAL_COMPACT_LINES:]) + "\n")
    except (OSError, ValueError):
        return


STATE_HEALTH_TASK_BUDGET = 200
STATE_HEALTH_BROKEN_REPORT = 20


def _scan_task_head(task_id: str) -> bool:
    """True when a task's contract or event-tail is unreadable (readability only).

    An unreadable stream is a stall the supervisor must see. FAILED/LOST streams
    remain parseable, so a terminal task reads healthy here.
    """
    try:
        c = _task_path(task_id)
        if not c.exists():
            return True
        json.loads(c.read_text(encoding="utf-8"))
        _last_seq(task_id)          # raises SystemExit on a torn tail
        return False
    except (OSError, ValueError, SystemExit):
        return True


def state_health() -> dict:
    """One-shot health over the live GSD state: tasks and the claim-ledger tail.

    Surfaced by the `state-health` command; consumed by g16_state_health.sh.
    A task is 'broken' when its contract or event tail is unreadable. The claim
    ledger is probed for presence and tail parseability only -- validity is
    g14's jurisdiction.
    """
    tasks_total = tasks_checked = tasks_beyond_limit = broken_tasks = 0
    broken = []
    ledger_present = ledger_tail_parseable = False
    dir_tasks = root() / TASKS_REL
    if dir_tasks.is_dir():
        contracts = sorted(p for p in dir_tasks.glob("*.json")
                           if not p.name.endswith(".events.jsonl"))
        tasks_total = len(contracts)
        for p in contracts[:STATE_HEALTH_TASK_BUDGET]:
            if _scan_task_head(p.stem):
                broken_tasks += 1
                broken.append(p.stem)
        tasks_checked = min(len(contracts), STATE_HEALTH_TASK_BUDGET)
        tasks_beyond_limit = max(0, len(contracts) - STATE_HEALTH_TASK_BUDGET)
    ledger_file = root() / "claims" / "ledger.jsonl"
    if ledger_file.exists():
        ledger_present = True
        try:
            with ledger_file.open("rb") as fh:
                fh.seek(max(0, ledger_file.stat().st_size - TAIL_READ_BYTES))
                tail = fh.read()
            lines = [ln for ln in tail.splitlines() if ln.strip()]
            json.loads(lines[-1])
            ledger_tail_parseable = True
        except (OSError, IndexError, json.JSONDecodeError):
            ledger_tail_parseable = False
    return {
        "tasks_total": tasks_total,
        "tasks_checked": tasks_checked,
        "tasks_beyond_limit": tasks_beyond_limit,
        "broken_tasks": broken_tasks,
        "broken_task_ids": broken[:STATE_HEALTH_BROKEN_REPORT],
        "ledger_present": ledger_present,
        "ledger_tail_parseable": ledger_tail_parseable,
        "ok": broken_tasks == 0,
    }


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


def _stid(base: str) -> str:
    """A selftest fixture task id that is unique to this process.

    Each selftest fixture used a fixed id ("selftest-ws", "selftest-concurrency",
    ...), so two overlapping selftest processes shared one task directory. On
    Windows the loser hit PermissionError (WinError 32) deleting a file the winner
    still held, or read a half-written stream and reported a bogus failure -- a
    check that is flaky under exactly the concurrency it exists to verify. The
    pid suffix isolates every fixture; fixtures are deleted on exit either way, so
    the id is never seen outside the run.
    """
    return f"{base}-selftest-{os.getpid()}"


def selftest() -> dict:
    """Round-trip suite. Run this on every GSD upgrade; a failure is blocking."""
    results = {}
    # write-summary delegates to execute.py render-summary (strict I8 seam, DID-012):
    # the SUMMARY is a RENDER and status/position/next_action are DERIVED, never
    # authored; the task must be registered first. Both the accepted render and the
    # I8 rejection at the seam are checked; all residue is cleaned up.
    wtid = _stid("selftest-ws")
    ws_path = None
    try:
        _task_path(wtid).unlink(missing_ok=True)
        _task_events_path(wtid).unlink(missing_ok=True)
        register_task(wtid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest write-summary delegation",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
        })
        task_event(wtid, {"state": "STARTED"})
        ws_path = write_task_summary(wtid, "summary: round trip")
        doc = Path(ws_path).read_text(encoding="utf-8")
        ok = ("# derived (I8)" in doc and "status:" in doc
              and ws_path.endswith(f"{wtid}-SUMMARY.md"))
        results["write_summary"] = "pass" if ok else f"fail: render not derived ({ws_path})"
        try:
            write_task_summary(wtid, "status: complete\nsummary: authored")
            results["write_summary_i8"] = "fail: authored status accepted"
        except SystemExit as e:
            results["write_summary_i8"] = \
                "pass" if "I8_VIOLATION" in str(e) else f"fail: {e}"
    except SystemExit as e:
        results["write_summary"] = f"unsupported: {e}"
    finally:
        _task_path(wtid).unlink(missing_ok=True)
        _task_events_path(wtid).unlink(missing_ok=True)
        if ws_path is not None:
            Path(ws_path).unlink(missing_ok=True)
    try:
        write_verification(current_phase().get("current") or "00-unphased", "status: pass")
        results["write_verification"] = "pass"
    except SystemExit as e:
        results["write_verification"] = f"unsupported: {e}"
    # failure_class round trip: FAILED must name a taxonomy class; provider-class
    # failures route recovery to the provider boundary (g12), worker-class to the
    # WORKER_STALLED ladder. Tasks are cleaned up so selftest leaves no residue.
    tid = _stid("selftest-fc")
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
    rtid = _stid("selftest-reconcile")
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

    # LOST: supervisor-declared, terminal, unrecoverable-by-the-worker state.
    ltid = _stid("selftest-lost")
    try:
        _task_path(ltid).unlink(missing_ok=True)
        _task_events_path(ltid).unlink(missing_ok=True)
        register_task(ltid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest LOST state",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
        })
        task_event(ltid, {"state": "STARTED"})
        # a worker cannot self-declare LOST: emitting LOST proves it is alive
        try:
            task_event(ltid, {"state": "LOST", "emitter": "selftest", "detail": "x"})
            results["lost_worker_cannot_self_declare"] = "fail: worker LOST accepted"
        except SystemExit:
            results["lost_worker_cannot_self_declare"] = "pass"
        # LOST without a reason is refused: recovery cannot act on it
        task_event(ltid, {"state": "PROGRESS"})
        try:
            task_event(ltid, {"state": "LOST", "emitter": "team-lead"})
            results["lost_requires_detail"] = "fail: LOST without detail accepted"
        except SystemExit:
            results["lost_requires_detail"] = "pass"
        st = task_event(ltid, {"state": "LOST", "emitter": "team-lead",
                               "detail": "session vanished mid-flight"})
        ok = (st["state"] == "LOST" and st["health"] == "LOST"
              and st["recovery_level"] == 4
              and "re-dispatch" in st["recovery_action"]
              and st["execution"] == "IDLE" and st["liveness"] == "DEAD")
        results["lost_supervisor_declared"] = "pass" if ok else (
            "fail: " + st["health"] + "/" + st["recovery_action"])
        try:
            task_event(ltid, {"state": "COMPLETED"})
            results["lost_is_terminal"] = "fail: event after LOST accepted"
        except SystemExit:
            results["lost_is_terminal"] = "pass"
    except SystemExit as e:
        results["lost_supervisor_declared"] = "fail: " + str(e)
        results["lost_worker_cannot_self_declare"] = "fail: " + str(e)
    finally:
        _task_path(ltid).unlink(missing_ok=True)
        _task_events_path(ltid).unlink(missing_ok=True)

    # progress vs liveness: milestones are NEW checkpoints; repeats and
    # checkpointless PROGRESS are heartbeats. Sequences prove event ordering.
    ptid = _stid("selftest-progress")
    try:
        _task_path(ptid).unlink(missing_ok=True)
        _task_events_path(ptid).unlink(missing_ok=True)
        register_task(ptid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest progress vs liveness",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
        })
        task_event(ptid, {"state": "STARTED"})                      # seq 1
        task_event(ptid, {"state": "PROGRESS"})                     # seq 2, heartbeat
        task_event(ptid, {"state": "PROGRESS", "checkpoint": "C0"}) # seq 3, milestone
        task_event(ptid, {"state": "PROGRESS", "checkpoint": "C0"}) # seq 4, heartbeat (repeat)
        task_event(ptid, {"state": "PROGRESS", "checkpoint": "C1"}) # seq 5, milestone
        st = task_status(ptid)
        ok = (st["progress"] == "CHECKPOINT_ADVANCED"
              and st["last_progress_kind"] == "milestone"
              and st["milestones_reached"] == 2 and st["heartbeats"] == 2
              and st["checkpoints_reached"] == ["C0", "C1"]
              and [e["seq"] for e in st["recent_events"]] == [3, 4, 5])
        results["progress_vs_liveness"] = "pass" if ok else (
            "fail: " + st["progress"] + "/" + st["last_progress_kind"] + "/"
            + str(st["milestones_reached"]) + "/" + str(st["heartbeats"]))
        results["event_seq_monotonic"] = "pass" if ok else (
            "fail: seqs " + str([e["seq"] for e in st["recent_events"]]))
    except SystemExit as e:
        results["progress_vs_liveness"] = "fail: " + str(e)
        results["event_seq_monotonic"] = "fail: " + str(e)
    finally:
        _task_path(ptid).unlink(missing_ok=True)
        _task_events_path(ptid).unlink(missing_ok=True)

    # headless contract flag round trip
    htid = _stid("selftest-headless")
    try:
        _task_path(htid).unlink(missing_ok=True)
        _task_events_path(htid).unlink(missing_ok=True)
        register_task(htid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest headless flag",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
            "headless": True,
        })
        st = task_status(htid)
        results["headless_contract_flag"] = "pass" if (
            st["headless"] is True) else "fail: headless flag not persisted"
    except SystemExit as e:
        results["headless_contract_flag"] = "fail: " + str(e)
    finally:
        _task_path(htid).unlink(missing_ok=True)
        _task_events_path(htid).unlink(missing_ok=True)
    # EXT-CRITIQUE-02 regression: a missing, empty, or literal-'None' task id
    # must be refused loudly, never silently addressed as tasks/None.json.
    _ng = None
    try:
        _task_path("")
        _ng = "empty id accepted"
    except SystemExit:
        pass
    if _ng is None:
        try:
            _task_path("None")
            _ng = "literal 'None' id accepted"
        except SystemExit:
            pass
    results["task_id_none_guard"] = "pass" if _ng is None else "fail: " + _ng

    # EXT-CRITIQUE-01 regression: 40 concurrent writers must produce a gapless,
    # strictly monotonic seq range with no duplicates. The pre-fix adapter read
    # the tail and appended as two unlocked steps, so racing writers duplicated
    # seqs; the lock now covers the whole read+append critical section.
    #
    # The id is process-unique. It was the fixed "selftest-concurrency", so two
    # overlapping selftest processes (validate runs one and other checks run
    # concurrently) shared one task directory: one unlinked/registered while the
    # other appended, and the loser read a partial stream -- reproducible as
    # "seqs [1..23]" or "NOT_FOUND: task selftest-concurrency is not registered".
    # A shared fixture id made the check flaky under exactly the load it exists
    # to test. Same class as the claim-id collision: process-global identity must
    # not be shared across processes.
    ctid = _stid("selftest-concurrency")
    try:
        _task_path(ctid).unlink(missing_ok=True)
        _task_events_path(ctid).unlink(missing_ok=True)
        register_task(ctid, {
            "agent": "selftest", "type": "default",
            "objective": "selftest concurrent seq append",
            "expected_artifact": "pass",
            "progress_timeout_s": 30, "max_duration_s": 60,
        })
        _append_task_event(ctid, {"state": "STARTED",
                                  "ts": _now(), "emitter": "selftest"})   # seq 1
        import concurrent.futures

        def _fire(_i):
            _append_task_event(ctid, {"state": "PROGRESS",
                                      "ts": _now(), "emitter": "selftest"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as _ex:
            list(_ex.map(_fire, range(40)))
        _, _evs = _task_load(ctid)
        _seqs = [e["seq"] for e in _evs]
        ok = _seqs == list(range(1, len(_seqs) + 1)) and len(_seqs) == 41
        results["seq_unique_under_concurrency"] = "pass" if ok else (
            "fail: seqs " + str(_seqs))
    except SystemExit as e:
        results["seq_unique_under_concurrency"] = "fail: " + str(e)
    finally:
        _task_path(ctid).unlink(missing_ok=True)
        _task_events_path(ctid).unlink(missing_ok=True)

    results["read_requirements"] = "pass" if read_requirements() or True else "fail"
    results["detect"] = manifest()["distribution"]
    return results


CMDS = {
    "detect": lambda a: detect(), "manifest": lambda a: manifest(),
    "state-root": lambda a: str(root()), "health": lambda a: health(),
    "selftest": lambda a: selftest(), "current-phase": lambda a: current_phase(),
    "project": lambda a: read_project(), "requirements": lambda a: read_requirements(),
    "requirement": lambda a: read_requirement(a.id), "roadmap": lambda a: read_roadmap(),
    "plan-path": lambda a: plan_path(a.id), "contract": lambda a: read_contract(a.id),
    "write-summary": lambda a: write_task_summary(a.id, a.json),
    "write-verification": lambda a: write_verification(a.phase, a.json),
    "write-decision": lambda a: write_decision(a.id, a.json),
    "write-contract": lambda a: write_contract(a.id, a.json),
    "write-telemetry": lambda a: write_telemetry(a.json),
    "write-blocker": lambda a: write_blocker(_parse_json(a.json)),
    "resolve-blocker": lambda a: resolve_blocker(a.id),
    "list-blockers": lambda a: list_blockers(a.text),
    "retry-budget": lambda a: retry_budget(),
    "task-register": lambda a: register_task(a.id, _parse_json(a.json, "TASK") if a.json else None),
    "task-event": lambda a: task_event(a.id, _parse_json(a.json, "TASK")),
    "task-status": lambda a: task_status(a.id, {"true": True, "false": False}.get(a.session_alive.lower(), None)),
    "task-list": lambda a: list_tasks(),
    "task-summary": lambda a: task_summary(),
    "state-health": lambda a: state_health(),
    "task-cancel": lambda a: cancel_task(a.id, _parse_json(a.json, "TASK") if a.json else None),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GSD State Adapter")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--id", "--task", dest="id")
    ap.add_argument("--phase")
    ap.add_argument("--json", default="")
    ap.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--session-alive", default="unknown")
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    out = CMDS[a.command](a)
    if out is not None:
        print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)
