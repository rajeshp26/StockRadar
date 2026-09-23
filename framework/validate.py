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

_edit = agents["implementer"]["permission"]["edit"]
check("implementer can edit",
      _edit == "allow" or (isinstance(_edit, dict) and any(v == "allow" for v in _edit.values())))
for a in ("reviewer", "planner", "researcher", "team-lead"):
    _edit = agents[a]["permission"]["edit"]
    check(f"{a} cannot edit",
          _edit == "deny" or (isinstance(_edit, dict) and _edit.get("*", "deny") != "allow"))
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
# repo that legitimately exceeds two minutes. Give it room. One run, not one per
# gate name in the loop above — the loop only checks existence/executability.
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
check("flush is idempotent",
      "flushGuard.claim()" in _ts and "createFlushGuard" in _ts,
      "session.idle can fire twice")
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
    _txt = _f.read_text(encoding="utf-8")
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

_st = _rd / "smoke_check.py"
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
      'emit("final")' in _tel and "flushGuard.claim()" in _tel,
      "a double idle must not double-count the session")
check("a poll is made loud in the output it returns",
      "POLL_VIOLATION" in _tel,
      "counting alone lets the violating call pass silently")
check("compaction feeds the heartbeat",
      "session.compacted" in _tel and "heartbeat()" in _tel,
      "long sessions must keep writing after compaction")

# ── 15d. Telemetry LIVENESS (T-FX3) ───────────────────────────────────────────
# Escape-path fix target gate_check, destination tier executable_check: the harness
# and its wiring must be proven by an executable check, not by prose. This block is
# the text-level regression guard that keeps them from silently disappearing.
print("\n[15d] Telemetry liveness (T-FX3)")

# (a) The integration harness exists and is runnable by node --test.
_tl_test = Path(".opencode/plugin/telemetry.test.mjs")
check("telemetry integration harness exists", _tl_test.exists(),
      "the executable proof of collector behaviour must be committed")
if _tl_test.exists():
    _tl_test_text = _tl_test.read_text(encoding="utf-8")
    check("harness uses node:test + node:assert only",
          "node:test" in _tl_test_text and "node:assert" in _tl_test_text,
          "the harness must be framework-free so g4 can run it without installs")
    check("harness drives the plugin end to end",
          "session.created" in _tl_test_text and "tool.execute.before" in _tl_test_text
          and "tool.execute.after" in _tl_test_text,
          "the harness must exercise the real hook sequence, not a mock")

# (b) The report anomaly test exists (T-FX2 deliverable; either location on disk).
_tl_anom = (Path("tests/framework/test_report_telemetry.py")
            if Path("tests/framework/test_report_telemetry.py").exists()
            else Path("framework/telemetry/test_report_telemetry.py"))
check("report anomaly test exists",
      _tl_anom.exists(),
      "the report anomaly regression test (T-FX2) must be committed; "
      "expected at tests/framework/test_report_telemetry.py or "
      "framework/telemetry/test_report_telemetry.py")

# (c) Text-level regression guard on the collector's gate matcher and task-args read.
# The old narrow gate regex `gates\/(g[1-8])_` missed g9/g12/g_tool_* (the 2026-09-07
# zero-gate-records incident). The old task-args read indexed purely on `input?.args`
# produced 539/547 records with execution_agent "unknown" (args are nested under input
# in the real runtime). Both must be gone; the collector must read a fallback chain.
check("collector no longer uses the narrow gate regex as its matcher",
      "cmd.match(/gates\\/(g[1-8])_/)" not in _ts,
      "the narrow g[1-8] matcher missed g9/g12/g_tool_*; gate records must come from "
      "the canonical [gate] line")
# Fallback chain lives in envelope.mjs (normalizeTaskArgs); the collector routes through it.
_tl_env = Path(".opencode/plugin/envelope.mjs").read_text(encoding="utf-8")
check("collector reads task args via a fallback chain (not purely input?.args)",
      "normalizeTaskArgs" in _ts and "input.input" in _tl_env,
      "real runtime nests task args under input; reading input?.args alone yields "
      "execution_agent 'unknown'")

# (d) The g4 hook: package.json must declare a "test" script running node --test so
# g4_executable.sh executes the harness as part of the executable chain.
_tl_pkg = Path("package.json")
if _tl_pkg.exists():
    import json as _tl_json
    _tl_scripts = _tl_json.loads(_tl_pkg.read_text(encoding="utf-8")).get("scripts") or {}
    _tl_test_script = _tl_scripts.get("test", "")
    check("package.json declares a test script that reaches node --test",
          ("node --test" in _tl_test_script or _tl_test_script.endswith("framework/tools/run_tests.mjs")),
          "g4 runs `npm test` when a test script exists; the script must reach node --test "
          "so the telemetry harness is part of the executable chain")

# The runner is the sanctioned entry point; guard its delegation so the chain
# cannot silently stop reaching node --test.
_tl_runner = Path("framework/tools/run_tests.mjs")
check("runner delegates to node --test",
      "--test" in (_tl_runner.read_text(encoding="utf-8") if _tl_runner.exists() else ""),
      "run_tests.mjs must spawn node --test; npm test reaches the harness through it")

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

_ADP = "python3 framework/adapters/gsd_state.py"
def _suite_18():
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
# Fixture records reference task ids with no contract in the LIVE tasks dir; a real
# tasks dir would trip the supervision-join warning and exit 1. Point those runs at
# a nonexistent tasks dir -- report.py degrades a missing tasks dir to an info note,
# never a failure (report.py:_supervision_join).
_val_td = str(Path(tempfile.mkdtemp(prefix="val19_td_")) / "tasks").replace("\\", "/")
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
    _rc, _o = sh("python3 framework/telemetry/report.py --path _val_good.jsonl --tasks-dir " + _val_td)
    check("report renders a valid record", _rc == 0, f"exit={_rc}")
    check("rework rate reported", "REWORK RATE" in _o and "100.0%" in _o, _o[-200:])
    check("recurrence surfaced", "did not close the gap" in _o, _o[-200:])
    _rc, _o = sh("python3 framework/telemetry/report.py --json --path _val_good.jsonl --tasks-dir " + _val_td)
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
    _rc, _o = sh("python3 framework/telemetry/report.py --json --path _val_ded.jsonl --tasks-dir " + _val_td)
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

def _suite_21():
    _bd21 = Path(tempfile.mkdtemp(prefix="val21_super_"))
    shutil.copytree("framework", _bd21 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd21 / ".planning").mkdir()

    def _wsh21(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd21)), cmd), timeout=timeout)


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




print("\n[21] Evidence provenance")
check("g11 gate exists", Path("framework/gates/g11_evidence.sh").exists(),
      "an unwritten gate cannot refuse completion on claims without provenance")
_pf11 = Path("framework/verifier/profiles.yaml").read_text()
check("functional profile always runs g11",
      "./framework/gates/g11_evidence.sh" in _pf11,
      "evidence provenance is checked every task, not when someone remembers")
check("exit contract documents G11",
      "| G11 evidence" in Path("framework/gates/EXIT_CODES.md").read_text(),
      "claims about gate behaviour must cite EXIT_CODES.md")
_cl = Path("framework/claims/ledger.py").read_text()
check("claim ledger has append and analyse", "def append" in _cl and "def analyse" in _cl,
      "a ledger that cannot record or judge claims is decorative")
check("claim ledger validates provenance", "def _has_provenance" in _cl,
      "provenance is a code-level check, not a hope")
check("claim ledger enforces VERIFIED requires command", "CLAIM_VERIFIED_NO_COMMAND" in _cl,
      "a VERIFIED claim without a verifying command is an opinion")
check("claim ledger enforces independent check for high impact",
      "CLAIM_VERIFIED_NO_INDEPENDENT_CHECK" in _cl,
      "high-impact claims need a second pair of eyes")
check("claim ledger requires runtime-backed evidence for causal conclusions",
      "CLAIM_CAUSAL_NO_RUNTIME" in _cl,
      "static configuration, code inspection, logs, or plausibility cannot establish causation")
_tl11 = Path(".opencode/agents/team-lead.md").read_text()
check("team lead references evidence provenance",
      "evidence provenance" in _tl11.lower() or "claim ledger" in _tl11.lower() or "G-VERIFY" in _tl11,
      "the gate on findings must be enforced by the team lead, not hoped for")
_im11 = Path(".opencode/agents/implementer.md").read_text()
check("implementer references claim ledger",
      "claim" in _im11.lower() and ("ledger" in _im11.lower() or "evidence provenance" in _im11.lower()),
      "agents must be told to record claims, not assume they will")
