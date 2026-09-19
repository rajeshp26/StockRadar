"""Control adapter tests -- DID-012 Pillar 3 (lease/reap, deterministic reaper).

Each test asserts an invariant the adapter must refuse to violate; the point is that the
adapter goes RED, not that the happy path runs. Exit-code contract (0 ok / 1 violation /
2 BLOCKED / 4 NOT_APPLICABLE) is asserted where a gate consumes it.

control.py reports violations on stderr and raises SystemExit(1), so unlike intake tests
the marker is asserted via capsys, not str(e.value). Corrupt-log and invalid-JSON paths
carry the marker in the SystemExit payload itself.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ADAPTER = HERE / "control.py"

NOW_FAR = "2999-01-01T00:00:00+00:00"   # lease with lease_s=-1 is always expired by NOW_FAR


def _load():
    spec = importlib.util.spec_from_file_location("control_adapter", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["control_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


control = _load()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _telemetry(store, records):
    d = store / "telemetry"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return d


def _raw_task(store, task_id, owner=None, lease_until="2000-01-01T00:00:00+00:00"):
    d = store / "control"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "tasks.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "event": "TASK_BOUND", "task_id": task_id,
            "owner_session_id": owner, "state": "RUNNING",
            "created_at": NOW_FAR, "last_heartbeat": NOW_FAR,
            "lease_until": lease_until}) + "\n")


def _retro_entry(task_id="T-RET", **over):
    e = {"task_id": task_id, "injected_at": "implementation",
         "caught_at": "review", "defect_class": "logic_error",
         "primary_gap": "gate_check", "fix_target": "gate_check",
         "fix_landed": True}
    e.update(over)
    return e


def _pending(store, entries):
    d = store / "retro"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "pending.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    return d


# --- identities are unique and adapter-owned (I4) --------------------------

def test_register_starts_running(store):
    s = control.session_register("ses_1")
    assert s["state"] == "RUNNING"
    assert s["started_at"] and s["lease_until"]
    assert s["termination_observed"] is False


def test_duplicate_register_blocked(store, capsys):
    control.session_register("ses_1")
    with pytest.raises(SystemExit) as e:
        control.session_register("ses_1")
    assert e.value.code == 1
    assert "I4 VIOLATED" in capsys.readouterr().err


def test_register_requires_id(store, capsys):
    with pytest.raises(SystemExit) as e:
        control.session_register("")
    assert e.value.code == 1
    assert "CONTROL_INVALID_ID" in capsys.readouterr().err


# --- session lifecycle (I5) -------------------------------------------------

def test_terminate_is_terminal(store):
    control.session_register("ses_1")
    t = control.session_terminate("ses_1", "DEAD")
    assert t["state"] == "DEAD" and t["termination_observed"] is True
    assert t["lease_until"] is None


def test_heartbeat_after_terminal_blocked(store, capsys):
    control.session_register("ses_1")
    control.session_terminate("ses_1", "DEAD")
    with pytest.raises(SystemExit) as e:
        control.session_heartbeat("ses_1")
    assert e.value.code == 1
    assert "INVALID_TRANSITION" in capsys.readouterr().err


def test_second_terminate_blocked(store, capsys):
    control.session_register("ses_1")
    control.session_terminate("ses_1", "CLOSED")
    with pytest.raises(SystemExit) as e:
        control.session_terminate("ses_1", "ABORTED")
    assert e.value.code == 1
    assert "terminal is final (I5)" in capsys.readouterr().err


def test_terminate_invalid_state_blocked(store, capsys):
    control.session_register("ses_1")
    with pytest.raises(SystemExit) as e:
        control.session_terminate("ses_1", "EXPIRED")
    assert e.value.code == 1
    assert "INVALID_STATE" in capsys.readouterr().err


def test_unknown_session_heartbeat_blocked(store, capsys):
    with pytest.raises(SystemExit) as e:
        control.session_heartbeat("ses_ghost")
    assert e.value.code == 1
    assert "SESSION_UNKNOWN" in capsys.readouterr().err


# --- task ownership is bound, never inferred (I3, I7) -----------------------

def test_bind_ok(store):
    control.session_register("ses_1")
    t = control.task_bind("bg_1", "ses_1")
    assert t["owner_session_id"] == "ses_1" and t["state"] == "RUNNING"


def test_bind_requires_registered_session(store, capsys):
    with pytest.raises(SystemExit) as e:
        control.task_bind("bg_1", "ses_ghost")
    assert e.value.code == 1
    assert "I7 VIOLATED" in capsys.readouterr().err


def test_rebind_blocked(store, capsys):
    control.session_register("ses_1")
    control.session_register("ses_2")
    control.task_bind("bg_1", "ses_1")
    with pytest.raises(SystemExit) as e:
        control.task_bind("bg_1", "ses_2")
    assert e.value.code == 1
    assert "I3 VIOLATED" in capsys.readouterr().err


# --- task lifecycle (I6) ----------------------------------------------------

def test_collect_terminal(store):
    control.session_register("ses_1")
    control.task_bind("bg_1", "ses_1")
    t = control.task_collect("bg_1", "verifier")
    assert t["state"] == "COMPLETED" and t["collected_by"] == "verifier"


def test_heartbeat_after_collect_blocked(store, capsys):
    control.session_register("ses_1")
    control.task_bind("bg_1", "ses_1")
    control.task_collect("bg_1")
    with pytest.raises(SystemExit) as e:
        control.task_heartbeat("bg_1")
    assert e.value.code == 1
    assert "terminal is final (I6)" in capsys.readouterr().err


def test_cancel_and_fail_are_terminal(store):
    control.session_register("ses_1")
    control.task_bind("bg_1", "ses_1")
    control.task_bind("bg_2", "ses_1")
    assert control.task_cancel("bg_1")["state"] == "CANCELLED"
    assert control.task_fail("bg_2", "boom")["state"] == "FAILED"
    for st in ("CANCELLED", "FAILED"):
        assert st in control.TASK_TERMINAL


def test_unknown_task_blocks(store, capsys):
    with pytest.raises(SystemExit) as e:
        control.task_heartbeat("bg_ghost")
    assert e.value.code == 1
    assert "TASK_UNKNOWN" in capsys.readouterr().err


# --- derivation determinism (I10) ------------------------------------------

def test_derivation_is_deterministic(store):
    control.session_register("ses_1", lease_s=10)
    control.task_bind("bg_1", "ses_1", lease_s=10)
    assert control.derive(NOW_FAR) == control.derive(NOW_FAR)


# --- the reaper never converts uncertainty into success (I7) ---------------

def test_stale_never_confirmed(store):
    control.session_register("ses_1", lease_s=10)
    control.task_bind("bg_stale", "ses_1", lease_s=-1)   # lease already expired
    out = control.reap(NOW_FAR)
    rec = [r for r in out["reaped"] if r["task_id"] == "bg_stale"][0]
    assert rec["result"] == control.REAP_UNCONFIRMED
    assert rec["action"] == "hold"
    st = control.derive(NOW_FAR)["tasks"]["bg_stale"]["derived_state"]
    assert st != "REAPED"                                # UNCONFIRMED never reaps


def test_unknown_never_confirmed(store):
    _raw_task(store, "bg_ghost", owner=None)             # no binding (I7)
    out = control.reap(NOW_FAR)
    rec = [r for r in out["reaped"] if r["task_id"] == "bg_ghost"][0]
    assert rec["result"] == control.REAP_UNCONFIRMED
    assert rec["action"] == "hold"
    st = control.derive(NOW_FAR)["tasks"]["bg_ghost"]["derived_state"]
    assert st == "UNKNOWN" and st != "REAPED"


def test_lost_writes_no_reap_record(store):
    # owner dead but lease still live at NOW_PAST -> LOST, never reaped, no record
    control.session_register("ses_dead", lease_s=600)
    control.task_bind("bg_lost", "ses_dead", lease_s=600)
    control.session_terminate("ses_dead", "DEAD")
    now_past = "2000-01-01T00:00:00+00:00"
    out = control.reap(now_past)
    assert out["reaped"] == []
    assert control._reaps() == []
    st = control.derive(now_past)["tasks"]["bg_lost"]["derived_state"]
    assert st == "LOST"


# --- ORPHANED is the only state the reaper confirms ------------------------

def test_orphan_confirmed_and_reaped(store):
    control.session_register("ses_dead", lease_s=10)
    control.task_bind("bg_orph", "ses_dead", lease_s=-1)
    control.session_terminate("ses_dead", "DEAD")
    out = control.reap(NOW_FAR)
    rec = [r for r in out["reaped"] if r["task_id"] == "bg_orph"][0]
    assert rec["result"] == control.REAP_CONFIRMED
    assert rec["action"] == "cancel"
    assert rec["reap_id"].startswith("REAP-")
    st = control.derive(NOW_FAR)["tasks"]["bg_orph"]
    assert st["derived_state"] == "REAPED"
    assert st["reaped_by"] == rec["reap_id"]


def test_reap_is_idempotent(store):
    control.session_register("ses_1", lease_s=10)
    control.task_bind("bg_stale", "ses_1", lease_s=-1)
    control.reap(NOW_FAR)
    before = len(control._reaps())
    control.reap(NOW_FAR)
    assert len(control._reaps()) == before               # no duplicate records


# --- append-only provenance (I11) ------------------------------------------

def test_each_command_appends_exactly_one_event(store):
    control.session_register("ses_1")
    path = store / "control" / "sessions.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    control.session_heartbeat("ses_1")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_reload_is_pure(store):
    control.session_register("ses_1")
    first = [json.loads(l) for l in (store / "control" / "sessions.jsonl")
             .read_text(encoding="utf-8").splitlines()]
    second = [json.loads(l) for l in (store / "control" / "sessions.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    assert first == second


def test_torn_log_blocks_instead_of_reading_healthy(store):
    control.session_register("ses_1")
    with (store / "control" / "sessions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    with pytest.raises(SystemExit) as e:
        control.derive()
    assert "CONTROL_CORRUPT_LOG" in str(e.value)


# --- item 4: telemetry rollup -----------------------------------------------

def test_rollup_archives_old_keeps_fresh(store):
    old = {"session_id": "ses_old", "kind": "final", "ts": "2000-01-01T00:00:00+00:00"}
    fresh = {"session_id": "ses_new", "kind": "final", "ts": NOW_FAR}
    _telemetry(store, [old, fresh])
    out = control.rollup(max_age_days=30, archive_dir=str(store / "archive"))
    assert out["records_archived"] == 1 and out["records_kept"] == 1
    live = [json.loads(l) for l in (store / "telemetry" / "records.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert [r["session_id"] for r in live] == ["ses_new"]      # old out of live set
    assert list((store / "archive").glob("records-*.jsonl"))   # durable archive


def test_rollup_position_final_folds_closed(store):
    _telemetry(store, [{"session_id": "ses_f", "kind": "final", "ts": NOW_FAR}])
    first = control.rollup(max_age_days=30, archive_dir=str(store / "archive"))
    assert "ses_f" in first["positions_folded"]
    assert control._sessions()["ses_f"]["state"] == "CLOSED"
    assert control._sessions()["ses_f"]["termination_observed"] is True
    second = control.rollup(max_age_days=30, archive_dir=str(store / "archive"))
    assert second["positions_folded"] == []                    # idempotent


def test_rollup_position_started_folds_running(store):
    _telemetry(store, [{"session_id": "ses_r", "kind": "started", "ts": NOW_FAR}])
    control.rollup(max_age_days=30, archive_dir=str(store / "archive"))
    assert control._sessions()["ses_r"]["state"] == "RUNNING"


# --- item 6: one-way retro-entry sync --------------------------------------

def test_retro_sync_writes_ledger(store):
    d = _pending(store, [_retro_entry()])
    out = control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    assert out["synced"] == ["T-RET"]
    assert (d / "ledger.jsonl").exists()


def test_retro_sync_skips_already_synced(store):
    d = _pending(store, [_retro_entry()])
    control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    out = control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    assert out["synced"] == [] and [s["task_id"] for s in out["skipped"]] == ["T-RET"]
    assert len((d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_retro_sync_blocks_unknown_fix_target(store, capsys):
    d = _pending(store, [_retro_entry(fix_target="made_up_target")])
    with pytest.raises(SystemExit) as e:
        control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    assert e.value.code == 1
    assert "UNKNOWN_FIX_TARGET" in capsys.readouterr().err
    assert not (d / "ledger.jsonl").exists()                  # nothing partial written


def test_retro_sync_blocks_incomplete_entry(store, capsys):
    entry = _retro_entry()
    del entry["fix_landed"]
    d = _pending(store, [entry])
    with pytest.raises(SystemExit) as e:
        control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    assert e.value.code == 1
    assert "incomplete retro entry" in capsys.readouterr().err


def test_retro_sync_torn_pending_blocked(store):
    d = store / "retro"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pending.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        control.retro_sync(str(d / "pending.jsonl"), str(d / "ledger.jsonl"))
    assert "CONTROL_INVALID_JSON" in str(e.value)


def test_retro_sync_no_pending(store):
    out = control.retro_sync()
    assert out["status"] == "no pending entries"


# --- the gate itself -------------------------------------------------------

def test_selftest_passes(store, monkeypatch):
    monkeypatch.delenv("CONTROL_ROOT", raising=False)
    results = control.selftest()
    assert all(v == "pass" for v in results.values()), results


def test_selftest_cli_exits_zero():
    p = subprocess.run([sys.executable, str(ADAPTER), "selftest"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr