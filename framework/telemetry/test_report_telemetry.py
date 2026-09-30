"""Fixture-driven tests for framework/telemetry/report.py anomaly blocks (T-FX2).

Each of the 8 detection blocks (gate_silence, twin_sessions, spawn_burst,
early_death, poll_escalation, cache_read_ratio, supervision_join, torn_lines)
gets a positive test on real Sep-7-shaped data and a negative test on clean
data. Fixtures are inlined Sep-7 shapes (the reference export lives under a
temp path and must never be referenced from committed tests).

The blocks are pure functions returning structured anomaly dicts, so tests
assert on structure, not printed text. main() is exercised end-to-end with
monkeypatched state_root so the supervision join is deterministic.
"""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# report.state_root() imports gsd_state at call time, so the repo root must be
# importable however pytest was invoked.
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import report


def _rec(session_id, kind="final", started_at="2026-09-07T16:49:16.383Z",
         duration_s=600, tools=None, gates=None, taxo=None, bg_tasks=None,
         bg_poll_total=0, task_id="", tokens=None):
    return {
        "record_version": 3,
        "kind": kind,
        "session_id": session_id,
        "task_id": task_id,
        "started_at": started_at,
        "duration_s": duration_s,
        "agents": {},
        "tokens": tokens or {"input": 1000, "output": 500, "reasoning": 200,
                             "cache_read": 0, "cache_write": 0},
        "models_seen": {},
        "tools": tools or {},
        "gates": gates or {},
        "taxonomy_events": taxo or [],
        "bg_tasks": bg_tasks or {},
        "bg_poll_total": bg_poll_total,
    }


def _sep7_sessions():
    """13 sessions shaped like the real Sep-7 export (inline, no temp path)."""
    t1, t2, t3, t4, t5 = (
        "2026-09-07T16:49:16.383Z", "2026-09-07T16:55:23.252Z",
        "2026-09-07T17:05:23.531Z", "2026-09-07T22:14:53.218Z",
        "2026-09-07T23:53:08.396Z")
    return [
        _rec("ses_f81b19405ffe8InzyECT", "heartbeat", t5, 1586,
             tools={"bash": {"count": 11, "ms": 1000}},
             tokens={"input": 1000000, "output": 500000, "reasoning": 200000,
                     "cache_read": 23305664, "cache_write": 591686}),
        _rec("ses_f820f26f1ffeKPDQ4Nnm", "heartbeat", t4, 5560),
        _rec("ses_f832a6ef5ffePiKt3yOz", "heartbeat", t3, 3044,
             tools={"read": {"count": 5, "ms": 500}}),
        _rec("ses_f832f9285ffeGm1vyNix", "heartbeat", t2, 3667,
             tools={"bash": {"count": 12, "ms": 2000}}, bg_poll_total=10),
        _rec("ses_f832fc62bffeeHtEfCHH", "started", t2, 293,
             tools={"read": {"count": 1, "ms": 100}}),
        _rec("ses_f832fec4effeaPAZ2pjR", "started", t2, 283,
             tools={"read": {"count": 1, "ms": 100}}),
        _rec("ses_f833013eaffePt27cc0r", "started", t2, 273,
             tools={"read": {"count": 1, "ms": 100}}),
        _rec("ses_f83303c7cffeD9qiD4Sc", "started", t2, 263),
        _rec("ses_f83335ae4ffeeUpgxHXt", "final", t2, 83),
        _rec("ses_f833666f6ffeXtAx4zwB", "heartbeat", t1, 19471,
             tools={"bash": {"count": 9, "ms": 1500}}, bg_poll_total=3),
        _rec("ses_f8336d18effeX7c5nG1h", "started", t1, 198,
             tools={"read": {"count": 1, "ms": 100}}),
        _rec("ses_f83370cd2ffeKcr32z9A", "final", t1, 185,
             tools={"read": {"count": 1, "ms": 100}}),
        _rec("ses_f833738d2ffetH1d38P0", "started", t1, 172),
    ]


def _twin_sessions():
    """Two sessions sharing four background-task ids (Sep-7 shape)."""
    shared = {bg: {"launched": 1, "polls": 0, "collects": 0, "cancelled": 0}
              for bg in ("bg_b6288483", "bg_af378573", "bg_62fa5735", "bg_13672324")}
    return [
        _rec("ses_f834be76effeTCAKhzHDm6ylRI", "final", "2026-09-07T16:49:16.383Z",
             600, bg_tasks=shared),
        _rec("ses_f835888e0ffedJI5trxFOVosuv", "final", "2026-09-07T16:49:16.383Z",
             600, bg_tasks=shared),
    ]


def _write_torn(tmp_path):
    p = tmp_path / "torn.jsonl"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(
            '{"record_version":3,"kind":"final","session_id":"s1",'
            '"started_at":"2026-09-07T16:49:16.383Z","duration_s":600}\n'
            'garbage line one\n'
            '{"record_version":3,"kind":"final","session_id":"s2",'
            '"started_at":"2026-09-07T16:55:23.252Z","duration_s":600}\n'
            '{oops\n'
            '{"record_version":3,"kind":"final","session_id":"s3",'
            '"started_at":"2026-09-07T17:05:23.531Z","duration_s":600}\n')
    return p


