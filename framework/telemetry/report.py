#!/usr/bin/env python3
"""Aggregate telemetry records into a performance and bottleneck report.

WHY: records.jsonl is append-only and unreadable at volume. This is the surface that answers
the two questions the framework was instrumented for:
  1. Where does cost accumulate?          -> tokens by agent, tools by wall-clock
  2. Is context narrowing hurting us?     -> rework rate, gate failure distribution

DELIBERATELY NOT COMPUTED: "context efficiency" (relevant/total context). That requires
labelling which tokens were relevant, which is a post-hoc human judgement. Every metric here
is derived from recorded facts only.

Exit codes:
  0  report produced
  1  report produced but session(s) never finalized OR the model-resolution snapshot records failures (both named in the output)
  2  records exist but none are parseable
  3  no telemetry yet (not an error -- nothing has run)
"""
import argparse
import glob
import json
import os
import re
import statistics as st
import subprocess
import sys
from collections import defaultdict

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# Rework = a task that needed correction after review or verification. This is the framework's
# primary decision metric: if narrow context is costing correctness, it shows up here first.
REWORK_SIGNALS = ("review_rejection", "test_failure", "integration_failure")

# P0-1 (§3): canonical taxonomy vocabulary and the rework subset. The vocabulary is frozen in
# .opencode/plugin/taxonomy.mjs (EVENTS); this tuple mirrors it for the report's aggregation.
TAXONOMY_EVENTS = (
    "WORK_ATTEMPTED", "TEST_FAILED", "REVIEW_REJECTED", "VERIFICATION_FAILED",
    "INTEGRATION_FAILED", "BLOCKER_DETECTED", "CONTEXT_INSUFFICIENT",
    "TASK_REOPENED", "RETRY", "TASK_COMPLETED",
)
REWORK_EVENTS = ("TEST_FAILED", "REVIEW_REJECTED", "INTEGRATION_FAILED", "TASK_REOPENED")

GATE_EVENTS_TUPLE = ("GATE_REQUIRED", "GATE_NOT_REACHED", "GATE_EXECUTION_STARTED", "GATE_RESULT")
GATE_STATES_TUPLE = ("NOT_REACHED", "EXECUTED_PASS", "EXECUTED_UNVERIFIABLE", "UNOBSERVED")


