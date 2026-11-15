"""End-to-end tests for the system-test enforcement chain (DID-017): lint -> matrix -> freeze ->
red -> green -> verify, against a small REAL HTTP service started in-process (no mocks)."""
import http.server
import importlib.util
import json
import os
import os
import shutil
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _wsl(path):
    r"""C:\x\y -> /mnt/c/x/y. WSL bash cannot stat a Win32 path; identity off Windows."""
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return "/mnt/%s%s" % (p[0].lower(), p[2:])
    return p


PLAN_TEXT = """status: approved
ask_id: ASK-001
files_or_components:
  - svc/total.py
acceptance_criteria:
  - AC-1 [e2e] GET /total with items returns the sum, equal to the independent sum within 0.01
  - AC-2 [data-invariant] for every account in the real snapshot the total equals the sum of its items, with no mocking
"""
TEST_PY = '''import json, os, pathlib, urllib.request
BASE = os.environ["SYSTEM_TEST_BASE_URL"]
DATA = json.load(open(pathlib.Path(__file__).parent / "data" / "accounts.json"))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

def _q(items):
    return "/total?items=" + ",".join(str(i) for i in items)

def test_total_matches_independent_sum():
    """AC-1 kind:positive data:accts shape:single_lot"""
    a = DATA["accounts"][0]
    assert abs(get(_q(a["items"]))["total"] - sum(a["items"])) < 0.01

def test_empty_items_total_zero():
    """AC-1 kind:negative"""
    assert get("/total?items=")["total"] == 0

def test_total_for_every_account():
    """AC-2 kind:positive data:accts shape:mixed_lot"""
    for a in DATA["accounts"]:
        assert abs(get(_q(a["items"]))["total"] - sum(a["items"])) < 0.01, a["name"]

def test_duplicate_items_count_twice():
    """AC-2 kind:boundary data:accts shape:mixed_lot"""
    assert get(_q([5, 5]))["total"] == 10
'''


class Svc:
    bug = True

    def __init__(self):
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if u.path == "/total":
                    raw = urllib.parse.parse_qs(u.query).get("items", [""])[0]
                    items = [float(x) for x in raw.split(",") if x]
                    total = sum(set(items)) if outer.bug else sum(items)
                    body = json.dumps({"total": total}).encode()
                else:
                    body = b"{}"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def suite_dir(root):
    """The suite directory the POLICY declares, so no test carries the layout as a literal.

    The fixture pins a non-default ``test_dir`` in its copy of the policy, so a module that
    hardcodes ``backend/tests/system`` fails here instead of quietly passing. That is the
    property the harness exists to have: the policy is the single place a project tailors the
    suite location, and ``run_system_tests.py`` / ``system_test_lint.py`` already read it.
    """
    pol = json.loads((root / "framework/testing/system_test_policy.json").read_text())
    return root / pol["test_dir"]


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    for sub in ("testing", "plan"):
        shutil.copytree(ROOT / "framework" / sub, tmp_path / "framework" / sub,
                        ignore=shutil.ignore_patterns("__pycache__", "eval", "test_*"))
    pol_path = tmp_path / "framework/testing/system_test_policy.json"
    pol = json.loads(pol_path.read_text())
    pol["runners"][0]["cmd"][0] = sys.executable
    # The test root is not a git repository and holds no approver's key, so the signed-baseline
    # control is declared off in THIS copy of the policy. The shipped policy keeps it on, and
    # test_the_shipped_policy_requires_a_signed_baseline is what holds that line.
    pol["baseline"] = {"require_signed": False}
    # A non-default layout, so the harness is proven to follow the policy rather than a
    # literal. suite_dir() reads these two values back; nothing else knows the path.
    pol["test_dir"] = "suite/system"
    pol["data_manifest"] = "suite/system/data/MANIFEST.json"
    pol_path.write_text(json.dumps(pol))
    td = suite_dir(tmp_path) / "data"
    td.mkdir(parents=True)
    (td / "accounts.json").write_text(json.dumps({"accounts": [
        {"name": "a1", "items": [1, 2, 3]}, {"name": "a2", "items": [5, 5, 10]}]}))
    import hashlib
    sha = hashlib.sha256((td / "accounts.json").read_bytes()).hexdigest()
    (td / "MANIFEST.json").write_text(json.dumps({"datasets": [{
        "id": "accts", "source": "export of the real test snapshot", "captured_at": "2026-10-10",
        "file": "accounts.json", "sha256": sha, "rows": 2, "shapes": ["single_lot", "mixed_lot"]}]}))
    (suite_dir(tmp_path) / "test_total.py").write_text(TEST_PY)
    plans = tmp_path / ".planning/plans"
    plans.mkdir(parents=True)
    (plans / "feat.md").write_text(PLAN_TEXT)
    svc = Svc()
    monkeypatch.setenv("SYSTEM_TEST_BASE_URL", svc.url)
    mods = {n: _load(tmp_path / f"framework/testing/{n}.py", f"{n}_t{id(tmp_path)}")
            for n in ("system_test_lint", "scenario_matrix", "run_system_tests")}
    yield tmp_path, svc, mods
    svc.stop()


