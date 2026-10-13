#!/usr/bin/env python3
"""Intake adapter -- DID-012 Pillar 1 (durable ASK identity and conservation).

One append-only event log is the single source; ASK state is DERIVED from it by a
deterministic fold. Nothing here mutates or deletes an event (I11), and no caller may
supply a status or an id -- the adapter allocates the id and the capture event always
establishes CAPTURED (I8: no model-authored authoritative status).

Invariants enforced by this adapter (DID-012 section 6):
  I1  every executable request has an ASK_ID               -> verify-task / coverage
  I2  every ASK_ID terminates COMPLETED|DEFERRED|REJECTED  -> coverage
  I8  no model-authored authoritative status               -> capture rejects status/ask_id
  I10 deterministic derivation: same log -> same state      -> selftest
  I11 append-only provenance: events never mutate or delete -> _asks() blocks on divergence

Storage (adapter-owned, under the GSD state root):
  <state_root>/intake/asks.jsonl    append-only event log

Exit codes:
  0  success / invariant holds
  1  named violation (invalid transition, unbound executable task, corrupt log)
  2  BLOCKED -- state root or a required input is unreadable (never a pass)
  4  NOT_APPLICABLE -- the check cannot apply to the subject (never a pass)

CLI:
  capture --json '{"session_id":..,"original_text":..[,...]}'
  transition --id ASK-001 --json '{"status":"CONFIRMED"}'
  show --id ASK-001
  list
  coverage [--completion]
  verify-task --id T-01
  selftest
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# --- vocabulary (DID-012 section 3.3) -------------------------------------
ASK_STATES = ("CAPTURED", "CONFIRMED", "PLANNED", "EXECUTING",
              "COMPLETED", "DEFERRED", "REOPENED", "REJECTED")
# I2 resting points. DEFERRED is terminal for I2 but reopenable (section 3.3), so it is
# deliberately excluded from ASK_FINAL -- conflating the two breaks DEFERRED -> REOPENED.
ASK_TERMINAL = ("COMPLETED", "DEFERRED", "REJECTED")
ASK_FINAL = ("COMPLETED", "REJECTED")
# CAPTURED -> CONFIRMED -> PLANNED -> EXECUTING -> COMPLETED
#                 \-> DEFERRED -> REOPENED            \-> DEFERRED
#                 \-> REJECTED
ASK_NEXT = {
    "CAPTURED": ("CONFIRMED", "DEFERRED", "REJECTED"),
    "CONFIRMED": ("PLANNED", "DEFERRED", "REJECTED"),
    "PLANNED": ("EXECUTING", "DEFERRED", "REJECTED"),
    "EXECUTING": ("COMPLETED", "DEFERRED"),
    "DEFERRED": ("REOPENED", "REJECTED"),
    "REOPENED": ("PLANNED", "EXECUTING", "REJECTED"),
}
PRIORITIES = ("P0", "P1", "P2", "P3")
SOURCES = ("hook", "user", "system")
# The model may propose content, never the authoritative record: a capture that names its
# own emitter as a model is refused rather than silently relabelled.
MODEL_EMITTERS = ("model", "assistant", "agent", "llm")

TASKS_REL = "tasks"
INTAKE_REL = "intake"
LOG_NAME = "asks.jsonl"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _state_root() -> Path:
    """State root via the GSD state adapter -- one resolution path, not a second one."""
    if os.environ.get("INTAKE_ROOT"):
        return Path(os.environ["INTAKE_ROOT"])
    try:
        import gsd_state
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import gsd_state
        except ImportError as e:
            raise SystemExit(
                "BLOCKED: gsd_state.py not importable -- intake must not invent its own "
                "state root: " + str(e)
            )
    return gsd_state.root()


def _intake_dir() -> Path:
    return _state_root() / INTAKE_REL


def _log_path() -> Path:
    return _intake_dir() / LOG_NAME


def _tasks_dir() -> Path:
    return _state_root() / TASKS_REL


def _parse_json(raw, what="ASK"):
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"ASK_INVALID_JSON: {what} payload unreadable: {e}")
    if not isinstance(v, dict):
        raise SystemExit(f"ASK_INVALID_JSON: {what} payload must be a JSON object")
    return v


# --- log + derivation ------------------------------------------------------

def _load_events() -> list:
    p = _log_path()
    if not p.exists():
        return []
    out = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"ASK_INTAKE_BLOCKED: intake log unreadable: {e}")
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            # Fail closed: a torn line must not read as "no asks".
            raise SystemExit(
                f"ASK_INTAKE_BLOCKED: intake log corrupt at line {i + 1}: {e}"
            )
    return out


def _append(event: dict):
    d = _intake_dir()
    d.mkdir(parents=True, exist_ok=True)
    with (d / LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def asks() -> dict:
    """Deterministic derivation: fold the event log into current ASK state.

    Divergence (a transition whose `from` does not match the derived state, a duplicate
    capture, a transition for an unknown ask) is a corrupted log and BLOCKS -- it is never
    reconciled by guessing which view is right (DID-012 section 1.3).
    """
    state = {}
    for ev in _load_events():
        kind = ev.get("event")
        aid = ev.get("ask_id")
        if not aid:
            raise SystemExit("ASK_INTAKE_BLOCKED: event without ask_id")
        if kind == "ASK_CAPTURED":
            if aid in state:
                raise SystemExit(
                    f"ASK_INTAKE_BLOCKED: duplicate capture for {aid} "
                    "(append-only provenance violated)"
                )
            rec = dict(ev.get("record") or {})
            rec["ask_id"] = aid
            rec["status"] = "CAPTURED"
            rec["history"] = [{"to": "CAPTURED", "ts": ev.get("ts"),
                               "emitter": ev.get("emitter")}]
            state[aid] = rec
        elif kind == "ASK_TRANSITIONED":
            rec = state.get(aid)
            if rec is None:
                raise SystemExit(
                    f"ASK_INTAKE_BLOCKED: transition for uncaptured ask {aid}"
                )
            if rec["status"] != ev.get("from"):
                raise SystemExit(
                    f"ASK_INTAKE_BLOCKED: {aid} transitions from {ev.get('from')!r} but "
                    f"derived state is {rec['status']!r} -- log is not self-consistent"
                )
            rec["status"] = ev.get("to")
            rec["history"].append({"from": ev.get("from"), "to": ev.get("to"),
                                   "ts": ev.get("ts"), "emitter": ev.get("emitter")})
        else:
            raise SystemExit(f"ASK_INTAKE_BLOCKED: unknown event kind {kind!r}")
    return state


def _next_id(state: dict) -> str:
    mx = 0
    for aid in state:
        if aid.startswith("ASK-"):
            try:
                mx = max(mx, int(aid[4:]))
            except ValueError:
                continue
    return f"ASK-{mx + 1:03d}"


# --- commands --------------------------------------------------------------

CAPTURE_REQUIRED = ("session_id", "original_text")


def capture(payload: dict) -> dict:
    payload = payload or {}
    # I8: the adapter allocates identity and status. A payload that tries to author
    # either is refused, not silently ignored.
    if payload.get("ask_id"):
        raise SystemExit(
            "ASK_INVALID_FIELD: ask_id is adapter-allocated; a caller may not author it"
        )
    if payload.get("status"):
        raise SystemExit(
            "ASK_INVALID_FIELD: status is derived from events; a caller may not author it"
        )
    for f in CAPTURE_REQUIRED:
        if not str(payload.get(f) or "").strip():
            raise SystemExit(f"ASK_INVALID_FIELD: {f} is required and must be non-empty")

    emitter = str(payload.get("emitter") or "intake-hook").strip().lower()
    if emitter in MODEL_EMITTERS:
        raise SystemExit(
            "ASK_INVALID_EMITTER: capture is a deterministic hook, not a model act "
            f"(emitter={emitter!r}); the model proposes content, never the record"
        )
    source = str(payload.get("source") or "user").strip().lower()
    if source not in SOURCES:
        raise SystemExit(
            f"ASK_INVALID_FIELD: source {source!r}; legal: {', '.join(SOURCES)}"
        )
    priority = str(payload.get("priority") or "P2").strip().upper()
    if priority not in PRIORITIES:
        raise SystemExit(
            f"ASK_INVALID_FIELD: priority {priority!r}; legal: {', '.join(PRIORITIES)}"
        )
    acs = payload.get("acceptance_criteria") or []
    if not isinstance(acs, list):
        raise SystemExit("ASK_INVALID_FIELD: acceptance_criteria must be a list")

    state = asks()
    parent = payload.get("parent_ask_id")
    if parent and parent not in state:
        raise SystemExit(
            f"ASK_INVALID_FIELD: parent_ask_id {parent} is not a captured ask"
        )
    aid = _next_id(state)
    record = {
        "session_id": str(payload["session_id"]),
        "source": source,
        "original_text": str(payload["original_text"]),
        "normalized_requirement": str(
            payload.get("normalized_requirement") or payload["original_text"]
        ),
        "created_at": _now(),
        "parent_ask_id": parent,
        "acceptance_criteria": [str(a) for a in acs],
        "priority": priority,
        "provenance": payload.get("provenance") or {"session": str(payload["session_id"])},
    }
    _append({"event": "ASK_CAPTURED", "ask_id": aid, "ts": record["created_at"],
             "emitter": emitter, "record": record})
    return show(aid)


def _completion_guard(ask_id: str) -> None:
    """DID-017: an ASK cannot be COMPLETED while a plan that declares it lacks fresh, passing,
    harness-produced system-test evidence. Unverifiable is not a pass. No-op where the harness
    is not installed (isolated self-tests)."""
    harness = Path("framework/testing/run_system_tests.py")
    if not harness.exists():
        return
    import subprocess
    try:
        r = subprocess.run([sys.executable, str(harness), "ask-gate", "--ask", ask_id],
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise SystemExit(f"COMPLETION_BLOCKED: system-test guard could not run: {e}")
    if r.returncode != 0:
        detail = (r.stdout or r.stderr).strip()
        raise SystemExit(
            f"COMPLETION_BLOCKED: {ask_id} lacks fresh, passing system-test evidence. "
            f"Run framework/testing/run_system_tests.py for its plan. {detail}")


def transition(ask_id: str, payload: dict) -> dict:
    payload = payload or {}
    if not ask_id:
        raise SystemExit("ASK_INVALID_FIELD: --id is required for transition")
    to = str(payload.get("status") or "").strip().upper()
    if not to:
        raise SystemExit("ASK_INVALID_FIELD: status is required for transition")
    if to not in ASK_STATES:
        raise SystemExit(
            f"ASK_INVALID_STATE: {to!r}; legal states: {', '.join(ASK_STATES)}"
        )
    state = asks()
    rec = state.get(ask_id)
    if rec is None:
        raise SystemExit(f"NOT_FOUND: ask {ask_id} is not captured (capture first)")
    cur = rec["status"]
    if cur in ASK_FINAL:
        raise SystemExit(
            f"ASK_TERMINAL_STATE: {ask_id} is already {cur}; no further transitions"
        )
    nxt = ASK_NEXT.get(cur, ())
    if to not in nxt:
        raise SystemExit(
            f"INVALID_TRANSITION: {cur} -> {to}; "
            f"legal next states: {', '.join(sorted(nxt))}"
        )
    if to == "COMPLETED":
        _completion_guard(ask_id)
    _append({"event": "ASK_TRANSITIONED", "ask_id": ask_id, "from": cur, "to": to,
             "ts": _now(), "emitter": str(payload.get("emitter") or "team-lead")})
    return show(ask_id)


def show(ask_id: str) -> dict:
    rec = asks().get(ask_id)
    if rec is None:
        raise SystemExit(f"NOT_FOUND: ask {ask_id} is not captured")
    return rec


def list_asks() -> list:
    return [v for _, v in sorted(asks().items())]


def open_asks() -> list:
    return [r for r in list_asks() if r["status"] not in ASK_TERMINAL]


# --- invariant checks ------------------------------------------------------

def _task_contract(task_id: str):
    p = _tasks_dir() / f"{task_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"ASK_INTAKE_BLOCKED: task contract {task_id} unreadable: {e}")


TASK_TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "LOST")


def _task_state(task_id: str) -> str:
    """Last event state, or SPAWNED when no events exist (gsd_state convention)."""
    p = _tasks_dir() / f"{task_id}.events.jsonl"
    if not p.exists():
        return "SPAWNED"
    last = None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                raise SystemExit(
                    f"ASK_INTAKE_BLOCKED: event stream for {task_id} corrupt"
                )
    return last.get("state") if last else "SPAWNED"


def verify_task(task_id: str) -> dict:
    """I1 at dispatch: every EXECUTABLE task carries an ask_id bound to a known ask.

    A terminal task is not executable, so the invariant does not apply to it (exit 4).
    Exits 1 with a named reason when an executable task is unbound or bound to an
    unknown ask. Exits 2 when the task itself is unreadable.
    """
    if not task_id:
        raise SystemExit("ASK_INVALID_FIELD: --id is required for verify-task")
    contract = _task_contract(task_id)
    if contract is None:
        print(f"BLOCKED: task {task_id} is not registered -- ownership unreadable",
              file=sys.stderr)
        raise SystemExit(2)
    state = _task_state(task_id)
    if state in TASK_TERMINAL:
        print(f"NOT_APPLICABLE: task {task_id} is {state}; I1 governs executable tasks")
        raise SystemExit(4)
    aid = str(contract.get("ask_id") or "").strip()
    if not aid:
        print(
            f"ASK_UNBOUND: executable task {task_id} ({state}) has no ask_id; "
            "I1 asks conservation violated", file=sys.stderr,
        )
        raise SystemExit(1)
    if aid not in asks():
        print(
            f"ASK_UNBOUND: task {task_id} references {aid}, which is not in durable "
            "intake", file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"OK: task {task_id} is bound to {aid} ({asks()[aid]['status']})")
    return {"task_id": task_id, "state": state, "ask_id": aid,
            "ask_status": asks()[aid]["status"]}


def coverage(completion: bool = False) -> dict:
    """I1 + I2 across the whole store. Exit 1 on any violation; 2 when unreadable.

    I1 (every executable task is bound to a known ASK) always gates the exit code.
    I2 (every ASK has terminated) is REPORTED truthfully in every mode, and gates the
    exit code only when `completion` is true -- the caller is asserting "the work is
    finished", and finished work with an open ASK is a violation. Without that flag an
    open ASK is the normal state of work in progress, so the default exit code is
    unchanged for existing callers.
    """
    state = asks()
    unbound, executable = [], 0
    d = _tasks_dir()
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            if p.name.endswith(".contract.json"):
                continue
            tid = p.stem
            st = _task_state(tid)
            if st in TASK_TERMINAL:
                continue
            executable += 1
            contract = _task_contract(tid) or {}
            aid = str(contract.get("ask_id") or "").strip()
            if not aid or aid not in state:
                unbound.append({"task_id": tid, "state": st, "ask_id": aid or None})
    unterminated = [{"ask_id": r["ask_id"], "status": r["status"]}
                    for r in open_asks()]
    report = {
        "asks_total": len(state),
        "asks_unterminated": unterminated,
        "tasks_executable": executable,
        "tasks_unbound": unbound,
        "invariants": {
            "I1_every_executable_task_has_ask": not unbound,
            "I2_every_ask_terminates": not unterminated,
        },
        "completion_mode": bool(completion),
    }
    violated = False
    if unbound:
        violated = True
        print("I1 VIOLATED: executable tasks without a bound ASK_ID:", file=sys.stderr)
        for u in unbound:
            print(f"  - {u['task_id']} ({u['state']}) ask_id={u['ask_id']}", file=sys.stderr)
    if completion and unterminated:
        violated = True
        print("I2 VIOLATED: ASKs that have not terminated "
              "(COMPLETED | DEFERRED | REJECTED):", file=sys.stderr)
        for u in unterminated:
            print(f"  - {u['ask_id']} ({u['status']})", file=sys.stderr)
    if violated:
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    return report


# --- selftest --------------------------------------------------------------

def selftest() -> dict:
    import tempfile
    results = {}
    with tempfile.TemporaryDirectory() as td:
        os.environ["INTAKE_ROOT"] = td
        try:
            a = capture({"session_id": "ses_test", "original_text": "do the thing",
                         "priority": "P1"})
            results["capture_allocates_id"] = "pass" if a["ask_id"] == "ASK-001" else (
                "fail: " + a["ask_id"])
            results["capture_starts_CAPTURED"] = "pass" if a["status"] == "CAPTURED" else (
                "fail: " + a["status"])

            # I8: the model may not author identity or status
            try:
                capture({"session_id": "s", "original_text": "x", "status": "COMPLETED"})
                results["rejects_authored_status"] = "fail: authored status accepted"
            except SystemExit:
                results["rejects_authored_status"] = "pass"
            try:
                capture({"session_id": "s", "original_text": "x", "ask_id": "ASK-999"})
                results["rejects_authored_id"] = "fail: authored id accepted"
            except SystemExit:
                results["rejects_authored_id"] = "pass"
            try:
                capture({"session_id": "s", "original_text": "x", "emitter": "model"})
                results["rejects_model_emitter"] = "fail: model emitter accepted"
            except SystemExit:
                results["rejects_model_emitter"] = "pass"

            # required fields
            try:
                capture({"original_text": "no session"})
                results["requires_session_id"] = "fail: missing session_id accepted"
            except SystemExit:
                results["requires_session_id"] = "pass"

            # INVALID_TRANSITION names the legal next states
            b = capture({"session_id": "ses_test", "original_text": "second ask"})
            try:
                transition(b["ask_id"], {"status": "COMPLETED"})
                results["rejects_invalid_transition"] = "fail: CAPTURED->COMPLETED accepted"
            except SystemExit as e:
                results["rejects_invalid_transition"] = (
                    "pass" if "legal next states" in str(e) else "fail: " + str(e))

            # legal chain + terminal
            transition(b["ask_id"], {"status": "CONFIRMED"})
            transition(b["ask_id"], {"status": "PLANNED"})
            transition(b["ask_id"], {"status": "EXECUTING"})
            done = transition(b["ask_id"], {"status": "COMPLETED"})
            results["legal_chain"] = "pass" if done["status"] == "COMPLETED" else (
                "fail: " + done["status"])
            try:
                transition(b["ask_id"], {"status": "DEFERRED"})
                results["terminal_is_final"] = "fail: transition after COMPLETED accepted"
            except SystemExit:
                results["terminal_is_final"] = "pass"
            results["history_is_append_only"] = "pass" if len(done["history"]) == 5 else (
                "fail: history len " + str(len(done["history"])))

            c = capture({"session_id": "ses_test", "original_text": "third"})
            transition(c["ask_id"], {"status": "DEFERRED"})
            try:
                re_ = transition(c["ask_id"], {"status": "REOPENED"})
                results["deferred_reopens"] = "pass" if re_["status"] == "REOPENED" else (
                    "fail: " + re_["status"])
            except SystemExit as e:
                results["deferred_reopens"] = "fail: reopen refused: " + str(e)

            # I10: same log derives the same state twice
            results["deterministic_derivation"] = (
                "pass" if asks() == asks() else "fail: derivation diverged")

            # I1: executable task bound / unbound
            tasks = Path(td) / "tasks"
            tasks.mkdir(parents=True, exist_ok=True)
            (tasks / "T-BOUND.json").write_text(
                json.dumps({"agent": "x", "ask_id": "ASK-001"}), encoding="utf-8")
            (tasks / "T-FREE.json").write_text(
                json.dumps({"agent": "x"}), encoding="utf-8")
            try:
                verify_task("T-BOUND")
                results["bound_task_passes"] = "pass"
            except SystemExit as e:
                results["bound_task_passes"] = "fail: exit " + str(e.code)
            try:
                verify_task("T-FREE")
                results["unbound_task_blocks"] = "fail: unbound task accepted"
            except SystemExit as e:
                results["unbound_task_blocks"] = "pass" if e.code == 1 else (
                    "fail: exit " + str(e.code))
            try:
                coverage()
                results["coverage_blocks_unbound"] = "fail: coverage passed with unbound task"
            except SystemExit as e:
                results["coverage_blocks_unbound"] = "pass" if e.code == 1 else (
                    "fail: exit " + str(e.code))

            # torn log blocks rather than reading as empty
            with _log_path().open("a", encoding="utf-8") as fh:
                fh.write("{not json\n")
            try:
                asks()
                results["torn_log_blocks"] = "fail: torn log read as healthy"
            except SystemExit:
                results["torn_log_blocks"] = "pass"
        finally:
            os.environ.pop("INTAKE_ROOT", None)
    failed = sorted(k for k, v in results.items() if v != "pass")
    if failed:
        print(json.dumps(results, indent=2))
        print("SELFTEST FAILED: " + ", ".join(failed), file=sys.stderr)
        raise SystemExit(1)
    return results


CMDS = {
    "capture": lambda a: capture(_parse_json(a.json)),
    "transition": lambda a: transition(a.id, _parse_json(a.json)),
    "show": lambda a: show(a.id),
    "list": lambda a: list_asks(),
    "open": lambda a: open_asks(),
    "coverage": lambda a: coverage(completion=a.completion),
    "verify-task": lambda a: verify_task(a.id),
    "selftest": lambda a: selftest(),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Intake adapter (DID-012 Pillar 1)")
    ap.add_argument("command", choices=sorted(CMDS))
    ap.add_argument("--id", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--completion", action="store_true",
                    help="coverage only: also fail (exit 1) when any ASK has not terminated")
    ap.add_argument("--json-file", default="",
                    help="read the command payload from a file instead of --json "
                         "(PowerShell-safe: avoids inline-quote mangling)")
    a = ap.parse_args()
    payload_file = getattr(a, "json_file", "")
    if payload_file:
        a.json = Path(payload_file).read_text(encoding="utf-8")
    out = CMDS[a.command](a)
    if out is not None:
        print(json.dumps(out, indent=2) if isinstance(out, (dict, list)) else out)
