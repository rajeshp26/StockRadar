"""Execution-position adapter tests -- DID-012 Pillar 2 (C0-C8 derivation, SUMMARY as render).

Each test asserts an invariant the adapter must refuse to violate; the point is that the
adapter goes RED, not that the happy path runs. Derived fields (status, position,
derived_state, next_action) are I8-protected: the adapter rejects any attempt to author
them, which is what makes "what is established" survive compaction (DID-012 4.1, I9/I10).

execute.py carries violation markers in the SystemExit payload itself (SystemExit(marker)),
unlike control.py which prints to stderr and exits 1 -- so markers are asserted via
str(e.value), mirroring test_control.py's corrupt-log paths.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ADAPTER = HERE / "execute.py"


def _load():
    spec = importlib.util.spec_from_file_location("execute_adapter", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["execute_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


execute = _load()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_ROOT", str(tmp_path))
    return tmp_path


def _write_contract(store, task_id, contract=None):
    d = store / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{task_id}.json").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(contract or {"objective": "test", "status": "live"}))
    return d


def _write_events(store, task_id, events):
    d = store / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{task_id}.events.jsonl").open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, sort_keys=True) + "\n")
    return d


def _ack(seq=1):
    return {"state": "ACK", "ts": "2026-01-01T00:00:00+00:00", "seq": seq}


def _started(seq=1):
    return {"state": "STARTED", "ts": "2026-01-01T00:00:01+00:00", "seq": seq}


def _progress(checkpoint=None, seq=2):
    ev = {"state": "PROGRESS", "ts": "2026-01-01T00:00:10+00:00", "seq": seq}
    if checkpoint:
        ev["checkpoint"] = checkpoint
    return ev


# --- vocabulary is the C0-C8 contract, verbatim (DID-012 4.2) ---------------

def test_checkpoint_vocabulary_is_declared(store):
    assert execute.CHECKPOINTS == [
        "C0-TASK_ACCEPTED", "C1-CONTEXT_READ", "C2-PLAN_CONFIRMED",
        "C3-IMPLEMENTATION_STARTED", "C4-IMPLEMENTATION_COMPLETE", "C5-TESTS_GREEN",
        "C6-REVIEW_READY", "C7-VERIFICATION_DONE", "C8-HANDOFF_READY",
    ]
    assert len(execute.C_INDEX) == 9


def test_derive_reports_checkpoint_vocabulary(store):
    out = execute.derive()
    assert out["checkpoint_vocabulary"] == execute.CHECKPOINTS


# --- derived position: no authoring, deterministic floor (I10) --------------

def test_no_events_is_not_started(store):
    _write_contract(store, "T-00")
    st = execute.derive()["tasks"]["T-00"]
    assert st["position"] == "NOT_STARTED"
    assert st["status"] == "in_progress"
    assert st["terminal"] is False


def test_ack_floor_is_acceptance(store):
    _write_contract(store, "T-01")
    _write_events(store, "T-01", [_ack()])
    st = execute.derive()["tasks"]["T-01"]
    assert st["position"] == "C0-TASK_ACCEPTED"


def test_started_never_claims_unrecorded_checkpoints(store):
    # STARTED raises the floor to C3 but C1/C2 are only claimed via checkpoint events
    _write_contract(store, "T-02")
    _write_events(store, "T-02", [_started()])
    st = execute.derive()["tasks"]["T-02"]
    assert st["position"] == "C3-IMPLEMENTATION_STARTED"


def test_checkpoint_progress_advances_position(store):
    _write_contract(store, "T-03")
    _write_events(store, "T-03", [_started(), _progress(checkpoint="C5-TESTS_GREEN")])
    st = execute.derive()["tasks"]["T-03"]
    assert st["position"] == "C5-TESTS_GREEN"


def test_heartbeat_progress_does_not_advance(store):
    # PROGRESS without a new checkpoint is liveness, not progress (gsd_state health rule)
    _write_contract(store, "T-04")
    _write_events(store, "T-04", [_started(), _progress()])
    st = execute.derive()["tasks"]["T-04"]
    assert st["position"] == "C3-IMPLEMENTATION_STARTED"


def test_highest_recorded_checkpoint_wins(store):
    _write_contract(store, "T-05")
    _write_events(store, "T-05", [_started(),
                                 _progress(checkpoint="C6-REVIEW_READY", seq=3)])
    st = execute.derive()["tasks"]["T-05"]
    assert st["position"] == "C6-REVIEW_READY"


def test_completed_is_c8_terminal(store):
    _write_contract(store, "T-06")
    _write_events(store, "T-06", [_started(),
                                 {"state": "COMPLETED", "ts": "2026-01-01T00:00:20+00:00",
                                  "seq": 2}])
    st = execute.derive()["tasks"]["T-06"]
    assert st["position"] == "C8-HANDOFF_READY"
    assert st["status"] == "complete"
    assert st["terminal"] is True
    assert "NEXT_ACTION_SET" in st["structural_states"]


def test_failed_keeps_last_achieved_position_and_is_terminal(store):
    _write_contract(store, "T-07")
    _write_events(store, "T-07", [_started(),
                                 {"state": "FAILED", "ts": "2026-01-01T00:00:20+00:00",
                                  "seq": 2}])
    st = execute.derive()["tasks"]["T-07"]
    assert st["status"] == "failed"
    assert st["terminal"] is True
    assert st["position"] == "C3-IMPLEMENTATION_STARTED"   # last achieved, never invented


def test_cancelled_and_lost_are_terminal(store):
    _write_contract(store, "T-08", {"objective": "x"})
    _write_contract(store, "T-09", {"objective": "x"})
    _write_events(store, "T-08", [{"state": "CANCELLED", "ts": "2026-01-01T00:00:00+00:00",
                                   "seq": 1}])
    _write_events(store, "T-09", [{"state": "LOST", "ts": "2026-01-01T00:00:00+00:00",
                                   "seq": 1}])
    assert execute.derive()["tasks"]["T-08"]["terminal"] is True
    assert execute.derive()["tasks"]["T-08"]["status"] == "cancelled"
    assert execute.derive()["tasks"]["T-09"]["terminal"] is True
    assert execute.derive()["tasks"]["T-09"]["status"] == "lost"


def test_blocked_sets_structural_and_status(store):
    _write_contract(store, "T-10")
    _write_events(store, "T-10",
                  [_started(),
                   {"state": "BLOCKED", "detail": {"note": "missing credential"},
                    "ts": "2026-01-01T00:00:05+00:00", "seq": 2}])
    st = execute.derive()["tasks"]["T-10"]
    assert st["status"] == "blocked"
    assert "BLOCKED" in st["structural_states"]


def test_structural_states_ride_event_detail(store):
    _write_contract(store, "T-11")
    _write_events(store, "T-11", [
        _ack(),
        {"state": "PROGRESS", "checkpoint": "C1-CONTEXT_READ",
         "detail": {"evidence": ["REQ-1"], "step": "started", "decision": "use adapter"},
         "ts": "2026-01-01T00:00:02+00:00", "seq": 2},
    ])
    st = execute.derive()["tasks"]["T-11"]
    for s in ("STEP_STARTED", "EVIDENCE_FOUND", "DECISION_MADE"):
        assert s in st["structural_states"]


def test_facts_and_decisions_are_never_positions(store):
    # evidence/facts live in structural detail; they must not move the CHECKPOINT
    _write_contract(store, "T-12")
    _write_events(store, "T-12", [_ack(),
                                  {"state": "PROGRESS",
                                   "detail": {"evidence_verified": ["R1"], "evidence": ["R1"]},
                                   "ts": "2026-01-01T00:00:03+00:00", "seq": 2}])
    st = execute.derive()["tasks"]["T-12"]
    assert st["position"] == "C3-IMPLEMENTATION_STARTED"
    assert "EVIDENCE_FOUND" in st["structural_states"]
    assert "EVIDENCE_VERIFIED" in st["structural_states"]


def test_derive_is_deterministic(store):  # I10
    _write_contract(store, "T-13")
    _write_events(store, "T-13", [_started(), _progress(checkpoint="C4-IMPLEMENTATION_COMPLETE")])
    now = "2026-01-01T00:00:00+00:00"
    assert execute.derive(now) == execute.derive(now)


# --- liveness folds the control log read-only (one-log-one-derivation) ------

def test_liveness_reads_control_log_not_events(store):
    _write_contract(store, "T-14")
    _write_events(store, "T-14", [_started()])
    d = store / "control"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "tasks.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "TASK_BOUND", "task_id": "T-14",
                             "owner_session_id": "ses_1", "state": "RUNNING"}) + "\n")
    st = execute.derive()["tasks"]["T-14"]
    assert st["last_liveness_event"]["owner_session_id"] == "ses_1"


def test_liveness_absent_is_unknown_not_invented(store):
    # hermetic EXEC_ROOT: no control log -> "unknown", never fabricated liveness
    _write_contract(store, "T-15")
    _write_events(store, "T-15", [_started()])
    assert execute.derive()["tasks"]["T-15"]["last_liveness_event"] is None


# --- fail-closed inputs -----------------------------------------------------

def test_missing_events_read_as_empty_not_error(store):
    _write_contract(store, "T-16")
    assert execute.derive()["tasks"]["T-16"]["checkpoint_history"] == []


def test_torn_events_block(store):
    _write_contract(store, "T-17")
    p = store / "tasks" / "T-17.events.jsonl"
    p.write_text('{"state": "STARTED"}\nNOT JSON\n', encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        execute.derive()
    assert "EXEC_CORRUPT_LOG" in str(e.value)


def test_torn_control_log_blocks(store):
    d = store / "control"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tasks.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        execute.derive()
    assert "EXEC_CORRUPT_LOG" in str(e.value)


def test_bad_contract_blocks(store):
    p = store / "tasks" / "T-18.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{oops\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        execute.derive()
    assert "EXEC_BLOCKED" in str(e.value)


def test_unreadable_events_block(store):
    # events path exists as a directory -> open() raises OSError -> never a pass
    _write_contract(store, "T-19")
    (store / "tasks" / "T-19.events.jsonl").mkdir(parents=True, exist_ok=True)
    with pytest.raises(SystemExit) as e:
        execute.derive()
    assert "EXEC_UNREADABLE" in str(e.value)


# --- I8: status/position/derived_state/next_action are derived-only --------

def _derived():
    return {"position": "C3-IMPLEMENTATION_STARTED", "status": "in_progress",
            "terminal": False, "next_action": "resume"}


def test_render_rejects_authored_status(store):
    with pytest.raises(SystemExit) as e:
        execute._render_status({"task_id": "T-20", "status": "complete"}, _derived())
    assert "I8_VIOLATION" in str(e.value)
    assert "status" in str(e.value)


def test_render_rejects_authored_position(store):
    with pytest.raises(SystemExit) as e:
        execute._render_status({"task_id": "T-20", "position": "C8-HANDOFF_READY"}, _derived())
    assert "I8_VIOLATION" in str(e.value)
    assert "position" in str(e.value)


def test_render_rejects_authored_next_action(store):
    with pytest.raises(SystemExit) as e:
        execute._render_status({"task_id": "T-20", "next_action": "do x"}, _derived())
    assert "I8_VIOLATION" in str(e.value)
    assert "next_action" in str(e.value)


def test_render_rejects_authored_derived_state(store):
    with pytest.raises(SystemExit) as e:
        execute._render_status({"task_id": "T-20", "derived_state": "BLOCKED"}, _derived())
    assert "I8_VIOLATION" in str(e.value)


def test_render_passes_proposed_content_verbatim(store):
    out = execute._render_status(
        {"task_id": "T-20", "summary": "done the thing",
         "files_changed": ["a.py", "b.py"]}, _derived())
    assert "summary: done the thing" in out
    assert "files_changed: [\"a.py\", \"b.py\"]" in out
    assert out.index("status: in_progress") < out.index("summary:")  # derived block first


def test_render_marks_derived_lines(store):
    out = execute._render_status({"task_id": "T-20", "summary": "s"}, _derived())
    assert "# derived (I8)" in out
    assert out.count("# derived (I8)") >= 3


def test_render_is_deterministic(store):
    a = execute._render_status({"task_id": "T-20", "summary": "s"}, _derived())
    b = execute._render_status({"task_id": "T-20", "summary": "s"}, _derived())
    assert a == b


def test_doc_rebuild_is_byte_identical(store):  # DID-012 7.7
    payload = execute._parse_payload('{"task_id": "T-20", "summary": "done"}')
    body = execute._render_status(payload, _derived())
    now = "2026-01-01T00:00:00+00:00"
    assert execute._render_doc("T-20", body, now) == execute._render_doc("T-20", body, now)


def test_parse_payload_json(store):
    assert execute._parse_payload('{"task_id": "T-20", "summary": "hi"}') == \
        {"task_id": "T-20", "summary": "hi"}


def test_parse_payload_yaml_block(store):
    raw = ("task_id: T-20\n"
           "summary: wrote the thing\n"
           "agents: [implementer, reviewer]\n")
    parsed = execute._parse_payload(raw)
    assert parsed["task_id"] == "T-20"
    assert parsed["summary"] == "wrote the thing"
    assert parsed["agents"] == "[implementer, reviewer]"


def test_parse_payload_empty(store):
    assert execute._parse_payload("") == {}
    assert execute._parse_payload(None) == {}


# --- next action is derived from position, never written --------------------

def test_next_action_terminal(store):
    d = {"position": "C8-HANDOFF_READY", "status": "complete", "terminal": True}
    assert execute._derived_next_action("T-20", d) == "terminal -- no further execution"


def test_next_action_not_started(store):
    d = {"position": "NOT_STARTED", "status": "in_progress", "terminal": False}
    assert "accept the task" in execute._derived_next_action("T-20", d)


def test_next_action_resumes_toward_next_checkpoint(store):
    d = {"position": "C0-TASK_ACCEPTED", "status": "in_progress", "terminal": False}
    assert "C1-CONTEXT_READ" in execute._derived_next_action("T-20", d)


# --- CLI exit-code contract -------------------------------------------------

def _run(store, *args):
    env = {**os.environ, "EXEC_ROOT": str(store)}
    return subprocess.run([sys.executable, str(ADAPTER), *args],
                          capture_output=True, text=True, env=env)


def test_cli_derive_exits_zero(store):
    _write_contract(store, "T-21")
    p = _run(store, "derive")
    assert p.returncode == 0
    assert json.loads(p.stdout)["tasks"]["T-21"]["position"] == "NOT_STARTED"


def test_cli_render_summary_writes_file(store):
    _write_contract(store, "T-22")
    _write_events(store, "T-22", [_started()])
    p = _run(store, "render-summary", "--task", "T-22",
             "--json", '{"summary": "done"}')
    assert p.returncode == 0
    out = Path(p.stdout.strip())
    assert out == store / "phases" / "00-unphased" / "T-22-SUMMARY.md"
    assert "status: in_progress" in out.read_text(encoding="utf-8")


def test_cli_render_summary_unknown_task(store):
    p = _run(store, "render-summary", "--task", "T-GHOST", "--json", "{}")
    assert p.returncode == 1
    assert "NOT_FOUND" in p.stderr


def test_cli_render_summary_i8_rejects_without_writing(store):
    _write_contract(store, "T-23")
    p = _run(store, "render-summary", "--task", "T-23",
             "--json", '{"status": "complete"}')
    assert p.returncode == 1
    assert "I8_VIOLATION" in p.stderr
    assert not (store / "phases" / "00-unphased" / "T-23-SUMMARY.md").exists()


def test_cli_render_summary_overwrite_is_deterministic(store):
    _write_contract(store, "T-24")
    _write_events(store, "T-24", [_started()])
    now = "2026-01-01T00:00:00+00:00"
    a = _run(store, "render-summary", "--task", "T-24", "--json", '{"summary": "s"}', "--now", now)
    b = _run(store, "render-summary", "--task", "T-24", "--json", '{"summary": "s"}', "--now", now)
    assert a.returncode == 0 and b.returncode == 0
    pa = Path(a.stdout.strip())
    pb = Path(b.stdout.strip())
    assert pa == pb
    assert pa.read_bytes() == pb.read_bytes()


def test_cli_resume_context_unknown_task(store):
    p = _run(store, "resume-context", "--task", "T-GHOST")
    assert p.returncode == 1
    assert "NOT_FOUND" in p.stderr


def test_cli_resume_context_prints_derived_block(store):
    _write_contract(store, "T-25")
    _write_events(store, "T-25", [_started()])
    p = _run(store, "resume-context", "--task", "T-25")
    assert p.returncode == 0
    assert "RESUME T-25" in p.stdout
    assert "Position: C3-IMPLEMENTATION_STARTED" in p.stdout
    assert "# derived (I8)" in p.stdout


def test_cli_selftest_exits_zero():
    env = {k: v for k, v in os.environ.items() if k != "EXEC_ROOT"}
    p = subprocess.run([sys.executable, str(ADAPTER), "selftest"],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stdout + p.stderr


# --- the hermetic suite itself ---------------------------------------------

def test_selftest_passes(store, monkeypatch):
    monkeypatch.delenv("EXEC_ROOT", raising=False)
    results = execute.selftest()
    assert all(v == "pass" for v in results.values()), results