#!/usr/bin/env python3
"""Verification matrix -- the artifact that carries a decision from plan to verdict.

WHY THIS EXISTS
===============
The framework had five components in the decision chain and no artifact between them:

    impact analysis   -> impact class        (written only into a post-hoc handoff)
    acceptance criteria -> AC-n [tag]        (minted by plan_lint, then dropped)
    skill routing     -> prose condition     (read by skill_coverage, not by gates)
    gate routing      -> gate ids            (profiles.yaml, executed by nothing)
    evidence          -> claim ids, exit codes

``AC-n`` is the join key that already existed and was never propagated. This module gives it
a durable row, derives the row's method/gates/skills from ``evidence_classes.yaml``, records
gate results against it, and refuses completion while any row is not pass or human-waived.

WHAT THIS DOES NOT PROVE
========================
``check`` proves a fresh, bound artifact exists for every criterion. It does not prove the
artifact is good (review), that the impact scope is correct (the matrix makes the claim
visible, not true), or that the test is independent (g17's freeze/hash checks).

Usage:
  matrix.py emit   --plan PLAN.md [--root DIR] [--out PATH] [--json]
  matrix.py record --matrix M --ac AC-1 --gate g17 --exit 0 [--artifact F] [--stack-reached]
  matrix.py waive  --matrix M --ac AC-1 --by NAME --reason TEXT
  matrix.py check  --matrix M [--plan PLAN.md] [--strict] [--json]
  matrix.py show   --matrix M [--json]
  matrix.py self-test
Exit: 0 ok | 1 fail | 2 BLOCKED | 3 UNVERIFIABLE (drift) | 4 NOT_APPLICABLE
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_FRAMEWORK = os.path.dirname(_HERE)
if _FRAMEWORK not in sys.path:
    sys.path.insert(0, _FRAMEWORK)

import evidence  # noqa: E402  (sibling module, resolved by the path insert above)
import route as routing  # noqa: E402

SCHEMA = "verification-matrix/1"
MATRIX_SUFFIX = ".matrix.json"
PASS, FAIL, BLOCKED, UNVERIFIABLE, NOT_APPLICABLE = 0, 1, 2, 3, 4


class MatrixError(Exception):
    """The matrix is unreadable or structurally wrong. Never a silent empty result."""


def _now():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_root(root="."):
    try:
        import locate  # framework/locate.py, already on sys.path
        return str(locate.state_root())
    except Exception:  # pragma: no cover - locate is stdlib-only and present
        return os.path.join(root, ".planning")


def matrix_path_for(plan_path):
    """Convention: the matrix sits next to its plan, named after it."""
    base = os.path.splitext(plan_path)[0]
    return base + MATRIX_SUFFIX


def pointer_path(root=".", state_root=None):
    """The pointer to the matrix that governs the current task.

    ``state_root`` exists so a fixture can write a pointer into its own temp tree. Without it
    the pointer is always the LIVE one (locate reads the cwd, not ``root``), and a validation
    fixture would repoint the real task's closure gate at a throwaway matrix.
    """
    if state_root:
        return os.path.join(state_root, "verification", "current.json")
    return os.path.join(_state_root(root), "verification", "current.json")


def _read_plan(plan_path):
    with open(plan_path, encoding="utf-8-sig") as fh:
        return fh.read()


def load_matrix(path):
    if not os.path.isfile(path):
        raise MatrixError("matrix not found: %s" % path)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise MatrixError("matrix unreadable: %s" % exc) from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise MatrixError("matrix schema is not %s" % SCHEMA)
    if not isinstance(data.get("rows"), list):
        raise MatrixError("matrix has no rows list")
    return data


def _write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- gate records
# A gate writes <state_root>/verification/gates/<gate>.json when it judges (framework/gates/
# gate_record.py). `record --from-gate` reads it, so the gate identity, the exit code and the
# artifact hashes come from the instrument rather than from the caller's flag. Before this,
# `record --gate g6` let a caller file an artifact of the wrong shape under a routed gate.
GATE_RECORD_SCHEMA = "gate-result/1"
GATE_VERDICTS = ("pass", "fail", "unverifiable", "not_applicable", "precondition_missing",
                 "capability_missing", "not_reached")
GATE_RESULT_EXIT = {"pass": 0, "fail": 1, "unverifiable": 3, "not_applicable": 4,
                    "precondition_missing": 2, "capability_missing": 3}


def _rel(path):
    """Repo-relative when the path is inside the tree, POSIX-shaped either way.

    A record must be readable from both sides of the WSL/Windows boundary. Storing the absolute
    WSL path (/mnt/c/...) means a Windows interpreter cannot find the file it names, and the
    integrity check then reports "the file is gone" for a file that is right there.
    """
    norm = str(path).replace("\\", "/")
    try:
        rel = os.path.relpath(str(path)).replace("\\", "/")
    except ValueError:      # different drive on Windows
        return norm
    return norm if rel.startswith("../") else rel


def _gate_record_path(value, root="."):
    """Resolve --from-gate: an explicit file, or a gate id under the state root."""
    if os.path.isfile(value):
        return value
    candidate = os.path.join(_state_root(root), "verification", "gates", "%s.json" % value)
    return candidate if os.path.isfile(candidate) else None


def _read_gate_record(value, root="."):
    """Load the gate's own record. Returns (record, error_message)."""
    path = _gate_record_path(value, root)
    if path is None:
        return None, ("FAIL no gate record for %r: the gate has not judged. It writes "
                      "<state_root>/verification/gates/<gate>.json when it does" % value)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            rec = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, "BLOCKED gate record unreadable: %s (%s)" % (path, exc)
    if not isinstance(rec, dict) or rec.get("schema") != GATE_RECORD_SCHEMA:
        return None, ("FAIL %s is not a gate-result record (schema != %s)"
                      % (path, GATE_RECORD_SCHEMA))
    if not str(rec.get("gate") or "").strip():
        return None, "FAIL gate record %s names no gate" % path
    rec["_path"] = path.replace("\\", "/")
    return rec, None


