#!/usr/bin/env python3
"""System-test harness -- DID-017. The only producer of system-test evidence.

An agent can type "tests passed". It cannot forge this: the harness refuses to run unless the
frozen suite is byte-identical, runs the suite against the REAL stack, and writes a result with
the hashes of the JUnit XML and the log plus the state of the code under test. The gate and the
ASK-completion guard accept only that file, and only while it is still fresh.

  freeze     lint must be clean; record sha256 of every test file, the data manifest and the
             plan digest
  run        verify freeze + data hashes -> preflight the stack -> run -> parse JUnit -> write result
  verify     is there a fresh, passing, untampered result for every real-stack criterion?
  ask-gate   verify every plan that declares `ask_id: <ASK>` (used by intake COMPLETED)

The lock is the controlled artefact. It records a content hash for every test file, the data
manifest and the plan; `run` refuses to execute unless they are byte-identical, and `verify`
refuses a result produced against a different lock. That proves the suite did not change between
the freeze and the run.

It does NOT prove the suite predates the implementation: an edit followed by a re-freeze and a
re-run produces a valid result. Authorship is controlled elsewhere -- the implementer cannot write
the frozen suite and the verifier cannot read the implementation (opencode.json edit/read
permissions), which is the separation of duties a required-reviewer rule provides in a hosted
repository (configuration management: DO-178C 7, ISO 26262-8 7, IEC 62304 8). The suite stays
writable; the lock is what is controlled.

Phases: --phase red (before implementation; proves the tests CAN fail) | green (after).
Exit: 0 ok | 1 failed | 2 BLOCKED/UNVERIFIABLE (stack down, config missing, no freeze lock) |
3 unverifiable (verify only: result says the stack was unreachable) | 4 not applicable
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


stl = _mod("stl_for_harness", "system_test_lint.py")
pl = _mod("pl_for_harness", os.path.join("..", "plan", "plan_lint.py"))


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return stl.sha256_file(path)


def paths(plan, phase=None):
    stem = re.sub(r"\.md$", "", plan)
    p = {"lock": stem + ".system-tests.lock.json"}
    if phase:
        p.update(result="%s.system-tests.%s.result.json" % (stem, phase),
                 junit="%s.system-tests.%s.junit.xml" % (stem, phase),
                 log="%s.system-tests.%s.log" % (stem, phase))
    return p


def git(root, *args):
    try:
        r = subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_rc(root, *args, env=None):
    """git with the exit code kept.

    `git()` above collapses every failure to None, which is right for a best-effort read and wrong
    for a control decision: a non-zero exit with empty stdout is a diagnostic on stderr, never a
    clean result (git-runner rule).
    """
    try:
        r = subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True,
                           timeout=120, env=env)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def code_state(root, policy):
    """Content identity of the working tree -- the tree hash git would record.

    Why not `HEAD + git diff HEAD + untracked files`: that identifies the tree by its
    REPRESENTATION, so committing an unchanged tree changes the identity and voids evidence that
    is still valid. Measured: after commit 33a98f6c of an unchanged tree, g17 reported "code
    changed since the green run". The identity is a content hash.

    The index is a throwaway one: the real index and the working tree are not touched, and the
    frozen suite is excluded because the lock already binds it byte for byte.
    """
    tmp = tempfile.mkdtemp(prefix="code-state-")
    try:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        rc, _, _ = git_rc(root, "read-tree", "HEAD", env=env)
        if rc != 0:
            return None
        rc, _, _ = git_rc(root, "add", "-A", "--", ".", env=env)
        if rc != 0:
            return None
        for path in (policy.get("test_dir", ""), ".planning"):
            if path:
                git_rc(root, "rm", "-r", "-f", "--cached", "-q", "--ignore-unmatch", "--",
                       path, env=env)
        rc, out, _ = git_rc(root, "write-tree", env=env)
        return out.strip() if rc == 0 else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def tracked_files(root, policy):
    out = {}
    for p in stl.test_files(root, policy):
        out[os.path.relpath(p, root).replace("\\", "/")] = sha(p)
    mp = os.path.join(root, policy["data_manifest"])
    if os.path.isfile(mp):
        out[policy["data_manifest"]] = sha(mp)
    return out


def required(plan):
    acs, keys = stl.plan_acs(plan)
    return {a: v for a, v in acs.items() if v[0] in stl.REAL_TAGS}, keys


def plan_digest(plan):
    return pl.approval_digest(open(plan, encoding="utf-8-sig").read())


def lint_clean(root, plan):
    matrix = re.sub(r"\.md$", "", plan) + ".SYSTEM-MATRIX.md"
    rows, tests, policy = stl.run_lint(root, plan, matrix if os.path.isfile(matrix) else None)
    errs = [r for r in rows if r["severity"] == "ERROR"]
    if not os.path.isfile(matrix) and required(plan)[0]:
        errs.append({"rule": "ST08", "where": matrix, "message":
                     "no scenario matrix; run framework/testing/scenario_matrix.py --plan"})
    return errs, tests, policy


def cmd_freeze(a):
    errs, tests, policy = lint_clean(a.root, a.plan)
    if errs:
        for e in errs:
            print("[harness] ERROR %s %s: %s" % (e["rule"], e["where"], e["message"]))
        print("[harness] cannot freeze: fix the lint errors above")
        return 1
    files = tracked_files(a.root, policy)
    lock = {"frozen_at": now(), "plan_digest": plan_digest(a.plan), "files": files,
            "tests": len(tests)}
    json.dump(lock, open(paths(a.plan)["lock"], "w"), indent=1)
    print("[harness] frozen %d test(s) in %d file(s)" % (len(tests), len(files)))
    return 0


def check_lock(root, plan, policy):
    lp = paths(plan)["lock"]
    if not os.path.isfile(lp):
        return "no freeze lock: run `run_system_tests.py freeze --plan` before implementation"
    lock = json.load(open(lp))
    if lock["plan_digest"] != plan_digest(plan):
        return "plan changed after the suite was frozen; re-review, re-freeze"
    now_files = tracked_files(root, policy)
    if now_files != lock["files"]:
        diff = sorted(set(now_files.items()) ^ set(lock["files"].items()))
        return "frozen suite or data changed: %s" % ", ".join(sorted({d[0] for d in diff})[:4])
    return None


PROBE_DEADLINES = (5, 15, 30)


def probe_once(url, timeout):
    """-> (verdict, reason) with verdict in ok | transient | fatal.

    The distinction is the point: a refused connection or a 5xx is a definitive answer about the
    stack and retrying it only wastes time, while a timeout on the first Windows->WSL connection
    after idle is a property of the transport. Measured on this project: the health path answers
    200 on the second attempt. Treating that as "stack unreachable" made a healthy run report
    UNVERIFIABLE, which is honest but useless -- and a check that cries wolf gets ignored.
    """
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return "ok", None
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            return "fatal", "stack answered HTTP %d at the health path" % exc.code
        return "ok", None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason):
            return "transient", str(reason)
        return "fatal", str(reason)


def probe(policy):
    st = policy.get("stack", {})
    base = os.environ.get(st.get("base_url_env", ""), "")
    if st.get("require_base_url", True):
        if not base:
            return "environment variable %s is not set (real stack base URL)" % st.get("base_url_env")
        url = base.rstrip("/") + st.get("health_path", "/")
        retried = []
        for deadline in PROBE_DEADLINES:
            verdict, why = probe_once(url, deadline)
            if verdict == "ok":
                if retried:
                    print("[harness] NOTE the stack answered only after %d retry(ies) (%s); the "
                          "first connection after idle can time out" % (len(retried),
                                                                       "; ".join(retried)))
                break
            if verdict == "fatal":
                return "stack unreachable at %s: %s" % (base, why)
            retried.append("%ds: %s" % (deadline, why))
        else:
            return "stack unreachable at %s after %d attempts: %s" % (
                base, len(PROBE_DEADLINES), "; ".join(retried))
    if st.get("require_db") and not os.environ.get(st.get("db_url_env", "")):
        return "environment variable %s is not set (real database)" % st.get("db_url_env")
    return None


def junit_results(path):
    res, tot = {}, {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for tc in ET.parse(path).getroot().iter("testcase"):
        name = tc.get("name", "")
        st = "pass"
        if tc.find("failure") is not None:
            st = "fail"
        elif tc.find("error") is not None:
            st = "error"
        elif tc.find("skipped") is not None:
            st = "skipped"
        res[name] = st
        tot["tests"] += 1
        tot["failures"] += st == "fail"
        tot["errors"] += st == "error"
        tot["skipped"] += st == "skipped"
    return res, tot


def write_result(plan, phase, data):
    json.dump(data, open(paths(plan, phase)["result"], "w"), indent=1)


def cmd_run(a):
    root, plan, phase = a.root, a.plan, a.phase
    errs, tests, policy = lint_clean(root, plan)
    need, keys = required(plan)
    bad = check_lock(root, plan, policy)
    if bad:
        print("[harness] FAIL %s" % bad)
        return 1
    if errs:
        for e in errs:
            print("[harness] ERROR %s %s: %s" % (e["rule"], e["where"], e["message"]))
        return 1
    why = probe(policy)
    p = paths(plan, phase)
    if why:
        write_result(plan, phase, {"phase": phase, "exit": 2, "reason": why, "finished_at": now()})
        print("[harness] BLOCKED (unverifiable) %s" % why)
        return 2
    log_parts, results, totals = [], {}, {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    junit_all = []
    for i, r in enumerate(policy["runners"]):
        junit = p["junit"] if len(policy["runners"]) == 1 else p["junit"].replace(
            ".junit.xml", ".%d.junit.xml" % i)
        junit_all.append(junit)
        cmd = [c.replace("{test_dir}", policy["test_dir"]).replace("{junit}", junit)
               for c in r["cmd"]]
        env = dict(os.environ)
        env.update({k: v.replace("{junit}", os.path.abspath(junit)) for k, v in r.get("env", {}).items()})
        t0 = time.time()
        try:
            cp = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                                timeout=r.get("timeout_s", 900))
            log_parts.append("$ %s\n%s\n%s\n(exit %d, %.1fs)\n" % (" ".join(cmd), cp.stdout,
                                                                   cp.stderr, cp.returncode,
                                                                   time.time() - t0))
        except (OSError, subprocess.SubprocessError) as exc:
            write_result(plan, phase, {"phase": phase, "exit": 2, "reason": "runner failed to "
                                       "start: %s" % exc, "finished_at": now()})
            print("[harness] BLOCKED runner failed to start: %s" % exc)
            return 2
        if not os.path.isfile(junit):
            write_result(plan, phase, {"phase": phase, "exit": 2, "reason": "runner produced no "
                                       "JUnit file", "finished_at": now()})
            print("[harness] BLOCKED runner produced no JUnit file (%s)" % junit)
            return 2
        res, tot = junit_results(junit)
        results.update(res)
        for k in totals:
            totals[k] += tot[k]
    open(p["log"], "w", encoding="utf-8").write("\n".join(log_parts))
    per_ac, problems = {}, []
    for ac in need:
        mine = [t for t in tests if ac in t.acs]
        st = {"tests": len(mine), "passed": 0, "failed": [], "not_run": []}
        for t in mine:
            key = next((n for n in results if n == t.name or t.name in n), None)
            if key is None:
                st["not_run"].append(t.name)
            elif results[key] == "pass":
                st["passed"] += 1
            else:
                st["failed"].append(t.name)
        per_ac[ac] = st
    if totals["skipped"]:
        problems.append("%d skipped test(s): skipped is not passed" % totals["skipped"])
    if totals["tests"] < policy.get("min_total_tests", 1):
        problems.append("only %d test(s) executed" % totals["tests"])
    for ac, st in per_ac.items():
        if st["not_run"]:
            problems.append("%s: tests not executed: %s" % (ac, ", ".join(st["not_run"][:3])))
    failed = totals["failures"] + totals["errors"]
    if phase == "green":
        for ac, st in per_ac.items():
            if st["failed"]:
                problems.append("%s: failing: %s" % (ac, ", ".join(st["failed"][:3])))
    ok = (not problems) if phase == "green" else True
    data = {"phase": phase, "exit": 0 if ok else 1, "finished_at": now(), "totals": totals,
            "failed_total": failed, "per_ac": per_ac, "problems": problems,
            "lock_sha256": sha(paths(plan)["lock"]), "log_sha256": sha(p["log"]),
            "junit_sha256": {j: sha(j) for j in junit_all}, "code_state": code_state(root, policy)}
    write_result(plan, phase, data)
    print("[harness] %s run: %d test(s), %d failed, %d skipped%s" % (
        phase, totals["tests"], failed, totals["skipped"], "" if ok else "; " + "; ".join(problems)))
    return 0 if ok else 1


def verify_plan(root, plan):
    """-> (exit_code, message)"""
    try:
        need, keys = required(plan)
        policy = stl.load_policy(root)
    except (OSError, ValueError, KeyError) as exc:
        return 2, "BLOCKED: %s" % exc
    if not need:
        return 4, "no real-stack criteria in this plan"
    bad = check_lock(root, plan, policy)
    if bad:
        return 1, bad
    green = paths(plan, "green")
    if not os.path.isfile(green["result"]):
        return 1, "no green system-test result: run `run_system_tests.py run --plan --phase green`"
    r = json.load(open(green["result"]))
    if r.get("exit") == 2:
        return 3, "UNVERIFIABLE: " + str(r.get("reason"))
    if r.get("exit") != 0:
        return 1, "latest green run failed: " + "; ".join(r.get("problems", []))[:300]
    if r.get("lock_sha256") != sha(paths(plan)["lock"]):
        return 1, "result was produced against a different freeze lock"
    for j, h in (r.get("junit_sha256") or {}).items():
        if not os.path.isfile(j) or sha(j) != h:
            return 1, "JUnit file missing or altered after the run: " + os.path.basename(j)
    if not os.path.isfile(green["log"]) or sha(green["log"]) != r.get("log_sha256"):
        return 1, "run log missing or altered after the run"
    cur = code_state(root, policy)
    if cur is not None and r.get("code_state") is not None and cur != r["code_state"]:
        return 1, "code changed since the green run; re-run the system tests"
    for ac in need:
        st = (r.get("per_ac") or {}).get(ac)
        if not st or st["tests"] == 0 or st["passed"] != st["tests"]:
            return 1, "%s has no fully passing system tests in the result" % ac
    red = paths(plan, "red")["result"]
    exempt = keys.get("system_tests_red_exempt", {}).get("scalar", "")
    if exempt.strip():
        # Not a self-granted waiver: the exemption lives in the plan, plan_lint gates the plan's
        # approval, and the freeze lock binds the plan digest -- so adding or editing it after the
        # freeze is refused by check_lock.
        return 0, "pass (red-first exempt: %s)" % exempt[:60]
    if not os.path.isfile(red):
        return 1, "no red-phase result: run the frozen suite BEFORE implementing to prove it can " \
                  "fail, or declare system_tests_red_exempt: <reason> in the plan"
    if json.load(open(red)).get("failed_total", 0) < 1:
        return 1, "red-phase run had no failing test; the suite was never shown able to fail"
    return 0, "pass: %d real-stack criterion(s), %d test(s)" % (len(need),
                                                               r["totals"]["tests"])


def cmd_verify(a):
    code, msg = verify_plan(a.root, a.plan)
    print("[harness] verify: %s" % msg)
    return code


def plans_for_ask(root, ask):
    found = []
    for base in (".planning/plans", ".planning/phases"):
        for d, _dirs, files in os.walk(os.path.join(root, base)):
            for fn in files:
                if fn.endswith(".md") and ".SYSTEM-MATRIX" not in fn:
                    p = os.path.join(d, fn)
                    try:
                        k = pl.parse_plan(open(p, encoding="utf-8-sig").read())
                    except OSError:
                        continue
                    if k.get("ask_id", {}).get("scalar", "").strip() == ask:
                        found.append(p)
    return found


def cmd_ask_gate(a):
    policy = stl.load_policy(a.root)
    plans = plans_for_ask(a.root, a.ask)
    if not plans:
        if policy.get("require_plan_for_completion"):
            print("[harness] FAIL no plan declares ask_id: %s" % a.ask)
            return 1
        print("[harness] no plan declares ask_id: %s (policy does not require one)" % a.ask)
        return 0
    worst = 0
    for p in plans:
        code, msg = verify_plan(a.root, p)
        print("[harness] %s: %s" % (os.path.basename(p), msg))
        if code in (1, 2, 3):
            worst = 1
    return worst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("freeze", "run", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--plan", required=True)
        if name == "run":
            s.add_argument("--phase", choices=("red", "green"), required=True)
    s = sub.add_parser("ask-gate")
    s.add_argument("--ask", required=True)
    a = ap.parse_args(argv)
    try:
        return {"freeze": cmd_freeze, "run": cmd_run, "verify": cmd_verify,
                "ask-gate": cmd_ask_gate}[a.cmd](a)
    except (OSError, ValueError, KeyError) as exc:
        print("[harness] BLOCKED %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