def load_profiles():
    path = os.path.join(ROOT, "framework", "verifier", "profiles.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def gate_inventory():
    gates_dir = os.path.join(ROOT, "framework", "gates")
    result = []
    for p in sorted(glob.glob(os.path.join(gates_dir, "g*.sh"))):
        base = os.path.basename(p)
        if base == "_lib.sh":
            continue
        stem = re.sub(r"\.sh$", "", base)
        if re.match(r"^g[0-9]", stem):
            gid = re.split(r"[-_]", stem)[0]
        else:
            gid = stem
        result.append(gid)
    return sorted(set(result))


def gate_state_classifier(required_name, events):
    evs = [e for e in events if e.get("detail", {}).get("gate") == required_name]
    for e in evs:
        if e.get("event") == "GATE_NOT_REACHED":
            return "NOT_REACHED"
    started = any(e.get("event") == "GATE_EXECUTION_STARTED" for e in evs)
    result_event = None
    for e in evs:
        if e.get("event") == "GATE_RESULT":
            result_event = e
    if started and result_event:
        if result_event.get("detail", {}).get("result") == "pass":
            return "EXECUTED_PASS"
        return "EXECUTED_UNVERIFIABLE"
    return "UNOBSERVED"


def legacy_gate_state(result_str):
    if result_str == "pass":
        return "EXECUTED_PASS"
    if result_str in ("fail", "unverifiable"):
        return "EXECUTED_UNVERIFIABLE"
    return "UNOBSERVED"


def state_root() -> str:
    try:
        out = subprocess.run([sys.executable, "framework/adapters/gsd_state.py", "state-root"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
        p = out.stdout.strip()
        if p and os.path.isdir(p):
            return p
    except Exception:
        pass
    return os.path.join(ROOT, ".planning")


def load(path):
    recs, bad = [], 0
    if not os.path.exists(path):
        return recs, bad
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            bad += 1
    return recs, bad


def collapse(recs):
    """Lifecycle records: one record per session, last wins.

    The plugin now emits started/heartbeat/final per session; aggregating the whole
    series would triple-count every metric. Records without session_id (pre-lifecycle
    fixtures and legacy data) are kept verbatim."""
    out, by_sid = [], {}
    for r in recs:
        sid = r.get("session_id")
        if sid:
            by_sid[sid] = r
        else:
            out.append(r)
    return out + list(by_sid.values())


def stale_bg_tasks(recs):
    """Background tasks launched but never collected or cancelled per session."""
    stale = 0
    for r in recs:
        for t in (r.get("bg_tasks") or {}).values():
            if isinstance(t, dict):
                launched = t.get("launched", 0) or 0
                closed = (t.get("collects", 0) or 0) + (t.get("cancelled", 0) or 0)
                if launched > closed:
                    stale += 1
    return stale


def load_models(path=None):
    """Read the resolve snapshot written by `validate.py --models`.

    Returns None when the snapshot has never been written (preflight not run) --
    absence must not be read as a pass. A corrupt file is reported, not swallowed.
    """
    if path is None:
        path = os.environ.get("MODEL_RESOLUTION_JSON") or os.path.join(
            ROOT, "framework", "telemetry", "models-resolved.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # corrupt snapshot: surface, never silently skip
        return {"_unreadable": str(e)}


def tot(d):
    return sum(v for v in (d or {}).values() if isinstance(v, (int, float)))


def pct(n, d):
    return 0.0 if not d else round(100.0 * n / d, 1)


def bar(v, mx, w=22):
    if mx <= 0:
        return ""
    return "#" * max(1, int(round(w * v / mx))) if v > 0 else ""


def analyse(recs):
    n = len(recs)
    agents = defaultdict(lambda: {"tokens": 0, "in": 0, "out": 0, "calls": 0, "ms": 0, "inv": 0, "models": set()})
    tools = defaultdict(lambda: {"count": 0, "ms": 0})
    gates = defaultdict(lambda: defaultdict(int))
    gate_ms = defaultdict(int)
    models = defaultdict(int)
    retries = defaultdict(int)
    tok = defaultdict(int)
    dur, mat, exp, trunc, fb = [], 0, 0, 0, 0
    esc = retro = recur = 0
    poll = 0
    wreg = wev = wstall = 0
    tiers = defaultdict(int)
    rework_tasks = 0
    fix_targets = defaultdict(int)
    taxonomy = defaultdict(int)
    attempt_events = defaultdict(set)
    rework_events = 0
    completed_work_attempts = 0
    work_attempted_seen = False
    legacy_sessions = 0
    # P0-3: four-state gate accounting. Per (task, gate) we collect the GATE_*
    # taxonomy events and classify into the four states. Legacy rec.gates raw
    # results are mapped through legacy_gate_state and merged per gate.
    task_gate_events = defaultdict(list)
    gate_state_counts = defaultdict(lambda: defaultdict(int))
    gate_required_seen = defaultdict(set)

    for r in recs:
        for k, v in (r.get("tokens") or {}).items():
            if isinstance(v, (int, float)):
                tok[k] += v
        for name, a in (r.get("agents") or {}).items():
            g = agents[name]
            at = a.get("tokens") or {}
            g["tokens"] += tot(at)
            g["in"] += at.get("input", 0) or 0
            g["out"] += at.get("output", 0) or 0
            g["calls"] += a.get("tool_calls", 0) or 0
            g["ms"] += a.get("ms", 0) or 0
            g["inv"] += a.get("invocations", 0) or 0
            for m in a.get("models") or []:
                g["models"].add(m)
        for name, t in (r.get("tools") or {}).items():
            tools[name]["count"] += t.get("count", 0) or 0
            tools[name]["ms"] += t.get("ms", 0) or 0
        for gid, gv in (r.get("gates") or {}).items():
            if isinstance(gv, dict):
                gates[gid][gv.get("result", "unknown")] += 1
                gate_ms[gid] += gv.get("ms", 0) or 0
            else:
                gates[gid][str(gv)] += 1
        for m, c in (r.get("models_seen") or {}).items():
            models[m] += c
        # §8 record-version gate: only v<3 records carry the legacy retries
        # field. A v3 record's retries:{} is never read as zero rework.
        ver = r.get("record_version", 2)
        if ver < 3:
            legacy_sessions += 1
            rw = False
            for k, v in (r.get("retries") or {}).items():
                retries[k] += v
                if k in REWORK_SIGNALS and v:
                    rw = True
            if rw:
                rework_tasks += 1
        # P0-1 (§3): raw taxonomy events → derived rework metrics. Each event
        # occurrence counts; attempt identity is (task_id, attempt_id).
        for ev in r.get("taxonomy_events") or []:
            if not isinstance(ev, dict):
                continue
            name = ev.get("event")
            if not name:
                continue
            taxonomy[name] += 1
            attempt_events[(str(ev.get("task_id") or ""), ev.get("attempt_id"))].add(name)
            if name == "WORK_ATTEMPTED":
                work_attempted_seen = True
            elif name in REWORK_EVENTS:
                rework_events += 1
            if name in GATE_EVENTS_TUPLE:
                gid = ev.get("detail", {}).get("gate")
                if gid:
                    task_gate_events[(str(ev.get("task_id") or ""), gid)].append(ev)
                    if name == "GATE_REQUIRED":
                        gate_required_seen[gid].add(str(ev.get("task_id") or ""))
        if r.get("duration_s"):
            dur.append(r["duration_s"])
        mat += r.get("materialised_chars", 0) or 0
        exp += r.get("context_expansions", 0) or 0
        trunc += r.get("truncations", 0) or 0
        fb += r.get("fallbacks_used", 0) or 0
        esc += r.get("defect_escapes", 0) or 0
        retro += r.get("retros_recorded", 0) or 0
        recur += r.get("retro_recurrences", 0) or 0
        poll += r.get("bg_poll_total", 0) or 0
        wreg += r.get("worker_tasks_registered", 0) or 0
        wev += r.get("worker_events_written", 0) or 0
        wstall += r.get("worker_stalls_detected", 0) or 0
        if r.get("provider_tier") is not None:
            tiers[r["provider_tier"]] += 1
        for t in r.get("retro_fix_targets") or []:
            fix_targets[t] += 1

    completed_work_attempts = sum(
        1 for evs in attempt_events.values()
        if "WORK_ATTEMPTED" in evs and "TASK_COMPLETED" in evs)
    no_observations = [ev for ev in TAXONOMY_EVENTS if taxonomy.get(ev, 0) == 0]

    # P0-3: classify each (task, gate) into the four states from its GATE_*
    # events, then aggregate per gate. Legacy rec.gates raw results (pre-canonical
    # records) are mapped through legacy_gate_state and merged per gate so the
    # report reconciles both eras.
    #
    # Per-task coverage (§5 lines 176-179): required(impact(task)) is the set of
    # gates recorded as GATE_REQUIRED for that task (impact-derived at
    # orchestration time). The denominator universe is seeded from
    # framework/verifier/profiles.yaml impact_to_gates so a gate in the mapping
    # that is never seen across lifetime still appears in the UNOBSERVED section
    # (liveness self-check, plan line 162 intent).
    profiles = load_profiles()
    impact_to_gates = profiles.get("impact_to_gates") or {}
    mapped_gates = sorted({g for gl in impact_to_gates.values() for g in gl})

    task_required = defaultdict(set)   # task_id -> set of required gates (GATE_REQUIRED)
    task_states = {}                   # (task_id, gate) -> four-state classification
    for (task_id, gid), evs in task_gate_events.items():
        state = gate_state_classifier(gid, evs)
        task_states[(task_id, gid)] = state
        gate_state_counts[gid][state] += 1
        if any(e.get("event") == "GATE_REQUIRED" for e in evs):
            task_required[task_id].add(gid)
    for gid, gv in gates.items():
        if isinstance(gv, dict):
            for result_str, cnt in gv.items():
                gate_state_counts[gid][legacy_gate_state(result_str)] += cnt

    inventory = gate_inventory()
    required_gates = sorted(set(gate_required_seen.keys()) | set(gate_state_counts.keys())
                            | set(inventory) | set(mapped_gates))
    gate_coverage = {}
    for gid in required_gates:
        counts = dict(gate_state_counts.get(gid, {}))
        for st_ in GATE_STATES_TUPLE:
            counts.setdefault(st_, 0)
        gate_coverage[gid] = counts

    # Per-task execution vs pass coverage. Execution = EXECUTED_* ∩ required;
    # pass = EXECUTED_PASS ∩ required. The two are never merged (§5 line 179).
    task_coverage = {}
    for task_id, req in task_required.items():
        req = sorted(req)
        executed = sum(1 for g in req if task_states.get((task_id, g)) in
                       ("EXECUTED_PASS", "EXECUTED_UNVERIFIABLE"))
        passed = sum(1 for g in req if task_states.get((task_id, g)) == "EXECUTED_PASS")
        task_coverage[task_id] = {
            "required": req,
            "executed": executed,
            "passed": passed,
            "execution_coverage": pct(executed, len(req)),
            "pass_coverage": pct(passed, len(req)),
        }

    return dict(n=n, tok=tok, agents=agents, tools=tools, gates=gates, gate_ms=gate_ms,
                models=models, retries=retries, dur=dur, mat=mat, exp=exp, trunc=trunc,
                fb=fb, esc=esc, retro=retro, recur=recur, poll=poll, tiers=tiers,
                wreg=wreg, wev=wev, wstall=wstall,
                rework_tasks=rework_tasks, fix_targets=fix_targets,
                taxonomy=dict(taxonomy), no_observations=no_observations,
                rework_events=rework_events, completed_work_attempts=completed_work_attempts,
                work_attempted_seen=work_attempted_seen, legacy_sessions=legacy_sessions,
                gate_coverage=gate_coverage, gate_inventory=inventory,
                task_coverage=task_coverage, impact_to_gates=impact_to_gates)


def render(d, verbose=False):
    L, n = [], d["n"]
    total_tok = tot(d["tok"])
    L.append("=" * 72)
    L.append(f"TELEMETRY REPORT  --  {n} session record(s)")
    L.append("=" * 72)

    L.append("")
    L.append("-- COST ------------------------------------------------------------")
    if total_tok:
        for k in ("input", "output", "reasoning", "cache_read", "cache_write"):
            v = d["tok"].get(k, 0)
            if v:
                L.append(f"  {k:12s} {v:>12,}  ({pct(v, total_tok)}%)")
        L.append(f"  {'TOTAL':12s} {total_tok:>12,}")
        L.append(f"  per session  {round(total_tok / n):>12,}")
    else:
        L.append("  no token data recorded")

    L.append("")
    L.append("-- TOKENS BY AGENT  (the input to per-agent model choice) ----------")
    ags = sorted(d["agents"].items(), key=lambda kv: -kv[1]["tokens"])
    if ags and ags[0][1]["tokens"]:
        mx = ags[0][1]["tokens"]
        L.append(f"  {'agent':13s} {'tokens':>10s} {'share':>7s} {'calls':>6s} {'inv':>4s}")
        for name, a in ags:
            L.append(f"  {name:13s} {a['tokens']:>10,} {pct(a['tokens'], total_tok):>6}% "
                     f"{a['calls']:>6} {a['inv']:>4}  {bar(a['tokens'], mx)}")
        if verbose:
            for name, a in ags:
                if a["models"]:
                    L.append(f"    {name}: {', '.join(sorted(a['models']))}")
    else:
        L.append("  no per-agent attribution recorded")

    L.append("")
    L.append("-- BOTTLENECKS: WALL-CLOCK BY TOOL --------------------------------")
    tl = sorted(d["tools"].items(), key=lambda kv: -kv[1]["ms"])[:12]
    if tl and tl[0][1]["ms"]:
        mx = tl[0][1]["ms"]
        L.append(f"  {'tool':22s} {'total_s':>8s} {'calls':>6s} {'avg_ms':>7s}")
        for name, t in tl:
            avg = round(t["ms"] / t["count"]) if t["count"] else 0
            L.append(f"  {name:22s} {t['ms']/1000:>8.1f} {t['count']:>6} {avg:>7}  {bar(t['ms'], mx)}")
    else:
        L.append("  no tool timing recorded")

    L.append("")
    L.append("-- GATES ----------------------------------------------------------")
    if d["gates"]:
        L.append(f"  {'gate':6s} {'runs':>5s} {'pass':>5s} {'fail':>5s} {'other':>6s} {'total_s':>8s}")
        for gid in sorted(d["gates"]):
            r = d["gates"][gid]
            runs = sum(r.values())
            other = runs - r.get("pass", 0) - r.get("fail", 0)
            L.append(f"  {gid:6s} {runs:>5} {r.get('pass',0):>5} {r.get('fail',0):>5} "
                     f"{other:>6} {d['gate_ms'][gid]/1000:>8.1f}")
            if verbose:
                L.append(f"         {dict(r)}")
        # An unverifiable result is not a pass. Surface it separately or it hides in "other".
        unv = sum(d["gates"][g].get("unverifiable", 0) for g in d["gates"])
        if unv:
            L.append(f"  !! {unv} UNVERIFIABLE result(s) -- claim nothing for these")
    else:
        L.append("  no gate results recorded")

    # P0-3: four-state gate coverage. Execution vs pass coverage split (§5
    # lines 176-177): execution coverage = EXECUTED_* / required; pass coverage
    # = EXECUTED_PASS / required. UNOBSERVED and NOT_REACHED are never pass.
    L.append("")
    L.append("-- GATE COVERAGE (four-state) -------------------------------------")
    gc = d.get("gate_coverage") or {}
    if gc:
        L.append(f"  {'gate':6s} {'UNOBS':>6s} {'N_REACH':>7s} {'EXEC_PASS':>9s} {'EXEC_UNV':>8s}  exec%  pass%")
        for gid in sorted(gc):
            c = gc[gid]
            req = sum(c.values())
            execd = c.get("EXECUTED_PASS", 0) + c.get("EXECUTED_UNVERIFIABLE", 0)
            L.append(f"  {gid:6s} {c.get('UNOBSERVED',0):>6} {c.get('NOT_REACHED',0):>7} "
                     f"{c.get('EXECUTED_PASS',0):>9} {c.get('EXECUTED_UNVERIFIABLE',0):>8} "
                     f"{pct(execd, req):>5}% {pct(c.get('EXECUTED_PASS',0), req):>5}%")
        unobs = sum(c.get("UNOBSERVED", 0) for c in gc.values())
        if unobs:
            L.append(f"  !! {unobs} UNOBSERVED gate-task(s) -- no execution evidence; never a pass")
    else:
        L.append("  no gate coverage recorded")

    # P0-3: per-task execution vs pass coverage (§5 lines 176-179). The two
    # numbers are never merged — execution coverage can be 100% while pass
    # coverage is lower, and neither is ever read as "passed everything".
    tc = d.get("task_coverage") or {}
    if tc:
        L.append("")
        L.append("-- GATE COVERAGE PER TASK (execution vs pass, never merged) --------")
        L.append(f"  {'task':14s} {'req':>3s} {'exec':>5s} {'pass':>5s}  exec%  pass%")
        for task_id in sorted(tc):
            t = tc[task_id]
            L.append(f"  {task_id:14s} {len(t['required']):>3} {t['executed']:>5} {t['passed']:>5} "
                     f"{t['execution_coverage']:>5}% {t['pass_coverage']:>5}%")
            if verbose:
                L.append(f"      required: {', '.join(t['required'])}")
    else:
        L.append("")
        L.append("-- GATE COVERAGE PER TASK ----------------------------------------")
        L.append("  no per-task coverage recorded (no GATE_REQUIRED events)")

    L.append("")
    L.append("-- CONTEXT --------------------------------------------------------")
    L.append(f"  materialised chars   {d['mat']:>10,}   ({round(d['mat']/n) if n else 0:,} per session)")
    L.append(f"  cap truncations      {d['trunc']:>10}")
    L.append(f"  context expansions   {d['exp']:>10}   ({pct(d['exp'], n)}% of sessions)")
    L.append(f"  tier-4 fallbacks     {d['fb']:>10}")
    if d["tiers"]:
        L.append(f"  provider tiers seen  {dict(sorted(d['tiers'].items()))}")
        if d["tiers"].get(4):
            L.append("  note: tier 4 cannot assert 'no dependents', so impact always expands")

    L.append("")
    L.append("-- QUALITY: REWORK RATE (primary decision metric) -----------------")
    if d["legacy_sessions"]:
        L.append(f"  sessions with rework (legacy v<3)  {d['rework_tasks']} / {d['legacy_sessions']}  = {pct(d['rework_tasks'], d['legacy_sessions'])}%")
        if d["retries"]:
            for k, v in sorted(d["retries"].items(), key=lambda kv: -kv[1]):
                flag = "  <- rework" if k in REWORK_SIGNALS else ""
                L.append(f"    {k:22s} {v:>4}{flag}")
        else:
            L.append("    no legacy retries recorded")
    else:
        L.append("  no legacy rework measurement (v3 records carry taxonomy events, not retries)")
    # P0-1 (§3/§6): taxonomy-derived rework rate, liveness-gated on WORK_ATTEMPTED
    # sightings. No WORK_ATTEMPTED ever recorded → no measurement, never zero rework.
    if d["work_attempted_seen"]:
        rate = pct(d["rework_events"], d["completed_work_attempts"]) if d["completed_work_attempts"] else None
        rate_s = f"{rate}%" if rate is not None else "n/a (no completed attempts)"
        L.append(f"  taxonomy rework events   {d['rework_events']}")
        L.append(f"  completed work attempts  {d['completed_work_attempts']}")
        L.append(f"  taxonomy rework rate     {rate_s}")
    else:
        L.append("  taxonomy rework rate     no measurement (no WORK_ATTEMPTED recorded -- never zero rework)")
    L.append(f"  defect escapes         {d['esc']}")
    L.append(f"  retrospectives         {d['retro']}")
    L.append(f"  recurrences            {d['recur']}"
             + ("   <- a fix did not close the gap" if d["recur"] else ""))
    if d["fix_targets"]:
        L.append(f"  fix targets            {dict(sorted(d['fix_targets'].items(), key=lambda kv: -kv[1]))}")

    L.append("")
    L.append("-- TAXONOMY (P0-1 canonical events) ------------------------------")
    if d["taxonomy"]:
        for ev in TAXONOMY_EVENTS:
            L.append(f"  {ev:22s} {d['taxonomy'].get(ev, 0):>6}")
        if d["no_observations"]:
            L.append(f"  NO_OBSERVATIONS (informational, never a liveness verdict): {', '.join(d['no_observations'])}")
    else:
        L.append("  no taxonomy events recorded")

    if d["dur"]:
        L.append("")
        L.append("-- DURATION -------------------------------------------------------")
        L.append(f"  median {st.median(d['dur']):.0f}s   mean {st.mean(d['dur']):.0f}s   max {max(d['dur'])}s")

    L.append("")
    L.append("-- TELEMETRY HEALTH ------------------------------------------------")
    L.append(f"  unfinalized sessions  {len(d.get('unfinalized') or [])}"
             + ("   <- session died before a final record" if d.get("unfinalized") else ""))
    L.append(f"  bg poll total         {d.get('poll', 0)}"
             + ("   <- polling anti-pattern recorded" if d.get('poll') else ""))
    L.append(f"  stale bg tasks        {d.get('stale', 0)}"
             + ("   <- launched but never collected or cancelled" if d.get('stale') else ""))
    L.append(f"  tasks registered      {d.get('wreg', 0)}")
    L.append(f"  stalls detected       {d.get('wstall', 0)}"
             + ("   <- supervision caught a silent worker" if d.get('wstall') else ""))

    if d.get("models_resolution") is not None:
        mr = d["models_resolution"]
        L.append("")
        L.append("-- MODEL RESOLUTION (validate.py --models snapshot) ---------------")
        if "_unreadable" in mr:
            L.append(f"  snapshot unreadable: {mr['_unreadable']}")
        else:
            L.append(f"  active profile   {mr.get('active_profile') or '(none)'}")
            L.append(f"  {'agent/slot':13s} {'model':38s} source")
            for name in sorted(mr.get("agents") or {}):
                a = mr["agents"][name]
                flag = "  <- RESOLUTION FAILURE" if a.get("source") == "error" else ""
                L.append(f"  {name:13s} {a.get('model') or '(none)':38s} {a.get('source')}{flag}")
            fails = mr.get("failures") or []
            if fails:
                L.append(f"  !! {len(fails)} resolution failure(s): {', '.join(fails)}")
                L.append("  !! an unresolved model stalls the subagent at spawn; fix before use")

    L.append("")
    L.append("-- READING THIS ---------------------------------------------------")
    if n < 20:
        L.append(f"  {n} session(s). Under ~20 these numbers are indicative, not decisive.")
    L.append("  Highest-token agent is the first candidate for a cheaper model.")
    L.append("  Raise rework rate after any model change = revert it.")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit aggregate as JSON")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--path", help="override records.jsonl path")
    a = ap.parse_args()

    path = a.path or os.path.join(state_root(), "telemetry", "records.jsonl")
    recs, bad = load(path)
    recs = collapse(recs)

    if not recs and not bad:
        print(f"[telemetry] no records at {path}")
        print("[telemetry] nothing has run yet -- this is exit 3, not a failure")
        return 3
    if not recs and bad:
        print(f"[telemetry] {bad} record(s) present but none parseable: {path}")
        return 2

    d = analyse(recs)
    d["unfinalized"] = sorted({r["session_id"] for r in recs
                               if r.get("session_id") and (r.get("kind") or "final") != "final"})
    d["stale"] = stale_bg_tasks(recs)
    d["models_resolution"] = load_models()
    if a.json:
        out = {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in d.items()}
        out["agents"] = {k: {**v, "models": sorted(v["models"])} for k, v in d["agents"].items()}
        out["tools"] = {k: dict(v) for k, v in d["tools"].items()}
        out["gates"] = {k: dict(v) for k, v in d["gates"].items()}
        out["gate_coverage"] = d.get("gate_coverage") or {}
        out["gate_inventory"] = d.get("gate_inventory") or []
        out["rework_rate_pct"] = pct(d["rework_tasks"], d["legacy_sessions"]) if d["legacy_sessions"] else None
        out["taxonomy"] = d["taxonomy"]
        out["no_observations"] = d["no_observations"]
        out["rework_events"] = d["rework_events"]
        out["completed_work_attempts"] = d["completed_work_attempts"]
        out["taxonomy_rework_rate_pct"] = (
            pct(d["rework_events"], d["completed_work_attempts"])
            if d["work_attempted_seen"] and d["completed_work_attempts"] else None)
        out["unfinalized_sessions"] = d["unfinalized"]
        out["stale_bg_tasks"] = d["stale"]
        out["model_resolution"] = d["models_resolution"]
        print(json.dumps(out, indent=2, default=str))
    else:
        print(render(d, a.verbose))
        if bad:
            print(f"[telemetry] warning: skipped {bad} unparseable line(s)")
    rc = 0
    if d["unfinalized"]:
        _head = ", ".join(d["unfinalized"][:5])
        if len(d["unfinalized"]) > 5:
            _head += f" +{len(d['unfinalized']) - 5} more"
        print(f"[telemetry] {len(d['unfinalized'])} session(s) have no final record "
              f"(died before SESSION_FINALIZED): {_head}")
        rc = 1
    mr = d.get("models_resolution")
    if mr and not mr.get("_unreadable") and (mr.get("failures") or []):
        print(f"[telemetry] {len(mr['failures'])} model resolution failure(s): "
              f"{', '.join(mr['failures'])} -- an unresolved model stalls subagent spawn")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