def _bound_artifact(rec):
    """First artifact the gate hashed, verified against the file on disk.

    Returns (path, problem) where problem is (kind, message) and kind is "missing" (the gate
    named a file that was not there), "gone" (deleted since) or "changed" (edited since).
    """
    for entry in rec.get("artifacts") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        want = entry.get("sha256")
        if not path:
            continue
        if want is None:
            return None, ("missing", "FAIL the gate record names an artifact that did not exist "
                                     "when the gate judged: %s" % path)
        if not os.path.isfile(path):
            return None, ("gone", "UNVERIFIABLE the gate's artifact is gone: %s" % path)
        actual = _sha256(path)
        if actual != str(want):
            return None, ("changed", "FAIL the artifact changed after the gate recorded it: %s "
                                     "(recorded %s, now %s)"
                          % (path, str(want)[:12], actual[:12]))
        return path, None
    return None, None


def _artifact_problem(ev):
    """A bound artifact must still be the bytes that were hashed.

    Without this a record proves only that a file once existed; the file could be edited to say
    anything after the verdict, and every reader downstream would still see a pass.
    """
    path, want = ev.get("artifact"), ev.get("artifact_sha256")
    if not path or not want:
        return None
    if not os.path.isfile(path):
        return "the file is gone (%s)" % path
    if _sha256(path) != str(want):
        return "the file changed after it was recorded (%s)" % path
    return None



def _gate_evidence(row):
    """gate id -> its evidence dict.

    ``gate_evidence`` is the authoritative store: one entry per gate that actually ran. The
    single ``evidence`` field is the pre-existing shape and is still written (last gate wins) so
    older matrices and readers keep working; it is never the basis for a verdict when
    ``gate_evidence`` is present.

    WHY ONE ENTRY PER GATE
    ======================
    ``browser`` routes ``[g6, g17]`` on purpose: g6 proves the visible behaviour, g17 proves the
    stack was real. A single ``evidence`` slot let an artifact recorded against g6 alone mark the
    row ``pass``, so the pairing existed in ``evidence_classes.yaml`` and evaporated at the row --
    a mocked browser run could close a criterion that claims real data.
    """
    ge = row.get("gate_evidence")
    if isinstance(ge, dict):
        return {str(k): v for k, v in ge.items() if isinstance(v, dict)}
    ev = row.get("evidence") or {}
    return {str(ev["gate"]): ev} if ev.get("gate") else {}


def _row_status(row):
    """A row passes only when EVERY routed gate has recorded a green result.

    Missing is ``pending``, never ``pass``: a criterion routed to two gates and proven by one is
    half-verified, and half-verified is not verified (AGENTS.md > Evidence).
    """
    if row.get("waiver"):
        return "waived"
    gates = [str(g) for g in (row.get("gates") or [])]
    if not gates:
        # A `manual` class routes no gate: no evidence can close it, only a waiver can.
        return row.get("status") if row.get("status") in ("fail", "unverifiable") else "pending"
    ge = _gate_evidence(row)
    codes = [None if g not in ge else int(ge[g].get("exit_code", 0)) for g in gates]
    if any(c is None for c in codes):
        recorded = [c for c in codes if c is not None]
        if any(c not in (0,) for c in recorded):
            return "unverifiable" if 3 in recorded else "fail"
        return "pending"
    if all(c == 0 for c in codes):
        if row.get("real_stack"):
            for g in gates:
                ev = ge[g]
                if not ev.get("stack_reached") or not ev.get("artifact_sha256"):
                    return "unverifiable"
        return "pass"
    return "unverifiable" if 3 in codes else "fail"


