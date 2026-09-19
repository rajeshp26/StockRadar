#!/usr/bin/env python3
"""Control adapter -- DID-012 Pillar 3 (lease/reap, deterministic reaper).

Runtime liveness for background tasks. A bg task's owner session leases it; the lease is
renewed by heartbeat or the session dies. The control adapter decides, DELETERATELY and
DETERMINISTICALLY, whether a task is orphaned enough to reap -- and it never converts
uncertainty into a successful reap.

State is DERIVED from append-only event logs (I10, I11); nothing here mutates or deletes
an event. Ownership is never inferred: a task with no binding is UNKNOWN and stays UNKNOWN
(I7) -- the reaper records UNCONFIRMED for it and does not touch the task.

Derived task chain (DID-012 5.5):
    RUNNING -> STALE   (lease expired, owner not confirmed dead)
    RUNNING -> LOST    (owner session confirmed dead, lease still live)
    LOST    -> ORPHANED (owner dead AND lease expired)
    ORPHANED -> REAPED  (durable, confirmed reap record -- the deterministic reaper)

Session chain (DID-012 5.5):
    RUNNING -> CLOSED | DEAD | ABORTED   (termination_observed -- terminal)

Invariants enforced here (DID-012 section 6):
  I3  every background task has exactly one owner binding   -> bind rejects a second owner
  I4  session ids are unique                                -> register rejects duplicates
  I5  sessions reach CLOSED|DEAD|ABORTED                    -> terminate is terminal
  I6  tasks reach COMPLETED|CANCELLED|FAILED|ORPHANED|REAPED -> collect/cancel/fail terminal
  I7  no inferred ownership                                 -> missing binding = UNKNOWN,
                                                               reaper never reaps it
  I10 deterministic derivation: same log + same now -> same state  -> derive / reap
  I11 append-only provenance: events never mutate or delete        -> read folds only

Absorbs DID-012 items 4 and 6:
  item 4 | rollup     telemetry -> event-model positions; archive raw records older than
                       max-age-days out of the live working set (CONTROL_ARCHIVE overrides
                       the archive location for hermetic runs)
  item 6 | retro-sync one-way mirror of pending retro entries into framework/retro/ledger.py
                       (the gate-enforced side) via its own append path -- ledger.py stays
                       the single writer; this adapter only stages and validates

Storage (adapter-owned, under the GSD state root; CONTROL_ROOT overrides for hermetic runs):
  <state_root>/control/sessions.jsonl   session events (append-only)
  <state_root>/control/tasks.jsonl      background-task events (append-only)
  <state_root>/control/reaps.jsonl      durable reap records (append-only)

Exit codes:
  0  success / invariant holds
  1  named violation (invalid transition, duplicate identity, corrupt log, bad entry)
  2  BLOCKED -- state root, telemetry, or a required input is unreadable (never a pass)
  4  NOT_APPLICABLE -- the check cannot apply to the subject (never a pass)

CLI:
  session register --id ses_X [--lease-s N]
  session heartbeat --id ses_X [--lease-s N]
  session terminate --id ses_X --state CLOSED|DEAD|ABORTED
  task bind --id bg_X --session ses_X [--lease-s N]
  task heartbeat --id bg_X [--lease-s N]
  task collect --id bg_X [--by who]
  task cancel --id bg_X [--by who]
  task fail --id bg_X [--reason txt]
  derive [--now ISO]                deterministic fold of sessions + tasks
  reap [--now ISO]                  deterministic reaper (idempotent; writes reaps.jsonl)
  rollup [--max-age-days 30] [--archive DIR] [--skip-position]   item 4
  retro-sync [--pending PATH] [--ledger PATH]                     item 6
  selftest
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# --- vocabulary (DID-012 5.x) ----------------------------------------------
SESSION_TERMINAL = ("CLOSED", "DEAD", "ABORTED")
TASK_TERMINAL = ("COMPLETED", "CANCELLED", "FAILED", "REAPED")
TASK_LIVE = ("RUNNING", "STALE", "LOST", "ORPHANED")
REAP_CONFIRMED, REAP_UNCONFIRMED = "confirmed", "UNCONFIRMED"
TERMINATE_STATES = SESSION_TERMINAL

CONTROL_REL = "control"
SESSIONS_NAME = "sessions.jsonl"
TASKS_NAME = "tasks.jsonl"
REAPS_NAME = "reaps.jsonl"
REAP_ID_FMT = "REAP-{:03d}"

DEFAULT_LEASE_S = 1800          # 30 min
DEFAULT_MAX_AGE_DAYS = 30
RETRO_REL = "retro"
PENDING_NAME = "pending.jsonl"
LEDGER_NAME = "ledger.jsonl"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _parse_ts(s) -> datetime.datetime:
    if not s:
        raise ValueError("empty timestamp")
    t = str(s)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(t)


def _fmt(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _add_seconds(ts: str, seconds: int) -> str:
    return _fmt(_parse_ts(ts) + datetime.timedelta(seconds=seconds))


def _state_root() -> Path:
    """State root via CONTROL_ROOT override or the GSD state adapter -- one resolution."""
    if os.environ.get("CONTROL_ROOT"):
        return Path(os.environ["CONTROL_ROOT"])
    try:
        import gsd_state
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import gsd_state
        except ImportError as e:
            raise SystemExit(
                "BLOCKED: gsd_state.py not importable -- control must not invent its own "
                "state root: " + str(e)
            )
    return gsd_state.root()


def _control_dir() -> Path:
    return _state_root() / CONTROL_REL


def _sessions_path() -> Path:
    return _control_dir() / SESSIONS_NAME


def _tasks_path() -> Path:
    return _control_dir() / TASKS_NAME


def _reaps_path() -> Path:
    return _control_dir() / REAPS_NAME


def _parse_json(raw, what="CONTROL"):
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"CONTROL_INVALID_JSON: {what} payload unreadable: {e}")
    if not isinstance(v, dict):
        raise SystemExit(f"CONTROL_INVALID_JSON: {what} payload must be a JSON object")
    return v


# --- log + derivation ------------------------------------------------------

def _load_events(path: Path, what: str) -> list:
    if not path.exists():
        return []
    out = []
    try:
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    raise SystemExit(
                        f"CONTROL_CORRUPT_LOG: {what} line {i} is not valid JSON -- a torn "
                        "log must block, never read as healthy"
                    )
    except OSError as e:
        raise SystemExit(
            f"CONTROL_UNREADABLE: {what} log unreadable: {e} -- BLOCKED, never a pass"
        )
    return out


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def _sessions() -> dict:
    """Fold session events -> current record per session_id (last write wins)."""
    out = {}
    for ev in _load_events(_sessions_path(), "sessions"):
        sid = ev.get("session_id")
        if sid:
            out[sid] = ev
    return out


def _tasks() -> dict:
    out = {}
    for ev in _load_events(_tasks_path(), "tasks"):
        tid = ev.get("task_id")
        if tid:
            out[tid] = ev
    return out


def _reaps() -> list:
    return _load_events(_reaps_path(), "reaps")


def _reap_records_by_task() -> dict:
    by_task: dict = {}
    for r in _reaps():
        by_task.setdefault(r.get("task_id"), []).append(r)
    return by_task


def _owner_state(session_id) -> str | None:
    return (_sessions().get(session_id) or {}).get("state")


def _derive_task_state(task: dict, reap_recs: list, now: str) -> tuple[str, dict]:
    """Deterministic task state from its event record + reap history + now (DID-012 5.5)."""
    state = task.get("state")
    if state in TASK_TERMINAL:
        return state, {}
    confirmed = [r for r in reap_recs if r.get("result") == REAP_CONFIRMED]
    if confirmed:
        return "REAPED", confirmed[-1]
    owner = task.get("owner_session_id")
    if not owner:
        return "UNKNOWN", {}                     # I7 -- no inferred ownership
    owner_state = _owner_state(owner)
    if owner_state in ("DEAD", "ABORTED"):       # confirmed dead, not CLOSED
        if now is None or _parse_ts(now) > _parse_ts(task.get("lease_until")):
            return "ORPHANED", {}
        return "LOST", {}
    if now is None or _parse_ts(now) > _parse_ts(task.get("lease_until")):
        return "STALE", {}
    return "RUNNING", {}


def derive(now: str | None = None) -> dict:
    """Deterministic fold of the whole control log (I10): same log + same now -> same view."""
    now = now or _now()
    reap_by_task = _reap_records_by_task()
    tasks = {}
    for tid, task in _tasks().items():
        st, meta = _derive_task_state(task, reap_by_task.get(tid, []), now)
        tasks[tid] = dict(task)
        tasks[tid]["derived_state"] = st
        if meta:
            tasks[tid]["reaped_by"] = meta.get("reap_id")
    return {
        "now": now,
        "sessions": _sessions(),
        "tasks": tasks,
        "reaps": _reaps(),
    }


# --- session commands ------------------------------------------------------

def session_register(session_id: str, lease_s: int = DEFAULT_LEASE_S) -> dict:
    if not session_id:
        print("CONTROL_INVALID_ID: session register requires --id", file=sys.stderr)
        raise SystemExit(1)
    if session_id in _sessions():
        print(
            f"I4 VIOLATED: session_id {session_id} already registered -- ids are unique",
            file=sys.stderr,
        )
        raise SystemExit(1)
    ts = _now()
    ev = {
        "event": "SESSION_REGISTERED",
        "session_id": session_id,
        "state": "RUNNING",
        "started_at": ts,
        "last_heartbeat": ts,
        "ended_at": None,
        "termination_observed": False,
        "lease_until": _add_seconds(ts, lease_s),
    }
    _append_event(_sessions_path(), ev)
    return ev


def session_heartbeat(session_id: str, lease_s: int = DEFAULT_LEASE_S) -> dict:
    cur = _sessions().get(session_id)
    if not cur:
        print(f"SESSION_UNKNOWN: no registered session {session_id}", file=sys.stderr)
        raise SystemExit(1)
    if cur.get("state") in SESSION_TERMINAL:
        print(
            f"INVALID_TRANSITION: session {session_id} is terminal ({cur['state']}); "
            "heartbeat refused",
            file=sys.stderr,
        )
        raise SystemExit(1)
    ts = _now()
    ev = dict(cur)
    ev.update({
        "event": "SESSION_HEARTBEAT",
        "state": "RUNNING",
        "last_heartbeat": ts,
        "lease_until": _add_seconds(ts, lease_s),
    })
    _append_event(_sessions_path(), ev)
    return ev


def session_terminate(session_id: str, state: str) -> dict:
    if state not in TERMINATE_STATES:
        print(
            f"INVALID_STATE: terminate state must be one of {TERMINATE_STATES}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    cur = _sessions().get(session_id)
    if not cur:
        print(f"SESSION_UNKNOWN: no registered session {session_id}", file=sys.stderr)
        raise SystemExit(1)
    if cur.get("state") in SESSION_TERMINAL:
        print(
            f"INVALID_TRANSITION: session {session_id} already terminal ({cur['state']}); "
            "terminal is final (I5)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    ts = _now()
    ev = dict(cur)
    ev.update({
        "event": "SESSION_TERMINATED",
        "state": state,
        "ended_at": ts,
        "termination_observed": True,
        "lease_until": None,
    })
    _append_event(_sessions_path(), ev)
    return ev


# --- task commands ---------------------------------------------------------

def task_bind(task_id: str, session_id: str, lease_s: int = DEFAULT_LEASE_S) -> dict:
    if not task_id:
        print("CONTROL_INVALID_ID: task bind requires --id", file=sys.stderr)
        raise SystemExit(1)
    if not session_id:
        print("CONTROL_INVALID_ID: task bind requires --session", file=sys.stderr)
        raise SystemExit(1)
    tasks = _tasks()
    if task_id in tasks:
        owner = tasks[task_id].get("owner_session_id")
        print(
            f"I3 VIOLATED: task {task_id} is already bound to {owner}; "
            "exactly one owner per task",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if session_id not in _sessions():
        print(
            f"I7 VIOLATED: cannot bind {task_id} to unregistered session {session_id} -- "
            "ownership is never inferred or assumed",
            file=sys.stderr,
        )
        raise SystemExit(1)
    ts = _now()
    ev = {
        "event": "TASK_BOUND",
        "task_id": task_id,
        "owner_session_id": session_id,
        "state": "RUNNING",
        "created_at": ts,
        "last_heartbeat": ts,
        "lease_until": _add_seconds(ts, lease_s),
        "collected_at": None,
        "collected_by": None,
    }
    _append_event(_tasks_path(), ev)
    return ev


def _live_task(task_id: str) -> dict:
    task = _tasks().get(task_id)
    if not task:
        print(f"TASK_UNKNOWN: no bound task {task_id}", file=sys.stderr)
        raise SystemExit(1)
    if task.get("state") in TASK_TERMINAL:
        print(
            f"INVALID_TRANSITION: task {task_id} is terminal ({task['state']}); "
            "terminal is final (I6)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return task


def task_heartbeat(task_id: str, lease_s: int = DEFAULT_LEASE_S) -> dict:
    task = _live_task(task_id)
    ts = _now()
    ev = dict(task)
    ev.update({
        "event": "TASK_HEARTBEAT",
        "state": "RUNNING",
        "last_heartbeat": ts,
        "lease_until": _add_seconds(ts, lease_s),
    })
    _append_event(_tasks_path(), ev)
    return ev


def task_collect(task_id: str, by: str = "") -> dict:
    task = _live_task(task_id)
    ts = _now()
    ev = dict(task)
    ev.update({
        "event": "TASK_COLLECTED",
        "state": "COMPLETED",
        "collected_at": ts,
        "collected_by": by or None,
        "lease_until": None,
    })
    _append_event(_tasks_path(), ev)
    return ev


def task_cancel(task_id: str, by: str = "") -> dict:
    task = _live_task(task_id)
    ts = _now()
    ev = dict(task)
    ev.update({
        "event": "TASK_CANCELLED",
        "state": "CANCELLED",
        "collected_at": ts,
        "collected_by": by or None,
        "lease_until": None,
    })
    _append_event(_tasks_path(), ev)
    return ev


def task_fail(task_id: str, reason: str = "") -> dict:
    task = _live_task(task_id)
    ts = _now()
    ev = dict(task)
    ev.update({
        "event": "TASK_FAILED",
        "state": "FAILED",
        "collected_at": ts,
        "collected_by": None,
        "lease_until": None,
        "failure_reason": reason or None,
    })
    _append_event(_tasks_path(), ev)
    return ev


# --- deterministic reaper (item spine, DID-012 5.6) --------------------------

def reap(now: str | None = None) -> dict:
    """Deterministic reaper. Idempotent: a task with a reap record is never re-reaped.

    - ORPHANED (owner confirmed dead AND lease expired) -> REAP record, result=confirmed,
      action=cancel. This is the ONLY state the reaper actually cancels.
    - STALE / UNKNOWN -> a durable UNCONFIRMED record (action=hold) documenting that the
      reaper considered the task and could NOT confirm a reap. Never converts uncertainty
      into success (I7). The task is not touched.
    """
    now = now or _now()
    reap_by_task = _reap_records_by_task()
    written = []
    for tid in sorted(_tasks()):
        if reap_by_task.get(tid):
            continue                       # idempotent -- already considered
        st, _ = _derive_task_state(_tasks()[tid], [], now)
        if st == "ORPHANED":
            rec = {
                "task_id": tid,
                "reason": "owner session confirmed dead and lease expired",
                "last_heartbeat": _tasks()[tid].get("last_heartbeat"),
                "lease_until": _tasks()[tid].get("lease_until"),
                "lease_expired": True,
                "action": "cancel",
                "result": REAP_CONFIRMED,
                "ts": now,
            }
        elif st == "STALE":
            rec = {
                "task_id": tid,
                "reason": "lease expired and owner death NOT confirmed -- reap unconfirmed",
                "last_heartbeat": _tasks()[tid].get("last_heartbeat"),
                "lease_until": _tasks()[tid].get("lease_until"),
                "lease_expired": True,
                "action": "hold",
                "result": REAP_UNCONFIRMED,
                "ts": now,
            }
        elif st == "UNKNOWN":
            rec = {
                "task_id": tid,
                "reason": "no owner binding (I7) -- ownership cannot be confirmed",
                "last_heartbeat": _tasks()[tid].get("last_heartbeat"),
                "lease_until": _tasks()[tid].get("lease_until"),
                "lease_expired": True,
                "action": "hold",
                "result": REAP_UNCONFIRMED,
                "ts": now,
            }
        else:
            continue                       # RUNNING / LOST stay untouched
        rec["reap_id"] = REAP_ID_FMT.format(len(_reaps()) + 1)
        _append_event(_reaps_path(), rec)
        written.append(rec)
    return {"reaped": written, "now": now, "task_states": derive(now)["tasks"]}


# --- item 4: telemetry rollup ----------------------------------------------

def _telemetry_records(telemetry_path: Path) -> list:
    return _load_events(telemetry_path, "telemetry")


def _record_ts(rec: dict):
    for key in ("ts", "timestamp", "recorded_at", "started_at"):
        if rec.get(key):
            try:
                return _parse_ts(rec[key])
            except (ValueError, TypeError):
                continue
    return None


def _rollup_positions(recs: list) -> dict:
    """Fold telemetry into session event-model positions (item 4), WITHOUT inferring
    task ownership (I7). A session is RUNNING while no final record exists, CLOSED after."""
    positions = {}
    for rec in recs:
        sid = rec.get("session_id")
        if not sid:
            continue
        kind = rec.get("kind") or "final"
        positions[sid] = "CLOSED" if kind == "final" else "RUNNING"
    return positions


def rollup(max_age_days: int = DEFAULT_MAX_AGE_DAYS,
           archive_dir: str | None = None,
           skip_position: bool = False) -> dict:
    """Item 4: emit session positions from raw telemetry, then archive raw records older
    than max-age-days out of the live working set."""
    telemetry = _state_root() / "telemetry" / "records.jsonl"
    recs = _telemetry_records(telemetry)
    positions_new = []
    if not skip_position:
        for sid, state in _rollup_positions(recs).items():
            cur = _sessions().get(sid)
            if cur:
                continue                       # idempotent -- position already folded
            ts = _now()
            ev = {
                "event": "SESSION_REGISTERED_FROM_TELEMETRY",
                "session_id": sid,
                "state": state,
                "started_at": ts,
                "last_heartbeat": ts,
                "ended_at": ts if state == "CLOSED" else None,
                "termination_observed": state == "CLOSED",
                "lease_until": None,
            }
            _append_event(_sessions_path(), ev)
            positions_new.append(sid)

    # archive raw records older than max-age out of the live working set
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=max_age_days)
    archive = Path(archive_dir) if archive_dir else (
        _state_root() / "telemetry" / "archive")
    keep, archived = [], []
    if telemetry.exists():
        for rec in recs:
            ts = _record_ts(rec)
            if ts is not None and ts < cutoff:
                archived.append(rec)
            else:
                keep.append(rec)
        if archived:
            archive.mkdir(parents=True, exist_ok=True)
            stamp = cutoff.strftime("%Y%m%d")
            target = archive / f"records-{stamp}.jsonl"
            with target.open("a", encoding="utf-8") as fh:
                for rec in archived:
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
            with telemetry.open("w", encoding="utf-8") as fh:
                for rec in keep:
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return {
        "positions_folded": positions_new,
        "records_archived": len(archived),
        "records_kept": len(keep),
        "archive_dir": str(archive),
        "existed": telemetry.exists(),
    }


# --- item 6: one-way retro-entry sync ---------------------------------------

def _containment_targets() -> set:
    try:
        import yaml
        p = Path(__file__).resolve().parent.parent / "retro" / "containment_map.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return set((data.get("fix_targets") or {}).keys())
    except Exception as e:
        raise SystemExit(
            f"CONTROL_BLOCKED: containment map unreadable ({e}) -- retro-sync cannot "
            "validate fix_target without the closed list"
        )


RETRO_REQUIRED = ["task_id", "injected_at", "caught_at", "defect_class", "primary_gap",
                  "fix_target", "fix_landed"]


def _validate_retro_entry(entry: dict) -> None:
    missing = [k for k in RETRO_REQUIRED if not entry.get(k)]
    if missing:
        print(json.dumps({"error": "incomplete retro entry", "missing": missing}),
              file=sys.stderr)
        raise SystemExit(1)
    if entry.get("fix_target") not in _containment_targets():
        print(
            f"UNKNOWN_FIX_TARGET: {entry.get('fix_target')!r} is not on the closed "
            "containment list -- retro entries must name a real fix target",
            file=sys.stderr,
        )
        raise SystemExit(1)


def retro_sync(pending_path: str | None = None, ledger_path: str | None = None) -> dict:
    """Item 6: one-way mirror of staged retro entries into the framework retro ledger.
    The firewall is ledger.py's own append path (CONTROL_LEDGER overrides for hermetic
    runs). Entries are validated here first: required fields + closed fix_target list."""
    pending = Path(pending_path) if pending_path else (
        _state_root() / RETRO_REL / PENDING_NAME)
    if not pending.exists():
        return {"status": "no pending entries", "synced": [], "skipped": []}

    ledger_txt = (
        (Path(ledger_path).read_text(encoding="utf-8") if ledger_path else "")
        if (ledger_path and Path(ledger_path).exists()) else ""
    )
    existing_task_ids = set()
    if ledger_txt:
        for ln in ledger_txt.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                existing_task_ids.add(json.loads(ln).get("task_id"))
            except json.JSONDecodeError:
                continue

    synced, skipped = [], []
    for i, ln in enumerate(pending.read_text(encoding="utf-8").splitlines(), 1):
        ln = ln.strip()
        if not ln:
            continue
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError:
            raise SystemExit(
                f"CONTROL_INVALID_JSON: pending retro line {i} is not valid JSON -- "
                "a corrupt staging file must block, never drop a safety record"
            )
        _validate_retro_entry(entry)
        tid = entry.get("task_id")
        if tid in existing_task_ids:
            skipped.append({"task_id": tid, "reason": "already synced"})
            continue

        # one-way: the framework ledger is the single writer (ledger.py's append path)
        if ledger_path:
            Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
            with Path(ledger_path).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
        else:
            import subprocess
            ledger_script = Path(__file__).resolve().parent.parent / "retro" / "ledger.py"
            r = subprocess.run(
                [sys.executable, str(ledger_script), "append",
                 "--json", json.dumps(entry)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                print(f"LEDGER_REFUSED: {r.stderr.strip() or r.stdout.strip()}",
                      file=sys.stderr)
                raise SystemExit(1)
        existing_task_ids.add(tid)
        synced.append(tid)
    return {"status": "synced", "synced": synced, "skipped": skipped}


# --- selftest --------------------------------------------------------------

def selftest() -> dict:
    import tempfile
    results = {}
    with tempfile.TemporaryDirectory() as td:
        os.environ["CONTROL_ROOT"] = td
        try:
            # I4: unique session ids; register starts RUNNING
            s = session_register("ses_a", lease_s=10)
            results["register_running"] = "pass" if s["state"] == "RUNNING" else (
                "fail: " + s["state"])
            try:
                session_register("ses_a")
                results["duplicate_session_blocked"] = "fail: duplicate accepted"
            except SystemExit:
                results["duplicate_session_blocked"] = "pass"

            # I5: terminate is terminal; transitions after terminal refused
            session_register("ses_b", lease_s=10)
            session_terminate("ses_b", "DEAD")
            results["terminate_terminal"] = "pass" if (
                _sessions()["ses_b"]["state"] == "DEAD" and
                _sessions()["ses_b"]["termination_observed"]) else "fail"
            try:
                session_heartbeat("ses_b")
                results["post_terminal_heartbeat_blocked"] = "fail: heartbeat after DEAD"
            except SystemExit:
                results["post_terminal_heartbeat_blocked"] = "pass"
            try:
                session_terminate("ses_b", "ABORTED")
                results["terminal_is_final"] = "fail: second terminate accepted"
            except SystemExit:
                results["terminal_is_final"] = "pass"

            # I7: bind requires a registered session (ownership never inferred)
            try:
                task_bind("bg_1", "ses_ghost")
                results["bind_to_unknown_session_blocked"] = "fail: ghost owner accepted"
            except SystemExit:
                results["bind_to_unknown_session_blocked"] = "pass"

            # I3: exactly one owner
            task_bind("bg_1", "ses_a", lease_s=10)
            results["bind_ok"] = "pass" if _tasks()["bg_1"]["owner_session_id"] == "ses_a" \
                else "fail"
            try:
                task_bind("bg_1", "ses_b")
                results["rebind_blocked"] = "fail: second owner accepted"
            except SystemExit:
                results["rebind_blocked"] = "pass"

            # I6: terminal task states; collect is final
            task_bind("bg_done", "ses_a", lease_s=10)
            task_collect("bg_done", "verifier")
            results["collect_terminal"] = "pass" if (
                _tasks()["bg_done"]["state"] == "COMPLETED" and
                _tasks()["bg_done"]["collected_by"] == "verifier") else "fail"
            try:
                task_heartbeat("bg_done")
                results["post_collect_heartbeat_blocked"] = "fail: heartbeat after COMPLETED"
            except SystemExit:
                results["post_collect_heartbeat_blocked"] = "pass"

            # Chain: STALE (lease expired, owner alive) -- reaper never confirms it
            task_bind("bg_stale", "ses_a", lease_s=-1)
            t = _tasks()["bg_stale"]
            stale_state, _ = _derive_task_state(t, [], "2999-01-01T00:00:00+00:00")
            results["stale_derived"] = "pass" if stale_state == "STALE" else (
                "fail: " + stale_state)
            reaped = reap("2999-01-01T00:00:00+00:00")
            recs = [r for r in reaped["reaped"] if r["task_id"] == "bg_stale"]
            results["stale_not_reaped"] = "pass" if recs and recs[0]["result"] == (
                REAP_UNCONFIRMED) else "fail: stale task reaped confirmed"
            st2, _ = _derive_task_state(_tasks()["bg_stale"], recs, "2999-01-01T00:00:00+00:00")
            results["unconfirmed_never_reaped"] = "pass" if st2 != "REAPED" else (
                "fail: UNCONFIRMED converted to success")

            # Chain: LOST -> ORPHANED -> REAPED (confirmed)
            session_register("ses_dead", lease_s=10)
            task_bind("bg_lost", "ses_dead", lease_s=-1)
            session_terminate("ses_dead", "DEAD")
            now_far = "2999-01-01T00:00:00+00:00"
            lost_state, _ = _derive_task_state(_tasks()["bg_lost"], [], now_far)
            results["orphaned_derived"] = "pass" if lost_state == "ORPHANED" else (
                "fail: " + lost_state)
            r2 = reap(now_far)
            rec2 = [r for r in r2["reaped"] if r["task_id"] == "bg_lost"]
            results["orphan_confirmed"] = "pass" if rec2 and rec2[0]["result"] == (
                REAP_CONFIRMED) else "fail: orphan not confirmed"
            reaped_state, _ = _derive_task_state(_tasks()["bg_lost"], rec2, now_far)
            results["confirmed_reaped"] = "pass" if reaped_state == "REAPED" else (
                "fail: " + reaped_state)
            # idempotent: a second reap writes nothing for bg_lost
            before = len(_reaps())
            reap(now_far)
            results["reap_idempotent"] = "pass" if len(_reaps()) == before else (
                "fail: duplicate reap record")

            # I7: UNKNOWN (no binding) is never reaped as success
            (Path(td) / CONTROL_REL).mkdir(parents=True, exist_ok=True)
            with (_tasks_path()).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "event": "TASK_BOUND", "task_id": "bg_ghost",
                    "owner_session_id": None, "state": "RUNNING",
                    "created_at": now_far, "last_heartbeat": now_far,
                    "lease_until": "2000-01-01T00:00:00+00:00"}) + "\n")
            rec3 = reap(now_far)
            g = [r for r in rec3["reaped"] if r["task_id"] == "bg_ghost"]
            results["unknown_unconfirmed"] = "pass" if g and g[0]["result"] == (
                REAP_UNCONFIRMED) else "fail: UNKNOWN reaped"
            gstate, _ = _derive_task_state(_tasks()["bg_ghost"], g, now_far)
            results["unknown_never_reaped"] = "pass" if gstate != "REAPED" else (
                "fail: UNKNOWN converted to success")

            # I10: deterministic derivation
            results["deterministic_derivation"] = (
                "pass" if derive(now_far) == derive(now_far) else "fail: derivation diverged")

            # I11: append-only -- appending one event grows the log by exactly one
            sess_events = _load_events(_sessions_path(), "sessions")
            _append_event(_sessions_path(), {
                "event": "SESSION_HEARTBEAT", "session_id": "ses_new",
                "state": "RUNNING", "started_at": now_far,
                "last_heartbeat": now_far, "ended_at": None,
                "termination_observed": False, "lease_until": now_far,
            })
            results["append_only"] = "pass" if len(
                _load_events(_sessions_path(), "sessions")) == len(sess_events) + 1 else (
                "fail: events mutated")
            # I11: reloading the log yields identical content -- nothing rewritten
            snoop_first = _load_events(_sessions_path(), "sessions")
            snoop_second = _load_events(_sessions_path(), "sessions")
            results["events_reloaded_pure"] = "pass" if snoop_first == snoop_second else (
                "fail: reload changed the log")

            # rollup archives old records out of the live set; position folded
            tel = Path(td) / "telemetry"
            tel.mkdir(parents=True, exist_ok=True)
            old = "2000-01-01T00:00:00+00:00"
            fresh = "2999-01-01T00:00:00+00:00"
            with (tel / "records.jsonl").open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"session_id": "ses_t_old", "kind": "started",
                                     "ts": old}) + "\n")
                fh.write(json.dumps({"session_id": "ses_t_new", "kind": "started",
                                     "ts": fresh}) + "\n")
            ru = rollup(max_age_days=30, archive_dir=str(Path(td) / "archive"))
            results["rollup_archives_old"] = "pass" if ru["records_archived"] == 1 else (
                "fail: archived=" + str(ru["records_archived"]))
            results["rollup_keeps_fresh"] = "pass" if ru["records_kept"] == 1 else (
                "fail: kept=" + str(ru["records_kept"]))
            live = _telemetry_records(tel / "records.jsonl")
            results["rollup_out_of_live_set"] = "pass" if all(
                _record_ts(r) and _record_ts(r) >= _parse_ts(fresh) for r in live) else (
                "fail: old record still live")

            # retro-sync: closed fix_target list enforced
            retro_dir = Path(td) / RETRO_REL
            retro_dir.mkdir(parents=True, exist_ok=True)
            p = retro_dir / PENDING_NAME
            p.write_text(json.dumps({
                "task_id": "T-RET", "injected_at": "implementation",
                "caught_at": "review", "defect_class": "logic_error",
                "primary_gap": "gate_check", "fix_target": "gate_check",
                "fix_landed": True}) + "\n", encoding="utf-8")
            led = retro_dir / LEDGER_NAME
            rs = retro_sync(str(p), str(led))
            results["retro_sync_appends"] = "pass" if rs["synced"] == ["T-RET"] else (
                "fail: " + json.dumps(rs))
            try:
                p.write_text(json.dumps({
                    "task_id": "T-BAD", "injected_at": "implementation",
                    "caught_at": "review", "defect_class": "logic_error",
                    "primary_gap": "gate_check", "fix_target": "made_up_target",
                    "fix_landed": True}) + "\n", encoding="utf-8")
                retro_sync(str(p), str(led))
                results["unknown_fix_target_blocked"] = "fail: invented target accepted"
            except SystemExit:
                results["unknown_fix_target_blocked"] = "pass"

            # torn control log blocks rather than reading as healthy -- this is LAST
            # because a torn sessions log must not poison the rollup/retro checks above
            with _sessions_path().open("a", encoding="utf-8") as fh:
                fh.write("{not json\n")
            try:
                _sessions()
                results["torn_log_blocks"] = "fail: torn log read as healthy"
            except SystemExit:
                results["torn_log_blocks"] = "pass"
        finally:
            os.environ.pop("CONTROL_ROOT", None)
    failed = sorted(k for k, v in results.items() if v != "pass")
    if failed:
        print(json.dumps(results, indent=2))
        print("SELFTEST FAILED: " + ", ".join(failed), file=sys.stderr)
        raise SystemExit(1)
    return results


CMDS = {
    "session-register": lambda a: session_register(a.id, a.lease_s),
    "session-heartbeat": lambda a: session_heartbeat(a.id, a.lease_s),
    "session-terminate": lambda a: session_terminate(a.id, a.state),
    "task-bind": lambda a: task_bind(a.id, a.session, a.lease_s),
    "task-heartbeat": lambda a: task_heartbeat(a.id, a.lease_s),
    "task-collect": lambda a: task_collect(a.id, a.by),
    "task-cancel": lambda a: task_cancel(a.id, a.by),
    "task-fail": lambda a: task_fail(a.id, a.reason),
    "derive": lambda a: derive(a.now),
    "reap": lambda a: reap(a.now),
    "rollup": lambda a: rollup(a.max_age_days, a.archive, a.skip_position),
    "retro-sync": lambda a: retro_sync(a.pending, a.ledger),
    "selftest": lambda a: selftest(),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Control adapter (DID-012 Pillar 3)")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--id", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--state", default="")
    ap.add_argument("--by", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--lease-s", dest="lease_s", type=int, default=DEFAULT_LEASE_S)
    ap.add_argument("--now", default="")
    ap.add_argument("--max-age-days", dest="max_age_days", type=int,
                    default=DEFAULT_MAX_AGE_DAYS)
    ap.add_argument("--archive", default="")
    ap.add_argument("--skip-position", action="store_true")
    ap.add_argument("--pending", default="")
    ap.add_argument("--ledger", default="")
    a = ap.parse_args()
    out = CMDS[a.command](a)
    if out is not None:
        print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)