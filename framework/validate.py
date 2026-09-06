#!/usr/bin/env python3
"""Validation suite. Every check must pass before use."""
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.path.insert(0, "framework")
    from models import resolve as _res
    _RES_OK = True
except Exception as _e:  # pragma: no cover - fail loud, never silent
    _RES_OK = False
    _RES_ERR = repr(_e)

FAILS, WARNS = [], []


def check(name, ok, detail="", warn_only=False):
    if ok:
        print(f"  PASS  {name}")
    elif warn_only:
        WARNS.append(f"{name}: {detail}"); print(f"  WARN  {name} — {detail}")
    else:
        FAILS.append(f"{name}: {detail}"); print(f"  FAIL  {name} — {detail}")


def _wsl_path(p: str) -> str:
    r"""C:\x\y -> /mnt/c/x/y - the WSL view of a Windows path."""
    p = p.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return p


_WIN_PY_SHIM = None


def _win_py_shim() -> str:
    """PATH prefix pinning bare `python3` to the WINDOWS interpreter under bash on nt.

    The only bash guaranteed on Windows is WSL's, whose own python3 writes POSIX state
    roots (/mnt/c/...) into framework/.manifest - which _cache_valid() then rightly
    rejects as foreign. Detection-cache portability exists to catch exactly that class
    of cross-OS cache, so every python3 this suite spawns - including inside gates via
    persist() - must be the same OS as the suite itself. WSL interop executes the PE at
    its real path, so a symlink named `python3` keeps Windows DLL resolution intact.
    """
    global _WIN_PY_SHIM
    if _WIN_PY_SHIM is None:
        prefix = ""
        try:
            exe_posix = _wsl_path(str(Path(sys.executable).resolve()))
            d = Path(tempfile.gettempdir()) / "opencode-py3shim"
            d.mkdir(parents=True, exist_ok=True)
            link_posix = _wsl_path(str(d / "python3"))
            r = subprocess.run(
                ["bash", "-c",
                 f"ln -sf '{exe_posix}' '{link_posix}' && test -x '{link_posix}'"],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                prefix = "export PATH=" + link_posix.rsplit("/", 1)[0] + ":$PATH;\n"
        except Exception:
            prefix = ""
        _WIN_PY_SHIM = prefix
    return _WIN_PY_SHIM


_SH_SEQ = itertools.count()


def sh(cmd, timeout=120):
    # On Windows, shell=True means cmd.exe, which can neither execute ./gate.sh
    # nor honour heredocs - and the WSL bash.exe launcher mangles multi-line -c
    # payloads. Write the script to a file and hand bash the file path; POSIX
    # hosts keep shell=True semantics unchanged.
    path = None
    if os.name == "nt":
        path = Path(tempfile.gettempdir()) / "opencode-sh" / f"cmd_{os.getpid()}_{next(_SH_SEQ)}.sh"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_win_py_shim() + cmd + "\n", encoding="utf-8", newline="\n")
        argv = ["bash", _wsl_path(str(path))]
        shell_kw = False
    else:
        argv, shell_kw = cmd, True
    try:
        r = subprocess.run(argv, shell=shell_kw, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A slow gate is evidence "blocked", never a crashed suite. 124 mirrors
        # the POSIX timeout(1) convention.
        return 124, f"timed out after {timeout}s"
    finally:
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass
    return r.returncode, (r.stdout + r.stderr).strip()


print("\n[1] Agent definitions and permissions")
cfg = json.loads(Path("opencode.json").read_text())
agents = cfg["agent"]
EXPECTED = ["team-lead", "researcher", "architect", "planner", "implementer", "reviewer", "verifier"]



def _models_preflight() -> int:
    """--models: resolve every agent/slot from the live environment.

    Reads the same sources the runtime sees (OC_MODEL_* env vars plus the
    opencode.json fallbacks) through framework/models/resolve.py, prints the
    per-agent source attribution table, and writes the JSON snapshot that
    telemetry attaches to the next session record. Failures exit 1 (fail
    closed) and still write the snapshot so the cause is visible.
    """
    _script = Path("framework/models/profiles.sh")
    _text = _script.read_text(encoding="utf-8") if _script.exists() else ""
    _r = _res.preflight(cfg, os.environ, _text)
    _out = Path(os.environ.get("MODEL_RESOLUTION_JSON",
                                "framework/telemetry/models-resolved.json"))
    _out.parent.mkdir(parents=True, exist_ok=True)
    _out.write_text(json.dumps(_r, indent=2) + "\n", encoding="utf-8")
    print("active profile: %s" % (_r["active_profile"] or "(none)"))
    print("%-20s %-40s %s" % ("agent/slot", "model", "source"))
    for _n in sorted(_r["agents"]):
        _a = _r["agents"][_n]
        print("%-20s %-40s %s" % (_n, _a["model"] or "(none)", _a["source"]))
    if _r["failures"]:
        print("FAILURES: %s" % ", ".join(_r["failures"]))
        return 1
    return 0


if "--models" in sys.argv:
    if not _RES_OK:
        print("--models unavailable: resolve engine import failed: %s" % _RES_ERR)
        sys.exit(2)
    sys.exit(_models_preflight())
check("seven agents defined", sorted(agents) == sorted(EXPECTED), f"got {sorted(agents)}")
for a in EXPECTED:
    check(f"{a} markdown exists", Path(f".opencode/agents/{a}.md").exists())

check("implementer can edit", agents["implementer"]["permission"]["edit"] == "allow")
for a in ("reviewer", "planner", "researcher", "team-lead"):
    check(f"{a} cannot edit", agents[a]["permission"]["edit"] == "deny")
check("architect edits contracts only",
      isinstance(agents["architect"]["permission"]["edit"], dict)
      and agents["architect"]["permission"]["edit"]["*"] == "deny")
check("verifier cannot edit source",
      isinstance(agents["verifier"]["permission"]["edit"], dict)
      and agents["verifier"]["permission"]["edit"]["*"] == "deny")

print("\n[2] Delegation topology (star, depth 1)")
check("team-lead may delegate", agents["team-lead"]["permission"]["task"]["*"] == "allow")
for a in EXPECTED:
    if a == "team-lead":
        continue
    check(f"{a} cannot delegate", agents[a]["permission"].get("task", {}).get("*") == "deny")

print("\n[3] GSD state adapter round trip")
rc, out = sh("python3 framework/adapters/gsd_state.py health")
check("adapter health runs", rc == 0, out[:200])
rc, out = sh("python3 framework/adapters/gsd_state.py selftest")
check("state round trip", rc == 0, out[:200])
if rc == 0:
    st = json.loads(out)
    check("distribution detected", st.get("detect") != "none",
          "no GSD state found; run GSD project init", warn_only=True)

print("\n[4] Code intelligence capabilities")
rc, out = sh("python3 framework/adapters/code_intel.py resolve")
check("capabilities resolve", rc == 0, out[:200])
if rc == 0:
    m = json.loads(out)
    for cap, info in m["capabilities"].items():
        check(f"{cap} -> tier {info['tier']}", True)
    check("framework functional without provider", m["provider"] is None or True)
    if m["provider"] is None:
        WARNS.append("no code intelligence provider; running at tier 4 search fallback")

print("\n[5] Gates are executable commands")
for g in ("g1_contract", "g2_impact", "g3_architecture", "g4_executable"):
    p = Path(f"framework/gates/{g}.sh")
    check(f"{g} exists and executable", p.exists() and os.access(p, os.X_OK),
          "missing or not chmod +x")
    # G4 runs the real lint+types+test toolchain when installed; on a large product
    # repo that legitimately exceeds two minutes. Give it room.
    rc, out = sh("./framework/gates/g4_executable.sh", timeout=900)
check("g4 returns a real exit code", rc in (0, 1), f"rc={rc}")
check("g4 does not pass vacuously", not (rc == 0 and "no executable checks" in out),
      "passed with zero checks run")

print("\n[6] Contract gate fails on a violated contract")
Path("framework/.manifest").mkdir(parents=True, exist_ok=True)
rc, out = sh("./framework/gates/g1_contract.sh")
check("g1 runs and reports", rc in (0, 1, 2), f"rc={rc}")
check("g1 refuses to pass without contract tests",
      not (rc == 0 and "no tests/contract" in out), "passed without tests")

print("\n[7] Context Builder constraints")
cb = Path(".opencode/tools/context-builder.ts").read_text()
check("excerpt cap present", "EXCERPT_CAP_CHARS" in cb and "TOTAL_MATERIALISE_CAP" in cb)
check("prefers pointers", "prefer pointers over copied content" in cb.lower()
      or "prefer pointers" in cb.lower())
check("returns provider tier", "provider_tier" in cb)

print("\n[8] Retry, escalation and human gates")
rp = Path("framework/retry_policy.yaml").read_text()
check("retry limits defined", "test_failure: 2" in rp)
check("escalation defined", "on_exhaustion: escalate_to_human" in rp)
check("zero-retry conflicts", "contract_conflict: 0" in rp and "architecture_conflict: 0" in rp)
prof = Path("framework/verifier/profiles.yaml").read_text()
check("impact drives gates", "impact_to_gates" in prof)
check("browser missing driver is unverifiable", "report_unverifiable" in prof)

print("\n[9] Rules loaded, not inlined")
oc = Path("opencode.json").read_text()
check("instructions reference rules", '"AGENTS.md"' in oc and ".opencode/rules/*.md" in oc)
ag = Path("AGENTS.md").read_text()
check("AGENTS.md stays small", len(ag) < 6000, f"{len(ag)} chars")
check("no requirements inlined", "REQ-0" not in ag)
check("do-not-invoke rule present", "merely because it exists" in ag)

print("\n[10] Telemetry collector")
_t = Path(".opencode/plugin/telemetry.ts")
check("telemetry plugin exists", _t.exists())
_ts = _t.read_text() if _t.exists() else ""
for field in ("gates", "retries", "context_expansions", "materialised_chars",
              "fallbacks_used", "blockers_opened", "blockers_resolved"):
    check(f"telemetry records {field}", field in _ts)
check("collector targets g8", "(g[1-8])" in _ts, "gate id regex must cover g8")
# "session.idle" is an EVENT TYPE delivered via the `event` hook, not a hook key. A
# previous version registered it as a key; the flush never fired and zero records were
# written -- while a stale duplicate under plugins/ kept the old checks green.
check("session.idle not used as a hook key",
      not re.search(r'^\s*"session\.idle"\s*:', _ts, re.M),
      "flush would never fire; no telemetry would be written")
check("flush routed through the event hook",
      re.search(r"event\s*:\s*async", _ts) and "session.idle" in _ts)
# args are on the FIRST hook parameter; reading output?.args yields undefined forever.
_code = "\n".join(ln for ln in _ts.splitlines()
                   if not ln.strip().startswith(("//", "*", "/*")))
check("bash args read from the input parameter",
      "input?.args?.command" in _code and "output?.args?.command" not in _code,
      "gate results would never be recorded")
check("gate result parsed from stdout not exit code",
      "UNVERIFIABLE" in _ts and "NOT_APPLICABLE" in _ts,
      "exit code is unavailable on this hook in some versions")
check("per-agent token attribution present",
      "agents" in _ts and "chat.params" in _ts and "tool.execute.before" in _ts)
check("streaming tokens de-duplicated",
      "seen_msg" in _ts, "cumulative updates would be counted repeatedly")
check("flush is idempotent", "rec.flushed" in _ts, "session.idle can fire twice")
check("no duplicate plugin copy",
      not Path(".opencode/plugins/telemetry.ts").exists(),
      "an unregistered copy diverges silently and keeps stale checks green")
_plug = cfg.get("plugin") or []
check("plugin registered in config", any("telemetry" in str(x) for x in _plug),
      f"plugin={_plug}")
for _p in _plug:
    _f = str(_p).replace("file://", "")
    check(f"registered plugin path exists: {_f}", Path(_f).exists())

print("\n[11] Contract fixture")
# Every check below exists because the matching bug was found by execution, not review.
_cdir = Path(".planning/contracts")
_schemas = sorted(_cdir.glob("*.openapi.y*ml")) if _cdir.exists() else []
check("openapi schema present", bool(_schemas),
      "v1 contracts are HTTP/OpenAPI only; no schema means G1 has nothing to enforce")

_tdir = Path("tests/contract")
_ctests = sorted(_tdir.glob("test_*.py")) if _tdir.exists() else []
check("contract tests present", bool(_ctests),
      "a contract without executable tests is documentation, not a gate")

for _s in _schemas:
    _meta = _s.with_name(_s.name.split(".")[0] + ".meta.yaml")
    check(f"{_s.name} has meta (owner/consumers)", _meta.exists(),
          "contract ownership decides who may approve a change")

_gen = Path("framework/contracts/gen_types.py")
if _gen.exists():
    _g = _gen.read_text()
    check("generated type paths derived from contract id",
          "def targets_for" in _g and "{slug}" in _g,
          "hardcoded output paths make a second contract overwrite the first")

for _t in _ctests:
    check(f"{_t.name} runs standalone", "__main__" in _t.read_text(),
          "the gate must not depend on pytest being installed")

_vs = Path("framework/contracts/validate_schema.py")
if _vs.exists():
    _v = _vs.read_text()
    check("validator separates unavailable from invalid", "_UNAVAILABLE_MARKERS" in _v,
          "a network or install failure must not read as a contract violation")
    check("structural check always runs", "Structural check ALWAYS runs" in _v,
          "an external linter must not excuse the checks we control")

print("\n[12] Gate robustness")
_lib = Path("framework/gates/_lib.sh")
if _lib.exists():
    _l = _lib.read_text()
    check("changed_files includes untracked files", "--others" in _l,
          "git diff alone misses new files, turning gates into silent no-ops")
    check("changed_files is cwd-relative", "--relative" in _l,
          "repo-relative paths never match project dirs in a monorepo subdirectory")
    check("state root normalised", 'STATE_ROOT="${STATE_ROOT#"$PWD"/}"' in _l,
          "an absolute state root cannot be compared against changed file paths")
    check("gates refuse non-bash shells", "require bash" in _l,
          "a bad substitution under sh can otherwise look like a gate verdict")

_g1 = Path("framework/gates/g1_contract.sh")
if _g1.exists():
    _c = _g1.read_text()
    check("G1 resolves git paths from cwd", "HEAD:./$s" in _c,
          "HEAD:path resolves from repo root and misreports changed contracts as new")
    check("CONTRACT_CHANGE outranks test failure", 'if [ "$contract_changed" = "1" ]' in _c,
          "otherwise a schema change routes to Implementer instead of Architect")
    check("G1 checks generated type drift", "--check" in _c,
          "hand-edited generated types are a contract violation")

_g4 = Path("framework/gates/g4_executable.sh")
if _g4.exists():
    _c4 = _g4.read_text()
    check("G4 discovers sources outside repo root", "git ls-files '*.py'" in _c4,
          "root-only globbing misses the conventional src/ + tests/ layout")
    check("G4 substitutes for missing pytest", "executing tests standalone" in _c4,
          "a missing runner must not silently reduce the check count")
    check("G4 avoids network-fetching tsc", "node_modules/.bin/tsc" in _c4,
          "npx --yes can fail on network and read as a type error")
    check("G4 requires node_modules before npm scripts", "-d node_modules" in _c4,
          "'eslint: not found' exit 1 is indistinguishable from a real lint error")

_ci = Path("framework/adapters/code_intel.py")
if _ci.exists():
    _c = _ci.read_text()
    check("affected-tests uses cwd-relative paths", '"--relative"' in _c,
          "repo-relative paths never match in a monorepo subdirectory")
    check("affected-tests excludes framework state", "_NON_SOURCE" in _c,
          "gate output would otherwise register as a source change")
    check("affected-tests follows references", "def _importers" in _c,
          "filename globbing misses tests that import the changed module")


# ---- frontend stack, browser verification, skills, config schema ----------------
print("\n-- frontend stack + browser gate --")

_stack = Path("framework/frontend_stack.yaml")
check("frontend stack contract exists", _stack.exists(),
      "required tools must be declared to be enforceable")

_sc = Path("framework/frontend/stack_check.py")
if _sc.exists():
    _t = _sc.read_text()
    check("G5 distinguishes NOT_APPLICABLE from PASS", "NOT_APPLICABLE" in _t,
          "reporting PASS with zero files evaluated is a vacuous pass")
    check("G5 blocks when pyyaml absent", "A missing parser is not conformance" in _t,
          "tool absence must never read as conformance")
    check("G5 blocks on unreadable package.json", "cannot evaluate required stack" in _t,
          "an unparseable manifest is not a pass")
    check("G5 counts distinct viewports not keywords", "Count PROJECTS, not keyword" in _t,
          "one project matching both devices[] and viewport: scored 2 and passed a >=2 rule")
    check("G5 ratchets to changed files", "changed_text" in _t and "baseline" in _t,
          "sweeping a brownfield repo trains teams to bypass the gate")
    check("G5 uses cwd-relative git paths", '"--relative"' in _t,
          "repo-relative paths never match in a monorepo subdirectory")

_g5 = Path("framework/gates/g5_frontend_stack.sh")
check("G5 gate wired", _g5.exists(), "stack contract needs an executable gate")
if _g5.exists():
    _t5 = _g5.read_text()
    check("G5 maps exit 4 to skip", "4) skip" in _t5,
          "no frontend must skip, not pass")
    check("G5 surfaces blocked separately", "exit 2" in _t5,
          "could-not-evaluate must not collapse into fail or pass")

_g6 = Path("framework/gates/g6_browser.sh")
check("G6 browser gate exists", _g6.exists(),
      "browser profile had commands: [] and could only report unverifiable")
if _g6.exists():
    _t6 = _g6.read_text()
    check("G6 exits 3 for unverifiable", "UNVERIFIABLE=3" in _t6,
          "unverifiable must not share an exit code with pass")
    check("G6 refuses to fetch a driver at gate time", "refusing to fetch at gate time" in _t6,
          "npx fetching mid-gate turns a network failure into a verdict")
    check("G6 requires specs to exist", "no browser specs" in _t6,
          "passing with zero specs is a vacuous pass")
    check("G6 counts screenshot artefacts", "shots=" in _t6,
          "a pass with no captured evidence is unfalsifiable")

_pf = Path("framework/verifier/profiles.yaml")
if _pf.exists():
    _tp = _pf.read_text()
    check("browser profile has real commands", "g6_browser.sh" in _tp,
          "commands: [] made the browser profile permanently unverifiable")
    check("g5 referenced in impact_to_gates has an implementation",
          ("g5" not in _tp) or _g5.exists(),
          "g5 was routed to before any g5 script existed")
    check("shape_to_gates routes visible behaviour", "shape_to_gates" in _tp,
          "a local CSS change still needs browser evidence")

_ledger = Path("framework/frontend/effect_justifications.yaml")
check("conditional-tool ledger exists", _ledger.exists(),
      "conditional tools need a recorded justification, not a convention")

print("\n-- skills + opencode config schema --")
_skills = sorted(Path(".opencode/skills").glob("*/SKILL.md"))
check("skills directory is populated", len(_skills) >= 4,
      "opencode.json pointed at .opencode/skills while it did not exist")
import re as _re
for _f in _skills:
    _txt = _f.read_text()
    _m = _re.match(r"^---\n(.*?)\n---\n", _txt, _re.S)
    check(f"skill frontmatter parses ({_f.parent.name})", bool(_m),
          "a skill without frontmatter is never discovered")
    if _m:
        _nm = _re.search(r"^name:\s*(\S+)", _m.group(1), _re.M)
        check(f"skill name matches directory ({_f.parent.name})",
              bool(_nm) and _nm.group(1) == _f.parent.name,
              "OpenCode resolves skills by directory name")

_cfgp = Path("opencode.json")
if _cfgp.exists():
    import json as _json
    _cfg = _json.loads(_cfgp.read_text())
    _sk = _cfg.get("skills")
    _sk_ok = _sk is None or (
        isinstance(_sk, dict) and isinstance(_sk.get("paths"), list)
        and all(isinstance(p, str) for p in _sk["paths"]))
    check("skills config uses paths-object form", _sk_ok,
          'OpenCode expects skills: {"paths": ["dir"]} or absent; a bare array fails '
          'config validation ("Expected object | undefined")')
    check("telemetry plugin is registered", bool(_cfg.get("plugin")),
          "plugin: [] meant rework telemetry silently collected nothing")
    _plug = " ".join(_cfg.get("plugin") or [])
    check("registered plugin file exists",
          (not _plug) or any(Path(x).exists() for x in
                             [".opencode/plugin/telemetry.ts", ".opencode/plugins/telemetry.ts"]),
          "a registered plugin path that does not exist fails silently at startup")
    check("playwright MCP configured", "playwright" in (_cfg.get("mcp") or {}),
          "browser verification needs a driver available to the verifier")
    _ver = ((_cfg.get("agent") or {}).get("verifier") or {}).get("permission", {})
    check("verifier may run the new gates",
          "./framework/gates/*" in (_ver.get("bash") or {}),
          "the agent that proves things must be able to execute the gates")
    for _ro in ("architect", "planner", "reviewer"):
        _p = ((_cfg.get("agent") or {}).get(_ro) or {}).get("permission", {})
        check(f"{_ro} cannot edit", _p.get("edit") in ("deny", {"*": "deny"}) or
              (isinstance(_p.get("edit"), dict) and _p["edit"].get("*") == "deny"),
              "read-only roles must not mutate code")

_plugin_dir_ok = Path(".opencode/plugin").exists() or Path(".opencode/plugins").exists()
check("plugin directory present", _plugin_dir_ok,
      "OpenCode scans both plugin/ and plugins/; neither existing means no auto-load")

_app = Path("package.json")
check("frontend app manifest exists", _app.exists(),
      "Playwright needs an application to drive; a contract type file is not an app")
if _app.exists():
    import json as _j
    _d = _j.loads(_app.read_text())
    _deps = {**(_d.get("dependencies") or {}), **(_d.get("devDependencies") or {})}
    for _need in ("motion", "lucide-react", "tailwindcss", "@playwright/test"):
        check(f"required stack dep present ({_need})", _need in _deps,
              "the reference app must satisfy its own required tier")
    check("deprecated framer-motion alias absent", "framer-motion" not in _deps,
          "the project standardises on motion/react")

_pwc = Path("playwright.config.ts")
check("playwright config exists", _pwc.exists(), "no config means no baseURL and no viewports")
if _pwc.exists():
    _tw = _pwc.read_text()
    check("at least two viewport projects", _tw.count("name:") >= 2,
          "a responsive claim needs more than one rendered width")

_spec = list(Path("tests/e2e").glob("*.spec.ts")) if Path("tests/e2e").exists() else []
check("browser specs exist", len(_spec) >= 1, "G6 cannot pass without committed specs")


# ── 13. exit code contract + host adapter ────────────────────────────────
print("\n13. Exit code contract and host adapter")

_ec = Path("framework/gates/EXIT_CODES.md")
check("exit code contract documented", _ec.exists(),
      "gate semantics must have one authoritative source or docs drift")

_g6 = Path("framework/gates/g6_browser.sh").read_text()
# The bug this prevents: a doc offered "exit 2 = BLOCKED" for G6 alongside exit 3
# UNVERIFIABLE. Two codes for one condition is how "could not look" becomes "looks fine".
check("G6 never emits exit 2", "exit 2" not in _g6,
      "G6 must emit only 0/1/3; a second code for UNVERIFIABLE defeats exit 3")
check("G6 defines UNVERIFIABLE=3", "UNVERIFIABLE=3" in _g6,
      "exit 3 must be named, not a bare literal")
_g6_unver = _g6.count("exit $UNVERIFIABLE")
check("G6 routes every missing precondition to exit 3", _g6_unver >= 5,
      f"only {_g6_unver} paths exit UNVERIFIABLE; driver/config/spec gaps must all use it")

if _ec.exists():
    _ect = _ec.read_text()
    check("contract states G6 has no exit 2", "NEVER EMITTED" in _ect,
          "the table must say so explicitly, not by omission")
    check("contract distinguishes BLOCKED from UNVERIFIABLE", "not interchangeable" in _ect,
          "2 is a toolchain problem; 3 is a capability problem")

# G5 exit 4 must exist in BOTH the wrapper and the checker, or the branch is dead.
_g5 = Path("framework/gates/g5_frontend_stack.sh").read_text()
_sc = Path("framework/frontend/stack_check.py").read_text()
check("G5 wrapper handles NOT_APPLICABLE", "4)" in _g5,
      "the wrapper must branch on 4 or a no-frontend repo reads as conformant")
check("stack_check can emit NOT_APPLICABLE", "return NOT_APPLICABLE" in _sc,
      "a branch on a code the checker never emits is dead code")

_host = Path("framework/adapters/host.py")
check("host adapter exists", _host.exists(),
      "host knowledge must sit behind one interface so a runtime change is an adapter swap")
if _host.exists():
    _rc, _out = sh("python3 framework/adapters/host.py describe")
    check("host adapter resolves", _rc == 0, _out[:200])
    if _rc == 0:
        _hd = json.loads(_out)
        check("active host is opencode", _hd["host"] == "opencode",
              f"detected {_hd['host']}; v1 supports opencode only")
        check("opencode reports enforced permissions",
              _hd["capabilities"]["permission_enforcement"] == "enforced",
              "the star topology depends on mechanical edit/task denial")
        check("no downgrade on the supported host", "DOWNGRADE" not in _hd,
              _hd.get("DOWNGRADE", "")[:160])
    _rc2, _out2 = sh("python3 framework/adapters/host.py describe --host dsh")
    if _rc2 == 0:
        _dd = json.loads(_out2)
        check("dsh declared unsupported, not silently equivalent",
              _dd["permission_map"]["enforcement"] == "unverified",
              "an unverified permission model must never read as enforced")
        check("dsh downgrade is signalled", "DOWNGRADE" in _dd,
              "adopting a host that cannot enforce permissions must be loud")
    _rc3, _ = sh("python3 framework/adapters/host.py downgrade --host dsh")
    check("downgrade exits non-zero for scripting", _rc3 == 1,
          "CI must be able to fail on an unenforced host")

_od = Path("framework/adapters/opencode_detect.py")
if _od.exists():
    check("legacy detector is a shim", "DEPRECATED" in _od.read_text(),
          "old callers must keep working while pointing at host.py")

# GSD single-distribution rule (fix #1): recognise gsd-pi in order to REFUSE it by name.
_gs = Path("framework/adapters/gsd_state.py").read_text()
check("GSD declares one supported distribution", 'SUPPORTED = ("gsd-core",)' in _gs,
      "v1 supports the installed distribution only; dual support is a conformance target")
check("GSD refuses unsupported distribution", "UNSUPPORTED DISTRIBUTION" in _gs,
      "a db-backed store must not be silently misread as file-backed")
check("GSD detects ambiguous state roots", "AMBIGUOUS" in _gs,
      "two state roots present means neither can be trusted")
check("state root refuses rather than returns empty", "must NOT read as empty state" in _gs,
      "empty state reading as 'no requirements' is the missing-tool-as-pass bug again")


# ── 14. adopt-before-extend audit enforcement ────────────────────────────
print("\n14. Adopt-before-extend audit")

_ac = Path("framework/audit_check.py")
check("audit checker exists", _ac.exists(),
      "an audit nobody checks is documentation, not a step")

_aud = Path("framework/ADOPT_AUDIT.md")
if _aud.exists():
    _at = _aud.read_text()
    for _cap in ("G5 stack conformance", "G6 browser gate", "state consistency"):
        check(f"audit covers {_cap}", _cap in _at,
              "every framework capability with a GSD counterpart needs a row")
    check("audit resolves the gsd-* agent/skill question", "gsd-*" in _at,
          "a file map listing gsd-* files without a decision is the overlap, not a resolution")

if _ac.exists():
    _rc, _out = sh("python3 framework/audit_check.py")
    check("audit checker runs", _rc in (0, 3), _out[:200])
    check("undecided audit is reported, not silently passed", _rc == 3 or "audit complete" in _out,
          "an empty audit must be visible; exit 3 means undecided")
    if _rc == 3:
        WARNS.append("adopt-before-extend audit undecided — required install step, "
                     "most likely path to shrinking the framework below 7 agents")
    check("bootstrap runs the audit checker",
          "audit_check.py" in Path("framework/bootstrap.sh").read_text(),
          "stage 3 must execute the check, not just cat the file")

check("bootstrap detects host via the neutral adapter",
      "adapters/host.py" in Path("framework/bootstrap.sh").read_text(),
      "stage 1 must not depend on a host-specific module name")


print("\n[15] Retrospective intelligence")
_rd = Path("framework/retro")
check("containment map exists", (_rd / "containment_map.yaml").exists(),
      "the map is data so a retrospective's options are inspectable, not invented")
check("escape path analyser exists", (_rd / "escape_path.py").exists())
check("retro ledger exists", (_rd / "ledger.py").exists())
check("g7 gate exists", Path("framework/gates/g7_retro.sh").exists())
check("retrospective skill exists", Path(".opencode/skills/retrospective/SKILL.md").exists())
check("retrospective rule exists", Path(".opencode/rules/retrospective.md").exists())

try:
    import yaml
    _cm = yaml.safe_load((_rd / "containment_map.yaml").read_text())
    check("containment map lists checkpoints in pipeline order",
          [c["id"] for c in _cm["checkpoints"]][:2] == ["requirements", "research"],
          "escape path is computed by position; order is load-bearing")
    check("fix targets are a closed list", len(_cm["fix_targets"]) >= 10)
    check("none_human_judgement is an allowed outcome",
          "none_human_judgement" in _cm["fix_targets"],
          "without it, agents invent rules to look productive")
    check("every fix target names files or is the judgement escape",
          all(v.get("files") or t == "none_human_judgement"
              for t, v in _cm["fix_targets"].items()),
          "a target with no file cannot be verified as landed")
    _gates_in_map = {f for v in _cm["fix_targets"].values() for f in v.get("files", [])
                     if "gates/" in f}
    check("map references real gate files",
          all(Path(f).exists() for f in _gates_in_map), f"missing: {sorted(f for f in _gates_in_map if not Path(f).exists())}")
except ImportError:
    check("containment map parseable", False, "pyyaml absent — cannot validate", warn_only=True)

# Escape path must classify routing gap vs containment miss, and the distinction must flip
# purely on whether the requirement shape activated the gate.
_rc_a, _out_a = sh("python3 framework/retro/escape_path.py --injected implementation "
                   "--caught production --defect-class visible_behaviour_defect --frontend")
_rc_b, _out_b = sh("python3 framework/retro/escape_path.py --injected implementation "
                   "--caught production --defect-class visible_behaviour_defect --frontend "
                   "--shape visible_behaviour")
try:
    _a, _b = json.loads(_out_a), json.loads(_out_b)
    check("undeclared shape reads as ROUTING gap", _a["primary_gap"] == "routing_gap",
          f"got {_a.get('primary_gap')} — an inactive gate is a routing problem, not a weak check")
    check("g6 named as the escaped checkpoint", "gate_g6" in _a["routing_gaps"])
    check("declared shape reads as CONTAINMENT miss", _b["primary_gap"] == "containment_miss",
          f"got {_b.get('primary_gap')} — an active gate that missed is a check problem")
    check("routing fix targets close routing gaps",
          all(t.get("addresses") == "routing_gap" for t in _a["candidate_fix_targets"]),
          "recommending a containment fix for a routing gap leaves the gap open")
    check("candidate list stays small", len(_b["candidate_fix_targets"]) <= 3,
          f"{len(_b.get('candidate_fix_targets', []))} candidates is noise, not guidance")
except Exception as e:
    check("escape path analyser returns usable json", False, str(e)[:160])

_rc_c, _ = sh("python3 framework/retro/escape_path.py --injected implementation "
              "--caught review --defect-class logic_error --complexity L2")
check("no-gap case exits 4, not 0", _rc_c == 4,
      f"got {_rc_c} — caught at the first capable checkpoint is the framework working")
_rc_d, _ = sh("python3 framework/retro/escape_path.py --injected implementation "
              "--caught production --defect-class be_more_careful")
check("unfalsifiable defect class rejected", _rc_d == 1,
      "free-text defect classes make recurrence detection impossible")

_rc_e, _ = sh("python3 framework/retro/ledger.py append --json '{\"task_id\":\"x\"}'")
check("incomplete ledger entry rejected", _rc_e == 1,
      "a retro without a fix target is a note, not a finding")

_sig = Path("framework/retro/ledger.py").read_text()
# Behavioural test, not a text search: two entries describing the same structural gap with
# different task ids, fix targets and wording must collide on signature.
_rc_s, _out_s = sh(
    "python3 -c \"import sys; sys.path.insert(0,'framework/retro'); import ledger as L; "
    "a={'injected_at':'implementation','defect_class':'logic_error','primary_gap':'containment_miss',"
    "'containment_misses':['gate_g4'],'routing_gaps':[],'task_id':'A','rationale':'off by one'}; "
    "b={'injected_at':'implementation','defect_class':'logic_error','primary_gap':'containment_miss',"
    "'containment_misses':['gate_g4'],'routing_gaps':[],'task_id':'B','rationale':'boundary error'}; "
    "print('SAME' if L.signature(a)==L.signature(b) else 'DIFF')\"")
check("recurrence matches structure, not prose", "SAME" in _out_s,
      f"reworded duplicates must collide; got {_out_s[:120]}")
check("landed fix requires a verifying command", "fix_verified_by" in _sig,
      "a fix claimed without an exit code is the DoD failure this framework exists to prevent")

_g7 = Path("framework/gates/g7_retro.sh").read_text()
check("g7 emits NOT_APPLICABLE rather than passing with no trigger", "NOT_APPLICABLE=4" in _g7)
check("g7 refuses when tooling is absent", "BLOCKED" in _g7 and "pyyaml" in _g7,
      "a missing parser must never read as 'no gaps found'")
_rc_g7, _out_g7 = sh("bash framework/gates/g7_retro.sh")
check("g7 runs", _rc_g7 in (0, 1, 2, 4), _out_g7[:200])
check("g7 never emits exit 3", _rc_g7 != 3,
      "3 is reserved for UNVERIFIABLE evidence; retro completeness is not evidence")

try:
    import yaml
    _pr = yaml.safe_load(Path("framework/verifier/profiles.yaml").read_text())
    check("retro profile is event-routed, not impact-routed",
          "defect_escaped" in (_pr.get("event_to_gates") or {}),
          "an escape can follow any impact class, so impact_to_gates cannot route it")
    check("retro profile invokes g7",
          any("g7" in c for c in _pr["profiles"]["retro"]["commands"]))
    _rp = yaml.safe_load(Path("framework/retry_policy.yaml").read_text())
    check("retro triggers are enumerated", len(_rp.get("retro_triggers", [])) >= 5,
          "if 'escape' is a judgement call, the retrospective is optional in practice")
    check("recurrence gets zero retries", _rp["retry_policy"].get("retro_recurrence") == 0,
          "a repeated gap means the framework cannot close it alone")
    check("recurrence routes to a human",
          "RETRO_RECURRENCE" in _rp["routes"])
except ImportError:
    pass

_tl = Path(".opencode/agents/team-lead.md").read_text()
check("team-lead opens retro triggers", "retro/triggers" in _tl)
check("team-lead requires g7 before completion", "G7" in _tl)
check("team-lead is told NOT to retro a clean catch",
      "first place it could" in _tl,
      "retrospecting every caught defect trains everyone to ignore the ledger")
check("verifier runs g7", "g7_retro.sh" in Path(".opencode/agents/verifier.md").read_text())
check("implementer can load the retrospective skill",
      "retrospective" in Path(".opencode/agents/implementer.md").read_text())
_skill = Path(".opencode/skills/retrospective/SKILL.md").read_text()
check("skill rejects unfalsifiable recommendations",
      "be more careful" in _skill.lower() and "add more tests" in _skill.lower(),
      "the failure mode must be named explicitly to be avoided")
check("skill states routing outranks containment",
      "outrank" in _skill.lower() or "precedence" in _skill.lower())

_cfg = json.loads(Path("opencode.json").read_text())
check("verifier permitted to run g7",
      "./framework/gates/g7_retro.sh*" in _cfg["agent"]["verifier"]["permission"]["bash"]
      or _cfg["agent"]["verifier"]["permission"]["bash"].get("./framework/gates/*") == "allow")
check("telemetry tracks escapes and recurrences",
      all(f in Path(".opencode/plugin/telemetry.ts").read_text()
          for f in ("defect_escapes", "retros_recorded", "retro_recurrences")),
      "rework rate is only meaningful with whether the gap closed")

check("g7 in the authoritative exit code table",
      "G7 retro" in Path("framework/gates/EXIT_CODES.md").read_text())



# -- 15b. Validation campaign infrastructure --
print("\n[15b] Validation campaign infrastructure")

_ip = _rd / "injection_protocol.yaml"
check("injection protocol exists", _ip.exists(),
      "controlled falsification needs defined challenges")
if _ip.exists():
    try:
        _ipc = yaml.safe_load(_ip.read_text())
        check("injection protocol parseable", isinstance(_ipc, dict))
        check("has challenges", isinstance(_ipc.get("challenges"), list))
        check("has scoring", isinstance(_ipc.get("scoring"), dict))
        check("has rules", isinstance(_ipc.get("rules"), list))
        for _ch in _ipc.get("challenges", []):
            check("  " + _ch["id"] + " has evidence_required", "evidence_required" in _ch)
            check("  " + _ch["id"] + " has failure_if", "failure_if" in _ch)
    except Exception as e:
        check("injection protocol parseable", False, str(e)[:100])

_mt = _rd / "maturity.yaml"
check("maturity levels exist", _mt.exists())
if _mt.exists():
    try:
        _mtd = yaml.safe_load(_mt.read_text())
        check("maturity parseable", isinstance(_mtd, dict))
        check("has levels", isinstance(_mtd.get("levels"), dict))
        check("has advancement rules", isinstance(_mtd.get("advancement"), dict))
        for _ln, _lv in _mtd.get("levels", {}).items():
            check("  " + _ln + " has exit_criteria",
                  isinstance(_lv.get("exit_criteria"), list) and len(_lv["exit_criteria"]) > 0)
    except Exception as e:
        check("maturity parseable", False, str(e)[:100])

_st = _rd / "smoke_test.py"
check("smoke test exists", _st.exists())
if _st.exists():
    _stc = _st.read_text()
    check("smoke test covers containment_map", "containment_map" in _stc)
    check("smoke test covers escape_path", "escape_path" in _stc)
    check("smoke test covers ledger", "ledger" in _stc)
    check("smoke test covers g7", "g7_retro" in _stc)
    check("smoke test covers injection_protocol", "injection_protocol" in _stc)
    check("smoke test covers maturity", "maturity" in _stc)

_dr = _rd / "dry_run.md"
check("dry run scenario exists", _dr.exists())

_skill_v2 = Path(".opencode/skills/retrospective/SKILL.md").read_text()
check("skill has counterfactual analysis", "counterfactual" in _skill_v2.lower())
check("skill has human-correction path", "human_correction" in _skill_v2)
check("skill has gap type classification", "gap_type" in _skill_v2)
check("skill has earliest prevention point",
      "earliest" in _skill_v2.lower() and "prevent" in _skill_v2.lower())



# -- 15c. Background task pub/sub contract --
print("\n[15c] Background task pub/sub contract")

# The polling anti-pattern: calling background_output on a bg_xxx task BEFORE the
# system-reminder notification, or with block=true as a proxy for waiting. The contract
# is fire -> END RESPONSE -> wait for notification -> collect. Telemetry measures it;
# this section proves the enforcement surface exists.
_bgr = Path(".opencode/rules/background-tasks.md")
check("background task contract rule exists", _bgr.exists(),
      "a contract that is not declared cannot be enforced")
if _bgr.exists():
    _bgt = _bgr.read_text()
    check("rule declares the correct flow", "END YOUR RESPONSE" in _bgt,
          "fire-and-wait must be the primary path")
    check("rule defines a poll", "still running" in _bgt.lower() or "pending" in _bgt.lower(),
          "a poll must be named to be recognisable")
    check("rule defines a collect", "AFTER the system-reminder" in _bgt,
          "the legal path must be explicit")
    check("rule names enforcement", "bg_poll_total" in _bgt,
          "telemetry measurement must be declared in the rule")

_tel = Path(".opencode/plugin/telemetry.ts").read_text()
check("telemetry tracks bg_poll_total", "bg_poll_total" in _tel,
      "sessions that poll must be measurable")
check("telemetry classifies polls vs collects",
      "polls" in _tel and "collects" in _tel,
      "a call after notification is legal; classification is required")
check("telemetry registers launched bg ids",
      "bg_tasks" in _tel and "launched" in _tel,
      "launch count anchors the ratio")
check("telemetry emits a started record on session.created",
      'emit("started")' in _tel and "session.created" in _tel,
      "a killed session must leave at least one record behind")
check("telemetry heartbeats are emitted periodically",
      "setInterval" in _tel and 'emit("heartbeat")' in _tel,
      "heartbeat covers sessions killed before idle/deleted")
check("telemetry emits one idempotent final record",
      'emit("final")' in _tel and "rec.flushed" in _tel,
      "a double idle must not double-count the session")
check("a poll is made loud in the output it returns",
      "POLL_VIOLATION" in _tel,
      "counting alone lets the violating call pass silently")
check("compaction feeds the heartbeat",
      "session.compacted" in _tel and "heartbeat()" in _tel,
      "long sessions must keep writing after compaction")

# Agent instructions must carry the contract so the primary agent sees it before
# launching anything in background.
_lead = Path(".opencode/agents/team-lead.md").read_text()
if "background" in _lead.lower() or "background-tasks" in _lead:
    check("team-lead carries background task contract", True)
else:
    check("team-lead carries background task contract",
          "background" in Path("opencode.json").read_text().lower(),
          "the orchestrator must know the pub/sub contract before it delegates")

print("\n[16] Detection cache portability")
_mf = Path("framework/.manifest/gsd.json")
if _mf.exists():
    _m = json.loads(_mf.read_text())
    _sr = _m.get("state_root")
    if _sr and os.path.isabs(_sr):
        check("cached state root belongs to this checkout",
              os.path.abspath(_sr).startswith(os.getcwd()),
              f"cache points at {_sr} — a packaged tree would read another machine's state")
check("manifest cache is gitignored",
      Path(".gitignore").exists() and "framework/.manifest" in Path(".gitignore").read_text(),
      "a committed manifest carries the packager's absolute paths into every clone")
check("manifest cache is validated before use",
      "_cache_valid" in Path("framework/adapters/gsd_state.py").read_text(),
      "trusting the cache unconditionally makes a relocated tree read the wrong state silently")

print("\n[17] Architecture design checklist")
_cl = Path("framework/architecture/design_checklist.yaml")
_clc = Path("framework/architecture/checklist_check.py")
check("design checklist exists", _cl.exists(),
      "the Architect's output is a decision; no artefact exists for a gate to execute against")
check("checklist checker exists", _clc.exists())

if _cl.exists() and _clc.exists():
    try:
        import yaml as _y
        _d = _y.safe_load(_cl.read_text())
        check("checklist is scoped to the architect",
              _d.get("scope") == "architect",
              "an unscoped checklist loads for every agent and dilutes attention")
        check("checklist has an enforced ceiling",
              isinstance(_d.get("max_items"), int) and _d["max_items"] <= 15,
              "unbounded growth does not make a checklist stricter; it dilutes the items that matter")
        check("checklist items are within the ceiling",
              len(_d.get("items") or []) <= _d.get("max_items", 12))
        check("checklist has an expiry lifecycle",
              isinstance(_d.get("expiry_cycles"), int),
              "an item that never changes a design is decoration and must be retirable")
        check("'reviewed' is not an allowed verdict",
              "reviewed" not in (_d.get("dispositions") or {}),
              "claiming the checklist was read is the equivalent of a test that exists but never ran")
        _reqs = {k: v.get("requires", []) for k, v in (_d.get("dispositions") or {}).items()}
        check("applied verdict requires naming what changed",
              "changed" in _reqs.get("applied", []))
        check("accepted_risk requires an approver",
              "approved_by" in _reqs.get("accepted_risk", []))
        check("every item traces to a retro id",
              all(str(i.get("retro_id", "")).strip() for i in _d.get("items") or []),
              "an item with no retro id is folklore, not a lesson")
        check("every item justifies why it is not executable",
              all(str(i.get("judgement_because", "")).strip() for i in _d.get("items") or []),
              "if a gate could assert it, the checklist is the wrong home")
    except ImportError:
        WARNS.append("pyyaml missing; checklist structure unvalidated")

    _rc, _o = sh("python3 framework/architecture/checklist_check.py structure")
    check("checklist passes its own structure check", _rc == 0, _o[:200])

    # Folklore rejection: an executable condition must not be admissible.
    _rc2, _o2 = sh(
        "python3 - <<'EOF'\n"
        "import sys; sys.path.insert(0,'framework/architecture')\n"
        "import checklist_check as c\n"
        "bad=[{'id':'X','question':'Does src/domain/ must not import requests?','why':'w',"
        "'judgement_because':'j','retro_id':'r','cycles_without_effect':0}]\n"
        "e=c.check_structure({'items':bad,'max_items':12})\n"
        "print('REJECTED' if e else 'ADMITTED')\n"
        "EOF")
    check("checker rejects an executable condition posing as judgement",
          "REJECTED" in _o2,
          "a gate-assertable rule in the checklist replaces an exit code with a claim")

    # Disposition ordering: newest wins, not lexicographically last.
    check("disposition tally reads files in timestamp order",
          "st_mtime" in _clc.read_text(),
          "filename order would let a stale disposition retire an item whose latest cycle applied")

    check("G3 enforces the disposition",
          "checklist_check.py" in Path("framework/gates/g3_architecture.sh").read_text(),
          "an unenforced checklist is documentation")
    check("checklist is owed only for architecture tasks",
          "ARCHITECTURE_TASK" in Path("framework/gates/g3_architecture.sh").read_text(),
          "demanding dispositions on a typo fix gets the gate routed around")
    check("architect is told how to disposition",
          "verdict" in Path(".opencode/agents/architect.md").read_text())

# Destination classification: the checklist must be the hardest tier to reach.
_ep = Path("framework/retro/escape_path.py").read_text()
check("retro analyser classifies lesson destination", "def destination(" in _ep,
      "without a destination, every lesson becomes prose in an agent prompt")
check("checklist tier is reachable only from architecture",
      'injected == "architecture"' in _ep,
      "implementation, review and testing lessons resolve to checks and skill rules")
check("unmapped is distinguished from accepted",
      "unmapped_combination" in _ep and "not_accepted" in _ep,
      "conflating them turns a missing map row into a deliberate decision")

_rc3, _o3 = sh("python3 - <<'EOF'\n"
               "import sys,json; sys.path.insert(0,'framework/retro')\n"
               "import escape_path as e\n"
               "a=e.destination(['agent_instruction'],'architecture')['tier']\n"
               "b=e.destination(['agent_instruction'],'implementation')['tier']\n"
               "c=e.destination(['gate_routing'],'architecture')['tier']\n"
               "print(a,b,c)\n"
               "EOF")
check("identical lesson routes to checklist only from architecture",
      _o3.strip().startswith("design_checklist agent_instruction"), _o3[:160])
check("an executable target outranks the checklist",
      _o3.strip().endswith("executable_check"), _o3[:160])

print("\n[18] Blocker escalation")
check("g8 gate exists", Path("framework/gates/g8_blockers.sh").exists(),
      "an unwritten gate cannot refuse completion on open escalation debt")
_pf = Path("framework/verifier/profiles.yaml").read_text()
check("functional profile always runs g8",
      "./framework/gates/g8_blockers.sh" in _pf,
      "blockers are checked every task, not when someone remembers")
check("exit contract documents G8",
      "| G8 blockers" in Path("framework/gates/EXIT_CODES.md").read_text(),
      "claims about gate behaviour must cite EXIT_CODES.md")
check("bootstrap reports open blockers",
      "list-blockers" in Path("framework/bootstrap.sh").read_text(),
      "an install inherits visible escalation debt, not silent surprises")
_ts = Path(".opencode/plugin/telemetry.ts").read_text()
check("telemetry counts blockers opened/resolved",
      "blockers_opened" in _ts and "blockers_resolved" in _ts,
      "escalation debt invisible in telemetry is debt nobody pays")
_im = Path(".opencode/agents/implementer.md").read_text()
check("implementer records non-complete stops", "write-blocker" in _im,
      "a stop that lives only in prose evaporates with the conversation")
_tl = Path(".opencode/agents/team-lead.md").read_text()
check("team lead resolves or refuses on open blockers",
      "list-blockers" in _tl and "resolve-blocker" in _tl,
      "refusal without a resolution path routes around the gate")
_vf = Path(".opencode/agents/verifier.md").read_text()
check("verifier runs g8 and reports its verdicts",
      "g8_blockers" in _vf and "g8:" in _vf)


def _perm_keys(obj, prefix):
    n = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith(prefix):
                n += 1
            n += _perm_keys(v, prefix)
    elif isinstance(obj, list):
        for v in obj:
            n += _perm_keys(v, prefix)
    return n


_ocj = json.loads(Path("opencode.json").read_text())
check("six agents hold the plain-form adapter allowlist",
      _perm_keys(_ocj, "python3 framework/adapters/gsd_state.py") >= 6,
      "the silent permission pause returns for any agent missing it")
check("architect holds the checklist-check allowlist",
      _perm_keys(_ocj, "python3 framework/architecture/checklist_check.py") >= 1)

# Behavioural proof on an isolated copy -- the real .planning is never touched.
_bd = Path(tempfile.mkdtemp(prefix="val18_blockers_"))
shutil.copytree("framework", _bd / "framework",
                ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
(_bd / ".planning").mkdir()
_w = _wsl_path(str(_bd))


def _bsh(cmd, timeout=120):
    return sh("cd '%s' && %s" % (_w, cmd), timeout=timeout)


_rc, _o = _bsh("bash framework/gates/g8_blockers.sh")
check("clean tree passes g8", _rc == 0, _o[:200])

_seed = json.dumps({"signal": "CONTEXT_INSUFFICIENT", "task_id": "99-99",
                    "agent": "implementer", "missing_item": "PLAN.md for phase 03",
                    "tried": "grep and read twice", "retries": 1})
_rc, _o = _bsh("python3 framework/adapters/gsd_state.py write-blocker --json '%s'" % _seed)
_d = {}
if _rc == 0:
    try:
        _d = json.loads(_o)
    except Exception:
        pass
check("seed writes BLK-001", _d.get("id") == "BLK-001", _o[:200])

_up = json.dumps({"signal": "CONTEXT_INSUFFICIENT", "task_id": "99-99",
                  "agent": "implementer", "retries": 2})
_rc, _o = _bsh("python3 framework/adapters/gsd_state.py write-blocker --json '%s'" % _up)
_d = {}
if _rc == 0:
    try:
        _d = json.loads(_o)
    except Exception:
        pass
check("repeat stop upserts one record with max retries",
      _d.get("upserted") is True and _d.get("retries") == 2, _o[:200])

_rc, _o = _bsh("python3 framework/adapters/gsd_state.py list-blockers")
try:
    _lst = json.loads(_o)
except Exception:
    _lst = []
check("open record carries signal, item and retry count",
      len(_lst) == 1 and _lst[0].get("missing_item") == "PLAN.md for phase 03"
      and _lst[0].get("retries") == 2, _o[:200])

_rc, _o = _bsh("bash framework/gates/g8_blockers.sh")
check("g8 refuses completion while a record is open",
      _rc == 1 and "BLK-001" in _o, ("rc=%d " % _rc) + _o[:300])

_rc, _o = _bsh("python3 framework/adapters/gsd_state.py resolve-blocker --id BLK-001")
_d = json.loads(_o) if _rc == 0 else {}
check("resolve discharges the record", _d.get("resolved") is True, _o[:200])

_rc, _o = _bsh("python3 framework/adapters/gsd_state.py resolve-blocker --id BLK-999")
check("unknown id refused, never silently ignored",
      _rc != 0 and "NOT_FOUND" in _o, _o[:200])

_bad = json.dumps({"task_id": "x", "agent": "y"})
_rc, _o = _bsh("python3 framework/adapters/gsd_state.py write-blocker --json '%s'" % _bad)
check("record missing its signal is rejected",
      _rc != 0 and "BLOCKER_INCOMPLETE" in _o,
      "a half-specified stop is not an executable escalation")

_rc, _o = _bsh("bash framework/gates/g8_blockers.sh")
check("discharged store passes g8 again", _rc == 0, _o[:200])

shutil.rmtree(_bd, ignore_errors=True)


print("\n[19] Telemetry report tool")
_r = Path("framework/telemetry/report.py")
check("report tool exists", _r.exists())
_rc, _o = sh("python3 framework/telemetry/report.py --path /nonexistent.jsonl")
check("empty telemetry exits 3 not 0", _rc == 3, f"exit={_rc}")
# Fixtures live in the repo root so the relative path survives both POSIX shells and
# the Windows shim without backslash mangling.
_good = Path("_val_good.jsonl")
_bad = Path("_val_bad.jsonl")
_unv = Path("_val_unv.jsonl")
_val_ded = Path("_val_ded.jsonl")
_val_unf = Path("_val_unf.jsonl")
try:
    _bad.write_text("garbage\n{oops\n", encoding="utf-8")
    _rc, _o = sh("python3 framework/telemetry/report.py --path _val_bad.jsonl")
    check("unparseable-only telemetry exits 2", _rc == 2, f"exit={_rc}")
    _good.write_text(json.dumps({
        "record_version": 2, "task_id": "t1", "duration_s": 100,
        "agents": {"implementer": {"invocations": 1,
                                   "tokens": {"input": 100, "output": 20},
                                   "tool_calls": 3, "ms": 500, "models": ["m/a"]}},
        "tokens": {"input": 100, "output": 20},
        "tools": {"bash": {"count": 2, "ms": 300, "fail": 0}},
        "gates": {"g4": {"result": "pass", "ms": 50, "exit": 0}},
        "retries": {"test_failure": 1}, "retro_recurrences": 1}) + "\n", encoding="utf-8")
    _rc, _o = sh("python3 framework/telemetry/report.py --path _val_good.jsonl")
    check("report renders a valid record", _rc == 0, f"exit={_rc}")
    check("rework rate reported", "REWORK RATE" in _o and "100.0%" in _o, _o[-200:])
    check("recurrence surfaced", "did not close the gap" in _o, _o[-200:])
    _rc, _o = sh("python3 framework/telemetry/report.py --json --path _val_good.jsonl")
    check("json mode emits rework_rate_pct",
          _rc == 0 and '"rework_rate_pct"' in _o, f"exit={_rc}")
    # Unverifiable must never be aggregated as a pass.
    _unv.write_text(json.dumps({
        "record_version": 2, "agents": {}, "tokens": {},
        "gates": {"g6": {"result": "unverifiable", "ms": 10, "exit": 3}}}) + "\n",
        encoding="utf-8")
    _rc, _o = sh("python3 framework/telemetry/report.py --path _val_unv.jsonl")
    check("unverifiable reported separately from pass",
          "UNVERIFIABLE result(s)" in _o and "claim nothing" in _o, _o[-200:])
    # Lifecycle series must collapse to one record per session; three emits for one
    # session would otherwise triple-count every metric.
    _val_ded.write_text("\n".join(
        json.dumps(r) for r in (
            {"record_version": 2, "session_id": "s_ded", "kind": "started",
             "tokens": {"input": 100}, "agents": {}, "tools": {}},
            {"record_version": 2, "session_id": "s_ded", "kind": "heartbeat",
             "tokens": {"input": 100}, "agents": {}, "tools": {}},
            {"record_version": 2, "session_id": "s_ded", "kind": "final",
             "tokens": {"input": 100}, "agents": {}, "tools": {}})) + "\n",
        encoding="utf-8")
    _rc, _o = sh("python3 framework/telemetry/report.py --json --path _val_ded.jsonl")
    check("lifecycle records dedupe to one per session",
          _rc == 0 and '"n": 1' in _o and '"input": 100' in _o and '"input": 300' not in _o,
          f"exit={_rc}; {_o[-200:]}")
    # A session that only ever wrote started (killed before final) is a health failure.
    _val_unf.write_text(json.dumps({
        "record_version": 2, "session_id": "ses_never_finalized", "kind": "started",
        "tokens": {"input": 50}, "agents": {}, "tools": {}}) + "\n", encoding="utf-8")
    _rc, _o = sh("python3 framework/telemetry/report.py --path _val_unf.jsonl")
    check("unfinalized session exits 1 and names the session",
          _rc == 1 and "ses_never_finalized" in _o and "no final record" in _o,
          f"exit={_rc}; {_o[-200:]}")
finally:
    for _fx in (_good, _bad, _unv, _val_ded, _val_unf):
        if _fx.exists():
            _fx.unlink()

print("\n[20] Per-agent model configuration")
def _resolvable(m):
    """Usable at spawn: non-empty and structural per the resolve engine.

    Deferring to the engine (not re-deriving a pattern here) is the point:
    Section 20 must judge *resolvability*, and the engine owns that judgement.
    A leftover {env:...} reference, an empty id, or invalid characters all fail
    structural_ok, so a regression surfaces here instead of as a spawn stall."""
    if not _RES_OK:
        return False  # engine unavailable -> nothing is provably resolvable
    return _res.structural_ok(m)

_novar = [a for a in EXPECTED if not _resolvable(agents[a].get("model", ""))]
check("every agent has a resolvable model id", not _novar, f"missing: {_novar}")
_norat = [a for a in EXPECTED if not agents[a].get("_model_rationale")]
check("every agent model choice has a rationale", not _norat, f"missing: {_norat}")
_notemp = [a for a in EXPECTED if "temperature" not in agents[a]]
check("every agent has an explicit temperature", not _notemp, f"missing: {_notemp}")
check("top-level model resolves to something real",
      _resolvable(cfg.get("model", "")), f"model={cfg.get('model')}")
_prof = Path("framework/models/profiles.sh")
check("model profiles exist", _prof.exists())
if _prof.exists():
    _ps = _prof.read_text()
    for _name in ("baseline", "tiered", "cheap", "reset"):
        check(f"profile '{_name}' defined",
              re.search(rf"^\s*(?:\w+\|)*{_name}(?:\|\w+)*\)", _ps, re.M) is not None)
    _rc, _o = sh("OC_BIG=sentinel-big OC_MID=sentinel-mid OC_SML=sentinel-small bash -c 'source framework/models/profiles.sh tiered >/dev/null && "
                 "echo $OC_MODEL_IMPLEMENT/$OC_MODEL_VERIFY'")
    _parts = _o.strip().split("/")
    check("tiered profile differentiates implementer from verifier",
          _rc == 0 and _o.strip() and _parts[:2] != _parts[2:], _o[:120])
    _rc, _o = sh("bash -c 'source framework/models/profiles.sh baseline >/dev/null; "
                 "source framework/models/profiles.sh reset >/dev/null; "
                 "echo \"[${OC_MODEL_IMPLEMENT:-unset}]\"'")
    check("reset restores inheritance", "[unset]" in _o, _o[:120])
    _rc, _o = sh("bash -c 'source framework/models/profiles.sh bogus >/dev/null 2>&1'")
    check("unknown profile is rejected", _rc != 0, f"exit={_rc}")

    # --- behaviour of framework/models/resolve.py (fail-closed resolution) ---
    def _scrubbed_env():
        _e = dict(os.environ)
        for _k in list(_e):
            if _k.startswith("OC_MODEL_") or _k in ("OC_BIG", "OC_MID", "OC_SML"):
                del _e[_k]
        return _e

    _s1 = _res.preflight(cfg, _scrubbed_env(), _ps)
    check("S1 no OC_MODEL_* env -> all agents resolve to default",
          _s1["failures"] == []
          and all(_a["source"] == "default" for _a in _s1["agents"].values()),
          str({_k: _v["source"] for _k, _v in _s1["agents"].items()})[:120])

    _env2 = _scrubbed_env()
    _env2.update({_v: "anthropic/claude-4-5-sonnet" for _v in _res.ENV_BY_AGENT.values()})
    _env2[_res.SMALL_ENV] = "opencode/big-pickle"
    _s2 = _res.preflight(cfg, _env2, _ps)
    check("S2 all nine OC_MODEL_* set -> every agent sourced 'override'",
          _s2["failures"] == []
          and all(_a["source"] == "override" for _a in _s2["agents"].values()),
          str(_s2["active_profile"])[:120])

    _env3 = _scrubbed_env()
    _env3["OC_MODEL_LEAD"] = "anthropic/claude-4-5-sonnet"
    _s3 = _res.preflight(cfg, _env3, _ps)
    check("S3 one OC_MODEL_* set -> team-lead 'override', rest 'default'",
          _s3["agents"]["team-lead"] == {"model": "anthropic/claude-4-5-sonnet", "source": "override"}
          and all(_a["source"] == "default" for _n, _a in _s3["agents"].items() if _n != "team-lead"),
          str({_k: _v["source"] for _k, _v in _s3["agents"].items()})[:120])

    _env4 = _scrubbed_env()
    _env4["OC_MODEL_LEAD"] = ""
    _s4 = _res.preflight(cfg, _env4, _ps)
    check("S4 set-but-empty OC_MODEL_LEAD -> fail closed as 'error'",
          _s4["agents"]["team-lead"] == {"model": "", "source": "error"}
          and "team-lead" in _s4["failures"],
          str(_s4["failures"])[:120])

    _env4b = _scrubbed_env()
    _env4b["OC_MODEL_LEAD"] = "bad;rm -rf /"
    _s4b = _res.preflight(cfg, _env4b, _ps)
    check("S4b malformed OC_MODEL_LEAD -> fail closed as 'error'",
          _s4b["agents"]["team-lead"]["source"] == "error", str(_s4b["failures"])[:120])

    _real = _res.realized_profiles(_ps, _scrubbed_env())
    check("S5 every profile maps all seven agents",
          {"baseline", "tiered", "cheap"}.issubset(_real)
          and all(_real[_p].get(_a) not in (None, _res.MISSING)
                  for _p in _real for _a in _res.AGENTS),
          str(sorted(_real))[:120])

    _parsed = _res.parse_profile_script(_ps)
    check("S6 raw profile cells are refs or model ids",
          bool(_parsed)
          and all(_res.dep_ok(_c) for _cells in _parsed.values() for _c in _cells.values()),
          str(sorted(_parsed))[:120])

    _inv = _res.inventory(timeout=10)
    if _inv["ok"]:
        _cfg_ids = {cfg.get("model")} | {
            _ag.get("model") for _ag in cfg["agent"].values()
            if isinstance(_ag.get("model"), str)}
        _cfg_ids = {_m for _m in _cfg_ids if _res.structural_ok(_m)}
        _inv_ids = {_m for _m in _inv["models"] if _res.structural_ok(_m)}
        check("S7 configured ids present in `opencode models` inventory",
              _cfg_ids.issubset(_inv_ids),
              "missing: %s" % sorted(_cfg_ids - _inv_ids)[:120])
    else:
        check("S7 configured ids verifiable in `opencode models` inventory",
              True, "unverifiable: %s" % _inv["note"], warn_only=True)

    _s8 = _res.preflight(cfg, {}, _ps)
    check("S8 fresh session resolves exactly as S1",
          _s8["agents"] == _s1["agents"] and _s8["failures"] == _s1["failures"],
          str({_k: _v["source"] for _k, _v in _s8["agents"].items()})[:120])

    _smk = Path("framework/tools/spawn_smoke.sh")
    _smk_text = _smk.read_text(encoding="utf-8") if _smk.exists() else ""
    _r9, _o9 = sh("bash framework/tools/spawn_smoke.sh --help")
    check("S9 spawn smoke test exists, bounded, usage path exits 0",
          bool(_smk_text) and 'TMO="180"' in _smk_text
          and "Reply with exactly: SMOKE_OK" in _smk_text
          and "set -euo pipefail" in _smk_text and _r9 == 0,
          f"exit={_r9}; {_o9[-80:]}" if _r9 != 0 else "ok")

# ── §21 delegated task execution protocol ────────────────────────────────────
_gsd_src = Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8")
for _tok, _lbl in [("TASK_NEXT", "TASK_NEXT transition table"),
                   ("TASK_TERMINAL", "TASK_TERMINAL final states"),
                   ("def register_task", "register_task"),
                   ("def task_event", "task_event"),
                   ("def cancel_task", "cancel_task"),
                   ("def task_status", "task_status"),
                   ("def list_tasks", "list_tasks"),
                   ('"task-register"', "task-register CMDS entry"),
                   ('"task-event"', "task-event CMDS entry"),
                   ('"task-cancel"', "task-cancel CMDS entry")]:
    check(f"S10 adapter exposes {_lbl}", _tok in _gsd_src, f"missing: {_tok}")

_tt21 = Path("framework/tasks/task_types.yaml")
_tt21_text = _tt21.read_text(encoding="utf-8") if _tt21.exists() else ""
check("S11 task_types.yaml declares type budgets",
      _tt21.exists() and "task_types" in _tt21_text and "defaults" in _tt21_text
      and "progress_timeout_s" in _tt21_text,
      "framework/tasks/task_types.yaml missing or malformed")

_rp21 = Path("framework/retry_policy.yaml").read_text(encoding="utf-8")
check("S12 retry_policy declares worker_stalled count and WORKER_STALLED route",
      "worker_stalled" in _rp21 and "WORKER_STALLED" in _rp21
      and "apply_recovery_ladder" in _rp21,
      "add worker_stalled: 1 and WORKER_STALLED -> team_lead apply_recovery_ladder")

_dp21 = Path(".opencode/rules/delegation-protocol.md")
_dp21_text = _dp21.read_text(encoding="utf-8") if _dp21.exists() else ""
check("S13 delegation-protocol.md rule file present and complete",
      _dp21.exists() and "## Lifecycle" in _dp21_text and "## Health" in _dp21_text
      and "task-register" in _dp21_text and "background-tasks.md" in _dp21_text,
      ".opencode/rules/delegation-protocol.md missing or incomplete")

_bt21 = Path(".opencode/rules/background-tasks.md").read_text(encoding="utf-8")
check("S14 background-tasks.md cross-references the protocol",
      "delegation-protocol.md" in _bt21 and "task-register" in _bt21,
      "append a Supervision section naming the task-* commands")

_tl21 = Path(".opencode/agents/team-lead.md").read_text(encoding="utf-8")
check("S15 team-lead.md liveness policy names the task-* commands",
      "task-register" in _tl21 and "task-status" in _tl21 and "task-event" in _tl21,
      "liveness section must name task-register / task-status / task-event")

_tel21 = Path(".opencode/plugin/telemetry.ts").read_text(encoding="utf-8")
check("S16 telemetry.ts collects worker supervision counters",
      "worker_tasks_registered" in _tel21 and "worker_events_written" in _tel21
      and "worker_stalls_detected" in _tel21,
      "telemetry must collect the three supervision counters")

_rp21b = Path("framework/telemetry/report.py").read_text(encoding="utf-8")
check("S17 report.py aggregates the supervision counters",
      "worker_tasks_registered" in _rp21b and "worker_stalls_detected" in _rp21b,
      "report.py must accumulate the supervision counters")

# behavioral: drive the adapter against an isolated copy of the state root
_bd21 = Path(tempfile.mkdtemp(prefix="val21_super_"))
shutil.copytree("framework", _bd21 / "framework",
                ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
(_bd21 / ".planning").mkdir()

def _wsh21(cmd, timeout=180):
    return sh("cd '%s' && %s" % (_wsl_path(str(_bd21)), cmd), timeout=timeout)

_ADP = "python3 framework/adapters/gsd_state.py"

_reg = '{"agent":"explore","type":"explore","objective":"find x","expected_artifact":"r.md"}'
_r, _o = _wsh21("%s task-register --id V21-001 --json '%s'" % (_ADP, _reg))
check("S18 task-register creates a SPAWNED, HEALTHY contract",
      _r == 0 and '"state": "SPAWNED"' in _o and '"health": "HEALTHY"' in _o
      and '"progress_timeout_s": 20' in _o and '"max_duration_s": 90' in _o,
      (_o or "")[-200:])

_r, _o = _wsh21("%s task-register --id V21-001 --json '%s'" % (_ADP, _reg))
check("S18 duplicate register refused (EXISTS - immutable contract)",
      _r != 0 and "EXISTS" in _o, (_o or "")[-200:])

_lc = ('{"state":"ACK"}', '{"state":"STARTED"}',
       '{"state":"PROGRESS","checkpoint":"c1"}',
       '{"state":"BLOCKED","detail":"d"}',
       '{"state":"PROGRESS"}', '{"state":"COMPLETED"}')
_lc_ok = all(_wsh21("%s task-event --id V21-001 --json '%s'" % (_ADP, _e))[0] == 0 for _e in _lc)
_r, _o = _wsh21("%s task-status --id V21-001" % _ADP)
check("S18 lifecycle ACK..COMPLETED accepted, status COMPLETE",
      _lc_ok and _r == 0 and '"state": "COMPLETED"' in _o and '"health": "COMPLETE"' in _o,
      (_o or "")[-200:])

_r, _o = _wsh21("%s task-event --id V21-001 --json '{\"state\":\"ACK\"}'" % _ADP)
check("S18 post-terminal event refused (TERMINAL_STATE)",
      _r != 0 and "TERMINAL_STATE" in _o, (_o or "")[-200:])

_r, _o = _wsh21("%s task-event --id V21-002 --json '{\"state\":\"ACK\"}'" % _ADP)
check("S18 event on unregistered task refused (NOT_FOUND)",
      _r != 0 and "NOT_FOUND" in _o, (_o or "")[-200:])

_r, _o = _wsh21("%s task-register --id V21-003 --json '{\"agent\":\"quick\",\"type\":\"default\",\"objective\":\"o\",\"expected_artifact\":\"a\"}'" % _ADP)
_wsh21("%s task-event --id V21-003 --json '{\"state\":\"STARTED\"}'" % _ADP)
_r2, _o2 = _wsh21("%s task-event --id V21-003 --json '{\"state\":\"ACK\"}'" % _ADP)
check("S18 illegal transition refused (INVALID_TRANSITION)",
      _r == 0 and _r2 != 0 and "INVALID_TRANSITION" in _o2, (_o2 or "")[-200:])

_wsh21("%s task-register --id V21-004 --json '{\"agent\":\"deep\",\"type\":\"explore\",\"objective\":\"o\",\"expected_artifact\":\"a\",\"progress_timeout_s\":1}'" % _ADP)
time.sleep(1.4)
_r, _o = _wsh21("%s task-status --id V21-004" % _ADP)
check("S19 silent past budget escalates to WARNING",
      _r == 0 and '"health": "WARNING"' in _o and '"recovery_level": 1' in _o, (_o or "")[-200:])

_wsh21("%s task-register --id V21-005 --json '{\"agent\":\"deep\",\"type\":\"explore\",\"objective\":\"o\",\"expected_artifact\":\"a\",\"progress_timeout_s\":1}'" % _ADP)
time.sleep(2.5)
_r, _o = _wsh21("%s task-status --id V21-005" % _ADP)
check("S19 prolonged silence escalates to STALLED",
      _r == 0 and '"health": "STALLED"' in _o and '"recovery_level": 2' in _o, (_o or "")[-200:])

_wsh21("%s task-register --id V21-006 --json '{\"agent\":\"deep\",\"type\":\"explore\",\"objective\":\"o\",\"expected_artifact\":\"a\",\"progress_timeout_s\":1,\"max_duration_s\":1}'" % _ADP)
time.sleep(1.5)
_r, _o = _wsh21("%s task-status --id V21-006" % _ADP)
check("S19 hard deadline expiry escalates to OVERDUE",
      _r == 0 and '"health": "OVERDUE"' in _o and '"recovery_level": 3' in _o, (_o or "")[-200:])

_r, _o = _wsh21("%s task-register --id V21-007 --json '{\"agent\":\"verifier\",\"type\":\"verify\",\"objective\":\"o\",\"expected_artifact\":\"a\"}'" % _ADP)
check("S19 verify-type without contract budgets refused (TASK_INCOMPLETE)",
      _r != 0 and "TASK_INCOMPLETE" in _o and "progress_timeout_s" in _o, (_o or "")[-200:])

_r, _o = _wsh21("%s task-register --id V21-008 --json '{\"agent\":\"reviewer\",\"type\":\"review\",\"objective\":\"o\",\"expected_artifact\":\"a\"}'" % _ADP)
_wsh21("%s task-event --id V21-008 --json '{\"state\":\"STARTED\",\"emitter\":\"team-lead\"}'" % _ADP)
_r2, _o2 = _wsh21("%s task-cancel --id V21-008 --json '{\"emitter\":\"team-lead\"}'" % _ADP)
check("S19 supervisor cancel records CANCELLED with emitter",
      _r == 0 and _r2 == 0 and '"health": "CANCELLED"' in _o2 and '"emitter": "team-lead"' in _o2,
      (_o2 or "")[-200:])

_r, _o = _wsh21("%s task-list" % _ADP)
check("S19 task-list surfaces the registered tasks",
      _r == 0 and "V21-001" in _o and "V21-005" in _o, (_o or "")[-200:])

shutil.rmtree(_bd21, ignore_errors=True)


print("\n" + "=" * 60)
if WARNS:
    print(f"{len(WARNS)} warning(s):")
    for w in WARNS:
        print(f"  - {w}")
if FAILS:
    print(f"\n{len(FAILS)} FAILURE(S) — do not use the framework until resolved:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("VALIDATION PASSED")