def _write_tasks(tmp_path):
    td = tmp_path / "tasks"
    td.mkdir()
    (td / "T-P0-3R.json").write_text(json.dumps({
        "task_id": "T-P0-3R",
        "agent": "implementer",
        "objective": "gate coverage",
        "expected_artifact": "report",
        "session_id": "ses_f86d50a99ffet6LzqG9cn18jmV",
    }), encoding="utf-8")
    (td / "T-P0-3R.events.jsonl").write_text(
        '{"state": "STARTED", "ts": "2026-09-07T15:36:37.520305+00:00"}\n'
        '{"state": "COMPLETED", "ts": "2026-09-07T16:28:44.233197+00:00"}\n',
        encoding="utf-8")
    return td


def test_gate_silence_fires_on_sep7():
    anoms = report._gate_silence(_sep7_sessions())
    assert any(a["block"] == "gate_silence" for a in anoms)
    days = [a for a in anoms if a.get("day")]
    assert days and days[0]["day"] == "2026-09-07"
    sids = {a["session_id"] for a in anoms if a.get("session_id")}
    assert "ses_f81b19405ffe8InzyECT" in sids


def test_gate_silence_clean():
    recs = [_rec("s1", tools={"bash": {"count": 1, "ms": 10}},
                 gates={"g4": {"result": "pass", "ms": 5}})]
    assert report._gate_silence(recs) == []
    assert report._gate_silence([_rec("s2")]) == []


def test_twin_sessions_fires():
    anoms = report._twin_sessions(_twin_sessions())
    assert len(anoms) == 4
    a = anoms[0]
    assert a["block"] == "twin_sessions"
    assert set(a["sessions"]) == {"ses_f834be76effeTCAKhzHDm6ylRI",
                                  "ses_f835888e0ffedJI5trxFOVosuv"}


def test_twin_sessions_clean():
    recs = [_rec("s1", bg_tasks={"bg_a": {"launched": 1, "collects": 1}}),
            _rec("s2", bg_tasks={"bg_b": {"launched": 1, "collects": 1}})]
    assert report._twin_sessions(recs) == []


def test_spawn_burst_fires_on_sep7():
    anoms = report._spawn_burst(_sep7_sessions())
    assert sorted(a["count"] for a in anoms) == [4, 6]


def test_spawn_burst_clean():
    recs = [_rec(f"s{i}", started_at=f"2026-09-07T10:0{i}:00.000Z") for i in range(3)]
    assert report._spawn_burst(recs) == []


def test_early_death_fires_on_sep7():
    anoms = report._early_death(_sep7_sessions())
    sids = {a["session_id"] for a in anoms}
    assert "ses_f832fc62bffeeHtEfCHH" in sids
    assert "ses_f833738d2ffetH1d38P0" in sids
    assert "ses_f83335ae4ffeeUpgxHXt" not in sids
    assert "ses_f83370cd2ffeKcr32z9A" not in sids


def test_early_death_clean():
    recs = [_rec("s1", "started", duration_s=600),
            _rec("s2", "final", duration_s=10),
            _rec("s3", "started", duration_s=None)]
    assert report._early_death(recs) == []


def test_poll_escalation_fires_on_sep7():
    anoms = report._poll_escalation(_sep7_sessions())
    assert len(anoms) == 2
    assert anoms[0]["session_id"] == "ses_f832f9285ffeGm1vyNix"
    assert anoms[0]["bg_poll_total"] == 10


def test_poll_escalation_clean():
    recs = [_rec("s1", bg_poll_total=0), _rec("s2", bg_poll_total=0)]
    assert report._poll_escalation(recs) == []


def test_cache_read_ratio_fires_on_sep7():
    d = {"tok": {"input": 1000000, "output": 500000, "reasoning": 200000,
                 "cache_read": 23305664, "cache_write": 591686}}
    anoms = report._cache_read_ratio(d)
    assert len(anoms) == 1
    a = anoms[0]
    assert a["block"] == "cache_read_ratio"
    assert a["severity"] == "warning"
    assert a["ratio_pct"] == 91.0


def test_cache_read_ratio_clean():
    d = {"tok": {"input": 1000, "output": 500, "cache_read": 100, "cache_write": 0}}
    assert report._cache_read_ratio(d) == []
    assert report._cache_read_ratio({"tok": {}}) == []


def test_torn_lines_fires(tmp_path):
    p = _write_torn(tmp_path)
    recs, bad, offsets = report.load(str(p))
    assert bad == 2
    assert len(offsets) == 2
    anoms = report._torn_lines(bad, offsets)
    assert len(anoms) == 1
    a = anoms[0]
    assert a["block"] == "torn_lines"
    assert a["count"] == 2
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    expected = [sum(len(l.encode("utf-8")) for l in lines[:1]),
                sum(len(l.encode("utf-8")) for l in lines[:3])]
    assert a["offsets"] == expected