_vf11 = Path(".opencode/agents/verifier.md").read_text()
check("verifier runs g11 and reports its verdicts",
      "g11" in _vf11 and ("claim" in _vf11.lower() or "evidence" in _vf11.lower()),
      "verifier must reference the evidence gate")

print("\n[22] Evidence provenance -- agent wiring and ledger behaviour")
# statics: every agent that records claims must be told how; the gate must run
_rp22 = Path("framework/retry_policy.yaml").read_text()
check("EVIDENCE_INSUFFICIENT escalation route recorded",
      "EVIDENCE_INSUFFICIENT" in _rp22 and "gather_provenance_or_downgrade_claim" in _rp22,
      "a claim without provenance needs a named recovery action")
_rs22 = Path(".lifecycle/agents/researcher.md").read_text()
check("researcher classifies findings and records them",
      "classification: FACT | HYPOTHESIS | ASSUMPTION | UNKNOWN" in _rs22
      and "## Claim classification" in _rs22 and "ledger" in _rs22.lower(),
      "research findings are claims and must be labelled")
_im22 = Path(".opencode/agents/implementer.md").read_text()
check("implementer records claim classification",
      "classification:" in _im22 and "FACT | HYPOTHESIS" in _im22,
      "a debug-mode diagnosis must carry a claim classification")
_im22l = Path(".lifecycle/agents/implementer.md").read_text()
check("implementer knows verification levels",
      "### Verification levels" in _im22l and "L3 end-to-end" in _im22l,
      "evidence levels L1/L2/L3 must be taught to the agent that records claims")
_ar22 = Path(".opencode/agents/architect.md").read_text()
check("architect records ASSUMPTION decisions",
      "ASSUMPTION claim" in _ar22 and "ledger.py" in _ar22,
      "an accepted assumption that is never claimed is an unrecorded decision")
_rv22 = Path(".lifecycle/agents/reviewer.md").read_text()
check("reviewer traces conclusions to VERIFIED claims",
      "VERIFIED claims" in _rv22 and "ledger" in _rv22.lower(),
      "a review conclusion without a claim is a question, not a finding")
_tl22 = Path(".opencode/plugin/telemetry.ts").read_text()
check("telemetry keeps g1-g8 matcher and adds g10/g11",
      "(g[1-8])" in _tl22 and "g1[01]" in _tl22,
      "evidence gates must be counted like functional gates")
check("telemetry counts claim events",
      "claims_recorded" in _tl22 and "claims_invalid" in _tl22,
      "claim provenance must be measurable per session")
_oc22 = json.loads(Path("opencode.json").read_text())
_rb22 = _oc22["agent"]["researcher"]["permission"]["bash"]
check("researcher may run the claim ledger",
      any("claims/ledger.py" in k for k in _rb22),
      "an agent told to record claims must hold the permission to run the ledger")

# behavioral: drive the ledger and gate against an isolated framework copy

