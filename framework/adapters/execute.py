#!/usr/bin/env python3
"""Execution-position adapter -- DID-012 Pillar 2 (C0-C8 derivation, SUMMARY as render).

Makes "what is established, what is open, where do we continue" machine-readable and
DERIVED -- independent of conversation context and of compaction (DID-012 4.1, I9/I10).

Vocabulary (DID-012 4.2): reuses the C0-C8 checkpoint vocabulary VERBATIM from
`framework/tasks/task_types.yaml` (no rename) and extends with structural states:
STEP_STARTED | EVIDENCE_FOUND | EVIDENCE_VERIFIED | DECISION_MADE | STEP_COMPLETED |
BLOCKED | NEXT_ACTION_SET.

Semantics (DID-012 4.3) -- four concepts, never conflated:
  Completed    finished + verified          DERIVED (evidence + gate path), never model-written
  Fact         discovered during investigation  model proposes, claim ledger records
  Open question explicitly unresolved       model proposes
  Next action  where execution resumes      DERIVED from plan + completed/blocked

SUMMARY.md becomes a RENDER of materialized derived state, not authoritative state
(DID-012 4.4): write-summary generates the SUMMARY.md from materialized state; a handoff
is a view, and deleting + rebuilding from durable state must produce an equivalent
document (the first execution-state test, DID-012 7.7).

Invariant I8 (DID-012 section 6): NO model-authored authoritative status. `status`,
`position`, `derived_state`, and `next_action` are derived from evidence/events ONLY;
a write that authors any of them is REJECTED (exit 1, file not written).

Derivation rule (deterministic, I10):
  position = max(lifecycle floor, highest C-checkpoint RECORDED in events)
    no events                       -> NOT_STARTED        (contract written, never accepted)
    ACK seen                        -> floor C0-TASK_ACCEPTED
    STARTED seen                    -> floor C3-IMPLEMENTATION_STARTED  (work began; C1/C2 are
                                        only claimed when a checkpoint EVENT recorded them)
    PROGRESS w/o new checkpoint     -> heartbeat, NO advance (same milestone-vs-heartbeat
                                        semantics as gsd_state health)
    PROGRESS with checkpoint        -> position = that checkpoint (highest wins)
    BLOCKED event                   -> structural BLOCKED, status blocked
    COMPLETED event                 -> C8-HANDOFF_READY, status complete, terminal
    FAILED | CANCELLED | LOST       -> terminal (status failed/cancelled/lost)
  liveness: read from CONTROL_ROOT<state>/control/tasks.jsonl (one-log-one-derivation:
  this adapter reads the control adapter's DURABLE LOG, never re-derives its state
  machine). Absent under a hermetic EXEC_ROOT -> "unknown (no control record)".

Storage is not written by derive: the materialized view is a pure fold. Only
`render-summary` writes -- and it writes the SUMMARY.md render, atomically
(temp+os.replace; the T-FX1 lesson: a plain open("w") truncates before the new
content lands).

Exit codes:
  0  success / invariant holds
  1  named violation (I8 authored status, corrupt event stream, bad payload, unknown task)
  2  BLOCKED -- state root unreadable or a required input unreadable (never a pass)
  4  NOT_APPLICABLE -- the subject is terminal/empty and the check cannot apply

CLI:
  derive [--now ISO]                  materialized fold of every task in the state root
  render-summary --task TID [--json PAYLOAD] [--phase NAME] [--now ISO]
                                      compose the SUMMARY.md render; I8-reject authored status
  resume-context --task TID           RESUME block for context-builder (DID-012 4.5)
  selftest                            hermetic invariant suite (EXEC_ROOT isolated)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

# --- vocabulary (DID-012 4.2) ----------------------------------------------
C0_VALUE, C8_VALUE = 0, 8
CHECKPOINTS = [f"C{i}-{n}" for i, n in enumerate(
    ["TASK_ACCEPTED", "CONTEXT_READ", "PLAN_CONFIRMED", "IMPLEMENTATION_STARTED",
     "IMPLEMENTATION_COMPLETE", "TESTS_GREEN", "REVIEW_READY", "VERIFICATION_DONE",
     "HANDOFF_READY"])]
C_INDEX = {cp: i for i, cp in enumerate(CHECKPOINTS)}

STRUCTURAL_STATES = ["STEP_STARTED", "EVIDENCE_FOUND", "EVIDENCE_VERIFIED",
                     "DECISION_MADE", "STEP_COMPLETED", "BLOCKED", "NEXT_ACTION_SET"]

# Lifecycle-state -> position FLOOR. Deliberately under-claims: C1/C2 are only asserted
# when a checkpoint EVENT recorded them. PROGRESS without a new checkpoint is a heartbeat
# (liveness WITHOUT progress) and does not advance -- same rule gsd_state health uses.
LIFECYCLE_FLOOR = {
    "ACK": "C0-TASK_ACCEPTED",
    "STARTED": "C3-IMPLEMENTATION_STARTED",
    "PROGRESS": "C3-IMPLEMENTATION_STARTED",
    "BLOCKED": "C3-IMPLEMENTATION_STARTED",
    "COMPLETED": "C8-HANDOFF_READY",
    "FAILED": None, "CANCELLED": None, "LOST": None,
}
TERMINAL_STATUS = {"COMPLETED": "complete", "FAILED": "failed",
                   "CANCELLED": "cancelled", "LOST": "lost"}

# I8: derived-only fields a model may NOT author. All other payload keys are proposed
# content (summary, agent, files_changed, evidence pointers, risks, blockers, ...).
AUTHORITATIVE_FIELDS = ("status", "position", "derived_state", "next_action")

EXEC_REL = "execposition"
TASKS_REL = "tasks"
CONTROL_REL = "control"
DERIVED_FMT = "{:02d}"  # not used as log; kept for determinism tests

DEFAULT_PHASE = "00-unphased"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _state_root() -> Path:
    """State root via EXEC_ROOT override or the GSD state adapter -- one resolution."""
    if os.environ.get("EXEC_ROOT"):
        return Path(os.environ["EXEC_ROOT"])
    try:
        import gsd_state
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import gsd_state
        except ImportError as e:
            raise SystemExit(
                "BLOCKED: gsd_state.py not importable -- execute must not invent its own "
                "state root: " + str(e)
            )
    return gsd_state.root()


def _tasks_dir(root: Path | None = None) -> Path:
    return (root or _state_root()) / TASKS_REL


def _read_events(path: Path, what: str) -> list:
    """Fail-closed event load: a torn line blocks, never reads as healthy."""
    if not path.exists():
        return []
    out = []
    try:
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                s = line.strip()
                if not s:
                    continue
                try:
                    out.append(json.loads(s))
                except json.JSONDecodeError:
                    raise SystemExit(
                        f"EXEC_CORRUPT_LOG: {what} line {i} is not valid JSON -- a torn "
                        "log must block, never read as healthy"
                    )
    except OSError as e:
        raise SystemExit(f"EXEC_UNREADABLE: {what} unreadable: {e} -- BLOCKED, never a pass")
    return out


def _contract(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"NOT_FOUND: task {path.stem} is not registered (register first)")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"EXEC_BLOCKED: contract for {path.stem} unreadable: {e}")


def _list_tasks(root: Path) -> list:
    d = _tasks_dir(root)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json")
                  if not p.name.endswith(".events.jsonl")
                  and p.name != "index.json")


def _liveness(root: Path) -> dict:
    """Read-only fold of the CONTROL adapter's durable task log (one-log-one-derivation).
    Never re-derives control's state machine; absent control records under a hermetic
    EXEC_ROOT -> per-task liveness left unknown."""
    p = (root or _state_root()) / CONTROL_REL / "tasks.jsonl"
    out: dict = {}
    for ev in _read_events(p, "control/tasks"):
        tid = ev.get("task_id")
        if tid:
            out[tid] = ev
    return out


def _position_from_events(task_id: str, events: list) -> dict:
    """Fold a task's events into {position, status, structural, terminal} (I10)."""
    position = "NOT_STARTED"
    status = "in_progress"
    terminal = False
    structural: list = []
    log: list = []

    for ev in events:
        state = ev.get("state")
        cp = ev.get("checkpoint")
        detail = ev.get("detail") or {}
        if isinstance(detail, str):
            detail = {"note": detail}

        # terminal lifecycle states
        if state in TERMINAL_STATUS and state != "COMPLETED":
            return {"position": position, "status": TERMINAL_STATUS[state],
                    "terminal": True, "structural": structural, "log": log}

        if state == "COMPLETED":
            status = "complete"
            terminal = True
            position = "C8-HANDOFF_READY"
            structural.append("NEXT_ACTION_SET")
            return {"position": position, "status": status, "terminal": True,
                    "structural": sorted(set(structural)), "log": log}

        if state == "BLOCKED":
            structural.append("BLOCKED")
            status = "blocked"

        # lifecycle floor (never claims more than recorded)
        if state in LIFECYCLE_FLOOR and LIFECYCLE_FLOOR[state]:
            floor = LIFECYCLE_FLOOR[state]
            if position == "NOT_STARTED" or C_INDEX.get(floor, -1) > C_INDEX.get(position, -1):
                position = floor

        # explicit checkpoint event: highest recorded wins
        if cp and cp in C_INDEX:
            if position == "NOT_STARTED" or C_INDEX[cp] > C_INDEX.get(position, -1):
                position = cp

        # structural states from event detail (model may PROPOSE via detail; status never)
        if detail.get("step"):
            structural.append("STEP_STARTED" if detail.get("step") == "started" else "STEP_COMPLETED")
        if detail.get("evidence"):
            structural.append("EVIDENCE_FOUND")
        if detail.get("evidence_verified"):
            structural.append("EVIDENCE_VERIFIED")
        if detail.get("decision"):
            structural.append("DECISION_MADE")
        if detail.get("next_action"):
            structural.append("NEXT_ACTION_SET")

        log.append({"seq": ev.get("seq"), "state": state, "checkpoint": cp,
                    "ts": ev.get("ts")})

    return {"position": position, "status": status, "terminal": terminal,
            "structural": sorted(set(structural)), "log": log}