# ---------------------------------------------------------------- emit
def emit(plan_path, root=".", out=None, state_root=None):
    """Build the matrix from a plan. Returns (exit_code, report)."""
    if not os.path.isfile(plan_path):
        return BLOCKED, "BLOCKED plan not readable: %s" % plan_path
    try:
        text = _read_plan(plan_path)
        table = evidence.load_table(root)
        profiles = routing.load_profiles(root)
    except (OSError, evidence.TableError, routing.RouteError) as exc:
        return BLOCKED, "BLOCKED %s" % exc

    criteria, inline = evidence.parse_criteria(text)
    if not criteria:
        return NOT_APPLICABLE, "NOT_APPLICABLE plan has no acceptance_criteria"
    rows, errors = evidence.derive_rows(criteria, table)
    if errors:
        return FAIL, "FAIL cannot derive a verification row:\n  " + "\n  ".join(errors)

    files = evidence.collect_list(text, "files_or_components")
    impact = evidence.derive_impact(text, files)
    signals = evidence.collect_list(text, "risk_signals")
    try:
        required = routing.routed_gates(impact, rows, profiles, signals)
    except routing.RouteError as exc:
        return FAIL, "FAIL %s" % exc

    unknown = routing.unknown_gates(required, root)
    if unknown:
        return FAIL, "FAIL routing names gate(s) with no implementation: %s" % "; ".join(unknown)

    matrix = {
        "schema": SCHEMA,
        "plan": plan_path.replace("\\", "/"),
        "plan_sha256": evidence.plan_digest(text),
        "emitted_at": _now(),
        "impact": impact,
        "signals": signals,
        "rows": rows,
        "required_gates": required,
        "gate_results": {},
        "notes": [],
    }
    if inline:
        matrix["notes"].append("acceptance_criteria uses the inline list form; block form "
                               "keeps a criterion intact when it contains a comma")

    target = out or matrix_path_for(plan_path)
    try:
        _write_json(target, matrix)
        _write_json(pointer_path(root, state_root), {
            "matrix": target.replace("\\", "/"),
            "plan": plan_path.replace("\\", "/"),
            "at": matrix["emitted_at"],
        })
    except OSError as exc:
        return BLOCKED, "BLOCKED cannot write matrix: %s" % exc

    lines = [
        "matrix %s" % target,
        "impact %s (%s)" % (impact["scope"], impact.get("basis", "?")),
        "rows %d  required_gates %s" % (len(rows), ", ".join(required) or "(none)"),
    ]
    for row in rows:
        lines.append("  %s [%s] -> %s %s" % (row["id"], row["tag"], row["method"],
                                             "gates=" + ",".join(row["gates"]) or "no gate"))
    return PASS, "\n".join(lines)


# ---------------------------------------------------------------- record
def record(matrix_path, ac=None, gate=None, exit_code=0, artifact=None, stack_reached=False,
           from_gate=None, root="."):
    """Bind a gate result to a criterion row (or to a task-level gate).

    ``--from-gate`` is the authoritative route: the gate's own record supplies the gate
    identity, the exit code and the artifact hashes. The caller names only the criterion.
    """
    try:
        matrix = load_matrix(matrix_path)
    except MatrixError as exc:
        return BLOCKED, "BLOCKED %s" % exc

    stamp = _now()
    gate_record = None
    if from_gate:
        # Refusing to combine with --gate/--artifact is what makes the record authoritative:
        # otherwise a caller could cite it and override the one field that decides attribution.
        if gate or artifact:
            return FAIL, ("FAIL --from-gate cannot be combined with --gate/--artifact; the gate "
                          "record supplies both, and letting a caller override them is the hole "
                          "this path exists to close")
        rec, err = _read_gate_record(from_gate, root)
        if err:
            return (BLOCKED if err.startswith("BLOCKED") else FAIL), err
        gate = str(rec.get("gate") or "").strip()
        result = str(rec.get("result") or "")
        if result not in GATE_VERDICTS:
            return FAIL, ("FAIL gate record %s has an unknown result %r"
                          % (rec["_path"], result))
        try:
            exit_code = int(rec.get("exit"))
        except (TypeError, ValueError):
            return FAIL, "FAIL gate record %s has no integer exit code" % rec["_path"]
        want = GATE_RESULT_EXIT.get(result)
        if want is not None and exit_code != want:
            return FAIL, ("FAIL gate record %s says result=%s with exit=%d; a verdict and its "
                          "exit code must agree" % (rec["_path"], result, exit_code))
        stamp = str(rec.get("at") or stamp)
        emitted = str(matrix.get("emitted_at") or "")
        if emitted and stamp < emitted:
            return FAIL, ("FAIL the gate judged at %s, before the plan was emitted at %s: the "
                          "evidence predates what it claims to verify" % (stamp, emitted))
        artifact, problem = _bound_artifact(rec)
        if problem:
            kind, message = problem
            return (UNVERIFIABLE if kind == "gone" else FAIL), message
        gate_record = {"gate_result": _rel(rec["_path"]),
                       "gate_result_sha256": _sha256(rec["_path"])}

    if ac:
        row = next((r for r in matrix["rows"] if r.get("id") == ac.upper()), None)
        if row is None:
            return FAIL, "FAIL %s is not a criterion in %s" % (ac, matrix_path)
        routed = [str(g) for g in (row.get("gates") or [])]
        if gate and routed and gate not in routed:
            # Attribution is not a free-text field. A result filed under a gate that was not
            # routed for this criterion is either the wrong artifact or the wrong gate, and
            # either way the row would carry a pass it did not earn.
            return FAIL, "FAIL %s is not a gate routed for %s (routed: %s)" % (
                gate, ac.upper(), ", ".join(routed) or "(none)")
        if from_gate and row.get("real_stack") and not artifact:
            # Real-stack evidence must be a durable artifact: the claim is about a live system,
            # and without a record of the run there is nothing a reader can re-check.
            return FAIL, ("FAIL %s is real-stack evidence; %s recorded no artifact, and a claim "
                          "without a bound artifact is not evidence" % (ac.upper(), gate))
        ev = {"gate": gate, "exit_code": int(exit_code), "at": stamp,
              "stack_reached": bool(stack_reached)}
        if gate_record:
            ev.update(gate_record)
        if artifact:
            if not os.path.isfile(artifact):
                return FAIL, "FAIL evidence artifact not found: %s" % artifact
            ev["artifact"] = artifact.replace("\\", "/")
            ev["artifact_sha256"] = _sha256(artifact)
        row.setdefault("gate_evidence", {})[str(gate or "?")] = ev
        row["evidence"] = ev
        row["status"] = _row_status(row)
        verdict = row["status"]
    else:
        if not gate:
            return FAIL, "FAIL record needs --ac <id> or --gate <id>"
        entry = {"exit_code": int(exit_code), "at": stamp,
                 "stack_reached": bool(stack_reached)}
        if gate_record:
            entry.update(gate_record)
        matrix.setdefault("gate_results", {})[gate] = entry
        verdict = "pass" if int(exit_code) == 0 else "fail"

    try:
        _write_json(matrix_path, matrix)
    except OSError as exc:
        return BLOCKED, "BLOCKED cannot write matrix: %s" % exc
    return PASS, "recorded %s %s -> %s" % (ac or gate, gate or "", verdict)


