"""Gate-level tests for the plan lint inside g_entry.sh (DID-016). Skipped without bash/python3."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("python3")),
    reason="gate tests need bash and python3 on PATH")


@pytest.fixture()
def repo(tmp_path):
    shutil.copytree(ROOT / "framework", tmp_path / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (tmp_path / ".planning").mkdir()
    return tmp_path


def _wsl(path):
    r"""C:\x\y -> /mnt/c/x/y. WSL bash cannot stat a Win32 path; identity off Windows."""
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return "/mnt/%s%s" % (p[0].lower(), p[2:])
    return p


def run(repo, plan, env=None):
    import os
    extra = env or {}
    e = dict(os.environ, ENTRY_PLAN=_wsl(plan))
    e.update(extra)
    # WSL interop forwards ONLY the variables NAMED in WSLENV across the Win32->WSL
    # boundary (measured, see framework/gates/test_regex_conformance.py), and cannot
    # stat a Win32 plan path. Without both the gate sees no plan context. Inert on
    # POSIX, where variables are inherited natively.
    e["WSLENV"] = ":".join(filter(None, [e.get("WSLENV"), "ENTRY_PLAN", "ENTRY_TASK", *extra]))
    return subprocess.run(["bash", "framework/gates/g_entry.sh"], cwd=repo, env=e,
                          capture_output=True, text=True)


def good(repo):
    p = repo / "good.md"
    p.write_text((repo / "framework/plan/eval/cases/good_full.md").read_text(encoding="utf-8"),
                 encoding="utf-8")
    return p


def weak(repo):
    p = repo / "weak.md"
    p.write_text("status: approved\nfiles_or_components:\n  - framework/gates/g_entry.sh\n"
                 "acceptance_criteria:\n  - it works correctly\n", encoding="utf-8")
    return p


def set_mode(repo, mode):
    (repo / "framework/plan/lint_mode").write_text(mode + "\n", encoding="utf-8")


def test_default_is_enforce_and_good_plan_passes(repo):
    assert (repo / "framework/plan/lint_mode").read_text().strip().splitlines()[-1] == "enforce"
    assert run(repo, good(repo)).returncode == 0


def test_enforce_refuses_weak_plan(repo):
    r = run(repo, weak(repo))
    assert r.returncode == 1 and "plan lint errors" in r.stdout


def test_missing_mode_file_means_enforce(repo):
    (repo / "framework/plan/lint_mode").unlink()
    assert run(repo, weak(repo)).returncode == 1


def test_warn_mode_does_not_change_verdict(repo):
    set_mode(repo, "warn")
    r = run(repo, weak(repo))
    assert r.returncode == 0 and "WARN" in r.stdout


def test_invalid_mode_is_blocked(repo):
    set_mode(repo, "bogus")
    assert run(repo, good(repo)).returncode == 2


def test_environment_variable_cannot_downgrade(repo):
    r = run(repo, weak(repo), env={"ENTRY_PLAN_LINT": "off"})
    assert r.returncode == 1


def test_missing_lint_script_is_blocked_under_enforce(repo):
    (repo / "framework/plan/plan_lint.py").unlink()
    assert run(repo, good(repo)).returncode == 2


def test_plan_must_declare_the_ask_its_task_is_bound_to(repo):
    import json
    cap = subprocess.run(["python3", "framework/adapters/intake.py", "capture", "--json",
                          json.dumps({"session_id": "s", "original_text": "x"})],
                         cwd=repo, capture_output=True, text=True)
    ask = json.loads(cap.stdout)["ask_id"]
    (repo / ".planning/tasks").mkdir(parents=True, exist_ok=True)
    (repo / ".planning/tasks/T-1.json").write_text(json.dumps({"task_id": "T-1", "ask_id": ask}))
    p = repo / "p.md"
    base = (repo / "framework/plan/eval/cases/good_full.md").read_text(encoding="utf-8")
    p.write_text(base, encoding="utf-8")
    assert run(repo, p, env={"ENTRY_TASK": "T-1"}).returncode == 1
    p.write_text(base.replace("status: approved", "status: approved\nask_id: " + ask, 1),
                 encoding="utf-8")
    subprocess.run(["python3", "framework/plan/plan_lint.py", str(p), "--stamp"], cwd=repo,
                   capture_output=True)
    assert run(repo, p, env={"ENTRY_TASK": "T-1"}).returncode == 0