def derive(now: str | None = None) -> dict:
    """Deterministic materialized fold of the whole task set (I10)."""
    now = now or _now()
    root = _state_root()
    live = _liveness(root)
    tasks = {}
    for tid in _list_tasks(root):
        path = _tasks_dir(root) / f"{tid}.json"
        contract = _contract(path)
        events = _read_events(_tasks_dir(root) / f"{tid}.events.jsonl", f"events/{tid}")
        pos = _position_from_events(tid, events)
        tasks[tid] = {
            "task_id": tid,
            "position": pos["position"],
            "status": pos["status"],
            "terminal": pos["terminal"],
            "structural_states": pos["structural"],
            "checkpoint_history": pos["log"],
            "last_liveness_event": live.get(tid),
            "contract": contract,
        }
    return {"now": now, "tasks": tasks, "checkpoint_vocabulary": list(CHECKPOINTS)}


# --- payload parsing --------------------------------------------------------

def _parse_payload(payload: str) -> dict:
    """Parse the handoff payload into {key: raw value string}. Accepts a JSON object or
    a simple top-level `key: value` YAML-ish block (the .opencode/rules/handoff.md
    shape). The tiny parser is deliberately dependency-free."""
    if not payload or not payload.strip():
        return {}
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            return {str(k): v for k, v in obj.items()}
    except json.JSONDecodeError:
        pass
    out: dict = {}
    current = None
    for line in payload.splitlines():
        if not line.strip():
            continue
        if not line[:1].isspace():
            if ":" in line:
                key, _, val = line.partition(":")
                out[key.strip()] = val.strip()
                current = None
            continue
        # indented continuation (list items / multi-line values)
        if current is not None:
            out[current] = (str(out[current]) + "\n" + line.strip()).strip()
    return out