def waive(matrix_path, ac, by, reason):
    """A human waiver is the only route past a criterion no gate can prove."""
    try:
        matrix = load_matrix(matrix_path)
    except MatrixError as exc:
        return BLOCKED, "BLOCKED %s" % exc
    row = next((r for r in matrix["rows"] if r.get("id") == ac.upper()), None)
    if row is None:
        return FAIL, "FAIL %s is not a criterion in %s" % (ac, matrix_path)
    if not str(by or "").strip():
        return FAIL, "FAIL a waiver needs the identity that accepted the risk (--by)"
    if len(str(reason or "").split()) < 4:
        return FAIL, "FAIL a waiver needs a reason of at least four words (--reason)"
    row["waiver"] = {"by": str(by).strip(), "reason": str(reason).strip(), "at": _now()}
    row["status"] = "waived"
    try:
        _write_json(matrix_path, matrix)
    except OSError as exc:
        return BLOCKED, "BLOCKED cannot write matrix: %s" % exc
    return PASS, "waived %s by %s" % (ac.upper(), by)


# ---------------------------------------------------------------- check
def _policy_test_dir(root="."):
    """The system-test suite directory, taken from the policy that declares it.

    ``framework/testing/system_test_policy.json`` is the one place a project tailors the
    harness, and ``run_system_tests.py`` / ``system_test_lint.py`` both read
    ``policy["test_dir"]``. The literal that used to sit in ``_orphan_tests`` made a
    tailored policy silently ignored: the distribution ships this module with its own
    ``test_dir`` and the scan still walked StockerPro's directory. Reading the policy is
    what makes the module portable, and an absent policy is an empty scan, never a
    stale hardcoded one.
    """
    path = os.path.join(root, "framework", "testing", "system_test_policy.json")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return str(json.load(fh).get("test_dir") or "").strip().strip("/")
    except (OSError, ValueError):
        return ""


def _orphan_tests(matrix, root="."):
    """Test files that name no criterion. Warnings only: regression suites are legitimate."""
    out = []
    dirs = []
    td = _policy_test_dir(root)
    if td:
        dirs.append(td)
    try:
        import locate
        rd = locate.readiness()
        if rd.get("browser_specs"):
            dirs.append(rd["browser_specs"])
    except Exception:
        pass
    for rel in dirs:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                if not name.endswith((".py", ".ts", ".tsx", ".js")):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="ignore") as fh:
                        body = fh.read()
                except OSError:
                    continue
                if not any(r.get("id") and r["id"] in body for r in matrix.get("rows", [])):
                    out.append(os.path.relpath(path, root).replace("\\", "/"))
    return out


