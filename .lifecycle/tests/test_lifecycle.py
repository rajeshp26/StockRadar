"""P1-C pytest suite — exercises lifecycle-validate.py and orphan-check.py
against ok-*/bad-* fixtures under .lifecycle/fixtures/ (H9/H10)."""
import os, subprocess, pytest

PACK_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX  = os.path.join(PACK_ROOT, ".lifecycle", "fixtures")
LVC  = os.path.join(PACK_ROOT, ".lifecycle", "scripts", "lifecycle-validate.py")
OC   = os.path.join(PACK_ROOT, ".lifecycle", "scripts", "orphan-check.py")
PY   = __import__("sys").executable


def run_lvc(feature, config=None):
    args = [PY, LVC, os.path.join(FIX, feature)]
    if config:
        args += ["--config", config]
    else:
        args += ["--config", os.path.join(PACK_ROOT, ".lifecycle", "config.yml")]
    return subprocess.run(args, capture_output=True, text=True, cwd=PACK_ROOT)


def run_oc(trace_rel):
    trace = os.path.join(FIX, trace_rel)
    return subprocess.run([PY, OC, trace], capture_output=True, text=True, cwd=PACK_ROOT)


# --- ok-*: both scripts exit 0 ---

class TestOkFixtures:
    @pytest.mark.parametrize("feature", ["ok-l2", "ok-l0"])
    def test_lifecycle_passes(self, feature):
        r = run_lvc(feature)
        assert r.returncode == 0, r.stdout + r.stderr

    @pytest.mark.parametrize("trace", [
        "ok-l2/trace.yml", "ok-l0/trace.yml",
    ])
    def test_orphan_passes(self, trace):
        r = run_oc(trace)
        assert r.returncode == 0, r.stdout + r.stderr


# --- bad-*: each check fires ---

class TestBadFixtures:
    def test_trans_illegal(self):
        r = run_lvc("bad-trans-illegal")
        assert r.returncode != 0
        assert "TRANS-ILLEGAL" in r.stdout

    def test_gate_prereq(self):
        r = run_lvc("bad-gate-prereq")
        assert r.returncode != 0
        assert "GATE-PREREQ" in r.stdout

    def test_kind_missing(self):
        r = run_lvc("bad-kind-missing")
        assert r.returncode != 0
        assert "KIND" in r.stdout

    def test_sync_mismatch(self):
        cfg = os.path.join(FIX, "bad-sync-mismatch", "bad_config.yml")
        r = run_lvc("bad-sync-mismatch", config=cfg)
        assert r.returncode != 0
        assert "SYNC" in r.stdout

    def test_orphan_risk(self):
        r = run_oc("bad-orphan-risk/trace.yml")
        assert r.returncode != 0
        assert "orphan risk" in r.stdout
        line = [l for l in r.stdout.split("\n") if "orphan risk" in l][0]
        assert " 0" not in line.split("orphan risk")[1]

    def test_orphan_acceptance(self):
        r = run_oc("bad-bidirectional-ac/trace.yml")
        assert r.returncode != 0
        assert "orphan acceptance" in r.stdout
        line = [l for l in r.stdout.split("\n") if "orphan acceptance" in l][0]
        assert " 0" not in line.split("orphan acceptance")[1]

    def test_trans_chronological(self, tmp_path):
        """A transition recorded before its predecessor is a backwards timeline (§7)."""
        import json
        import shutil
        dst = tmp_path / "bad-trans-chrono"
        shutil.copytree(os.path.join(FIX, "ok-l2"), str(dst))
        sp = dst / "state.json"
        st = json.loads(sp.read_text(encoding="utf-8"))
        st["transitions"][8]["timestamp"] = "2026-08-26T09:15:00-04:00"
        sp.write_text(json.dumps(st, indent=2), encoding="utf-8")
        r = run_lvc(str(dst))
        assert r.returncode != 0
        assert "TRANS-CHRONO" in r.stdout