def resolve_matrix(tmp):
    m = tmp / ".planning/plans/feat.SYSTEM-MATRIX.md"
    lines = []
    for ln in m.read_text().split("\n"):
        if ln.startswith("| M-") and ln.rstrip().endswith("| [ ] |"):
            ln = ln.rstrip()[:-5] + "| NA: covered by the data-driven tests above |"
        lines.append(ln)
    m.write_text("\n".join(lines))


def prepare(tmp, mods):
    plan = str(tmp / ".planning/plans/feat.md")
    assert mods["scenario_matrix"].main(["--plan", plan, "--root", str(tmp)]) == 0
    resolve_matrix(tmp)
    return plan


def h(mods, tmp, *args):
    return mods["run_system_tests"].main(["--root", str(tmp)] + list(args))


def rules(mods, tmp, plan=None):
    rows, _, _ = mods["system_test_lint"].run_lint(str(tmp), plan)
    return {r["rule"] for r in rows if r["severity"] == "ERROR"}


# ------------------------------------------------------------------ lint
def test_clean_suite_passes_lint(proj):
    tmp, _svc, mods = proj
    assert rules(mods, tmp, str(tmp / ".planning/plans/feat.md")) == set()


@pytest.mark.parametrize("body,rule", [
    ("from unittest.mock import patch\n", "ST01"),
    ("import pytest\n@pytest.mark.skip\ndef test_x():\n    '''AC-1 kind:positive'''\n    assert 1 == 2\n", "ST03"),
    ("from backend.shared import thing\n", "ST02"),
    ("def test_y():\n    '''AC-1 kind:positive'''\n    assert True\n", "ST04"),
    ("def test_z():\n    '''kind:positive'''\n    assert 1 == 2\n", "ST05"),
])
def test_lint_rejects_bad_tests(proj, body, rule):
    tmp, _svc, mods = proj
    (suite_dir(tmp) / "test_bad.py").write_text(body)
    assert rule in rules(mods, tmp)


def test_lint_requires_a_break_it_test_per_criterion(proj):
    tmp, _svc, mods = proj
    p = suite_dir(tmp) / "test_total.py"
    p.write_text(p.read_text().replace("kind:negative", "kind:positive"))
    assert "ST07" in rules(mods, tmp, str(tmp / ".planning/plans/feat.md"))


def test_lint_rejects_tampered_dataset_and_unknown_data_tag(proj):
    tmp, _svc, mods = proj
    (suite_dir(tmp) / "data/accounts.json").write_text('{"accounts": []}')
    assert "ST06" in rules(mods, tmp)


def test_unresolved_matrix_fails(proj):
    tmp, _svc, mods = proj
    plan = str(tmp / ".planning/plans/feat.md")
    mods["scenario_matrix"].main(["--plan", plan, "--root", str(tmp)])
    rows, _, _ = mods["system_test_lint"].run_lint(
        str(tmp), plan, str(tmp / ".planning/plans/feat.SYSTEM-MATRIX.md"))
    assert any(r["rule"] == "ST08" for r in rows)


# ------------------------------------------------------------------ chain
def test_full_chain_red_then_green_then_verify(proj):
    tmp, svc, mods = proj
    plan = prepare(tmp, mods)
    assert h(mods, tmp, "freeze", "--plan", plan) == 0
    assert h(mods, tmp, "verify", "--plan", plan) == 1          # nothing run yet
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "red") == 0   # buggy service: fails
    red = json.loads(Path(plan.replace(".md", ".system-tests.red.result.json")).read_text())
    assert red["failed_total"] >= 1
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 1  # still buggy
    svc.bug = False
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 0
    assert h(mods, tmp, "verify", "--plan", plan) == 0
    assert h(mods, tmp, "ask-gate", "--ask", "ASK-001") == 0