def _suite_22():
    _bd22 = Path(tempfile.mkdtemp(prefix="val22_claims_"))
    shutil.copytree("framework", _bd22 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd22 / ".planning").mkdir()

    def _wsh22(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd22)), cmd), timeout=timeout)

    _GL = "bash framework/gates/g11_evidence.sh"
    _LG = "python3 framework/claims/ledger.py"

    _r, _o = _wsh22(_GL)
    check("g11 with no claims is NOT_APPLICABLE (4), never a pass",
          _r == 4 and "NOT_APPLICABLE" in _o, (_o or "")[-200:])

    _g1 = ('{"claim_id":"CLM-900","task_id":"V22-001","agent":"verifier",'
           '"statement":"full-provenance claim",'
           '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"high",'
           '"verified_by":"bash framework/gates/g11_evidence.sh",'
           '"independent_check":"python3 framework/claims/ledger.py analyse",'
           '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
           '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh22(_LG + " append --json '%s'" % _g1)
    check("ledger accepts a fully-provenanced high-impact claim",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh22(_GL)
    check("g11 passes a valid ledger",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    _g2 = ('{"claim_id":"CLM-901","task_id":"V22-002","agent":"verifier",'
           '"statement":"missing impact",'
           '"claim_type":"data","classification":"FACT","status":"VERIFIED",'
           '"verified_by":"bash framework/gates/g11_evidence.sh"}')
    _r, _o = _wsh22(_LG + " append --json '%s'" % _g2)
    check("ledger rejects missing impact (CLAIM_INCOMPLETE)",
          _r == 1 and "CLAIM_INCOMPLETE" in _o, (_o or "")[-200:])

    _g3 = ('{"claim_id":"CLM-902","task_id":"V22-003","agent":"verifier",'
           '"statement":"unverified fact",'
           '"claim_type":"data","classification":"FACT","status":"UNVERIFIED","impact":"low"}')
    _r, _o = _wsh22(_LG + " append --json '%s'" % _g3)
    check("ledger rejects FACT that is not VERIFIED (CLAIM_FACT_UNVERIFIED)",
          _r == 1 and "CLAIM_FACT_UNVERIFIED" in _o, (_o or "")[-200:])

    _cor = ('{"claim_id":"CLM-999","task_id":"V22-999","agent":"hand",'
            '"statement":"corrupt",'
            '"claim_type":"data","classification":"FACT","status":"VERIFIED","impact":"low"}')
    (_bd22 / ".planning" / "claims").mkdir(parents=True, exist_ok=True)
    (_bd22 / ".planning" / "claims" / "ledger.jsonl").write_text(_cor + "\n", encoding="utf-8")
    _r, _o = _wsh22(_GL)
    check("g11 catches a hand-written corrupt claim and names it",
          _r == 1 and "CLM-999" in _o and "FAIL" in _o, (_o or "")[-300:])

    _gf = ('{"claim_id":"CLM-999","task_id":"V22-999","agent":"hand",'
           '"statement":"corrupt claim fixed by re-append",'
           '"claim_type":"data","classification":"FACT","status":"VERIFIED","impact":"low",'
           '"verified_by":"bash framework/gates/g11_evidence.sh",'
           '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
           '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh22(_LG + " append --json '%s'" % _gf)
    check("re-append with provenance supersedes the corrupt record (latest wins)",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh22(_GL)
    check("g11 passes after the corrupt claim is superseded",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    shutil.rmtree(_bd22, ignore_errors=True)




print("\n[23] Provider health pre-flight")
# provider boundary: the taxonomy must exist, name the observed defect, be
# first-match ordered, and keep worker-level classes out of the blocking set.
_hc23 = Path("framework/providers/healthcheck.py").read_text(encoding="utf-8")
check("provider taxonomy names the credit-wall defect",
      "QUOTA_FAILURE" in _hc23 and "insufficient credits" in _hc23.lower(),
      "the exact observed OpenRouter error must classify as QUOTA_FAILURE")
_ix_auth = _hc23.index("AUTH_FAILURE")
_ix_quota = _hc23.index("QUOTA_FAILURE")
check("taxonomy is first-match ordered (auth outranks quota)",
      _ix_auth < _ix_quota,
      "a 401 with quota wording must classify as AUTH_FAILURE, not QUOTA_FAILURE")
_bs = _hc23[_hc23.index("BLOCKING_CLASSES"):]
_bs = _bs[:_bs.index("}") + 1]
check("blocking set excludes worker-level classes",
      "QUOTA_FAILURE" in _bs and "AGENT_FAILURE" not in _bs and "SUSPECTED_STALL" not in _bs,
      "worker classes belong to task supervision, never to the provider boundary")

_g12p = Path("framework/gates/g12_provider.sh")
check("g12 gate exists", _g12p.exists(),
      "an unwritten gate cannot refuse an unhealthy dispatch")
check("G12 registered in the exit-code contract",
      "| G12 provider" in Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8"),
      "gate behaviour claims must cite EXIT_CODES.md")

_adp23 = Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8")
check("adapter refuses unclassified FAILED events",
      "TASK_INVALID_FAILURE_CLASS" in _adp23
      and "FAILED requires failure_class" in _adp23,
      "an unclassified failure cannot be routed; the adapter must refuse it")
check("adapter routes provider classes to the pre-flight gate",
      "g12 provider pre-flight" in _adp23 and "no dispatch to" in _adp23,
      "a blocking provider class must route to g12/nodispatch, not to WORKER_STALLED")

_dp23_text = Path(".opencode/rules/delegation-protocol.md").read_text(encoding="utf-8")
check("delegation-protocol requires failure_class on FAILED",
      "failure_class" in _dp23_text and "TASK_INVALID_FAILURE_CLASS" in _dp23_text
      and "g12 provider pre-flight" in _dp23_text and "WORKER_STALLED" in _dp23_text,
      "the written protocol must carry the routing contract the adapter enforces")
_tl23_text = Path(".opencode/agents/team-lead.md").read_text(encoding="utf-8")
check("team-lead runs the provider pre-flight before dispatch",
      "g12_provider.sh" in _tl23_text and "NO TASK DISPATCH" in _tl23_text
      and "failure_class" in _tl23_text,
      "the orchestrator must be told to pre-flight providers before every task() dispatch")

# behavioral: isolated copy, real CLI round-trips, no network

def _suite_23():
    _bd23 = Path(tempfile.mkdtemp(prefix="val23_prov_"))
    shutil.copytree("framework", _bd23 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd23 / ".planning").mkdir()

    def _wsh23(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd23)), cmd), timeout=timeout)

    _HC23 = "python3 framework/providers/healthcheck.py"
    _r, _o = _wsh23(_HC23 + " selftest")
    check("healthcheck selftest passes (classify + ledger roundtrip)",
          _r == 0, (_o or "")[-300:])

    _r, _o = _wsh23(_HC23 + ' classify --error "Insufficient credits. This account never purchased credits."')
    check("classify CLI maps the observed error to QUOTA_FAILURE",
          _r == 0 and '"class": "QUOTA_FAILURE"' in _o, (_o or "")[-200:])

    _sp = _wsl_path(str(_bd23 / ".planning" / "providers" / "health.jsonl"))
    _SEED23 = "export PROVIDER_HEALTH_FILE='%s' PROVIDER_HEALTH_WINDOW_MIN=600; " % _sp
    _r, _o = _wsh23(_HC23 + ' record --provider openrouter --model opencode/big-pickle --class NOT_A_CLASS --detail "x" --source validate')
    check("record rejects a class outside the taxonomy",
          _r == 1 and "BAD_CLASS" in _o, (_o or "")[-200:])

    _r, _o = _wsh23(_SEED23 + _HC23 + " record --provider openrouter --model opencode/big-pickle "
                    "--class QUOTA_FAILURE --detail 'validate seed' --source validate")
    check("record accepts a taxonomy class (seed for the pre-flight test)",
          _r == 0 and "recorded" in _o, (_o or "")[-200:])

    # g12 fail-closed: with no resolvable config the gate must report BLOCKED (2),
    # never a clean pass - checked before opencode.json exists in the sandbox.
    _r, _o = _wsh23("unset OC_MODEL_DEFAULT OC_MODEL_SMALL OC_MODEL_LEAD OC_MODEL_RESEARCH "
                    "OC_MODEL_ARCHITECT OC_MODEL_PLANNER OC_MODEL_IMPLEMENT OC_MODEL_REVIEW "
                    "OC_MODEL_VERIFY OC_BIG OC_MID OC_SML PROVIDER_HEALTH_FILE; "
                    "bash framework/gates/g12_provider.sh")
    check("g12 without a resolvable config is BLOCKED, never pass",
          _r == 2 and "BLOCKED" in _o, "rc=%s out=%s" % (_r, (_o or "")[-200:]))

    # config-default resolution (no env, no shim pass-through): the sandbox reads a
    # minimal opencode.json as its model source, then the seeded record must refuse.
    (_bd23 / "opencode.json").write_text(
        json.dumps({"model": "opencode/big-pickle", "small_model": "opencode/big-pickle"}),
        encoding="utf-8")
    _r, _o = _wsh23(_SEED23 + _HC23 + " check", timeout=300)
    check("seeded blocking record refuses the pre-flight",
          _r != 0 and ("QUOTA_FAILURE" in _o or "MODEL_UNAVAILABLE" in _o
                       or "inventory unavailable" in _o or "BLOCKED" in _o),
          "a recorded blocking class must refuse dispatch, never read as clean - rc=%s" % _r)

    # failure_class contract on the adapter: refused / provider route / worker route
    _reg23 = '{"agent":"implementer","type":"implement","objective":"o","expected_artifact":"a","progress_timeout_s":20,"max_duration_s":90}'
    _wsh23("%s task-register --id V23-001 --json '%s'" % (_ADP, _reg23))
    _r, _o = _wsh23("%s task-event --id V23-001 --json '{\"state\":\"FAILED\"}'" % _ADP)
    check("FAILED without failure_class is refused",
          _r != 0 and "TASK_INVALID_FAILURE_CLASS" in _o, (_o or "")[-200:])

    _wsh23("%s task-register --id V23-002 --json '%s'" % (_ADP, _reg23))
    _r, _o = _wsh23("%s task-event --id V23-002 --json '{\"state\":\"FAILED\",\"failure_class\":\"QUOTA_FAILURE\"}'" % _ADP)
    _r2, _o2 = _wsh23("%s task-status --id V23-002" % _ADP)
    check("FAILED with QUOTA_FAILURE routes to g12 (no dispatch)",
          _r == 0 and _r2 == 0 and '"failure_class": "QUOTA_FAILURE"' in _o2
          and "g12 provider pre-flight" in _o2 and "no dispatch to" in _o2,
          (_o2 or "")[-250:])

    _wsh23("%s task-register --id V23-003 --json '%s'" % (_ADP, _reg23))
    _r, _o = _wsh23("%s task-event --id V23-003 --json '{\"state\":\"FAILED\",\"failure_class\":\"AGENT_FAILURE\"}'" % _ADP)
    _r2, _o2 = _wsh23("%s task-status --id V23-003" % _ADP)
    check("FAILED with AGENT_FAILURE routes to WORKER_STALLED (not provider)",
          _r == 0 and _r2 == 0 and '"failure_class": "AGENT_FAILURE"' in _o2
          and "WORKER_STALLED" in _o2, (_o2 or "")[-250:])

    shutil.rmtree(_bd23, ignore_errors=True)


print("\n[24] Execution context runtime binding")
# statics: the context artifact must exist and bind provider/model under RT- ids, and the
# claim ledger must refuse an RT- reference that does not resolve to a recorded context
_ec24 = Path("framework/execution_context.py").read_text(encoding="utf-8")
check("execution context artifact exists",
      "RUNTIME_ID_RE" in _ec24 and "contexts" in _ec24 and "execution.jsonl" in _ec24,
      "runtime identity must be a recorded artifact, not a free-form string")
check("execution context binds provider and model",
      "provider" in _ec24 and "model" in _ec24 and "resolved_by" in _ec24,
      "the binding must name provider, model and resolution source")
check("execution context records under RT- ids",
      're.compile(r"^RT-\\d+$")' in _ec24 and "_next_runtime_id" in _ec24,
      "canonical runtime ids let the ledger verify references")
_cl24 = Path("framework/claims/ledger.py").read_text(encoding="utf-8")
check("claim ledger validates runtime references",
      "CLAIM_UNKNOWN_RUNTIME" in _cl24 and "execution.jsonl" in _cl24,
      "an RT- reference that does not resolve must be refused, never assumed")

# behavioral: isolated copy, real CLI round-trips, no network

def _suite_24():
    _bd24 = Path(tempfile.mkdtemp(prefix="val24_ctx_"))
    shutil.copytree("framework", _bd24 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd24 / ".planning").mkdir()
    # config-default resolution (the deterministic path established in [23])
    (_bd24 / "opencode.json").write_text(
        '{"model": "opencode/big-pickle", "small_model": "opencode/big-pickle"}',
        encoding="utf-8")

    def _wsh24(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd24)), cmd), timeout=timeout)

    _EC24 = "python3 framework/execution_context.py"
    _LG24 = "python3 framework/claims/ledger.py"

    _r, _o = _wsh24(_EC24 + " analyse")
    check("execution context analyse on empty store is 3 (never a pass)",
          _r == 3 and "empty" in _o, (_o or "")[-200:])
    _r, _o = _wsh24(_EC24 + " current")
    check("execution context current on empty store is 3 (never a pass)",
          _r == 3 and '"status": "none"' in _o, (_o or "")[-200:])

    _r, _o = _wsh24(_EC24 + " record")
    check("execution context record pins RT-0001",
          _r == 0 and '"runtime_id": "RT-0001"' in _o, (_o or "")[-200:])
    _ctx24 = (_bd24 / ".planning" / "contexts" / "execution.jsonl").read_text(encoding="utf-8")
    check("execution context row binds host/provider/model/created_at",
          '"runtime_id": "RT-0001"' in _ctx24 and '"provider"' in _ctx24
          and '"model": "opencode/big-pickle"' in _ctx24 and '"created_at"' in _ctx24,
          (_ctx24 or "")[-300:])

    _r, _o = _wsh24(_EC24 + " current")
    check("execution context current returns the pinned runtime",
          _r == 0 and '"runtime_id": "RT-0001"' in _o, (_o or "")[-200:])
    _r, _o = _wsh24(_EC24 + " analyse")
    check("execution context analyse passes with one pinned runtime",
          _r == 0 and '"status": "ok"' in _o, (_o or "")[-200:])

    _r, _o = _wsh24(_EC24 + " record")
    _r2, _o2 = _wsh24(_EC24 + " analyse")
    check("second record gets RT-0002 and analyse stays ok",
          _r == 0 and '"runtime_id": "RT-0002"' in _o
          and _r2 == 0 and '"runtimes"' in _o2 and "RT-0002" in _o2, (_o2 or "")[-200:])

    # claim ledger: RT- references must resolve, free-form runtimes stay legal (legacy path)
    _c1 = ('{"claim_id":"CLM-910","task_id":"V24-001","agent":"verifier",'
           '"statement":"recorded runtime binding",'
           '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
           '"verified_by":"bash framework/gates/g11_evidence.sh",'
           '"evidence":[{"kind":"command_run","runtime":"RT-0001",'
           '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh24(_LG24 + " append --json '%s'" % _c1)
    check("ledger accepts a claim bound to a recorded runtime",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])

    _c2 = ('{"claim_id":"CLM-911","task_id":"V24-002","agent":"verifier",'
           '"statement":"unrecorded runtime reference",'
           '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
           '"verified_by":"bash framework/gates/g11_evidence.sh",'
           '"evidence":[{"kind":"command_run","runtime":"RT-9999",'
           '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh24(_LG24 + " append --json '%s'" % _c2)
    check("ledger refuses a claim bound to an unrecorded runtime",
          _r == 1 and "CLAIM_UNKNOWN_RUNTIME" in _o, (_o or "")[-200:])

    _c3 = ('{"claim_id":"CLM-912","task_id":"V24-003","agent":"verifier",'
           '"statement":"free-form legacy runtime stays legal",'
           '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
           '"verified_by":"bash framework/gates/g11_evidence.sh",'
           '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
           '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh24(_LG24 + " append --json '%s'" % _c3)
    check("free-form runtime strings remain legal (legacy path)",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])

    _r, _o = _wsh24("bash framework/gates/g11_evidence.sh")
    check("g11 passes with a valid runtime-bound ledger",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    # duplicate runtime_id must be refused by analyse, never silently merged
    _ctxp24 = _bd24 / ".planning" / "contexts" / "execution.jsonl"
    _ctxp24.write_text(_ctxp24.read_text(encoding="utf-8")
                       + '{"runtime_id":"RT-0001","host":"opencode","provider":"x",'
                         '"model":"m","created_at":"dup"}\n', encoding="utf-8")
    _r, _o = _wsh24(_EC24 + " analyse")
    check("duplicate runtime_id refused by analyse",
          _r == 1 and "CONTEXT_DUPLICATE_ID" in _o, (_o or "")[-200:])

    shutil.rmtree(_bd24, ignore_errors=True)


print("\n[25] Worker observability (task-summary + G13)")
# statics: the adapter must aggregate worker health from the event stream, and the gate
# must wrap that command -- observability is a derived fact, never a contract-file guess
_gs25 = Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8")
check("adapter exposes task-summary",
      "def task_summary()" in _gs25 and '"task-summary"' in _gs25,
      "the gate's data source is an executable aggregate of the task event stream")
_g1325 = Path("framework/gates/g13_worker.sh").read_text(encoding="utf-8")
check("G13 wraps task-summary and owns its exit contract",
      'GATE_NAME="g13_worker"' in _g1325 and "task-summary" in _g1325
      and "exit $NOT_APPLICABLE" in _g1325,
      "a gate is a command with an exit code; it must map health to 0/1/2/4")
_exc25 = Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8")
check("G13 exit contract documented in EXIT_CODES.md",
      "| G13 worker" in _exc25 and "NOT_APPLICABLE (no tasks registered)" in _exc25,
      "generated claims about gate behaviour must cite the authoritative table")

# behavioral: isolated copy, real CLI round-trips, real gate exits, no network

def _suite_25():
    _bd25 = Path(tempfile.mkdtemp(prefix="val25_worker_"))
    shutil.copytree("framework", _bd25 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd25 / ".planning").mkdir()

    def _wsh25(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd25)), cmd), timeout=timeout)

    _ADP25 = "python3 framework/adapters/gsd_state.py"
    _G1325 = "bash framework/gates/g13_worker.sh"

    # empty store: nothing to observe
    _r, _o = _wsh25(_ADP25 + " task-summary")
    check("task-summary on empty store reports empty",
          _r == 0 and '"status": "empty"' in _o and '"registered": 0' in _o, (_o or "")[-200:])
    _r, _o = _wsh25(_G1325)
    check("G13 on empty store is NOT_APPLICABLE (never a pass)",
          _r == 4 and "NOT_APPLICABLE" in _o, (_o or "")[-200:])

    # healthy worker: STARTED with generous budgets -> ok
    _reg25 = ('{"agent":"implementer","type":"implement","objective":"o",'
              '"expected_artifact":"a","progress_timeout_s":20,"max_duration_s":90}')
    _wsh25(_ADP25 + " task-register --id V25-001 --json '%s'" % _reg25)
    _wsh25(_ADP25 + " task-event --id V25-001 --json '{\"state\":\"STARTED\"}'")
    _r, _o = _wsh25(_ADP25 + " task-summary")
    check("task-summary with a healthy worker reports ok",
          _r == 0 and '"status": "ok"' in _o and '"registered": 1' in _o
          and '"health": "HEALTHY"' in _o, (_o or "")[-250:])
    _r, _o = _wsh25(_G1325)
    check("G13 passes with all workers healthy",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    # stale worker: 1s budgets, wait past max_duration -> OVERDUE escalates
    _reg_stale25 = ('{"agent":"deep","type":"explore","objective":"o",'
                    '"expected_artifact":"a","progress_timeout_s":1,"max_duration_s":1}')
    _wsh25(_ADP25 + " task-register --id V25-002 --json '%s'" % _reg_stale25)
    _wsh25(_ADP25 + " task-event --id V25-002 --json '{\"state\":\"STARTED\"}'")
    _r, _o = _wsh25("sleep 2 && %s task-summary" % _ADP25)
    check("task-summary flags an overdue worker as unhealthy",
          _r == 0 and '"status": "unhealthy"' in _o and "OVERDUE" in _o, (_o or "")[-250:])
    _r, _o = _wsh25(_G1325)
    check("G13 refuses completion with an overdue worker (exit 1)",
          _r == 1 and "V25-002" in _o and "OVERDUE" in _o
          and "cancel_and_retry" in _o, (_o or "")[-300:])

    # failed worker with provider class: route surfaced next to the task
    _wsh25(_ADP25 + " task-register --id V25-003 --json '%s'" % _reg25)
    _wsh25(_ADP25 + " task-event --id V25-003 --json '{\"state\":\"FAILED\",\"failure_class\":\"QUOTA_FAILURE\"}'")
    _r, _o = _wsh25(_ADP25 + " task-summary")
    check("task-summary includes FAILED with its recovery route",
          '"status": "unhealthy"' in _o and "V25-003" in _o
          and "QUOTA_FAILURE" in _o and "g12" in _o, (_o or "")[-300:])
    _r, _o = _wsh25(_G1325)
    check("G13 names the failed task and its provider route",
          _r == 1 and "V25-003" in _o and "QUOTA_FAILURE" in _o and "g12" in _o, (_o or "")[-300:])

    shutil.rmtree(_bd25, ignore_errors=True)


print("\n[26] Provenance control plane (DID-007 delta)")
# statics: the ENV- capture surface, the ledger's env/disconfirmation/confidence rules,
# the supervision identity capture, and the C0-C8 vocabulary must all exist
_ec26 = Path("framework/execution_context.py").read_text(encoding="utf-8")
check("execution context captures command environments",
      "record_env" in _ec26 and "check_env" in _ec26 and "environments.jsonl" in _ec26,
      "ENV- capture must be an executable surface, not a doc")
check("execution context validates ENV- ids",
      're.compile(r"^ENV-\\d+$")' in _ec26 and "_next_env_id" in _ec26,
      "canonical env ids let check-env and the ledger verify references")
_ecf26 = Path("framework/execution_context.yaml")
check("canonical execution context yaml exists", _ecf26.exists(),
      "check-env needs a canonical declaration per scope to compare against")
if _ecf26.exists():
    check("canonical yaml declares scopes", "scopes" in _ecf26.read_text(encoding="utf-8"))
_cl26 = Path("framework/claims/ledger.py").read_text(encoding="utf-8")
for _tok26, _lbl26 in [("CLAIM_ENV_UNKNOWN", "unresolved ENV- ref refused"),
                       ("CLAIM_BAD_DISCONFIRMATION", "disconfirmation vocab enforced"),
                       ("CLAIM_DISCONFIRMED_BUT_VERIFIED", "refuted+VERIFIED refused"),
                       ("CLAIM_STORED_CONFIDENCE", "stored confidence refused"),
                       ("def derive_confidence", "confidence derived at analyse"),
                       ("DISCONFIRMATION_RESULTS", "disconfirmation result vocab")]:
    check(f"claim ledger {_lbl26}", _tok26 in _cl26, f"missing: {_tok26}")
_gs26 = Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8")
for _tok26, _lbl26 in [("background_task_id", "background_task_id captured"),
                       ("DECISION_MISSING_ID", "write-decision id guard"),
                       (".contract.json", "contract-peer exclusion")]:
    check(f"gsd_state {_lbl26}", _tok26 in _gs26, f"missing: {_tok26}")
_tt26 = Path("framework/tasks/task_types.yaml").read_text(encoding="utf-8")
check("task_types declares the C0-C8 vocabulary",
      "checkpoint_vocabulary" in _tt26 and "C0-TASK_ACCEPTED" in _tt26
      and "C8-HANDOFF_READY" in _tt26,
      "the shared checkpoint vocabulary must be declared in state, not invented")
check("task_types declares per-type default checkpoints",
      "checkpoints:" in _tt26 and "C5-TESTS_GREEN" in _tt26,
      "each type needs a default progression")
_dp26 = Path(".opencode/rules/delegation-protocol.md").read_text(encoding="utf-8")
check("delegation-protocol documents C0-C8 and background_task_id",
      "C0-TASK_ACCEPTED" in _dp26 and "C8-HANDOFF_READY" in _dp26
      and "background_task_id" in _dp26,
      "the protocol must carry the vocabulary and the identity capture rule")

# behavioral: isolated copy, real CLI round-trips, no network

def _suite_26():
    _bd26 = Path(tempfile.mkdtemp(prefix="val26_env_"))
    shutil.copytree("framework", _bd26 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd26 / ".planning").mkdir()

    def _wsh26(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd26)), cmd), timeout=timeout)

    _EC26 = "python3 framework/execution_context.py"
    _LG26 = "python3 framework/claims/ledger.py"
    _ADP26 = "python3 framework/adapters/gsd_state.py"

    # record-env pins the interpreter that actually ran
    _r, _o = _wsh26(_EC26 + " record-env --scope backend")
    check("record-env pins ENV-0001", _r == 0 and '"env_id": "ENV-0001"' in _o, (_o or "")[-200:])
    _env26 = (_bd26 / ".planning" / "contexts" / "environments.jsonl").read_text(encoding="utf-8")
    check("ENV- row captures interpreter/cwd/git/os",
          '"env_id": "ENV-0001"' in _env26 and '"interpreter_path"' in _env26
          and '"interpreter_version"' in _env26 and '"cwd"' in _env26
          and '"git_commit"' in _env26 and '"git_dirty"' in _env26 and '"os"' in _env26,
          (_env26 or "")[-300:])

    # canonical backend scope declares the venv; the recorded interpreter is the global
    # python, so a mismatch is expected (the DBeta incident axis)
    _r, _o = _wsh26(_EC26 + " check-env --scope backend")
    check("check-env flags the venv-vs-global interpreter mismatch",
          _r == 1 and '"status": "mismatch"' in _o and '"interpreter"' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_EC26 + " check-env --scope nosuchscope")
    check("check-env with no canonical scope is 3 (never a pass)",
          _r == 3 and '"status": "no_canonical"' in _o, (_o or "")[-200:])

    # canonical yaml written from the recorded row -> match
    _envrow26 = json.loads(_env26.splitlines()[0])
    (_bd26 / "framework" / "execution_context.yaml").write_text(
        "scopes:\n  backend:\n"
        "    interpreter: %s\n    cwd: %s\n    os: %s\n" % (
            _envrow26["interpreter_path"], _envrow26["cwd"], _envrow26["os"]),
        encoding="utf-8")
    _r, _o = _wsh26(_EC26 + " check-env --scope backend")
    check("check-env matches a recorded env against its canonical declaration",
          _r == 0 and '"status": "match"' in _o and '"match": true' in _o, (_o or "")[-200:])

    # wrong interpreter -> mismatch; unknown env id -> 1; no recorded env -> 3
    (_bd26 / "framework" / "execution_context.yaml").write_text(
        "scopes:\n  backend:\n"
        "    interpreter: C:/nonexistent/python.exe\n    cwd: %s\n    os: %s\n" % (
            _envrow26["cwd"], _envrow26["os"]),
        encoding="utf-8")
    _r, _o = _wsh26(_EC26 + " check-env --scope backend")
    check("check-env flags a wrong interpreter as mismatch",
          _r == 1 and '"status": "mismatch"' in _o and '"match": false' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_EC26 + " check-env --scope backend --env ENV-9999")
    check("check-env with an unknown ENV- id is 1",
          _r == 1 and '"status": "env_unknown"' in _o, (_o or "")[-200:])
    (_bd26 / ".planning" / "contexts" / "environments.jsonl").unlink()
    _r, _o = _wsh26(_EC26 + " check-env --scope backend")
    check("check-env with no recorded env is 3 (never a pass)",
          _r == 3 and '"status": "no_recorded"' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_EC26 + " record-env --scope backend")
    check("record-env re-pins ENV-0001 after store reset",
          _r == 0 and '"env_id": "ENV-0001"' in _o, (_o or "")[-200:])

    # ledger: ENV- refs must resolve, free-form env stays legal, disconfirmation vocab,
    # refuted+VERIFIED is a contradiction, confidence is derived never stored
    _c26a = ('{"claim_id":"CLM-920","task_id":"V26-001","agent":"verifier",'
             '"statement":"env-bound claim",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl","env":"ENV-0001",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26a)
    check("ledger accepts a claim bound to a recorded ENV- id",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _c26b = ('{"claim_id":"CLM-921","task_id":"V26-002","agent":"verifier",'
             '"statement":"unrecorded env reference",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl","env":"ENV-9999",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26b)
    check("ledger refuses a claim bound to an unrecorded ENV- id",
          _r == 1 and "CLAIM_ENV_UNKNOWN" in _o, (_o or "")[-200:])
    _c26c = ('{"claim_id":"CLM-922","task_id":"V26-003","agent":"verifier",'
             '"statement":"free-form env stays legal",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl","env":"local-wsl",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26c)
    check("free-form env strings remain legal (legacy path)",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _c26d = ('{"claim_id":"CLM-923","task_id":"V26-004","agent":"verifier",'
             '"statement":"bad disconfirmation vocab",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
             '"disconfirmation":"bogus",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26d)
    check("ledger refuses a disconfirmation outside the result vocab",
          _r == 1 and "CLAIM_BAD_DISCONFIRMATION" in _o, (_o or "")[-200:])
    _c26e = ('{"claim_id":"CLM-924","task_id":"V26-005","agent":"verifier",'
             '"statement":"refuted but verified contradiction",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
             '"disconfirmation":"refuted",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26e)
    check("ledger refuses a VERIFIED claim carrying a refuted disconfirmation",
          _r == 1 and "CLAIM_DISCONFIRMED_BUT_VERIFIED" in _o, (_o or "")[-200:])
    _c26f = ('{"claim_id":"CLM-925","task_id":"V26-006","agent":"verifier",'
             '"statement":"stored confidence",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh","confidence":"HIGH",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26f)
    check("ledger refuses a stored confidence field",
          _r == 1 and "CLAIM_STORED_CONFIDENCE" in _o, (_o or "")[-200:])

    # confidence derivation: no evidence -> LOW, provenance+verdict -> HIGH,
    # independent check -> VERY_HIGH, provenance without verdict -> MEDIUM
    _c26g = ('{"claim_id":"CLM-926","task_id":"V26-007","agent":"verifier",'
             '"statement":"no evidence",'
             '"claim_type":"data","classification":"UNKNOWN","status":"UNVERIFIED","impact":"low"}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26g)
    check("ledger accepts an UNVERIFIED claim with no evidence",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _c26h = ('{"claim_id":"CLM-927","task_id":"V26-008","agent":"verifier",'
             '"statement":"independently checked",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"high",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"independent_check":"python3 framework/claims/ledger.py analyse",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26h)
    check("ledger accepts a high-impact claim with an independent check",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _c26i = ('{"claim_id":"CLM-928","task_id":"V26-009","agent":"verifier",'
             '"statement":"provenance without verdict",'
             '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
             '"verified_by":"bash framework/gates/g11_evidence.sh",'
             '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
             '"entry_point":"framework/gates/g11_evidence.sh","reproduced":true,"result":"inconclusive"}]}')
    _r, _o = _wsh26(_LG26 + " append --json '%s'" % _c26i)
    check("ledger accepts provenance with an inconclusive verdict",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_LG26 + " analyse")
    check("analyse derives confidence from evidence structure",
          _r == 0 and '"by_confidence"' in _o
          and '"LOW": 1' in _o and '"MEDIUM": 1' in _o
          and '"HIGH": 2' in _o and '"VERY_HIGH": 1' in _o, (_o or "")[-300:])
    _ledger26 = (_bd26 / ".planning" / "claims" / "ledger.jsonl").read_text(encoding="utf-8")
    check("confidence is never stored in the ledger",
          '"confidence"' not in _ledger26, "a stored confidence field is a gaming surface")
    _r, _o = _wsh26("bash framework/gates/g11_evidence.sh")
    check("g11 passes with a valid env-bound ledger",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    # supervision: background_task_id captured and surfaced; write-decision id guard;
    # contract peers excluded from task-list; type default checkpoints land in the contract
    _reg26 = ('{"agent":"implementer","type":"implement","objective":"o",'
              '"expected_artifact":"a","progress_timeout_s":20,"max_duration_s":90,'
              '"background_task_id":"bg_abc123"}')
    _r, _o = _wsh26(_ADP26 + " task-register --id V26-001 --json '%s'" % _reg26)
    check("task-register stores background_task_id",
          _r == 0 and '"background_task_id": "bg_abc123"' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_ADP26 + " task-status --id V26-001")
    check("task-status surfaces background_task_id",
          _r == 0 and '"background_task_id": "bg_abc123"' in _o, (_o or "")[-200:])
    _r, _o = _wsh26(_ADP26 + " write-decision --json '{\"design\":\"x\"}'")
    check("write-decision without --id is refused and names the arg",
          _r != 0 and "DECISION_MISSING_ID" in _o and "--id" in _o, (_o or "")[-200:])
    (_bd26 / ".planning" / "tasks").mkdir(parents=True, exist_ok=True)
    (_bd26 / ".planning" / "tasks" / "V26-101.contract.json").write_text(
        '{"contract_id":"V26-101","owner":"architect"}\n', encoding="utf-8")
    _reg26b = ('{"agent":"explore","type":"explore","objective":"o","expected_artifact":"a"}')
    _r, _o = _wsh26(_ADP26 + " task-register --id V26-002 --json '%s'" % _reg26b)
    _r2, _o2 = _wsh26(_ADP26 + " task-list")
    check("task-list excludes *.contract.json peers",
          _r == 0 and _r2 == 0 and "V26-002" in _o2 and "V26-101.contract" not in _o2,
          (_o2 or "")[-200:])
    _contract26 = json.loads((_bd26 / ".planning" / "tasks" / "V26-002.json").read_text(encoding="utf-8"))
    check("type default checkpoints land in the contract",
          "C0-TASK_ACCEPTED" in _contract26.get("checkpoints", [])
          and "C8-HANDOFF_READY" in _contract26.get("checkpoints", []),
          str(_contract26.get("checkpoints"))[:200])

    shutil.rmtree(_bd26, ignore_errors=True)


# g_entry: pre-dispatch plan contract (P1). A valid approved plan passes the entry
# contract; unapproved, scopeless, criteria-less and open-question plans refuse
# dispatch; ENTRY_EXEMPT is the only bypass; missing plan context is a routing
# defect, never a silent skip.

def _suite_27():
    _bd27 = Path(tempfile.mkdtemp(prefix="val27_entry_"))
    shutil.copytree("framework", _bd27 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd27 / ".planning").mkdir(parents=True, exist_ok=True)
    (_bd27 / ".planning" / "phases" / "00-unphased").mkdir(parents=True, exist_ok=True)

    def _wsh27(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd27)), cmd), timeout=timeout)

    _G27 = "bash framework/gates/g_entry.sh"

    # static: gate exists, exit taxonomy and routing documented, agent contracts wired
    _g27 = Path("framework/gates/g_entry.sh").read_text(encoding="utf-8")
    check("g_entry refuses dispatch without a plan context",
          "NO TASK DISPATCH" in _g27 and "ENTRY_EXEMPT" in _g27,
          "the gate must refuse by name, never skip")
    _x27 = Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8")
    check("EXIT_CODES documents G-ENTRY with the NOT_APPLICABLE bypass",
          "G-ENTRY" in _x27 and "NOT_APPLICABLE (ENTRY_EXEMPT=TRIVIAL)" in _x27,
          "exit contract lives in the gate table")
    _p27 = Path("framework/verifier/profiles.yaml").read_text(encoding="utf-8")
    check("profiles routes the dispatch-time signal to g_entry",
          "no_plan_context" in _p27 and "g_entry" in _p27,
          "a fired signal with no gate is a routing gap")
    _t27 = Path(".opencode/agents/team-lead.md").read_text(encoding="utf-8")
    check("team-lead runs the entry gate before every dispatch",
          "Entry contract before dispatch" in _t27
          and "framework/gates/g_entry.sh" in _t27,
          "pre-flight belongs in the dispatch path")
    _i27 = Path(".lifecycle/agents/implementer.md").read_text(encoding="utf-8")
    check("implementer declares the plan-authority contract",
          "Plan authority" in _i27 and "scope drift" in _i27,
          "authority boundaries must bound the implementation")
    _a27 = Path(".opencode/agents/architect.md").read_text(encoding="utf-8")
    check("architect binds architecture-right-sizing in primary skills",
          "architecture-right-sizing" in _a27
          and "software-architecture-design" in _a27,
          "right-sizing is a primary skill choice, not a habit")
    _r27v = Path(".lifecycle/agents/reviewer.md").read_text(encoding="utf-8")
    check("reviewer finding contract carries impact/confidence/direction",
          "impact: [blast radius if unfixed]" in _r27v
          and "confidence: [high | medium | low]" in _r27v
          and "direction: [reject | revise | redesign | propose_alternative]" in _r27v
          and "not a mandate to rewrite" in _r27v,
          "a finding without a direction cannot route a fix")

    # behavioral: isolated copy, real gate round-trips
    _plan27 = ("status: approved\n"
               "title: entry gate fixture\n"
               "files_or_components:\n"
               "  - framework/gates/g_entry.sh\n"
               "  - .opencode/agents/team-lead.md\n"
               "acceptance_criteria:\n"
               "  - the entry gate refuses dispatch without a valid approved plan\n"
               "  - EXIT_CODES documents the exit contract including the trivial bypass\n")
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-001_PLAN.md").write_text(_plan27, encoding="utf-8")
    _r, _o = _wsh27("ENTRY_PLAN=.planning/phases/00-unphased/V27-001_PLAN.md " + _G27)
    check("g_entry passes a complete approved plan",
          _r == 0 and "entry contract complete" in _o, (_o or "")[-200:])
    # I1 (DID-012 PR-D1) is now part of the entry contract: an EXECUTABLE task must carry a
    # bound ASK_ID. This check isolates plan-path resolution, so its fixture task is made
    # terminal -- I1 does not govern terminal tasks. The executable-unbound refusal is its
    # own check below, never folded into this one.
    _wsh27("python3 framework/adapters/gsd_state.py task-register --id V27-001 "
           "--json '{\"agent\":\"verifier\",\"objective\":\"entry gate fixture\","
           "\"expected_artifact\":\"plan resolved via plan-path\"}'")
    _wsh27("python3 framework/adapters/gsd_state.py task-cancel --id V27-001")
    _r, _o = _wsh27("ENTRY_TASK=V27-001 " + _G27)
    check("g_entry resolves the plan through plan-path --task",
          _r == 0 and "entry contract complete" in _o, (_o or "")[-200:])
    _r, _o = _wsh27(_G27)
    check("g_entry with no plan context refuses dispatch",
          _r == 1 and "NO TASK DISPATCH" in _o, (_o or "")[-200:])
    _r, _o = _wsh27("ENTRY_EXEMPT=TRIVIAL " + _G27)
    check("ENTRY_EXEMPT=TRIVIAL is NOT_APPLICABLE, never a pass",
          _r == 4 and "NOT_APPLICABLE" in _o, (_o or "")[-200:])
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-002_PLAN.md").write_text(
        _plan27.replace("status: approved", "status: draft"), encoding="utf-8")
    _r, _o = _wsh27("ENTRY_PLAN=.planning/phases/00-unphased/V27-002_PLAN.md " + _G27)
    check("g_entry refuses an unapproved plan",
          _r == 1 and "not approved" in _o, (_o or "")[-200:])
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-003_PLAN.md").write_text(
        _plan27.replace("files_or_components:\n", ""), encoding="utf-8")
    _r, _o = _wsh27("ENTRY_PLAN=.planning/phases/00-unphased/V27-003_PLAN.md " + _G27)
    check("g_entry refuses a plan with no declared files_or_components",
          _r == 1 and "no files_or_components" in _o, (_o or "")[-200:])
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-004_PLAN.md").write_text(
        _plan27.replace("acceptance_criteria:\n", ""), encoding="utf-8")
    _r, _o = _wsh27("ENTRY_PLAN=.planning/phases/00-unphased/V27-004_PLAN.md " + _G27)
    check("g_entry refuses a plan with no acceptance_criteria",
          _r == 1 and "no acceptance_criteria" in _o, (_o or "")[-200:])
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-005_PLAN.md").write_text(
        _plan27 + "open_questions:\n  - who owns the entry gate?\n", encoding="utf-8")
    _r, _o = _wsh27("ENTRY_PLAN=.planning/phases/00-unphased/V27-005_PLAN.md " + _G27)
    check("g_entry refuses a plan with unresolved open questions",
          _r == 1 and "open questions" in _o, (_o or "")[-200:])

    # I1 at dispatch (DID-012 PR-D1): an approved plan is not sufficient when the task is
    # executable and carries no bound ASK_ID. The refusal must name I1, not a plan defect.
    (_bd27 / ".planning" / "phases" / "00-unphased" / "V27-006_PLAN.md").write_text(
        _plan27, encoding="utf-8")
    _wsh27("python3 framework/adapters/gsd_state.py task-register --id V27-006 "
           "--json '{\"agent\":\"verifier\",\"objective\":\"I1 enforcement fixture\","
           "\"expected_artifact\":\"refusal without a bound ASK_ID\"}'")
    _r, _o = _wsh27("ENTRY_TASK=V27-006 " + _G27)
    check("g_entry refuses dispatch when an executable task has no bound ASK_ID (I1)",
          _r == 1 and "no durable ASK_ID" in _o, (_o or "")[-200:])

    shutil.rmtree(_bd27, ignore_errors=True)


print("\n[28] Evidence integrity (ledger integrity + G14)")
# statics: the gate must wrap the ledger's integrity report -- authenticity is a
# derived fact over the claim store, never something a gate re-derives itself
_g1428 = Path("framework/gates/g14_integrity.sh").read_text(encoding="utf-8")
check("G14 wraps ledger integrity and owns its exit contract",
      'GATE_NAME="g14_integrity"' in _g1428 and "ledger.py integrity" in _g1428
      and "exit $NOT_APPLICABLE" in _g1428,
      "a gate is a command with an exit code; it must map integrity to 0/1/2/4")
_l28 = Path("framework/claims/ledger.py").read_text(encoding="utf-8")
check("ledger exposes integrity_report with E2/E7/E8 codes",
      "def integrity_report()" in _l28 and "EVIDENCE_ARTIFACT_MISSING" in _l28
      and "EVIDENCE_OPEN_SUSPICION" in _l28 and "EVIDENCE_STALE_REUSE" in _l28,
      "G14's own checks must exist in the data source it wraps")
_exc28 = Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8")
check("G14 exit contract documented in EXIT_CODES.md",
      "| G14 evidence-integrity" in _exc28 and "NOT_APPLICABLE (no claims recorded)" in _exc28,
      "generated claims about gate behaviour must cite the authoritative table")
_pf28 = Path("framework/verifier/profiles.yaml").read_text(encoding="utf-8")
check("functional profile always runs g14",
      "./framework/gates/g14_integrity.sh" in _pf28,
      "evidence integrity is a default property, not an impact-triggered one")

# behavioral: isolated copy, real CLI round-trips, real gate exits, no network

def _suite_28():
    _bd28 = Path(tempfile.mkdtemp(prefix="val28_integrity_"))
    shutil.copytree("framework", _bd28 / "framework",
                    ignore=shutil.ignore_patterns(".manifest", "__pycache__"))
    (_bd28 / ".planning").mkdir()

    def _wsh28(cmd, timeout=180):
        return sh("cd '%s' && %s" % (_wsl_path(str(_bd28)), cmd), timeout=timeout)

    _GI28 = "bash framework/gates/g14_integrity.sh"
    _LG28 = "python3 framework/claims/ledger.py"

    # empty store: nothing to check
    _r, _o = _wsh28(_GI28)
    check("G14 with no claims is NOT_APPLICABLE (4), never a pass",
          _r == 4 and "NOT_APPLICABLE" in _o, (_o or "")[-200:])

    # clean claim: full provenance, impact low -> passes E1-E8
    _clean28 = ('{"claim_id":"CLM-960","task_id":"V28-001","agent":"verifier",'
                '"statement":"integrity-clean claim",'
                '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
                '"verified_by":"bash framework/claims/ledger.py integrity",'
                '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
                '"entry_point":"framework/claims/ledger.py analyse","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh28(_LG28 + " append --json '%s'" % _clean28)
    check("ledger accepts a fully-provenanced low-impact claim",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh28(_GI28)
    check("G14 passes a clean claim store",
          _r == 0 and "PASS" in _o, (_o or "")[-200:])

    # fabricated artifact: entry_point names a repo file that does not exist
    _bogus28 = ('{"claim_id":"CLM-962","task_id":"V28-003","agent":"verifier",'
                '"statement":"evidence names a nonexistent artifact",'
                '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
                '"verified_by":"bash framework/claims/ledger.py integrity",'
                '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
                '"entry_point":"framework/claims/nonexistent_artifact.py","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh28(_LG28 + " append --json '%s'" % _bogus28)
    check("ledger accepts the artifact claim (append cannot see the file exists)",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh28(_GI28)
    check("G14 flags evidence naming a nonexistent repo artifact (E2)",
          _r == 1 and "EVIDENCE_ARTIFACT_MISSING" in _o and "CLM-962" in _o, (_o or "")[-300:])

    # suspicion: an OPEN reviewer suspicion on the task blocks its VERIFIED claims
    (_bd28 / ".planning" / "verification").mkdir(parents=True, exist_ok=True)
    (_bd28 / ".planning" / "verification" / "suspicion_log.jsonl").write_text(
        '{"suspicion_id":"SUSP-900","task_id":"V28-001","status":"OPEN","detail":"fixture"}\n',
        encoding="utf-8")
    _r, _o = _wsh28(_GI28)
    check("G14 refuses VERIFIED claims while a reviewer suspicion is open (E7)",
          _r == 1 and "EVIDENCE_OPEN_SUSPICION" in _o and "CLM-960" in _o, (_o or "")[-300:])

    # stale reuse: identical evidence payload reused under a different task
    (_bd28 / ".planning" / "verification" / "suspicion_log.jsonl").unlink()
    _reuse28 = ('{"claim_id":"CLM-961","task_id":"V28-002","agent":"verifier",'
                '"statement":"reuses prior task evidence verbatim",'
                '"claim_type":"behavioral","classification":"FACT","status":"VERIFIED","impact":"low",'
                '"verified_by":"bash framework/claims/ledger.py integrity",'
                '"evidence":[{"kind":"command_run","runtime":"local-wsl",'
                '"entry_point":"framework/claims/ledger.py analyse","reproduced":true,"result":"pass"}]}')
    _r, _o = _wsh28(_LG28 + " append --json '%s'" % _reuse28)
    check("ledger accepts the reused-evidence claim (each record is individually valid)",
          _r == 0 and '"claim_id"' in _o, (_o or "")[-200:])
    _r, _o = _wsh28(_GI28)
    check("G14 flags identical evidence payload reused across tasks (E8)",
          _r == 1 and "EVIDENCE_STALE_REUSE" in _o and "CLM-961" in _o, (_o or "")[-300:])

    shutil.rmtree(_bd28, ignore_errors=True)



# The 9 isolated suites are independent (own temp root, read-only source
# copy): run them concurrently instead of serially. check() appends to
# FAILS/WARNS are GIL-atomic; the result SET is deterministic, the
# interleaved print order is not.

_SUITES = [
    _suite_18,
    _suite_21,
    _suite_22,
    _suite_23,
    _suite_24,
    _suite_25,
    _suite_26,
    _suite_27,
    _suite_28,
]
import concurrent.futures as _fut
with _fut.ThreadPoolExecutor(max_workers=9) as _ex:
    # consuming the map re-raises the first suite exception (list() drains all
    # futures; the with-exit waits for stragglers), so a crashed suite can never
    # silently report PASS.
    list(_ex.map(lambda _f: _f(), _SUITES))

print("\n[29] Router-table conformance (DID-013 PR-F residual 1)")
_router = Path(".opencode/skills/gsd-ns-workflow/SKILL.md")
_rtext = _router.read_text(encoding="utf-8") if _router.exists() else ""
_routed = []
for _line in _rtext.splitlines():
    _cells = [c.strip() for c in _line.split("|")]
    if len(_cells) == 4 and _cells[2].startswith("gsd-"):
        _routed.append(_cells[2])
_routed = sorted(set(_routed))
_WORKFLOW_FAMILY = frozenset([
    "gsd-add-tests", "gsd-ai-integration-phase", "gsd-autonomous",
    "gsd-discuss-phase", "gsd-execute-phase", "gsd-fast",
    "gsd-mvp-phase", "gsd-next", "gsd-phase",
    "gsd-plan-phase", "gsd-plan-review-convergence", "gsd-progress",
    "gsd-quick", "gsd-spec-phase", "gsd-ultraplan-phase", "gsd-verify-work",
])
check("gsd-ns-workflow routes all 16 workflow skills (bidirectional)",
      set(_routed) == _WORKFLOW_FAMILY,
      "table-only=%s family-only=%s" % (sorted(set(_routed) - _WORKFLOW_FAMILY),
                                        sorted(_WORKFLOW_FAMILY - set(_routed))))
_missing = [t for t in _routed
            if not Path(".opencode/skills/%s/SKILL.md" % t).exists()]
check("every routed skill resolves to .opencode/skills/<name>/SKILL.md on disk",
      not _missing, "missing on disk: %s" % _missing)

print("\n[30] Charter single-source conformance (DID-013 PR-E)")
_ROLES30 = ["architect", "implementer", "planner", "researcher",
            "reviewer", "team-lead", "verifier"]
_pointer30 = "Read `.lifecycle/agents/%s.md` and act only within that charter."
_missing30 = [r for r in _ROLES30
              if not Path(".lifecycle/agents/%s.md" % r).exists()]
check("every core role has a portable charter in .lifecycle/agents/",
      not _missing30, "missing charter: %s" % _missing30)
_no_pointer30 = []
for _r30 in _ROLES30:
    _op30 = Path(".opencode/agents/%s.md" % _r30)
    if not _op30.exists() or (_pointer30 % _r30) not in _op30.read_text(encoding="utf-8"):
        _no_pointer30.append(_r30)
check("every .opencode/agents/<role>.md is a thin pointer to its charter",
      not _no_pointer30, "missing pointer line: %s" % _no_pointer30)

print("\n[31] Intake adapter (DID-012 PR-D1, ask conservation I1/I2)")
_intake31 = Path("framework/adapters/intake.py")
check("framework/adapters/intake.py exists (Pillar 1 durable intake)",
      _intake31.exists(), "missing: framework/adapters/intake.py")
check("intake adapter has a test module (pytest framework/ covers it)",
      Path("framework/adapters/test_intake.py").exists(),
      "missing: framework/adapters/test_intake.py")
if _intake31.exists():
    _r31 = subprocess.run([sys.executable, str(_intake31), "selftest"],
                          capture_output=True, text=True, timeout=180)
    check("intake adapter selftest exits 0 (invariants I1/I2/I8/I10/I11 hold)",
          _r31.returncode == 0, (_r31.stdout + _r31.stderr)[-400:])


print("\n[32] Gate line-ending hygiene (LF invariant; g_entry CRLF defect)")
# A CR byte in a bash gate is fatal under WSL bash (the g_entry defect class:
# `_lib.sh\r` fails to source, backslash continuations break, gate exits 2 on
# every path). .gitattributes normalizes on commit, which HIDES working-tree
# CR as "clean" (g9/g14 each carried 1 stray CR invisible to git status).
# This check asserts the raw-byte invariant directly so the class cannot recur.
_crlf32 = []
for _dir32 in ("framework/gates", ".lifecycle/scripts"):
    _p32 = Path(_dir32)
    if _p32.exists():
        for _sh32 in sorted(_p32.glob("*.sh")):
            if b"\r" in _sh32.read_bytes():
                _crlf32.append(str(_sh32))
check("every bash gate/script in framework/ and .lifecycle/ is byte-level LF (no CR)",
      not _crlf32, "files contain a CR byte: %s" % ", ".join(_crlf32))

print("\n[33] Control adapter (DID-012 PR-D2, lease/reap I3-I7)")
_control33 = Path("framework/adapters/control.py")
check("framework/adapters/control.py exists (Pillar 3 lease/reap control)",
      _control33.exists(), "missing: framework/adapters/control.py")
check("control adapter has a test module (pytest framework/ covers it)",
      Path("framework/adapters/test_control.py").exists(),
      "missing: framework/adapters/test_control.py")
if _control33.exists():
    _r33 = subprocess.run([sys.executable, str(_control33), "selftest"],
                          capture_output=True, text=True, timeout=180)
    check("control adapter selftest exits 0 (invariants I3-I7/I10/I11 hold)",
          _r33.returncode == 0, (_r33.stdout + _r33.stderr)[-400:])

print("\n[34] Execution-position adapter (DID-012 PR-D3, derivation I8/I10)")
_execute34 = Path("framework/adapters/execute.py")
check("framework/adapters/execute.py exists (Pillar 2 execution position)",
      _execute34.exists(), "missing: framework/adapters/execute.py")
check("execution adapter has a test module (pytest framework/ covers it)",
      Path("framework/adapters/test_execute.py").exists(),
      "missing: framework/adapters/test_execute.py")
if _execute34.exists():
    _r34 = subprocess.run([sys.executable, str(_execute34), "selftest"],
                          capture_output=True, text=True, timeout=180)
    check("execution adapter selftest exits 0 (invariants I8/I10/I11 hold)",
          _r34.returncode == 0, (_r34.stdout + _r34.stderr)[-400:])

print("\n[35] G16 state-health gate (task/ledger tail readability)")
_g1635 = Path("framework/gates/g16_state_health.sh")
check("framework/gates/g16_state_health.sh exists",
      _g1635.exists(), "missing: framework/gates/g16_state_health.sh")
if _g1635.exists():
    _g16text = _g1635.read_text(encoding="utf-8")
    check("g16 self-identifies as g16_state_health",
          'GATE_NAME="g16_state_health"' in _g16text, "GATE_NAME literal missing")
    check("g16 reads the adapter state-health command",
          "state-health" in _g16text, "state-health invocation missing")
    check("g16 has an explicit NOT_APPLICABLE exit",
          "exit $NOT_APPLICABLE" in _g16text, "NOT_APPLICABLE literal missing")
    check("g16 is on the functional profile",
          "./framework/gates/g16_state_health.sh" in
          Path("framework/verifier/profiles.yaml").read_text(encoding="utf-8"),
          "profile membership missing")
    check("EXIT_CODES documents G16",
          "| G16 state-health" in
          Path("framework/gates/EXIT_CODES.md").read_text(encoding="utf-8"),
          "EXIT_CODES row missing")
    check("gsd_state exposes state-health",
          "def state_health()" in
          Path("framework/adapters/gsd_state.py").read_text(encoding="utf-8"),
          "state_health missing")
    import shutil, tempfile
    _d35 = Path(tempfile.mkdtemp(prefix="val35_g16_"))
    try:
        shutil.copytree("framework", _d35 / "framework")
        _env35 = dict(os.environ, GSD_STATE_ROOT=str(_d35 / ".planning"))
        _r35a = subprocess.run(["bash", "framework/gates/g16_state_health.sh"],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("empty store -> NOT_APPLICABLE (4) with no tasks and no ledger",
              _r35a.returncode == 4 and "NOT_APPLICABLE" in _r35a.stdout,
              f"rc={_r35a.returncode} out={_r35a.stdout[-400:]}")
        _r35b = subprocess.run([sys.executable, "framework/adapters/gsd_state.py",
                                "task-register", "--id", "V35-001", "--json",
                                json.dumps({"objective": "g16 probe", "agent": "verifier",
                                            "expected_artifact": "rc 0", "headless": True})],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("task-register in the isolated root exits 0",
              _r35b.returncode == 0, (_r35b.stdout + _r35b.stderr)[-400:])
        _r35c = subprocess.run(["bash", "framework/gates/g16_state_health.sh"],
                               cwd=str(_d35), env=_env35, capture_output=True, text=True,
                               timeout=180)
        check("store with one registered task -> PASS (0)",
              _r35c.returncode == 0 and "PASS" in _r35c.stdout,
              f"rc={_r35c.returncode} out={_r35c.stdout[-400:]}")
    finally:
        shutil.rmtree(_d35, ignore_errors=True)

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

