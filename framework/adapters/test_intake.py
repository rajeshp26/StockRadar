"""Intake adapter tests -- DID-012 Pillar 1.

Each test asserts an invariant the adapter must refuse to violate; the point is that the
adapter goes RED, not that the happy path runs. Exit-code contract (0 ok / 1 violation /
2 BLOCKED / 4 NOT_APPLICABLE) is asserted where a gate consumes it.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ADAPTER = HERE / "intake.py"


def _load():
    spec = importlib.util.spec_from_file_location("intake_adapter", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["intake_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


intake = _load()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_ROOT", str(tmp_path))
    return tmp_path


def _task(store, task_id, contract):
    d = store / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}.json").write_text(json.dumps(contract), encoding="utf-8")


def _task_events(store, task_id, states):
    d = store / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{task_id}.events.jsonl").open("w", encoding="utf-8") as fh:
        for s in states:
            fh.write(json.dumps({"state": s}) + "\n")


# --- identity is adapter-authored (I8) ------------------------------------

def test_capture_allocates_sequential_ids(store):
    a = intake.capture({"session_id": "ses_1", "original_text": "first"})
    b = intake.capture({"session_id": "ses_1", "original_text": "second"})
    assert (a["ask_id"], b["ask_id"]) == ("ASK-001", "ASK-002")
    assert a["status"] == "CAPTURED" and b["status"] == "CAPTURED"


def test_capture_rejects_authored_status(store):
    with pytest.raises(SystemExit) as e:
        intake.capture({"session_id": "s", "original_text": "x", "status": "COMPLETED"})
    assert "ASK_INVALID_FIELD" in str(e.value)


def test_capture_rejects_authored_ask_id(store):
    with pytest.raises(SystemExit) as e:
        intake.capture({"session_id": "s", "original_text": "x", "ask_id": "ASK-042"})
    assert "ASK_INVALID_FIELD" in str(e.value)


def test_capture_rejects_model_emitter(store):
    with pytest.raises(SystemExit) as e:
        intake.capture({"session_id": "s", "original_text": "x", "emitter": "model"})
    assert "ASK_INVALID_EMITTER" in str(e.value)


@pytest.mark.parametrize("missing", ["session_id", "original_text"])
def test_capture_requires_provenance_and_text(store, missing):
    payload = {"session_id": "ses_1", "original_text": "the ask"}
    payload.pop(missing)
    with pytest.raises(SystemExit) as e:
        intake.capture(payload)
    assert missing in str(e.value)


def test_capture_rejects_unknown_parent(store):
    with pytest.raises(SystemExit) as e:
        intake.capture({"session_id": "s", "original_text": "x",
                        "parent_ask_id": "ASK-999"})
    assert "parent_ask_id" in str(e.value)


# --- lifecycle (section 3.3) ----------------------------------------------

@pytest.mark.parametrize("frm,to,legal", [
    ("CAPTURED", "COMPLETED", "CONFIRMED, DEFERRED, REJECTED"),
    ("CONFIRMED", "COMPLETED", "DEFERRED, PLANNED, REJECTED"),
    ("PLANNED", "COMPLETED", "DEFERRED, EXECUTING, REJECTED"),
    ("EXECUTING", "CONFIRMED", "COMPLETED, DEFERRED"),
])
def test_invalid_transition_names_legal_next_states(store, frm, to, legal):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    path = {"CAPTURED": [], "CONFIRMED": ["CONFIRMED"], "PLANNED": ["CONFIRMED", "PLANNED"],
            "EXECUTING": ["CONFIRMED", "PLANNED", "EXECUTING"]}[frm]
    for step in path:
        intake.transition(a["ask_id"], {"status": step})
    with pytest.raises(SystemExit) as e:
        intake.transition(a["ask_id"], {"status": to})
    assert "INVALID_TRANSITION" in str(e.value) and legal in str(e.value)


def test_full_legal_chain_to_completed(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    for st in ("CONFIRMED", "PLANNED", "EXECUTING", "COMPLETED"):
        rec = intake.transition(a["ask_id"], {"status": st})
    assert rec["status"] == "COMPLETED"


@pytest.mark.parametrize("final", ["COMPLETED", "REJECTED"])
def test_final_states_admit_no_further_transition(store, final):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    for st in ("CONFIRMED",):
        intake.transition(a["ask_id"], {"status": st})
    if final == "COMPLETED":
        for st in ("PLANNED", "EXECUTING", "COMPLETED"):
            intake.transition(a["ask_id"], {"status": st})
    else:
        intake.transition(a["ask_id"], {"status": "REJECTED"})
    with pytest.raises(SystemExit) as e:
        intake.transition(a["ask_id"], {"status": "DEFERRED"})
    assert "ASK_TERMINAL_STATE" in str(e.value)


def test_deferred_is_terminal_for_i2_but_reopenable(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    intake.transition(a["ask_id"], {"status": "DEFERRED"})
    assert intake.show(a["ask_id"])["status"] == "DEFERRED"
    reopened = intake.transition(a["ask_id"], {"status": "REOPENED"})
    assert reopened["status"] == "REOPENED"
    assert intake.transition(a["ask_id"], {"status": "PLANNED"})["status"] == "PLANNED"


def test_unknown_ask_is_not_found(store):
    with pytest.raises(SystemExit) as e:
        intake.transition("ASK-404", {"status": "CONFIRMED"})
    assert "NOT_FOUND" in str(e.value)


def test_history_is_append_only_provenance(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    for st in ("CONFIRMED", "PLANNED", "EXECUTING", "COMPLETED"):
        intake.transition(a["ask_id"], {"status": st})
    hist = intake.show(a["ask_id"])["history"]
    assert [h["to"] for h in hist] == ["CAPTURED", "CONFIRMED", "PLANNED",
                                       "EXECUTING", "COMPLETED"]


# --- derivation determinism (I10) -----------------------------------------

def test_derivation_is_deterministic(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    intake.transition(a["ask_id"], {"status": "CONFIRMED"})
    assert intake.asks() == intake.asks()


def test_torn_log_blocks_instead_of_reading_empty(store):
    intake.capture({"session_id": "s", "original_text": "x"})
    with (store / "intake" / "asks.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
    with pytest.raises(SystemExit) as e:
        intake.asks()
    assert "ASK_INTAKE_BLOCKED" in str(e.value)


def test_divergent_transition_log_blocks(store):
    intake.capture({"session_id": "s", "original_text": "x"})
    with (store / "intake" / "asks.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "ASK_TRANSITIONED", "ask_id": "ASK-001",
                             "from": "PLANNED", "to": "COMPLETED",
                             "ts": "2026-01-01T00:00:00Z"}) + "\n")
    with pytest.raises(SystemExit) as e:
        intake.asks()
    assert "not self-consistent" in str(e.value)


# --- I1 at dispatch -------------------------------------------------------

def test_verify_task_passes_for_bound_executable_task(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    _task(store, "T-BOUND", {"agent": "x", "ask_id": a["ask_id"]})
    out = intake.verify_task("T-BOUND")
    assert out["ask_id"] == a["ask_id"] and out["state"] == "SPAWNED"


def test_verify_task_blocks_unbound_executable_task(store):
    _task(store, "T-FREE", {"agent": "x"})
    with pytest.raises(SystemExit) as e:
        intake.verify_task("T-FREE")
    assert e.value.code == 1


def test_verify_task_blocks_ask_id_absent_from_intake(store):
    _task(store, "T-PHANTOM", {"agent": "x", "ask_id": "ASK-777"})
    with pytest.raises(SystemExit) as e:
        intake.verify_task("T-PHANTOM")
    assert e.value.code == 1


def test_verify_task_exempts_terminal_task(store):
    _task(store, "T-DONE", {"agent": "x"})
    _task_events(store, "T-DONE", ["STARTED", "COMPLETED"])
    with pytest.raises(SystemExit) as e:
        intake.verify_task("T-DONE")
    assert e.value.code == 4


def test_verify_task_blocks_when_task_unreadable(store):
    with pytest.raises(SystemExit) as e:
        intake.verify_task("T-MISSING")
    assert e.value.code == 2


def test_coverage_blocks_on_any_unbound_executable_task(store):
    a = intake.capture({"session_id": "s", "original_text": "x"})
    _task(store, "T-OK", {"agent": "x", "ask_id": a["ask_id"]})
    _task(store, "T-BAD", {"agent": "x"})
    with pytest.raises(SystemExit) as e:
        intake.coverage()
    assert e.value.code == 1


def test_coverage_excludes_terminal_tasks(store):
    intake.capture({"session_id": "s", "original_text": "x"})
    _task(store, "T-DONE", {"agent": "x"})
    _task_events(store, "T-DONE", ["COMPLETED"])
    assert intake.coverage()["tasks_unbound"] == []


# --- I2 is enforced at completion, and reported truthfully everywhere -----
# Before this change coverage() hard-coded I2 to True and exited 0 with an open ASK, so
# "every ASK terminates" was a documented invariant with no consumer able to fail on it.

def test_coverage_reports_open_ask_but_default_exit_is_unchanged(store):
    intake.capture({"session_id": "s", "original_text": "still open"})
    rep = intake.coverage()
    assert rep["invariants"]["I2_every_ask_terminates"] is False
    assert [u["ask_id"] for u in rep["asks_unterminated"]] == ["ASK-001"]
    assert rep["completion_mode"] is False


def test_coverage_completion_fails_on_open_ask(store):
    intake.capture({"session_id": "s", "original_text": "still open"})
    with pytest.raises(SystemExit) as e:
        intake.coverage(completion=True)
    assert e.value.code == 1


def test_coverage_completion_passes_when_every_ask_terminated(store):
    a = intake.capture({"session_id": "s", "original_text": "done"})["ask_id"]
    b = intake.capture({"session_id": "s", "original_text": "later"})["ask_id"]
    for st in ("CONFIRMED", "PLANNED", "EXECUTING", "COMPLETED"):
        intake.transition(a, {"status": st})
    intake.transition(b, {"status": "DEFERRED"})
    rep = intake.coverage(completion=True)
    assert rep["invariants"]["I2_every_ask_terminates"] is True
    assert rep["asks_unterminated"] == []


def test_coverage_completion_with_no_asks_passes(store):
    assert intake.coverage(completion=True)["asks_total"] == 0


def test_coverage_completion_cli_exit_codes(store):
    import os
    env = dict(os.environ, INTAKE_ROOT=str(store))
    intake.capture({"session_id": "s", "original_text": "open"})
    run = lambda *a: subprocess.run([sys.executable, str(ADAPTER), *a],
                                    capture_output=True, text=True, env=env)
    assert run("coverage").returncode == 0
    p = run("coverage", "--completion")
    assert p.returncode == 1 and "I2 VIOLATED" in p.stderr and "ASK-001" in p.stderr


# --- the gate itself ------------------------------------------------------

def test_selftest_passes(store, monkeypatch):
    monkeypatch.delenv("INTAKE_ROOT", raising=False)
    results = intake.selftest()
    assert all(v == "pass" for v in results.values()), results


def test_selftest_cli_exits_zero():
    p = subprocess.run([sys.executable, str(ADAPTER), "selftest"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
