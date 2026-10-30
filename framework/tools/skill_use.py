#!/usr/bin/env python3
"""Skill use -- did the agent LOAD the skills its plan required?

WHY THIS EXISTS
===============
Three different claims were being conflated, and only two were checked:

  resolution  the skill exists and parses                       <- validate.py
  selection   the plan REQUIRES it, so an agent must load it     <- g_skill_coverage
  use         the agent actually invoked it in this session       <- this module

A plan can name `apple-ui` in `required_skills` and a dispatched implementer can never call
the skill tool. G-SKILL-COVERAGE would be green the whole time. This module diffs intent
(the plan) against observation (the telemetry record), which is the only place the third
claim can be settled with a machine verdict.

EVIDENCE SOURCE -- no new sensor
================================
There is no separate recorder. `framework/opencode/plugin/telemetry.ts` already captures the
`skill` tool call into its per-session record's `skills_loaded` field, and flushes it in every
heartbeat and final write through `write-telemetry`. Adding a second log would be a second
source of truth for the same fact (the duplicate-capability failure this framework forbids),
and it would move the sensor into agent-writable territory. The plugin is a plane file, so
what it emits cannot be edited by the agent being measured.

WHAT THIS DOES NOT PROVE
========================
It proves a skill tool call was RECORDED for a session attributed to the task. It does not
prove the skill's instructions reached the model's context, and it cannot distinguish a
deliberate invocation from an exploratory one. Treat a PASS as "the call happened", never as
"the skill was applied".

`unknown` in `skills_loaded` is a SENSOR DEFECT, not a skill named "unknown": telemetry.ts
falls back to `"unknown"` when it cannot read the skill name off the tool call, which means
the tool's argument key differs from the one the recorder reads. This module reports it as a
warning and never lets it satisfy a required skill.

Exit: 0 every required skill observed | 1 missing | 2 BLOCKED (plan/state unreadable)
      4 NOT_APPLICABLE (no telemetry records, or the plan requires no skills)
Usage:
  python3 framework/tools/skill_use.py PLAN.md [--task ID] [--json]
  python3 framework/tools/skill_use.py --records
  python3 framework/tools/skill_use.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# One parser for `required_skills:` in the whole repository: a plan repeats the key once per
# task, and a consumer that reads only the first block verifies one task and passes the rest.
from skill_coverage import collect_lists  # noqa: E402

RECORDS = ("telemetry", "records.jsonl")
UNKNOWN_SKILL = "unknown"


def state_root():
    """Resolve the state root through the one adapter; announce any fallback on stderr."""
    try:
        from framework.adapters.gsd_state import root as _root

        p = str(_root())
        if os.path.isdir(p):
            return p
        reason = "resolved root is not a directory: %s" % p
    except Exception as exc:  # degrade loudly, never silently
        reason = "%s: %s" % (type(exc).__name__, exc)
    fallback = os.path.join(ROOT, ".planning")
    print("WARNING: could not resolve the GSD state root (%s); falling back to %s"
          % (reason, fallback), file=sys.stderr)
    return fallback


def load_records(path):
    """Return (records, bad_line_count). A torn line is counted, never silently dropped."""
    recs, bad = [], 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except ValueError:
                bad += 1
    return recs, bad


def collapse(recs):
    """One record per session, last line wins.

    The store is an append-only lifecycle series (started / heartbeat / final) and each line
    carries the cumulative `skills_loaded` for that session, so summing lines would multi-count
    and keeping the first would drop every skill loaded after start. This mirrors the collapse
    report.py applies before computing any metric.
    """
    by_session = {}
    for i, r in enumerate(recs):
        sid = r.get("session_id") or ("%s#anon%d" % ("", i) if not r.get("session_id") else "")
        by_session[sid] = r
    return list(by_session.values())


def attribution(rec, task_id):
    """The task a record is attributed to, across the shapes the collector has written."""
    env = rec.get("envelope") or {}
    return str(rec.get("task_id") or env.get("task_id") or (task_id or ""))


def observed(recs, task_id=None):
    """Return (sessions_used, skills, unknown_seen) for the records attributable to task_id."""
    used, skills, unknown = [], set(), 0
    for r in collapse(recs):
        if task_id and attribution(r, task_id) != task_id:
            continue
        used.append({"session_id": r.get("session_id") or "", "kind": r.get("kind") or "final"})
        for s in r.get("skills_loaded") or []:
            if not isinstance(s, str) or not s:
                continue
            if s == UNKNOWN_SKILL:
                unknown += 1
                continue
            skills.add(s)
    return used, skills, unknown


def judge(required, skills, sessions, unknown, task_id, records_bad):
    """Pure verdict. Returns (rows, exit_code, evidence)."""
    rows = []
    if unknown:
        rows.append({"severity": "WARN", "rule": "SU01",
                     "message": "telemetry recorded %d skill call(s) as '%s': the recorder could "
                                "not read the skill name, so the sensor's argument key does not "
                                "match the skill tool. Those calls cannot satisfy a requirement"
                                % (unknown, UNKNOWN_SKILL)})
    missing = [s for s in required if s not in skills]
    for s in missing:
        rows.append({"severity": "ERROR", "rule": "SU02",
                     "message": "plan requires '%s' but no skill tool call for it was recorded%s"
                                % (s, "" if sessions else " (no session attributed to the task)")})
    evidence = {"sessions": len(sessions), "task_id": task_id or "",
                "observed": sorted(skills), "required": list(required),
                "bad_records": records_bad, "unknown_skill_calls": unknown}
    return rows, (1 if missing else 0), evidence


def _selftest():
    cases = []

    def add(name, got, want):
        cases.append((name, got, want))

    plan = "required_skills:\n- apple-ui\nfiles:\n- x\nrequired_skills:\n- frontend-react\n"
    req = collect_lists(plan, "required_skills")

    sess = [{"session_id": "s1", "kind": "final", "task_id": "T-01",
             "skills_loaded": ["apple-ui", "frontend-react"]},
            {"session_id": "s2", "kind": "final", "task_id": "T-02",
             "skills_loaded": ["designmotion-design"]}]

    used, skills, unknown = observed(sess, "T-01")
    add("task attribution filters sessions", (len(used), sorted(skills)),
        (1, ["apple-ui", "frontend-react"]))
    used, skills, unknown = observed(sess)
    add("no task attribution -> every session", (len(used), sorted(skills)),
        (2, ["apple-ui", "designmotion-design", "frontend-react"]))

    # Lifecycle series: three lines for one session, the last one wins. Summing would
    # multi-count; keeping the first would drop a skill loaded after `started`.
    series = [{"session_id": "s1", "kind": "started", "skills_loaded": []},
              {"session_id": "s1", "kind": "heartbeat", "skills_loaded": ["apple-ui"]},
              {"session_id": "s1", "kind": "final",
               "skills_loaded": ["apple-ui", "frontend-react"]}]
    used, skills, unknown = observed(series, "T-01")
    add("lifecycle series collapses, last wins", (len(used), sorted(skills)),
        (1, ["apple-ui", "frontend-react"]))

    # `unknown` must never satisfy a requirement -- it is a sensor defect.
    used, skills, unknown = observed([{"session_id": "s1", "skills_loaded": ["unknown"]}], "T-01")
    add("'unknown' does not count as a skill", (sorted(skills), unknown), ([], 1))
    rows, code, _ = judge(["apple-ui"], skills, used, unknown, "T-01", 0)
    add("'unknown' leaves the requirement missing", (code, [r["rule"] for r in rows]),
        (1, ["SU01", "SU02"]))

    rows, code, _ = judge(req, set(req), [{"session_id": "s1"}], 0, "T-01", 0)
    add("every required skill observed -> clean", (code, rows), (0, []))
    rows, code, _ = judge(req, {"apple-ui"}, [{"session_id": "s1"}], 0, "T-01", 0)
    add("one of two required observed -> SU02", (code, [r["rule"] for r in rows]), (1, ["SU02"]))
    rows, code, _ = judge(req, set(), [], 0, "T-01", 0)
    add("no session attributed -> SU02 names why", (code, "no session attributed" in rows[0]["message"]),
        (1, True))

    failed = [(n, g, w) for n, g, w in cases if g != w]
    for name, got, want in cases:
        print("  %s  %s%s" % ("PASS" if got == want else "FAIL", name,
                              "" if got == want else "  got=%r want=%r" % (got, want)))
    print("selftest: %d/%d pass" % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="skill use: plan intent vs recorded invocation")
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--task", default=os.environ.get("ENTRY_TASK") or "",
                    help="only credit sessions attributed to this task id")
    ap.add_argument("--state-root", default="",
                    help="override the resolved state root (the caller already resolved it)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--records", action="store_true",
                    help="report what the telemetry sensor has recorded, and exit")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return _selftest()

    # One resolution, by the caller: the shell gate already normalised the root through the
    # same adapter, and resolving it twice lets the two disagree about which store is read.
    root = a.state_root or state_root()
    path = os.path.join(root, *RECORDS)
    if not os.path.isfile(path):
        print("[skill_use] NOT_APPLICABLE no telemetry records at %s" % path)
        return 4
    try:
        recs, bad = load_records(path)
    except OSError as exc:
        print("[skill_use] BLOCKED records unreadable: %s" % exc)
        return 2

    if a.records:
        used, skills, unknown = observed(recs, a.task or None)
        tasks = {}
        for r in collapse(recs):
            t = attribution(r, "")
            tasks[t or "(unattributed)"] = tasks.get(t or "(unattributed)", 0) + 1
        print("[skill_use] records=%d bad=%d sessions=%d skills=%d unknown_calls=%d"
              % (len(recs), bad, len(used), len(skills), unknown))
        print("[skill_use] observed: %s" % (", ".join(sorted(skills)) or "(none)"))
        print("[skill_use] by task: %s" % json.dumps(tasks, sort_keys=True))
        return 0

    if not a.plan or not os.path.isfile(a.plan):
        print("[skill_use] BLOCKED plan not readable: %s" % (a.plan or "(none)"))
        return 2
    try:
        with open(a.plan, encoding="utf-8-sig") as fh:
            required = collect_lists(fh.read(), "required_skills")
    except (OSError, UnicodeDecodeError) as exc:
        print("[skill_use] BLOCKED plan unreadable: %s" % exc)
        return 2
    if not required:
        print("[skill_use] NOT_APPLICABLE plan declares no required_skills")
        return 4

    used, skills, unknown = observed(recs, a.task or None)
    rows, code, evidence = judge(required, skills, used, unknown, a.task, bad)
    if a.json:
        print(json.dumps({"rows": rows, "evidence": evidence, "sessions": used}, indent=1))
    else:
        for r in rows:
            print("[skill_use] %s %s: %s" % (r["severity"], r["rule"], r["message"]))
        errs = sum(1 for r in rows if r["severity"] == "ERROR")
        print("[skill_use] %d error(s), %d warning(s); %d session(s) judged"
              % (errs, len(rows) - errs, len(used)))
    return code


if __name__ == "__main__":
    sys.exit(main())
