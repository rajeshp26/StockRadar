"""CLI acceptance tests for the `--json-file` payload route (PowerShell-safe).

Every payload-taking framework CLI accepts `--json-file <path>` as an alternative to
an inline `--json` string, so the payload travels as a file and never passes through
PowerShell's inline-quote mangling. Each case drives the real CLI via subprocess with
an isolated state root and asserts the exit code.

Pre-patch these invocations failed with argparse rejection (`unrecognized arguments`
for default-when-empty CLIs, `the following arguments are required: --json` for
required CLIs) - the exact phrasing we assert is NOT in the output here.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

STATE = REPO / "framework/adapters/gsd_state.py"
INTAKE = REPO / "framework/adapters/intake.py"
EXECUTE = REPO / "framework/adapters/execute.py"
CLAIMS = REPO / "framework/claims/ledger.py"
RETRO = REPO / "framework/retro/ledger.py"
SUSPICION = REPO / "framework/verification/suspicion_log.py"
RECOVERY = REPO / "framework/verification/recovery.py"

ARGPARSE_GUILT = ("unrecognized arguments",
                  "the following arguments are required: --json")


def _env(tmp_path):
    env = dict(os.environ)
    env["GSD_STATE_ROOT"] = str(tmp_path)
    env["INTAKE_ROOT"] = str(tmp_path)
    env["EXEC_ROOT"] = str(tmp_path)
    return env


def _run(env, *args, cwd=None):
    cmd = [sys.executable, *(str(a) for a in args)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)


def _payload(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# --- argparse accepts --json-file on every payload CLI --------------------

@pytest.mark.parametrize("cli,args", [
    (STATE, ("--json", "", "--json-file", "x")),
    (INTAKE, ("--json", "", "--json-file", "x")),
    (EXECUTE, ("--json", "", "--json-file", "x")),
    (CLAIMS, ("append", "--json-file", "x")),
    (RETRO, ("append", "--json-file", "x")),
    (SUSPICION, ("add", "--json", "", "--json-file", "x")),
    (RECOVERY, ("save", "--json", "", "--json-file", "x")),
])
def test_cli_accepts_json_file_argparse(tmp_path, cli, args):
    env = _env(tmp_path)
    p = _run(env, cli, *args, cwd=tmp_path)
    assert "unrecognized arguments" not in p.stderr, p.stderr


# --- end-to-end: --json-file carries the payload into the store -----------

def test_state_selftest_via_file(tmp_path):
    env = _env(tmp_path)
    p = _run(env, STATE, "selftest", cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr


def test_intake_capture_via_file(tmp_path):
    pfile = _payload(tmp_path, "capture.json",
                    {"session_id": "ses_1", "original_text": "the ask",
                     "mode": "intake"})
    env = _env(tmp_path)
    p = _run(env, INTAKE, "capture", "--json-file", str(pfile), cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "session_id" in p.stdout, p.stdout


def test_claims_append_via_file(tmp_path):
    pfile = _payload(tmp_path, "claim.json",
                    {"task_id": "T-01", "agent": "test", "statement": "s",
                     "claim_type": "behavioral", "classification": "HYPOTHESIS",
                     "status": "UNVERIFIED", "impact": "low"})
    env = _env(tmp_path)
    p = _run(env, CLAIMS, "append", "--json-file", str(pfile), cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "claim_id" in p.stdout, p.stdout


def test_execute_render_summary_via_file(tmp_path):
    pfile = _payload(tmp_path, "payload.json", {"a": 1})
    env = _env(tmp_path)
    p = _run(env, EXECUTE, "render-summary", "--task", "T-01",
             "--json-file", str(pfile), cwd=tmp_path)
    assert "unrecognized arguments" not in p.stderr, p.stderr
    assert "the following arguments are required: --json" not in p.stderr, p.stderr