def test_editing_a_frozen_test_is_refused(proj):
    tmp, svc, mods = proj
    plan = prepare(tmp, mods)
    h(mods, tmp, "freeze", "--plan", plan)
    svc.bug = False
    p = suite_dir(tmp) / "test_total.py"
    p.write_text(p.read_text().replace("< 0.01, a[\"name\"]", "< 99, a[\"name\"]"))
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 1
    assert h(mods, tmp, "verify", "--plan", plan) == 1


def test_stack_down_is_unverifiable_never_pass(proj):
    tmp, svc, mods = proj
    plan = prepare(tmp, mods)
    h(mods, tmp, "freeze", "--plan", plan)
    svc.stop()
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 2
    assert h(mods, tmp, "verify", "--plan", plan) == 3


def test_no_red_phase_blocks_verify_unless_exempt(proj):
    tmp, svc, mods = proj
    svc.bug = False
    plan = prepare(tmp, mods)
    h(mods, tmp, "freeze", "--plan", plan)
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 0
    assert h(mods, tmp, "verify", "--plan", plan) == 1
    Path(plan).write_text(PLAN_TEXT + "system_tests_red_exempt: regression suite over existing behaviour\n")
    h(mods, tmp, "freeze", "--plan", plan)
    h(mods, tmp, "run", "--plan", plan, "--phase", "green")
    assert h(mods, tmp, "verify", "--plan", plan) == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git needed for the staleness check")
def test_code_change_after_green_run_makes_result_stale(proj):
    tmp, svc, mods = proj
    svc.bug = False
    (tmp / "svc").mkdir()
    (tmp / "svc/total.py").write_text("x = 1\n")
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=t",
                                                "commit", "-qm", "init"]):
        subprocess.run(["git"] + c, cwd=tmp, check=True, capture_output=True)
    plan = prepare(tmp, mods)
    Path(plan).write_text(PLAN_TEXT + "system_tests_red_exempt: regression suite over existing behaviour\n")
    h(mods, tmp, "freeze", "--plan", plan)
    h(mods, tmp, "run", "--plan", plan, "--phase", "green")
    assert h(mods, tmp, "verify", "--plan", plan) == 0
    (tmp / "svc/total.py").write_text("x = 2\n")
    assert h(mods, tmp, "verify", "--plan", plan) == 1


# ------------------------------------------------------- the freeze is an approval (patch 04)
def test_the_shipped_policy_requires_a_signed_baseline():
    """Where it counts, the control is ON.

    A freeze lock alone proves the suite did not change after it was frozen; it cannot prove the
    freeze happened before the implementation. Only the signature does that, so a policy that
    turns it off is the bypass, and this asserts the shipped one does not.
    """
    pol = json.loads((ROOT / "framework/testing/system_test_policy.json").read_text(
        encoding="utf-8-sig"))
    assert (pol.get("baseline") or {}).get("require_signed") is True


@pytest.mark.skipif(shutil.which("git") is None, reason="git needed for the signed-baseline check")
def test_freeze_refuses_an_unsigned_baseline(proj):
    tmp, svc, mods = proj
    pol_path = tmp / "framework/testing/system_test_policy.json"
    pol = json.loads(pol_path.read_text())
    pol["baseline"] = {"require_signed": True}
    pol_path.write_text(json.dumps(pol))
    (tmp / "svc").mkdir()
    (tmp / "svc/total.py").write_text("x = 1\n")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git"] + c, cwd=tmp, check=True, capture_output=True)
    plan = prepare(tmp, mods)
    # HEAD is a real commit and the suite is committed, but nobody signed it, so there is no
    # approver: the freeze is refused rather than recorded as if it were one.
    assert h(mods, tmp, "freeze", "--plan", plan) == 2


