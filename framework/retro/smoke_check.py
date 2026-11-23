#!/usr/bin/env python3
"""Phase 0a smoke check - validates retro subsystem machinery in isolation.

Runs every component with synthetic input and verifies:
  - escape_path.py accepts valid args and returns structured JSON
  - ledger.py append and analyse round-trips
  - g7_retro.sh executes
  - containment_map.yaml is parseable and consistent
  - injection_protocol.yaml is parseable
  - maturity.yaml is parseable

Named ``smoke_check`` (not ``*_test``) deliberately: it is a direct-execution
harness, not a pytest test module. Collection must never execute gates or call
``sys.exit``, which is why the body lives in ``main()`` under the
``__name__ == "__main__"`` guard.

Exit codes:
  0  all smoke checks pass
  1  one or more smoke checks fail
"""
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# Make the framework package importable when this script is executed directly
# (sys.path[0] is framework/retro, not the repo root).
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, ok, detail=""):
    if ok:
        print(f"  PASS  {name}")
    else:
        FAILS.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


def sh(cmd, timeout=60):
    # Every caller passes a fixed, shell-free command string. Split it into an
    # argv and run without a shell: same behaviour, no shell-injection surface
    # (bandit B602). A command that genuinely needs shell syntax must be rewritten
    # with an explicit interpreter, not by restoring shell=True here.
    try:
        r = subprocess.run(shlex.split(cmd), shell=False, capture_output=True,
                           text=True, timeout=timeout, cwd=str(ROOT))
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def main():
    # 1. containment_map.yaml
    print("\n[1] containment_map.yaml")
    try:
        import yaml
        cm = yaml.safe_load((HERE / "containment_map.yaml").read_text())
        check("parseable", True)
        check("checkpoints is a list", isinstance(cm.get("checkpoints"), list))
        check("fix_targets is a dict", isinstance(cm.get("fix_targets"), dict))
        check("preferred_fix is a dict", isinstance(cm.get("preferred_fix"), dict))
        check("none_human_judgement exists",
              "none_human_judgement" in cm.get("fix_targets", {}))
    except ImportError:
        check("parseable", False, "pyyaml not installed")
    except Exception as e:
        check("parseable", False, str(e)[:100])

    # 2. escape_path.py
    print("\n[2] escape_path.py")
    rc, out = sh("python3 framework/retro/escape_path.py "
                 "--injected implementation --caught production "
                 "--defect-class logic_error --complexity L2")
    check("accepts valid input", rc in (0, 4), f"exit={rc}")
    try:
        data = json.loads(out)
        check("returns JSON", True)
        check("has primary_gap field", "primary_gap" in data)
        check("has escaped field", "escaped" in data)
        check("has candidate_fix_targets", "candidate_fix_targets" in data)
    except Exception as e:
        check("returns valid JSON", False, str(e)[:100])

    # Bad input
    rc2, _ = sh("python3 framework/retro/escape_path.py "
                "--injected bogus --caught production --defect-class logic_error")
    check("rejects invalid phase", rc2 == 1, f"exit={rc2}")

    # 3. ledger.py (retro)
    print("\n[3] ledger.py")
    from framework.retro import ledger as L

    with tempfile.TemporaryDirectory() as tmp:
        orig = L._state_root
        L._state_root = lambda: Path(tmp)

        entry = {
            "task_id": "smoke-01",
            "injected_at": "implementation",
            "caught_at": "production",
            "defect_class": "logic_error",
            "primary_gap": "containment_miss",
            "routing_gaps": [],
            "containment_misses": ["gate_g4"],
            "fix_target": "gate_check",
            "fix_landed": True,
            "fix_verified_by": "echo test (exit 0)",
        }
        try:
            path = L.append(entry)
            check("append succeeds", Path(path).exists())
            ledger_file = Path(tmp) / "retro" / "ledger.jsonl"
            check("entry written", ledger_file.exists())
            lines = ledger_file.read_text().strip().splitlines()
            check("exactly one entry", len(lines) == 1)
            parsed = json.loads(lines[0])
            check("task_id preserved", parsed.get("task_id") == "smoke-01")
            check("signature computed", "signature" in parsed)
        except Exception as e:
            check("append round-trip", False, str(e)[:100])

        try:
            result = L.analyse()
            check("analyse runs", result.get("status") in ("ok", "empty"))
            check("entries count", result.get("entries") == 1)
        except Exception as e:
            check("analyse runs", False, str(e)[:100])

        try:
            a = {"injected_at": "implementation", "defect_class": "logic_error",
                 "primary_gap": "containment_miss", "containment_misses": ["gate_g4"],
                 "routing_gaps": [], "task_id": "A", "rationale": "off by one"}
            b = {"injected_at": "implementation", "defect_class": "logic_error",
                 "primary_gap": "containment_miss", "containment_misses": ["gate_g4"],
                 "routing_gaps": [], "task_id": "B", "rationale": "boundary error"}
            check("signature collision on reworded duplicates",
                  L.signature(a) == L.signature(b))
        except Exception as e:
            check("signature collision", False, str(e)[:100])

        L._state_root = orig

    # 4. g7_retro.sh
    print("\n[4] g7_retro.sh")
    g7 = ROOT / "framework" / "gates" / "g7_retro.sh"
    check("g7 exists", g7.exists())
    if g7.exists():
        rc, out = sh("bash framework/gates/g7_retro.sh")
        check("g7 executes", rc in (0, 1, 2, 4), f"exit={rc}")

    # 5. injection_protocol.yaml
    print("\n[5] injection_protocol.yaml")
    ip = HERE / "injection_protocol.yaml"
    check("file exists", ip.exists())
    if ip.exists():
        try:
            proto = yaml.safe_load(ip.read_text())
            check("parseable", True)
            check("has challenges", isinstance(proto.get("challenges"), list))
            check("has scoring", isinstance(proto.get("scoring"), dict))
            check("has rules", isinstance(proto.get("rules"), list))
            for ch in proto.get("challenges", []):
                check(f"  {ch['id']} has evidence_required",
                      "evidence_required" in ch)
                check(f"  {ch['id']} has failure_if", "failure_if" in ch)
        except Exception as e:
            check("parseable", False, str(e)[:100])

    # 6. maturity.yaml
    print("\n[6] maturity.yaml")
    mat = HERE / "maturity.yaml"
    check("file exists", mat.exists())
    if mat.exists():
        try:
            mdata = yaml.safe_load(mat.read_text())
            check("parseable", True)
            check("has levels", isinstance(mdata.get("levels"), dict))
            check("has advancement rules", isinstance(mdata.get("advancement"), dict))
            for lvl_name, lvl in mdata.get("levels", {}).items():
                check(f"  {lvl_name} has exit_criteria",
                      isinstance(lvl.get("exit_criteria"), list)
                      and len(lvl["exit_criteria"]) > 0)
        except Exception as e:
            check("parseable", False, str(e)[:100])

    # 7. escape_path destination classification
    print("\n[7] escape_path destination routing")
    from framework.retro import escape_path as EP
    d1 = EP.destination(["gate_routing"], "implementation")
    check("gate_routing -> executable_check",
          d1.get("tier") == "executable_check")
    d2 = EP.destination(["skill_rule"], "implementation")
    check("skill_rule -> declared_rule", d2.get("tier") == "declared_rule")
    d3 = EP.destination(["agent_instruction"], "architecture")
    check("agent_instruction from architecture -> design_checklist",
          d3.get("tier") == "design_checklist")
    d4 = EP.destination(["agent_instruction"], "implementation")
    check("agent_instruction from implementation -> agent_instruction",
          d4.get("tier") == "agent_instruction")

    # Summary
    print("\n" + "=" * 50)
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())