def required_gates_from_pointer(root=".", state_root=None):
    """(gates, source) for the matrix the pointer names, or ([], None) when there is none.

    WHY THIS EXISTS
    ===============
    A gate needs to know WHY it was routed -- `g6` runs when the task has a
    visible-behaviour requirement. That was passed as an environment variable
    (`REQUIREMENT_SHAPE`), and on a Windows host the only bash is WSL, which does not
    inherit the caller's environment: `PROBE_VAR=hello` in PowerShell is empty inside
    `bash -c`. So the documented input silently read as absent and the gate fell back to
    guessing from changed files.

    The matrix already carries the answer: `required_gates` is the union of the impact gates
    and every criterion's evidence-class gates, so `g6` being in that list IS the
    visible-behaviour decision, recorded at dispatch time. Reading it here removes the
    environment dependency and makes the artifact the carrier it was designed to be.
    """
    try:
        with open(pointer_path(root, state_root), encoding="utf-8-sig") as fh:
            matrix_path = json.load(fh).get("matrix")
    except (OSError, ValueError):
        return [], None
    if not matrix_path or not os.path.isfile(matrix_path):
        return [], None
    try:
        matrix = load_matrix(matrix_path)
    except MatrixError:
        return [], None
    return [str(g) for g in (matrix.get("required_gates") or [])], matrix_path


def check(matrix_path=None, plan_path=None, root=".", strict=False, orphans=False):
    """Judge requirement closure. Returns (exit_code, report_lines)."""
    if matrix_path is None and plan_path:
        matrix_path = matrix_path_for(plan_path)
    if matrix_path is None:
        try:
            with open(pointer_path(root), encoding="utf-8-sig") as fh:
                matrix_path = json.load(fh).get("matrix")
        except (OSError, ValueError):
            matrix_path = None
    if matrix_path is None:
        return NOT_APPLICABLE, ["NOT_APPLICABLE no matrix and no plan given"]

    if not os.path.isfile(matrix_path):
        if plan_path and os.path.isfile(plan_path):
            return FAIL, ["FAIL no verification matrix for %s; g_entry must emit one "
                          "before dispatch" % plan_path]
        # The pointer NAMED an artifact and the artifact is gone. That is a lost decision,
        # not an absence of one: reporting NOT_APPLICABLE here would let a deleted or
        # never-written matrix read as "nothing to close".
        return UNVERIFIABLE, ["UNVERIFIABLE the verification pointer names a matrix that no "
                              "longer exists: %s" % matrix_path]

    try:
        matrix = load_matrix(matrix_path)
    except MatrixError as exc:
        return BLOCKED, ["BLOCKED %s" % exc]

    if plan_path and os.path.isfile(plan_path):
        try:
            want = evidence.plan_digest(_read_plan(plan_path))
        except (OSError, evidence.TableError) as exc:
            return BLOCKED, ["BLOCKED %s" % exc]
        if matrix.get("plan_sha256") != want:
            return UNVERIFIABLE, [
                "UNVERIFIABLE matrix drifted from the plan: the plan changed after emission, "
                "so the recorded evidence no longer corresponds to it",
                "  matrix %s" % matrix_path,
                "  plan   %s" % plan_path,
            ]

    rows = matrix.get("rows") or []
    if not rows:
        return NOT_APPLICABLE, ["NOT_APPLICABLE matrix has no criteria to close"]

    problems, warnings = [], []
    for row in rows:
        rid = row.get("id") or "?"
        tag = row.get("tag") or "?"
        status = _row_status(row)
        if row.get("status") != status:
            # The evidence is the verdict. A stored status that disagrees with it (hand-edited,
            # or written by an older recorder) is not allowed to claim a pass the evidence does
            # not support.
            warnings.append("%s [%s] stored status %r disagrees with its recorded evidence (%r); "
                            "the evidence decides" % (rid, tag, row.get("status"), status))
        ev = row.get("evidence") or {}
        if status == "pass":
            gates = [str(g) for g in (row.get("gates") or [])]
            ge = _gate_evidence(row)
            missing = [g for g in gates if g not in ge]
            if missing:
                problems.append("%s [%s] marked pass but %s recorded no result; every routed "
                                "gate must run" % (rid, tag, ", ".join(missing)))
            for g in gates:
                if g in ge and int(ge[g].get("exit_code", 0)) != 0:
                    problems.append("%s [%s] marked pass but %s exited %r"
                                    % (rid, tag, g, ge[g].get("exit_code")))
            if row.get("real_stack"):
                for g in gates:
                    e = ge.get(g) or {}
                    if g in ge and not e.get("stack_reached"):
                        problems.append("%s [%s] real-stack evidence from %s did not record that "
                                        "the stack was reached" % (rid, tag, g))
                    if g in ge and not e.get("artifact_sha256"):
                        problems.append("%s [%s] real-stack evidence from %s has no artifact hash; "
                                        "a claim without a bound artifact is not evidence"
                                        % (rid, tag, g))
            elif ev.get("artifact_sha256") is None:
                warnings.append("%s [%s] pass without a bound artifact (acceptable for a "
                                "non-real-stack class; prefer --artifact)" % (rid, tag))
        elif status == "waived":
            w = row.get("waiver") or {}
            if not w.get("by"):
                problems.append("%s [%s] waived without the identity that accepted the risk"
                                % (rid, tag))
            if len(str(w.get("reason") or "").split()) < 4:
                problems.append("%s [%s] waived without a substantive reason" % (rid, tag))
        elif status == "fail":
            problems.append("%s [%s] FAILED: %s" % (rid, tag, ev.get("gate") or "gate"))
        elif status == "unverifiable":
            # Name WHY, because "unverifiable" alone sends a reader to the wrong place: an
            # absent artifact, an unreachable stack and a gate that could not run are three
            # different fixes.
            reasons = []
            ge = _gate_evidence(row)
            for g in [str(x) for x in (row.get("gates") or [])]:
                e = ge.get(g)
                if e is None:
                    continue
                code_g = int(e.get("exit_code", 0))
                if code_g == 0 and row.get("real_stack"):
                    if not e.get("stack_reached"):
                        reasons.append("%s did not record that the stack was reached" % g)
                    if not e.get("artifact_sha256"):
                        reasons.append("%s has no artifact hash; a claim without a bound "
                                       "artifact is not evidence" % g)
                elif code_g == 3:
                    reasons.append("%s could not produce evidence" % g)
            problems.append("%s [%s] UNVERIFIABLE: %s" % (
                rid, tag, "; ".join(reasons) or
                "the evidence could not be produced, and unverifiable is never a pass"))
        else:
            problems.append("%s [%s] has no evidence (status=%s)" % (rid, tag, status))

    row_gates = {g for r in rows for g in (r.get("gates") or [])}
    for gate in matrix.get("required_gates") or []:
        if gate in row_gates:
            continue
        if gate not in (matrix.get("gate_results") or {}):
            warnings.append("required gate %s has no recorded result (routed by impact, not "
                            "by a criterion)" % gate)

    # Evidence integrity: a bound artifact must still be the bytes that were hashed. This is
    # the difference between "a file once existed" and "this is the run that was judged".
    # Tracked separately because a deleted or edited artifact means the criterion cannot be
    # judged (UNVERIFIABLE), not that the product failed.
    integrity = []
    for row in rows:
        rid = row.get("id") or "?"
        for gate, ev in sorted(_gate_evidence(row).items()):
            problem = _artifact_problem(ev)
            if problem:
                integrity.append("%s [%s] evidence from %s is no longer the recorded artifact: %s"
                                 % (rid, row.get("tag") or "?", gate, problem))
    problems.extend(integrity)

    if orphans:
        for path in _orphan_tests(matrix, root):
            warnings.append("orphan test names no criterion: %s" % path)

    if strict:
        problems.extend(warnings)
        warnings = []

    lines = []
    for row in rows:
        lines.append("  %-6s [%-14s] %-11s %s" % (row.get("id"), row.get("tag"),
                                                  _row_status(row), row.get("method")))
    if warnings:
        lines.append("warnings:")
        lines.extend("  " + w for w in warnings)
    if problems:
        lines.append("problems:")
        lines.extend("  " + p for p in problems)
        lines.append("%d of %d criterion(s) not closed" % (
            len([r for r in rows if _row_status(r) not in ("pass", "waived")]), len(rows)))
        # Every problem being an artifact-integrity problem means the evidence cannot be
        # judged, which is UNVERIFIABLE -- not FAIL, which would read as a product defect.
        if integrity and len(integrity) == len(problems):
            return UNVERIFIABLE, lines
        return FAIL, lines
    lines.append("%d criterion(s) closed (pass or human-waived)" % len(rows))
    return PASS, lines


