# -*- coding: utf-8 -*-
"""Failure-injection matrix for the task supervision control plane.

Adversarial proof, not unit tests: each scenario injects a real failure mode
(worker death, supervisor death, silent hang, headless block, stalled retry,
concurrent streams) and asserts the supervisor's observed behavior against the
semantics the P0 alignment implemented. A scenario passes only when every
assertion holds; the suite exits 0 only when all scenarios pass.

Run:  python framework/adapters/failure_injection.py
Self-cleaning: every registered task is removed in finally, like the selftest.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gsd_state as g  # noqa: E402

RESULTS = {}


def check(name, ok, detail=""):
    RESULTS[name] = "pass" if ok else "fail: " + detail


def cleanup(ids):
    for t in ids:
        g._task_path(t).unlink(missing_ok=True)
        g._task_events_path(t).unlink(missing_ok=True)


def register(tid, **kw):
    payload = {
        "agent": "adversarial",
        "type": "default",
        "objective": "failure-injection " + tid,
        "expected_artifact": "pass",
        "progress_timeout_s": 30,
        "max_duration_s": 60,
    }
    payload.update(kw)
    return g.register_task(tid, payload)


def scenario_a_worker_dies():
    """Worker process dies mid-flight. Supervisor declares LOST; the record is
    LOST, not FAILED, and no failure_class leaks in."""
    tid = "T-FIA"
    try:
        cleanup([tid])
        register(tid)
        g.task_event(tid, {"state": "STARTED"})
        g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C0"})
        st = g.task_event(tid, {"state": "LOST", "emitter": "team-lead",
                                "detail": "injected: worker process died, session vanished"})
        check("A_lost_state", st["state"] == "LOST" and st["health"] == "LOST"
              and st["recovery_level"] == 4 and st["execution"] == "IDLE"
              and st["liveness"] == "DEAD",
              "%s/%s/%s" % (st["state"], st["health"], st["execution"]))
        check("A_not_failed", st["health"] != "FAILED" and st["failure_class"] == "",
              st["failure_class"])
        check("A_recovery", "re-dispatch" in st["recovery_action"]
              and "retry_of=" + tid in st["recovery_action"]
              and "never classify as worker or provider failure" in st["recovery_action"],
              st["recovery_action"])
        check("A_terminal", g.TASK_TERMINAL and "LOST" in g.TASK_TERMINAL)
        seqs = [e["seq"] for e in st["recent_events"]]
        check("A_seq_monotonic", seqs == sorted(seqs) and len(seqs) == len(set(seqs)),
              str(seqs))
    except SystemExit as e:
        check("A_lost_state", False, "raised: %s" % e)
        check("A_not_failed", False, "raised")
        check("A_recovery", False, "raised")
        check("A_terminal", False, "raised")
        check("A_seq_monotonic", False, "raised")
    finally:
        cleanup([tid])


def scenario_b_supervisor_dies():
    """Supervisor vanishes. Worker state persists on disk; a successor supervisor
    reconciles and sees the SAME task identity, the SAME attempt, continued
    observation - and the worker can keep advancing."""
    tid = "T-FIB"
    try:
        cleanup([tid])
        register(tid, session_id="ses-fib-1", progress_timeout_s=2, max_duration_s=60)
        g.task_event(tid, {"state": "STARTED"})
        g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C0"})
        # supervisor vanishes here; successor reads the durable record
        st = g.task_status(tid)
        check("B_identity", st["task_id"] == tid and st["session_id"] == "ses-fib-1"
              and st["state"] == "PROGRESS" and st["checkpoints_reached"] == ["C0"],
              "%s/%s/%s" % (st["task_id"], st["session_id"], st["checkpoints_reached"]))
        # worker continued while supervisor was gone
        g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C1"})
        st = g.task_status(tid)
        check("B_worker_continues", st["checkpoints_reached"] == ["C0", "C1"]
              and st["milestones_reached"] == 2, str(st["checkpoints_reached"]))
        # contracts are immutable: re-register is refused, identity cannot fork
        try:
            register(tid)
            check("B_immutable", False, "re-register accepted")
        except SystemExit:
            check("B_immutable", True, "")
        # successor reconcile: silent worker is UNKNOWN/WARNING, alive -> WARNING,
        # absent -> STALLED. Supervisor absence never destroys worker state.
        time.sleep(3.2)  # pt=2: silent >= pt but < 2pt
        st = g.task_status(tid)
        check("B_reconcile_unknown", st["liveness"] == "UNKNOWN"
              and st["health"] == "WARNING" and st["recovery_level"] == 1,
              st["liveness"] + "/" + st["health"])
        st = g.task_status(tid, session_alive=True)
        check("B_reconcile_alive", st["liveness"] == "ALIVE"
              and st["health"] == "WARNING", st["liveness"] + "/" + st["health"])
        st = g.task_status(tid, session_alive=False)
        check("B_reconcile_absent", st["liveness"] == "DEAD"
              and st["health"] == "STALLED" and st["recovery_level"] == 2,
              st["liveness"] + "/" + st["health"])
        check("B_events_intact", [e["seq"] for e in g.task_status(tid)["recent_events"]]
              == [1, 2, 3], "seq drift after reconcile")
    except SystemExit as e:
        check("B_identity", False, "raised: %s" % e)
        check("B_worker_continues", False, "raised")
        check("B_immutable", False, "raised")
        check("B_reconcile_unknown", False, "raised")
        check("B_reconcile_alive", False, "raised")
        check("B_reconcile_absent", False, "raised")
        check("B_events_intact", False, "raised")
    finally:
        cleanup([tid])


def scenario_c_hang():
    """Worker alive but doing nothing: heartbeats continue, no checkpoint
    advances. Health escalates WARNING -> STALLED while progress stays
    HEARTBEAT_ONLY - the 'alive but stuck' signal."""
    tid = "T-FIC"
    try:
        cleanup([tid])
        register(tid, progress_timeout_s=2, max_duration_s=60)
        g.task_event(tid, {"state": "STARTED"})
        g.task_event(tid, {"state": "PROGRESS"})                       # heartbeat
        g.task_event(tid, {"state": "PROGRESS"})                       # heartbeat
        g.task_event(tid, {"state": "PROGRESS"})                       # heartbeat
        time.sleep(4.2)  # silent >= 2 * pt
        st = g.task_status(tid)
        check("C_stalled", st["health"] == "STALLED" and st["recovery_level"] == 2
              and st["execution"] == "WORKING", st["health"] + "/" + str(st["recovery_level"]))
        check("C_no_progress", st["progress"] == "HEARTBEAT_ONLY"
              and st["milestones_reached"] == 0 and st["heartbeats"] == 3
              and st["last_progress_kind"] == "heartbeat",
              "%s/%s/%s" % (st["progress"], st["milestones_reached"], st["heartbeats"]))
        check("C_liveness_unknown", st["liveness"] == "UNKNOWN", st["liveness"])
        check("C_policy", "STALLED=inspect_then_cancel_if_frozen" in st["recovery_policy"].values()
              or [v for k, v in st["recovery_policy"].items() if k == "STALLED"][0]
              == "inspect_then_cancel_if_frozen", str(st["recovery_policy"]))
        # supervisor confirms the worker is alive: downgrade to WARNING - but the
        # staleness signal (HEARTBEAT_ONLY) persists. Heartbeat != progress.
        st = g.task_status(tid, session_alive=True)
        check("C_alive_but_stuck", st["health"] == "WARNING" and st["recovery_level"] == 1
              and st["progress"] == "HEARTBEAT_ONLY",
              st["health"] + "/" + st["progress"])
        # a real milestone rescues it: progress, not heartbeat, heals the health
        g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C0"})
        g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C1"})
        st = g.task_status(tid)
        check("C_progress_heals", st["progress"] == "CHECKPOINT_ADVANCED"
              and st["milestones_reached"] == 2, st["progress"])
    except SystemExit as e:
        check("C_stalled", False, "raised: %s" % e)
        check("C_no_progress", False, "raised")
        check("C_liveness_unknown", False, "raised")
        check("C_policy", False, "raised")
        check("C_alive_but_stuck", False, "raised")
        check("C_progress_heals", False, "raised")
    finally:
        cleanup([tid])


def scenario_d_headless_blocked():
    """A headless worker that needs a decision must not sit asking: it emits
    BLOCKED with a named detail. The task stays non-terminal and resumable."""
    tid = "T-FID"
    try:
        cleanup([tid])
        register(tid, headless=True)
        g.task_event(tid, {"state": "STARTED"})
        st = g.task_event(tid, {"state": "BLOCKED",
                                "detail": "interactive permission required: push to production"})
        check("D_blocked_state", st["state"] == "BLOCKED" and st["execution"] == "BLOCKED"
              and st["health"] != "FAILED" and st["state"] not in g.TASK_TERMINAL,
              "%s/%s" % (st["state"], st["execution"]))
        check("D_headless_flag", st["headless"] is True, str(st["headless"]))
        check("D_named_detail", st["recent_events"][-1].get("detail")
              == "interactive permission required: push to production",
              str(st["recent_events"][-1]))
        check("D_policy_present", len(st["recovery_policy"]) == 5, str(st["recovery_policy"]))
        # BLOCKED is resumable: PROGRESS with a checkpoint is a legal next state
        st = g.task_event(tid, {"state": "PROGRESS", "checkpoint": "C0"})
        check("D_resumable", st["state"] == "PROGRESS" and st["checkpoints_reached"] == ["C0"],
              "%s/%s" % (st["state"], st["checkpoints_reached"]))
    except SystemExit as e:
        check("D_blocked_state", False, "raised: %s" % e)
        check("D_headless_flag", False, "raised")
        check("D_named_detail", False, "raised")
        check("D_policy_present", False, "raised")
        check("D_resumable", False, "raised")
    finally:
        cleanup([tid])


def scenario_e_recovery_taxonomy():
    """Attempt 1 stalls and is cancelled by the supervisor; attempt 2 retries the
    SAME objective under a fresh id linked by retry_of and completes. Derived
    counters prove the attempt taxonomy end-to-end."""
    t1, t2 = "T-FIE1", "T-FIE2"
    try:
        cleanup([t1, t2])
        register(t1, progress_timeout_s=2, max_duration_s=4)
        g.task_event(t1, {"state": "STARTED"})
        time.sleep(4.2)  # elapsed >= max_duration
        st = g.task_status(t1)
        check("E_attempt1_overdue", st["health"] == "OVERDUE" and st["recovery_level"] == 3
              and "cancel_and_retry" in st["recovery_action"],
              st["health"] + "/" + st["recovery_action"])
        st = g.cancel_task(t1)  # supervisor cancels the stalled attempt
        check("E_attempt1_cancelled", st["state"] == "CANCELLED" and st["health"] == "CANCELLED"
              and st["state"] in g.TASK_TERMINAL, st["state"])
        # attempt 2: fresh id, retry_of points at attempt 1
        register(t2, retry_of=t1)
        g.task_event(t2, {"state": "STARTED"})
        g.task_event(t2, {"state": "PROGRESS", "checkpoint": "C0"})
        g.task_event(t2, {"state": "PROGRESS", "checkpoint": "C1"})
        st = g.task_event(t2, {"state": "COMPLETED"})
        check("E_attempt2_completed", st["state"] == "COMPLETED" and st["health"] == "COMPLETE"
              and st["recovery_level"] == 0, st["state"] + "/" + st["health"])
        _, ev1 = g._task_load(t1)
        _, ev2 = g._task_load(t2)
        contract2 = json.loads(g._task_path(t2).read_text(encoding="utf-8"))
        # derived counters from the durable event streams (no framework change)
        attempts = sum(1 for e in ev1 + ev2 if e["state"] == "STARTED")
        retries = 1 if contract2.get("retry_of") == t1 else 0
        check("E_taxonomy_attempts", attempts == 2, "attempts=%d" % attempts)
        check("E_taxonomy_retry", retries == 1, "retry links=%d" % retries)
        check("E_taxonomy_recovery_success", attempts == 2 and retries == 1
              and ev2[-1]["state"] == "COMPLETED" and ev1[-1]["state"] == "CANCELLED",
              "recovery chain broken")
        check("E_policy_surfaced", len(g.task_status(t2)["recovery_policy"]) == 5,
              str(g.task_status(t2)["recovery_policy"]))
    except SystemExit as e:
        check("E_attempt1_overdue", False, "raised: %s" % e)
        check("E_attempt1_cancelled", False, "raised")
        check("E_attempt2_completed", False, "raised")
        check("E_taxonomy_attempts", False, "raised")
        check("E_taxonomy_retry", False, "raised")
        check("E_taxonomy_recovery_success", False, "raised")
        check("E_policy_surfaced", False, "raised")
    finally:
        cleanup([t1, t2])


def scenario_f_concurrency():
    """Three tasks run concurrently with interleaved events. Each stream stays
    isolated: no foreign events, per-task monotonic seq, distinct sessions,
    independent outcomes (one stalls, one completes, one advances)."""
    ids = ["T-FIF1", "T-FIF2", "T-FIF3"]
    try:
        cleanup(ids)
        register("T-FIF1", session_id="ses-fif-1", progress_timeout_s=2, max_duration_s=60)
        register("T-FIF2", session_id="ses-fif-2")
        register("T-FIF3", session_id="ses-fif-3")
        # interleave
        g.task_event("T-FIF1", {"state": "STARTED"})
        g.task_event("T-FIF2", {"state": "STARTED"})
        g.task_event("T-FIF3", {"state": "STARTED"})
        g.task_event("T-FIF1", {"state": "PROGRESS", "checkpoint": "C0"})
        g.task_event("T-FIF2", {"state": "PROGRESS", "checkpoint": "C0"})
        g.task_event("T-FIF2", {"state": "PROGRESS", "checkpoint": "C1"})
        g.task_event("T-FIF1", {"state": "PROGRESS", "checkpoint": "C0"})   # repeat = heartbeat
        g.task_event("T-FIF3", {"state": "PROGRESS", "checkpoint": "C0"})
        g.task_event("T-FIF2", {"state": "COMPLETED"})
        g.task_event("T-FIF3", {"state": "PROGRESS", "checkpoint": "C1"})
        # T1 goes silent -> stalls; T2 done; T3 healthy
        time.sleep(4.2)
        s1 = g.task_status("T-FIF1")
        s2 = g.task_status("T-FIF2")
        s3 = g.task_status("T-FIF3")
        check("F_t1_stalled", s1["health"] == "STALLED" and s1["recovery_level"] == 2,
              s1["health"])
        check("F_t2_completed", s2["state"] == "COMPLETED" and s2["health"] == "COMPLETE",
              s2["state"])
        check("F_t3_healthy", s3["state"] == "PROGRESS" and s3["health"] == "HEALTHY"
              and s3["checkpoints_reached"] == ["C0", "C1"], s3["state"] + "/" + s3["health"])
        # isolation: per-task streams contain only their own events; seq continuity
        for tid, expect_seqs, cps, hbs, sess in (
                ("T-FIF1", [1, 2, 3], ["C0"], 1, "ses-fif-1"),
                ("T-FIF2", [1, 2, 3, 4], ["C0", "C1"], 0, "ses-fif-2"),
                ("T-FIF3", [1, 2, 3], ["C0", "C1"], 0, "ses-fif-3")):
            _, evs = g._task_load(tid)
            seqs = [e["seq"] for e in evs]
            check("F_isolation_" + tid, seqs == expect_seqs
                  and g.task_status(tid)["session_id"] == sess
                  and len(seqs) == len(set(seqs)),
                  "%s seqs= %s" % (tid, seqs))
        # attribution crossover check: each status's own fields match its own stream
        check("F_attribution", s1["task_id"] != s2["task_id"] != s3["task_id"]
              and s1["session_id"] != s2["session_id"] and s2["session_id"] != s3["session_id"]
              and s1["checkpoints_reached"] == ["C0"] and s2["checkpoints_reached"] == ["C0", "C1"]
              and s3["checkpoints_reached"] == ["C0", "C1"],
              "cross-contamination suspected")
        check("F_contracts_durable", all(g._task_path(t).exists() for t in ids),
              "a contract disappeared")
    except SystemExit as e:
        for k in ("F_t1_stalled", "F_t2_completed", "F_t3_healthy",
                  "F_isolation_T-FIF1", "F_isolation_T-FIF2", "F_isolation_T-FIF3",
                  "F_attribution", "F_contracts_durable"):
            check(k, False, "raised: %s" % e)
    finally:
        cleanup(ids)


def main():
    scenario_a_worker_dies()
    scenario_b_supervisor_dies()
    scenario_c_hang()
    scenario_d_headless_blocked()
    scenario_e_recovery_taxonomy()
    scenario_f_concurrency()
    failed = [k for k, v in RESULTS.items() if v != "pass"]
    print("== FAILURE-INJECTION MATRIX ==")
    for k in sorted(RESULTS):
        print("  %-34s %s" % (k, RESULTS[k]))
    print("== %d checks, %d failed ==" % (len(RESULTS), len(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