def _render_status(payload: dict, derived: dict) -> str:
    """Compose the handoff YAML with status/position/next_action DERIVED. Raises I8."""
    authored = [f for f in AUTHORITATIVE_FIELDS if f in payload]
    if authored:
        raise SystemExit(
            f"I8_VIOLATION: model-authored authoritative status field(s): {', '.join(authored)}"
            " -- status, position, derived_state, next_action are DERIVED from "
            "events/evidence only (DID-012 I8); write rejected"
        )
    lines = [f"task_id: {payload.get('task_id', '')}"]
    position = derived["position"]
    lines.append(f"status: {derived['status']}   # derived (I8)")
    lines.append(f"position: {position}   # derived (I8)")
    lines.append(f"terminal: {str(derived['terminal']).lower()}   # derived (I8)")
    if derived.get("next_action"):
        lines.append(f"next_action: {derived['next_action']}   # derived (I8)")
    for key, value in payload.items():
        if key == "task_id" or key in AUTHORITATIVE_FIELDS:
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, sort_keys=True)
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines)


def _derived_next_action(task_id: str, derived: dict) -> str:
    if derived["terminal"]:
        return "terminal -- no further execution"
    pos = derived["position"]
    if pos == "NOT_STARTED":
        return "accept the task (C0-TASK_ACCEPTED) and read context"
    idx = C_INDEX.get(pos)
    if idx is None:
        return f"resume from {pos}"
    nxt = CHECKPOINTS[idx + 1] if idx < C8_VALUE else "C8-HANDOFF_READY"
    return f"resume from {pos} toward {nxt}"