# ---------------------------------------------------------------- self-test
def _self_test(tmp):
    failures = []

    def eq(name, got, want):
        if got != want:
            failures.append("%s: got %r want %r" % (name, got, want))

    plan = os.path.join(tmp, "T-PLAN.md")
    with open(plan, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join([
            "status: approved",
            "impact: cross_component",
            "acceptance_criteria:",
            "  - AC-1 [e2e] the portfolio page renders four periods from Supabase",
            "  - AC-2 [unit] the parser returns 4 for an empty ledger",
            "  - AC-3 [browser] the chart shows the real series in a real browser",
            "files_or_components:",
            "  - web/src/app/portfolio/page.tsx",
            "  - backend/portfolio/service.py",
        ]) + "\n")

    # state_root=tmp: the pointer is written into the fixture's own tree. Without it the
    # self-test repoints the LIVE closure pointer at a temp matrix that is deleted on exit,
    # so every later `g19` would judge a file that no longer exists.
    code, out = emit(plan, root=os.getcwd(), state_root=tmp)
    eq("emit exit", code, PASS)
    matrix_path = matrix_path_for(plan)
    matrix = load_matrix(matrix_path)
    eq("row count", len(matrix["rows"]), 3)
    eq("impact", matrix["impact"]["scope"], "cross_component")
    eq("required gates include g17", "g17" in matrix["required_gates"], True)
    eq("required gates include impact breadth", "g1" in matrix["required_gates"], True)

    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("pending matrix fails", code, FAIL)

    artifact = os.path.join(tmp, "junit.xml")
    with open(artifact, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<testsuite/>\n")
    code, _ = record(matrix_path, ac="AC-1", gate="g17", exit_code=0, artifact=artifact,
                     stack_reached=True)
    eq("record real-stack pass", code, PASS)
    code, _ = record(matrix_path, ac="AC-2", gate="g4", exit_code=0, artifact=artifact)
    eq("record unit pass", code, PASS)

    # A row routed to two gates is closed by two results, never by one. `browser` routes
    # [g6, g17] because g6 proves the visible behaviour and g17 proves the stack was real;
    # an artifact filed against g6 alone used to mark the row pass, which is how a mocked
    # browser run could claim real data.
    code, _ = record(matrix_path, ac="AC-3", gate="g4", exit_code=0, artifact=artifact)
    eq("a gate not routed for the criterion is refused", code, FAIL)
    code, _ = record(matrix_path, ac="AC-3", gate="g6", exit_code=0, artifact=artifact,
                     stack_reached=True)
    eq("record browser gate", code, PASS)
    eq("one of two routed gates is still pending",
       load_matrix(matrix_path)["rows"][2]["status"], "pending")
    code, _ = record(matrix_path, ac="AC-3", gate="g17", exit_code=0, artifact=artifact,
                     stack_reached=True)
    eq("record system-test gate", code, PASS)
    eq("both routed gates close the row",
       load_matrix(matrix_path)["rows"][2]["status"], "pass")

    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("all rows closed", code, PASS)

    # Hand-editing the stored status cannot buy a pass: the evidence decides.
    tampered = load_matrix(matrix_path)
    tampered["rows"][2]["gate_evidence"].pop("g17", None)
    _write_json(matrix_path, tampered)
    code, out = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("a row whose second gate has no result cannot pass", code, FAIL)

    # Restore the missing result so the remaining checks judge what they were written for.
    code, _ = record(matrix_path, ac="AC-3", gate="g17", exit_code=0, artifact=artifact,
                     stack_reached=True)
    eq("restore second gate", code, PASS)
    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("restored matrix closes", code, PASS)

    # --- the gate writes its own record (--from-gate) -----------------------------
    # Before this, `record --gate g6` let the caller name the gate, so an artifact of the wrong
    # shape could be filed under a routed gate. These cases pin the inversion: the record is the
    # authority, and a record that contradicts itself, predates the plan, or no longer matches
    # its artifact is refused.
    import subprocess
    writer = os.path.join("framework", "gates", "gate_record.py")

    def gate_record(path, gate, result, exit_code, artifacts, at=None):
        cmd = [sys.executable, writer, "--path", path, "--gate", gate,
               "--result", result, "--exit", str(exit_code), "--at", at or _now()]
        for art in artifacts:
            cmd += ["--artifact", art]
        return subprocess.run(cmd, capture_output=True, text=True)

    g6_log = os.path.join(tmp, "g6-run.txt")
    with open(g6_log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("8 passed (45.9s)\n")
    g6_record = os.path.join(tmp, "g6.json")
    eq("gate record written", gate_record(g6_record, "g6", "pass", 0, [g6_log]).returncode, 0)

    code, _ = record(matrix_path, ac="AC-2", from_gate=g6_record, root=tmp)
    eq("a gate record for an unrouted gate is refused", code, FAIL)

    code, _ = record(matrix_path, ac="AC-3", gate="g6", from_gate=g6_record, root=tmp)
    eq("--from-gate cannot be combined with --gate", code, FAIL)

    # The instrument must not write a record that contradicts itself.
    contradictory = os.path.join(tmp, "g6-bad.json")
    eq("a pass with exit 1 is not a record",
       gate_record(contradictory, "g6", "pass", 1, [g6_log]).returncode, 1)
    eq("the contradictory record was not written", os.path.exists(contradictory), False)

    stale = os.path.join(tmp, "g6-stale.json")
    gate_record(stale, "g6", "pass", 0, [g6_log], at="2000-01-01T00:00:00Z")
    code, _ = record(matrix_path, ac="AC-3", from_gate=stale, root=tmp)
    eq("evidence older than the plan is refused", code, FAIL)

    code, _ = record(matrix_path, ac="AC-3", from_gate=g6_record, stack_reached=True, root=tmp)
    eq("a gate's own record binds", code, PASS)
    eq("the row still passes", load_matrix(matrix_path)["rows"][2]["status"], "pass")
    bound = load_matrix(matrix_path)["rows"][2]["gate_evidence"]["g6"]
    eq("the record itself is bound", bool(bound.get("gate_result_sha256")), True)

    # The artifact is what makes the record re-checkable. Editing it after the fact must not
    # leave a pass standing: "a file once existed" is not "this is the run that was judged".
    with open(g6_log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("8 failed (0.1s)\n")
    code, out = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("an edited artifact is unverifiable", code, UNVERIFIABLE)
    eq("the edit is named", any("changed after it was recorded" in line for line in out), True)
    with open(g6_log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("8 passed (45.9s)\n")
    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("restored artifact closes again", code, PASS)

    code, _ = record(matrix_path, ac="AC-1", gate="g17", exit_code=0, artifact=artifact,
                     stack_reached=False)
    eq("real-stack pass without stack is not a pass", code, PASS)
    eq("status demoted", load_matrix(matrix_path)["rows"][0]["status"], "unverifiable")

    code, _ = waive(matrix_path, "AC-1", "rajes", "supabase snapshot unavailable offline")
    eq("waive", code, PASS)
    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("waived closes", code, PASS)

    with open(plan, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("review: changed\n")
    code, _ = check(matrix_path=matrix_path, plan_path=plan, root=os.getcwd())
    eq("drift is unverifiable", code, UNVERIFIABLE)

    if failures:
        for f in failures:
            print("FAIL " + f)
        return 1
    print("matrix self-test: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="verification matrix")
    sub = ap.add_subparsers(dest="cmd")

    e = sub.add_parser("emit")
    e.add_argument("--plan", required=True)
    e.add_argument("--root", default=".")
    e.add_argument("--out")
    # Without this, emitting a matrix for ANY plan (a fixture, a what-if) repoints the live
    # closure pointer at that plan. The pointer is what `g19` judges when no plan is given, so
    # an out-of-band emit would silently re-aim the task's closure gate.
    e.add_argument("--state-root", dest="state_root")
    e.add_argument("--json", action="store_true")

    r = sub.add_parser("record")
    r.add_argument("--matrix", required=True)
    r.add_argument("--ac")
    r.add_argument("--gate")
    r.add_argument("--exit", dest="exit_code", type=int, default=0)
    r.add_argument("--artifact")
    r.add_argument("--stack-reached", action="store_true")
    # The gate's own record: gate identity, exit code and artifact hashes come from the file,
    # so the caller can only name the criterion. `--from-gate g6` resolves the canonical path.
    r.add_argument("--from-gate", dest="from_gate")
    r.add_argument("--root", default=".")

    w = sub.add_parser("waive")
    w.add_argument("--matrix", required=True)
    w.add_argument("--ac", required=True)
    w.add_argument("--by", required=True)
    w.add_argument("--reason", required=True)

    c = sub.add_parser("check")
    c.add_argument("--matrix")
    c.add_argument("--plan")
    c.add_argument("--root", default=".")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--orphans", action="store_true")
    c.add_argument("--json", action="store_true")

    s = sub.add_parser("show")
    s.add_argument("--matrix", required=True)
    s.add_argument("--json", action="store_true")

    # `required-gates` is the gate-facing reader: a gate asks "was I routed for this task?"
    # and gets the answer from the artifact instead of an environment variable.
    # `--matrix` names the artifact directly, for the same reason `g19` accepts CLOSURE_MATRIX:
    # a harness that verifies a plan out-of-band has no pointer to read, and the decision still
    # has to come from the matrix rather than from a flag saying "yes, you were routed".
    g = sub.add_parser("required-gates")
    g.add_argument("--matrix")
    g.add_argument("--root", default=".")
    g.add_argument("--state-root", dest="state_root")
    g.add_argument("--json", action="store_true")

    sub.add_parser("self-test")

    a = ap.parse_args(argv)
    if a.cmd == "emit":
        code, out = emit(a.plan, a.root, a.out, a.state_root)
    elif a.cmd == "record":
        code, out = record(a.matrix, a.ac, a.gate, a.exit_code, a.artifact, a.stack_reached,
                           a.from_gate, a.root)
    elif a.cmd == "waive":
        code, out = waive(a.matrix, a.ac, a.by, a.reason)
    elif a.cmd == "check":
        code, lines = check(a.matrix, a.plan, a.root, a.strict, a.orphans)
        out = json.dumps({"exit": code, "lines": lines}) if a.json else "\n".join(lines)
    elif a.cmd == "show":
        try:
            m = load_matrix(a.matrix)
        except MatrixError as exc:
            print("BLOCKED %s" % exc)
            return BLOCKED
        out = json.dumps(m, indent=2) if a.json else "\n".join(
            "%s [%s] %s %s" % (r["id"], r["tag"], _row_status(r), r["method"]) for r in m["rows"])
        code = PASS
    elif a.cmd == "required-gates":
        if a.matrix:
            _src = a.matrix if os.path.isfile(a.matrix) else None
            _gates = []
            if _src:
                try:
                    _gates = [str(x) for x in (load_matrix(_src).get("required_gates") or [])]
                except MatrixError:
                    _src = None
        else:
            _gates, _src = required_gates_from_pointer(a.root, a.state_root)
        if a.json:
            out = json.dumps({"required_gates": _gates, "matrix": _src})
        else:
            out = ",".join(_gates)
        code = PASS if _src else NOT_APPLICABLE
        print(out)
        return code
    elif a.cmd == "self-test":
        import tempfile
        with tempfile.TemporaryDirectory(prefix="matrix_selftest_") as tmp:
            return _self_test(tmp)
    else:
        ap.print_help()
        return BLOCKED

    print(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