def test_torn_lines_clean(tmp_path):
    p = tmp_path / "clean.jsonl"
    p.write_text('{"record_version":3,"kind":"final","session_id":"s1"}\n', encoding="utf-8")
    recs, bad, offsets = report.load(str(p))
    assert bad == 0 and offsets == []
    assert report._torn_lines(0, []) == []


def test_supervision_join_fires(tmp_path):
    td = _write_tasks(tmp_path)
    anoms = report._supervision_join(_sep7_sessions(), tasks_dir=str(td))
    assert len(anoms) == 1
    a = anoms[0]
    assert a["block"] == "supervision_join"
    assert a["task_id"] == "T-P0-3R"
    assert a["state"] == "COMPLETED"


def test_supervision_join_clean(tmp_path):
    td = tmp_path / "tasks"
    td.mkdir()
    (td / "T-01.json").write_text(json.dumps({
        "task_id": "T-01", "agent": "implementer", "objective": "x",
        "expected_artifact": "y", "session_id": "s1"}), encoding="utf-8")
    recs = [_rec("s1", task_id="T-01")]
    assert report._supervision_join(recs, tasks_dir=str(td)) == []


def test_supervision_join_missing_dir(tmp_path):
    anoms = report._supervision_join(_sep7_sessions(), tasks_dir=str(tmp_path / "nope"))
    assert len(anoms) == 1
    assert anoms[0]["severity"] == "info"


def test_detect_anomalies_sep7_full_day(tmp_path):
    td = _write_tasks(tmp_path)
    recs = _sep7_sessions() + _twin_sessions()
    d = report.analyse(recs)
    d["unfinalized"] = sorted({r["session_id"] for r in recs
                               if r.get("session_id") and (r.get("kind") or "final") != "final"})
    d["stale"] = report.stale_bg_tasks(recs)
    anoms = report.detect_anomalies(recs, d, tasks_dir=str(td), bad=2, torn_offsets=[100, 200])
    blocks = {a["block"] for a in anoms}
    assert {"gate_silence", "twin_sessions", "spawn_burst", "early_death",
            "poll_escalation", "cache_read_ratio", "torn_lines",
            "supervision_join"} <= blocks
    assert any(a["severity"] == "warning" for a in anoms)


def test_main_exit_1_on_sep7_full_day(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(report, "state_root", lambda: str(tmp_path))
    _write_tasks(tmp_path)
    p = tmp_path / "sep7_full.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for r in _sep7_sessions() + _twin_sessions():
            fh.write(json.dumps(r) + "\n")
        fh.write("garbage torn line\n")
    rc = report.main(["--path", str(p), "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "gate_silence" in out
    assert "twin_sessions" in out
    assert "unfinalized" in out
    assert "torn_line_offsets" in out


def test_main_exit_0_on_clean(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(report, "state_root", lambda: str(tmp_path))
    p = tmp_path / "clean.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec("s1", tools={"bash": {"count": 1, "ms": 10}},
                                 gates={"g4": {"result": "pass", "ms": 5}},
                                 tokens={"input": 1000, "output": 500,
                                         "cache_read": 100, "cache_write": 0})) + "\n")
    rc = report.main(["--path", str(p), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"anomalies"' in out


def test_render_has_anomalies_section():
    d = report.analyse(_sep7_sessions())
    d["unfinalized"] = []
    d["stale"] = 0
    d["models_resolution"] = None
    d["anomalies"] = [{"block": "gate_silence", "severity": "warning",
                       "detail": "day 2026-09-07 has tool activity but no gate events"}]
    out = report.render(d)
    assert "-- ANOMALIES" in out
    assert "[gate_silence]" in out


def test_state_root_delegates_to_the_single_adapter(monkeypatch, tmp_path):
    """report.py must not grow a second state-root resolution of its own."""
    import framework.adapters.gsd_state as gs

    real = tmp_path / ".planning"
    real.mkdir()
    calls = []

    def _resolve():
        calls.append(1)
        return str(real)

    monkeypatch.setattr(gs, "root", _resolve)
    assert report.state_root() == str(real)
    assert calls == [1]


def test_state_root_announces_a_fallback_instead_of_falling_back_silently(monkeypatch, capsys):
    """A silent fallback yields a report built from state no other adapter writes."""
    import framework.adapters.gsd_state as gs

    def _boom():
        raise RuntimeError("manifest unreadable")

    monkeypatch.setattr(gs, "root", _boom)
    assert report.state_root() == os.path.join(report.ROOT, ".planning")
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "manifest unreadable" in err


def test_state_root_propagates_the_adapter_fail_closed_contract(monkeypatch):
    """SystemExit must not be downgraded into a report computed from the wrong root."""
    import framework.adapters.gsd_state as gs

    def _ambiguous():
        raise SystemExit("BLOCKED: ambiguous distribution")

    monkeypatch.setattr(gs, "root", _ambiguous)
    with pytest.raises(SystemExit):
        report.state_root()