def _render_doc(task_id: str, rendered_yaml: str, now: str) -> str:
    return (f"# Summary {task_id}\n\n"
            f"_generated {now}_\n\n"
            f"```yaml\n{rendered_yaml}\n```\n")


def _atomic_write(path: Path, body: str) -> str:
    """Atomic overwrite (T-FX1): write a sibling temp and os.replace over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return str(path)


# --- commands ---------------------------------------------------------------

def cmd_derive(a) -> int:
    out = derive(a.now)
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0


def cmd_render_summary(a) -> int:
    root = _state_root()
    task_path = _tasks_dir(root) / f"{a.task}.json"
    contract = _contract(task_path)          # unknown task -> NOT_FOUND, exit 1
    events = _read_events(_tasks_dir(root) / f"{a.task}.events.jsonl", f"events/{a.task}")
    pos = _position_from_events(a.task, events)
    payload = _parse_payload(a.json)
    pos["next_action"] = _derived_next_action(a.task, pos)
    rendered = _render_status(payload, pos)  # I8 raise before any write
    phase = a.phase or DEFAULT_PHASE
    p = root / "phases" / phase / f"{a.task}-SUMMARY.md"
    _atomic_write(p, _render_doc(a.task, rendered, a.now or _now()))
    print(str(p))
    return 0


def cmd_resume_context(a) -> int:
    root = _state_root()
    _contract(_tasks_dir(root) / f"{a.task}.json")     # NOT_FOUND -> exit 1
    events = _read_events(_tasks_dir(root) / f"{a.task}.events.jsonl", f"events/{a.task}")
    pos = _position_from_events(a.task, events)
    pos["next_action"] = _derived_next_action(a.task, pos)
    done = [f"{e.get('checkpoint')} @ {e.get('ts')}" for e in pos["log"]
            if e.get("checkpoint")]
    not_est = [e.get("state") for e in pos["log"] if e.get("state") == "BLOCKED"]
    lines = [
        f"RESUME {a.task}",
        "",
        f"Position: {pos['position']}   # derived (I10, I8)",
        f"Status: {pos['status']}   # derived (I8)",
        f"Already completed: {', '.join(done) if done else 'none recorded'}",
        f"Established facts: recorded in claim ledger (CLM refs in event detail)",
        f"Not established: {', '.join(not_est) if not_est else 'see open questions in summary'}",
        f"Next action: {pos['next_action']}   # derived (I8)",
    ]
    print("\n".join(lines))
    return 0


# --- selftest ---------------------------------------------------------------

def selftest() -> dict:
    """Hermetic invariant suite under an isolated EXEC_ROOT. Every check must be able
    to mutate-to-fail (validate.py [34] judges this adapter by selftest exit 0)."""
    import shutil
    results: dict = {}
    tmp = Path(tempfile.mkdtemp(prefix="exec-selftest-"))
    old = os.environ.get("EXEC_ROOT")
    os.environ["EXEC_ROOT"] = str(tmp)

    def _write_events(tid: str, events: list):
        p = _tasks_dir(tmp) / f"{tid}.events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")

    def _write_contract(tid: str, contract: dict | None = None):
        p = _tasks_dir(tmp) / f"{tid}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(contract or {"objective": "selftest", "status": "live"}),
                     encoding="utf-8")

    try:
        # 1. no events -> NOT_STARTED
        _write_contract("T-00")
        st = _position_from_events("T-00", [])
        results["no_events_is_not_started"] = "pass" if st["position"] == "NOT_STARTED" \
            else f"fail: {st['position']}"

        # 2. ACK -> C0 floor
        _write_events("T-01", [{"state": "ACK", "ts": "2026-01-01T00:00:00+00:00", "seq": 1}])
        st = _position_from_events("T-01",
                                   [{"state": "ACK", "ts": "2026-01-01T00:00:00+00:00"}])
        results["ack_floor_is_acceptance"] = "pass" if st["position"] == "C0-TASK_ACCEPTED" \
            else f"fail: {st['position']}"

        # 3. STARTED -> C3 floor (work began; C1/C2 not claimed without checkpoint events)
        _write_events("T-02", [{"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00", "seq": 1}])
        st = _position_from_events("T-02",
                                   [{"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00"}])
        results["started_floor_is_implementation"] = \
            "pass" if st["position"] == "C3-IMPLEMENTATION_STARTED" else f"fail: {st['position']}"

        # 4. explicit checkpoint event advances position
        _write_events("T-03", [
            {"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00", "seq": 1},
            {"state": "PROGRESS", "checkpoint": "C5-TESTS_GREEN",
             "ts": "2026-01-01T00:00:10+00:00", "seq": 2},
        ])
        st = _position_from_events("T-03", [
            {"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00"},
            {"state": "PROGRESS", "checkpoint": "C5-TESTS_GREEN",
             "ts": "2026-01-01T00:00:10+00:00"},
        ])
        results["progress_checkpoint_advances"] = \
            "pass" if st["position"] == "C5-TESTS_GREEN" else f"fail: {st['position']}"

        # 5. PROGRESS without a new checkpoint is a HEARTBEAT (no advance)
        _write_events("T-04", [
            {"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00", "seq": 1},
            {"state": "PROGRESS", "ts": "2026-01-01T00:00:10+00:00", "seq": 2},
        ])
        st = _position_from_events("T-04", [
            {"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00"},
            {"state": "PROGRESS", "ts": "2026-01-01T00:00:10+00:00"},
        ])
        results["heartbeat_does_not_advance"] = \
            "pass" if st["position"] == "C3-IMPLEMENTATION_STARTED" else f"fail: {st['position']}"

        # 6. COMPLETED -> C8 + complete + terminal
        st = _position_from_events("T-05", [{"state": "COMPLETED", "ts": "2026-01-01T00:00:00+00:00"}])
        results["completed_is_c8_terminal"] = \
            "pass" if (st["position"] == "C8-HANDOFF_READY" and st["status"] == "complete"
                       and st["terminal"]) else f"fail: {st}"

        # 7. FAILED -> terminal, status failed
        st = _position_from_events("T-06", [{"state": "FAILED", "ts": "2026-01-01T00:00:00+00:00"}])
        results["failed_is_terminal"] = \
            "pass" if (st["status"] == "failed" and st["terminal"]) else f"fail: {st}"

        # 8. BLOCKED event -> structural BLOCKED + status blocked
        _write_contract("T-07")
        _write_events("T-07", [{"state": "BLOCKED", "detail": {"note": "waiting"},
                                "ts": "2026-01-01T00:00:00+00:00", "seq": 1}])
        st = _position_from_events("T-07",
                                   [{"state": "BLOCKED", "detail": {"note": "waiting"},
                                     "ts": "2026-01-01T00:00:00+00:00"}])
        results["blocked_sets_structural"] = \
            "pass" if (st["status"] == "blocked" and "BLOCKED" in st["structural"]) \
            else f"fail: {st}"

        # 9. I8: model-authored status is REJECTED (write never happens)
        _write_contract("T-08")
        payload_w_status = '{"task_id": "T-08", "status": "complete", "summary": "hi"}'
        try:
            _render_status(_parse_payload(payload_w_status),
                           {"position": "C3-IMPLEMENTATION_STARTED", "status": "in_progress",
                            "terminal": False, "next_action": "x"})
            results["i8_rejects_model_status"] = "fail: no exception"
        except SystemExit as e:
            results["i8_rejects_model_status"] = \
                "pass" if "I8_VIOLATION" in str(e) else f"fail: wrong error {e}"

        # 10. I8: next_action is derived-only too
        payload_w_next = '{"task_id": "T-08", "next_action": "do the thing"}'
        try:
            _render_status(_parse_payload(payload_w_next),
                           {"position": "C3-IMPLEMENTATION_STARTED", "status": "in_progress",
                            "terminal": False, "next_action": "x"})
            results["i8_rejects_model_next_action"] = "fail: no exception"
        except SystemExit as e:
            results["i8_rejects_model_next_action"] = \
                "pass" if "next_action" in str(e) else f"fail: wrong error {e}"

        # 11. Render determinism: same state + same --now -> byte-identical document
        _write_contract("T-09", {"objective": "determinism"})
        _write_events("T-09", [
            {"state": "STARTED", "ts": "2026-01-01T00:00:00+00:00", "seq": 1},
            {"state": "PROGRESS", "checkpoint": "C4-IMPLEMENTATION_COMPLETE",
             "ts": "2026-01-01T00:00:10+00:00", "seq": 2},
        ])
        events9 = _read_events(_tasks_dir(tmp) / "T-09.events.jsonl", "events/T-09")
        pos9 = _position_from_events("T-09", events9)
        pos9["next_action"] = _derived_next_action("T-09", pos9)
        y1 = _render_status(_parse_payload('{"task_id": "T-09", "summary": "done"}'), pos9)
        y2 = _render_status(_parse_payload('{"task_id": "T-09", "summary": "done"}'), pos9)
        results["render_deterministic"] = \
            "pass" if y1 == y2 else f"fail: renders differ\n{y1}\n---\n{y2}"

        # 12. delete + rebuild equivalence (DID-012 7.7): same --now -> equivalent doc
        doc = _render_doc("T-09", y1, "2026-01-01T00:00:00+00:00")
        doc2 = _render_doc("T-09", _render_status(_parse_payload('{"task_id": "T-09", "summary": "done"}'),
                                                 pos9), "2026-01-01T00:00:00+00:00")
        results["summary_rebuild_equivalent"] = \
            "pass" if doc == doc2 else "fail: rebuild differs"

        # 13. torn event stream blocks (fail closed)
        _write_contract("T-10")
        p = _tasks_dir(tmp) / "T-10.events.jsonl"
        p.write_text('{"state": "STARTED"}\nNOT JSON\n', encoding="utf-8")
        try:
            _read_events(p, "events/T-10")
            results["torn_events_block"] = "fail: no exception"
        except SystemExit as e:
            results["torn_events_block"] = \
                "pass" if "EXEC_CORRUPT_LOG" in str(e) else f"fail: wrong error {e}"
        finally:
            # the torn fixture must not leak into the shared EXEC_ROOT: check 14's
            # derive() folds over EVERY task and would re-trip this torn log
            p.unlink(missing_ok=True)

        # 14. derive is deterministic across runs (I10)
        d1 = derive("2026-01-01T00:00:00+00:00")
        d2 = derive("2026-01-01T00:00:00+00:00")
        results["derive_deterministic"] = \
            "pass" if json.dumps(d1, sort_keys=True, default=str) == \
                      json.dumps(d2, sort_keys=True, default=str) else "fail: derive differs"
    finally:
        if old is None:
            os.environ.pop("EXEC_ROOT", None)
        else:
            os.environ["EXEC_ROOT"] = old
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def _run_selftest() -> int:
    results = selftest()
    fails = [k for k, v in results.items() if v != "pass"]
    print(json.dumps(results, indent=2, sort_keys=True))
    if fails:
        print(f"SELFTEST FAILED: {', '.join(sorted(fails))}", file=sys.stderr)
        return 1
    return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Execution-position adapter (DID-012 Pillar 2)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("derive").add_argument("--now")
    rs = sub.add_parser("render-summary")
    rs.add_argument("--task", required=True)
    rs.add_argument("--json", default="")
    rs.add_argument("--phase")
    rs.add_argument("--now")

    rc = sub.add_parser("resume-context")
    rc.add_argument("--task", required=True)

    sub.add_parser("selftest")

    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        return _run_selftest()
    if a.cmd == "derive":
        return cmd_derive(a)
    if a.cmd == "render-summary":
        return cmd_render_summary(a)
    if a.cmd == "resume-context":
        return cmd_resume_context(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())