# ------------------------------------------------------------------ ASK completion guard
def test_ask_cannot_complete_without_harness_evidence(proj, monkeypatch):
    tmp, svc, mods = proj
    shutil.copytree(ROOT / "framework" / "adapters", tmp / "framework" / "adapters",
                    ignore=shutil.ignore_patterns("__pycache__", "test_*"))
    # gsd_state.py imports `from framework import locate`, and locate.py anchors the app
    # root on its own package, so the sandbox needs both. No framework.config.json is
    # copied: locate then falls back to the framework's parent, i.e. this tmp root.
    for rel in ("__init__.py", "locate.py"):
        shutil.copy2(ROOT / "framework" / rel, tmp / "framework" / rel)
    monkeypatch.chdir(tmp)

    def intake(*a):
        return subprocess.run([sys.executable, "framework/adapters/intake.py", *a], cwd=tmp,
                              capture_output=True, text=True)

    def new_ask():
        cap = intake("capture", "--json", json.dumps({"session_id": "s", "original_text": "t"}))
        assert cap.returncode == 0, cap.stderr
        aid = json.loads(cap.stdout)["ask_id"]
        for st in ("CONFIRMED", "PLANNED", "EXECUTING"):
            assert intake("transition", "--id", aid, "--json",
                          json.dumps({"status": st})).returncode == 0
        return aid

    ask = new_ask()
    plan = prepare(tmp, mods)
    Path(plan).write_text(PLAN_TEXT.replace("ASK-001", ask))
    h(mods, tmp, "freeze", "--plan", plan)
    blocked = intake("transition", "--id", ask, "--json", json.dumps({"status": "COMPLETED"}))
    assert blocked.returncode != 0 and "COMPLETION_BLOCKED" in (blocked.stdout + blocked.stderr)
    h(mods, tmp, "run", "--plan", plan, "--phase", "red")
    svc.bug = False
    assert h(mods, tmp, "run", "--plan", plan, "--phase", "green") == 0
    done = intake("transition", "--id", ask, "--json", json.dumps({"status": "COMPLETED"}))
    assert done.returncode == 0, done.stdout + done.stderr
    # an ask that no plan declares is not blocked (policy.require_plan_for_completion is false)
    other = new_ask()
    assert intake("transition", "--id", other, "--json",
                  json.dumps({"status": "COMPLETED"})).returncode == 0


def test_g17_gate_exit_codes(proj):
    if not (shutil.which("bash") and shutil.which("python3")):
        pytest.skip("needs bash and python3")
    tmp, svc, mods = proj
    shutil.copytree(ROOT / "framework" / "gates", tmp / "framework" / "gates",
                    ignore=shutil.ignore_patterns("__pycache__", "test_*"))
    shutil.copytree(ROOT / "framework" / "adapters", tmp / "framework" / "adapters",
                    ignore=shutil.ignore_patterns("__pycache__", "test_*"))
    plan = prepare(tmp, mods)

    def gate(**env):
        env = {k: (_wsl(v) if k in ("SYSTEM_PLAN", "SYSTEM_TASK") else v)
               for k, v in env.items()}
        e = dict(os.environ, **env)
        # WSL interop forwards ONLY the variables NAMED in WSLENV (see
        # framework/gates/test_regex_conformance.py), and cannot stat a Win32 plan
        # path; without both SYSTEM_PLAN is dropped or unreadable at the Win32->WSL
        # boundary and the gate reports NOT_APPLICABLE. Inert on POSIX, where
        # variables are inherited natively.
        e["WSLENV"] = ":".join(filter(None, [e.get("WSLENV"), *env]))
        return subprocess.run(["bash", "framework/gates/g17_system_tests.sh"], cwd=tmp, env=e,
                              capture_output=True, text=True).returncode
    assert gate() == 4                                   # no plan given
    assert gate(SYSTEM_PLAN=plan) == 1                   # nothing frozen or run
    Path(plan).write_text(PLAN_TEXT.replace("[e2e]", "[unit]").replace("[data-invariant]", "[unit]"))
    assert gate(SYSTEM_PLAN=plan) == 4                   # no real-stack criteria
    Path(plan).write_text(PLAN_TEXT)
    mods["run_system_tests"].main(["--root", str(tmp), "freeze", "--plan", plan])
    svc.stop()
    mods["run_system_tests"].main(["--root", str(tmp), "run", "--plan", plan, "--phase", "green"])
    assert gate(SYSTEM_PLAN=plan) == 3                   # unverifiable, never a pass


def test_http_patch_method_is_not_mistaken_for_mock_patch(proj):
    tmp, _svc, mods = proj
    body = (
        "import urllib.request\n"
        "def test_patch_method():\n"
        "    \"\"\"AC-1 kind:negative\"\"\"\n"
        "    r = urllib.request.Request('http://x', method='PATCH')\n"
        "    assert r.get_method() == 'PATCH'\n"
        "def test_client_patch():\n"
        "    \"\"\"AC-1 kind:negative\"\"\"\n"
        "    class C:\n"
        "        def patch(self, u):\n"
        "            return 200\n"
        "    assert C().patch('/x') == 200\n")
    (suite_dir(tmp) / "test_http.py").write_text(body)
    assert "ST01" not in rules(mods, tmp)
