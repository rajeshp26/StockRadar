#!/usr/bin/env bash
# Regression test for framework/gates/g4_executable.sh's per-language branches.
#
# Each check below reproduces, mechanically, a verification step done by hand
# during this framework's audit: a deliberately bad fixture must fail the gate,
# a clean fixture (or a missing-tool scenario) must not silently pass vacuously.
#
# Design rule for these tests: every assertion must be able to FAIL. A test whose
# expected exit code is produced by some other defect than the one it is guarding
# passes just as happily against the broken gate as against the fixed one, and is
# worse than no test at all because it reads as coverage. Two consequences here:
#   * Assertions check the DIAGNOSTIC the gate emits, not just its exit code. A
#     tool reported "unavailable" must never be reported "FAIL", and vice versa --
#     those are different states (rule 2), so the test distinguishes them.
#   * Gating a regression behind an unrelated tool's presence made it unrunnable in
#     exactly the environment where the bug lived. Fixtures that can be made
#     tool-independent run unconditionally; a stub is used where a real binary
#     would otherwise be required.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
G4="$HERE/g4_executable.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Resolve tools the same way the gates do. Without this the suite's own `have ruff` /
# `have pytest` answered "no" on Windows even though both were installed, so the budget
# and pytest cases below skipped on precisely the platform their bug lived on -- the
# exact harness defect this file's header warns about ("gating a regression behind an
# unrelated tool's presence made it unrunnable in the environment where the bug lived").
# One case further down tests the resolver itself; every other case needs it to work.
. "$HERE/_toolchain.sh"

pass=0; fail=0; skip=0

expect_exit() {
  local desc="$1" dir="$2" want="$3"
  local out
  out="$(cd "$dir" && bash "$G4" 2>&1)"
  local got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'PASS  %s (exit %d as expected)\n' "$desc" "$got"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (expected exit %d, got %d)\n---\n%s\n---\n' "$desc" "$want" "$got" "$out"
    fail=$((fail+1))
  fi
}

# Assert exit code AND that the gate named the cause correctly. `needle` and
# `anti` are matched against the gate's combined output; a regex in `needle` may
# be supplied when the exact wording is not contractual.
expect_exit_saying() {
  local desc="$1" dir="$2" want="$3" needle="$4" anti="${5:-}"
  local out got
  out="$(cd "$dir" && bash "$G4" 2>&1)"
  got=$?
  local why=""
  [ "$got" -eq "$want" ] || why="${why}exit $got != $want; "
  printf '%s' "$out" | grep -qE "$needle" || why="${why}output lacks /$needle/; "
  if [ -n "$anti" ]; then
    printf '%s' "$out" | grep -qE "$anti" && why="${why}output wrongly contains /$anti/; "
  fi
  if [ -z "$why" ]; then
    printf 'PASS  %s (exit %d, correct diagnostic)\n' "$desc" "$got"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (%s)\n---\n%s\n---\n' "$desc" "$why" "$out"
    fail=$((fail+1))
  fi
}

skip_case() { printf 'SKIP  %s (%s not on PATH / not configured)\n' "$1" "$2"; skip=$((skip+1)); }

have() { command -v "$1" >/dev/null 2>&1; }

# A stub gitleaks that finds nothing, so the language-agnostic secrets branch is
# exercisable on machines that do not have the real thing. Needed only for
# fixtures that deliberately detect NO language, where the secrets scan is
# otherwise the sole thing that can make `ran` nonzero -- and without it the gate
# correctly fails with "no executable checks found", which would mask what the
# test is actually asserting.
STUB_BIN="$TMP/stub_bin"
make_secret_stub() {
  mkdir -p "$STUB_BIN"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB_BIN/gitleaks"
  chmod +x "$STUB_BIN/gitleaks"
}
run_with_secret_stub() {
  local dir="$1"
  (cd "$dir" && PATH="$STUB_BIN:$PATH" bash "$G4" 2>&1)
}

# ── JS: unavailable vs failing linter (the platform-independence regression) ────
# A declared "lint" script whose binary is not installed must be reported
# UNAVAILABLE and must not be counted as static coverage. Reproduced during
# external review: mark_static was called unconditionally on the `grep` match, so
# a linter that never ran still earned javascript its static-analysis coverage.
# The revision that claimed to fix this branched on exit 127, which cannot occur
# on Windows (npm and cmd.exe both report a missing binary as 1), so the branch
# was dead there and the bug survived the "fix".
if have npm; then
  # (a) Linter absent: node_modules present but empty of tools. javascript must end
  # up with zero static coverage, so the gate fails AND names the missing binary.
  # Before the fix this fixture passed, because mark_static javascript fired off the
  # grep match alone.
  mkdir -p "$TMP/js_lint_absent/node_modules" "$TMP/js_lint_absent/src"
  cat > "$TMP/js_lint_absent/package.json" <<'EOF'
{"name":"x","version":"1.0.0","scripts":{"lint":"eslint src --max-warnings=0"}}
EOF
  cat > "$TMP/js_lint_absent/src/App.jsx" <<'EOF'
export default function App(){ return <div>hi</div> }
EOF
  expect_exit_saying \
    "JS: declared lint script with uninstalled binary is UNAVAILABLE and never counted as static coverage" \
    "$TMP/js_lint_absent" 1 "lint-binary\(" "zero static analysis executed.*eslint"

  # (b) Linter present and green: static coverage must be earned, so the gate passes.
  # This is the falsifiable half of the pair -- if (a) were made to pass by simply
  # failing every JS fixture, (b) would catch it.
  mkdir -p "$TMP/js_lint_ok/node_modules/.bin" "$TMP/js_lint_ok/src"
  cat > "$TMP/js_lint_ok/package.json" <<'EOF'
{"name":"x","version":"1.0.0","scripts":{"lint":"eslint src --max-warnings=0"}}
EOF
  cat > "$TMP/js_lint_ok/src/App.jsx" <<'EOF'
export default function App(){ return <div>hi</div> }
EOF
  # npm resolves node_modules/.bin/* onto PATH for scripts; provide both a POSIX
  # shim and a .cmd shim so this works under Git Bash and WSL alike.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/js_lint_ok/node_modules/.bin/eslint"
  chmod +x "$TMP/js_lint_ok/node_modules/.bin/eslint"
  printf '@exit /b 0\r\n' > "$TMP/js_lint_ok/node_modules/.bin/eslint.cmd"
  expect_exit_saying \
    "JS: installed, green linter DOES earn static coverage (counter-test for the case above)" \
    "$TMP/js_lint_ok" 0 "checks green" "FAIL lint"

  # (c) Linter present but reporting real problems: the gate must FAIL and say the
  # linter FAILED -- it must not launder a genuine finding into an "unavailable"
  # diagnostic. This is the direction the exit-127 branch got wrong in the other
  # direction: there, `run` had already set rc=1 and the branch would have
  # announced the tool as unavailable while failing because of it.
  mkdir -p "$TMP/js_lint_fails/node_modules/.bin" "$TMP/js_lint_fails/src"
  cat > "$TMP/js_lint_fails/package.json" <<'EOF'
{"name":"x","version":"1.0.0","scripts":{"lint":"eslint src --max-warnings=0"}}
EOF
  cat > "$TMP/js_lint_fails/src/App.jsx" <<'EOF'
export default function App(){ return <div>hi</div> }
EOF
  printf '#!/usr/bin/env bash\necho "eslint: 1 problem" >&2\nexit 1\n' > "$TMP/js_lint_fails/node_modules/.bin/eslint"
  chmod +x "$TMP/js_lint_fails/node_modules/.bin/eslint"
  printf '@exit /b 1\r\n' > "$TMP/js_lint_fails/node_modules/.bin/eslint.cmd"
  expect_exit_saying \
    "JS: installed linter reporting real errors FAILS, and is not mislabelled unavailable" \
    "$TMP/js_lint_fails" 1 "FAIL lint" "lint-binary\("
else
  skip_case "JS linter availability branch" npm
fi

# ── JS: vacuous pass via the secrets scan ──────────────────────────────────────
# Real .jsx source, package.json with no "lint" script and no node_modules, no
# other language present. Before the per-language coverage fix the secrets scan
# alone (finding nothing) satisfied G4's "at least one check ran" bar and the gate
# reported PASS -- the React code itself was never linted.
make_secret_stub
mkdir -p "$TMP/react_no_lint"
cat > "$TMP/react_no_lint/package.json" <<'EOF'
{"name":"x","version":"1.0.0","scripts":{}}
EOF
cat > "$TMP/react_no_lint/App.jsx" <<'EOF'
export default function App(){ const x = 5 * 86400; return <div>{x}</div> }
EOF
out="$(run_with_secret_stub "$TMP/react_no_lint")"; got=$?
if [ "$got" -eq 1 ] && printf '%s' "$out" | grep -q "never checked"; then
  printf 'PASS  %s (exit %d, correct reason)\n' "Vacuous-pass regression: JS present, unconfigured, secrets-clean -> must still FAIL" "$got"
  pass=$((pass+1))
else
  printf 'FAIL  %s (expected exit 1 naming an unchecked language, got exit %d)\n---\n%s\n---\n' \
    "Vacuous-pass regression: JS present, unconfigured, secrets-clean -> must still FAIL" "$got" "$out"
  fail=$((fail+1))
fi

# ── C: virtualenv headers are not project source ───────────────────────────────
# Runs unconditionally. An earlier revision nested this behind `if have cppcheck`,
# which is unrelated to what it tests -- cppcheck's presence has no bearing on
# whether the C/C++ *discovery* step misreads a virtualenv as project source -- so
# on any machine without cppcheck (the common case) the regression went untested.
# The fixture still needs one check to run, or the gate correctly fails earlier
# with "no executable checks found"; the stub gitleaks supplies exactly that, and
# detects no language, so it cannot stand in for language-specific coverage.
mkdir -p "$TMP/venv_no_c/backend/venv/include/python3.11" "$TMP/venv_no_c/.venv/include"
for i in 1 2 3; do
  touch "$TMP/venv_no_c/backend/venv/include/python3.11/hdr$i.h"
  touch "$TMP/venv_no_c/.venv/include/hdr$i.h"
done
out="$(run_with_secret_stub "$TMP/venv_no_c")"; got=$?
if [ "$got" -eq 0 ]; then
  printf 'PASS  %s (exit %d as expected)\n' "C: virtualenv headers must not be mistaken for project C/C++ source" "$got"
  pass=$((pass+1))
else
  printf 'FAIL  %s (expected exit 0, got %d)\n---\n%s\n---\n' \
    "C: virtualenv headers must not be mistaken for project C/C++ source" "$got" "$out"
  fail=$((fail+1))
fi

# ── C / C++ ────────────────────────────────────────────────────────────────────
if have cppcheck; then
  mkdir -p "$TMP/c_bad"
  cat > "$TMP/c_bad/bad.c" <<'EOF'
int add(int a, int b) {
    return a + b;
}
EOF
  # A bare function definition with no prior compatible declaration is a real,
  # verified MISRA C 2012 rule 8.4 violation -- this fixture is intentionally
  # "clean C" by any non-MISRA measure to prove the addon itself is wired in,
  # not just cppcheck's ordinary bug-finding checks.
  expect_exit "C: MISRA-only violation fails the gate" "$TMP/c_bad" 1
else
  skip_case "C/C++ MISRA branch" cppcheck
fi

# ── Java ───────────────────────────────────────────────────────────────────────
if have java && [ -n "${CHECKSTYLE_JAR:-}" ] && [ -f "${CHECKSTYLE_JAR:-/nonexistent}" ]; then
  mkdir -p "$TMP/java_bad"
  cat > "$TMP/java_bad/Bad.java" <<'EOF'
package com.example;

public class Bad {
    public int calculate(int x) {
        return x * 86400 + 42;
    }
}
EOF
  expect_exit "Java: magic numbers fail the gate (checkstyle)" "$TMP/java_bad" 1

  mkdir -p "$TMP/java_good"
  cat > "$TMP/java_good/Good.java" <<'EOF'
package com.example;

public class Good {
    private static final int SECONDS_PER_DAY = 86400;

    public int calculate(int x) {
        return x * SECONDS_PER_DAY;
    }
}
EOF
  expect_exit "Java: named constant passes the gate" "$TMP/java_good" 0
else
  skip_case "Java branch" "java + \$CHECKSTYLE_JAR"
fi

# ── Python ─────────────────────────────────────────────────────────────────────
if have bandit; then
  mkdir -p "$TMP/py_bad"
  cat > "$TMP/py_bad/bad.py" <<'EOF'
import subprocess

def run(cmd):
    subprocess.call(cmd, shell=True)
EOF
  expect_exit "Python: shell=True fails the gate (bandit)" "$TMP/py_bad" 1
else
  skip_case "Python security branch" bandit
fi

# Static-analysis-specifically regression: a language covered ONLY by a passing
# test, with every static tool (ruff/mypy/bandit) unavailable, must still fail --
# a test proves the behavior it asserts, not the absence of a hardcoded secret
# nobody wrote a test for. Reproduced and fixed during this framework's audit.
# Simulated by shimming PATH to expose pytest but hide ruff/mypy/bandit, since on
# most machines running this suite all four live in the same bin directory.
if have pytest && have python3; then
  SHIM="$TMP/shim_bin"; mkdir -p "$SHIM"
  # Resolve a binary to an EXECUTABLE FILE, never to a bare builtin name.
  # `command -v printf` returns "printf" (a builtin) under bash, so `ln -sf`
  # created a link to a nonexistent RELATIVE path. The shim silently lost
  # printf/true/false, the case below could not run, and the suite reported a
  # FAILURE of the gate under test rather than a broken harness -- the wrong
  # direction for a diagnostic. `type -P` forces a PATH search restricted to
  # executable files (GNU bash manual, `type [-afptP]`), which returns a real
  # path even for a builtin. Measured on this host under WSL bash 5.2.21
  # (uname=Linux, bash=/usr/bin/bash) over 34 probe names: `command -v` returns 3
  # results that are not existing files (printf, true, false); `type -P` returns
  # 0. A shim built with `command -v` yields 33 links with 3 BROKEN (false,
  # printf, true); this binpath plus the -e guard yields 33 links with 0 broken.
  # Reproduce with `bash .planning/patches/probe_shim.sh` (cwd = patches/).
  # SCOPE LIMIT: that probe exercises the resolver and shim in isolation. It does
  # NOT run the enclosing suite, and it CANNOT: this block sits behind
  # `have pytest && have python3`, and pytest is ABSENT on this host (the same
  # probe reports pytest(absent)). Running the suite here would SKIP the block
  # and report nothing about it. `command -v` is still correct as a PRESENCE test
  # (see _lib.sh:183 have()); only its use as a symlink TARGET is wrong.
  binpath() {
    local p; p="$(type -P "$1" 2>/dev/null)" || p=""
    [ -n "$p" ] || p="$(command -v "$1" 2>/dev/null)" || p=""
    printf '%s' "$p"
  }
  # Guarded like the loop below: an unresolvable name makes `ln -sf ""` write a
  # stderr line that reads like a gate failure, so name the missing binary
  # instead of letting the shim imply one.
  for b in pytest python3; do
    p="$(binpath "$b")"
    if [ -n "$p" ] && [ -e "$p" ]; then ln -sf "$p" "$SHIM/$b"
    else echo "shim: cannot resolve $b to an executable file" >&2; fi
  done
  for b in bash sh grep sed find sort head tail cat mkdir rm printf env \
           dirname basename date wc tr awk cut xargs git uname id readlink \
           realpath expr sleep touch chmod true false; do
    p="$(binpath "$b")"
    # The -e guard is what makes a broken shim fail loudly: a bare builtin name
    # would create a link to a nonexistent path and the case would then fail for
    # the wrong reason.
    if [ -n "$p" ] && [ -e "$p" ]; then ln -sf "$p" "$SHIM/$b"; fi
  done

  mkdir -p "$TMP/py_static_gap/tests"
  cat > "$TMP/py_static_gap/app.py" <<'EOF'
def compute(x):
    return x * 86400 + 42
EOF
  cat > "$TMP/py_static_gap/tests/test_trivial.py" <<'EOF'
def test_trivial():
    assert True
EOF
  out="$(cd "$TMP/py_static_gap" && env -i PATH="$SHIM" HOME="$HOME" bash "$G4" 2>&1)"
  got=$?
  if [ "$got" -eq 1 ] && printf '%s' "$out" | grep -q "zero static analysis"; then
    printf 'PASS  %s (exit %d, correct reason)\n' "Static-analysis-only regression: test-only Python coverage must FAIL" "$got"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (expected exit 1 with a static-analysis message, got exit %d)\n---\n%s\n---\n' \
      "Static-analysis-only regression: test-only Python coverage must FAIL" "$got" "$out"
    fail=$((fail+1))
  fi
else
  skip_case "static-analysis-only regression" "pytest + python3"
fi

# ── Windows/WSL toolchain resolution ───────────────────────────────────────────
# On Windows the only bash is WSL's, and WSL resolves a command name to a file of
# exactly that name. Windows toolchains install `node.exe`, `ruff.exe`, `pytest.exe`,
# so `command -v node` returned nothing while /mnt/c/nvm4w/nodejs/node.exe sat on
# PATH. Measured consequence: G4 reported `FAIL types` (node_modules/.bin/tsc is
# `exec node`) and reported Python as having "zero static analysis" because
# ruff/mypy/bandit were all invisible -- on every Windows host, on every run.
#
# The test finds the tools this host exposes ONLY as .exe, then asserts that sourcing
# _toolchain.sh makes every one of them resolvable. It is falsifiable in both
# directions: with an empty .exe-only set it SKIPs rather than claiming a pass, and
# if the resolver stopped working the AFTER lines would read no.
if grep -qi microsoft /proc/version 2>/dev/null; then
  cat > "$TMP/toolchain_probe.sh" <<'PROBE'
#!/usr/bin/env bash
# $1 = path to _toolchain.sh, $2 = shim dir already on PATH (removed to restore the
# pre-fix state this case has to observe)
if [ -n "${2:-}" ]; then
  PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vxF "$2" | tr '\n' ':')"
fi
TOOLS="node npm npx tsc eslint prettier ruff mypy bandit pytest gitleaks cppcheck java javac"
exe_only=""
for t in $TOOLS; do
  command -v "$t" >/dev/null 2>&1 && continue
  for d in $(printf '%s' "$PATH" | tr ':' '\n'); do
    if [ -n "$d" ] && [ -x "$d/$t.exe" ]; then exe_only="$exe_only $t"; break; fi
  done
done
printf 'EXE_ONLY=%s\n' "${exe_only# }"
. "$1"
for t in $exe_only; do
  a=no; command -v "$t" >/dev/null 2>&1 && a=yes
  printf 'AFTER %s=%s\n' "$t" "$a"
done
PROBE
  probe_out="$(bash "$TMP/toolchain_probe.sh" "$HERE/_toolchain.sh" "${_FRAMEWORK_TOOLCHAIN_DIR:-}" 2>&1)"
  exe_only="$(printf '%s\n' "$probe_out" | sed -n 's/^EXE_ONLY=//p')"
  if [ -z "$exe_only" ]; then
    skip_case "WSL .exe toolchain resolution" "no tool is exposed only as .exe on this host"
  else
    unresolved="$(printf '%s\n' "$probe_out" | sed -n 's/^AFTER \([^=]*\)=no$/\1/p')"
    if [ -z "$unresolved" ]; then
      printf 'PASS  %s (resolved .exe-only: %s)\n' \
        "WSL interop: sourcing _toolchain.sh resolves every .exe-only tool" "$exe_only"
      pass=$((pass+1))
    else
      printf 'FAIL  %s (still unresolved after _toolchain.sh: %s)\n---\n%s\n---\n' \
        "WSL interop: sourcing _toolchain.sh resolves every .exe-only tool" "$unresolved" "$probe_out"
      fail=$((fail+1))
    fi
  fi
else
  skip_case "WSL .exe toolchain resolution" "not running under WSL"
fi

# ── Static-analysis budget: the ratchet must ratchet ───────────────────────────
# A tree-wide linter on a repository with history reports every pre-existing finding,
# so G4 could never pass there and therefore never ran. framework/tools/lint_budget.py
# records the existing findings per (file, rule) and fails only on NEW ones.
#
# These cases test the GATE INTEGRATION, not the module's comparison logic (that has
# its own --self-test). Each fixture carries a copy of the real tool so the gate takes
# its budget path, and a ruff config that keeps the copied tool out of its own scan.
if have ruff; then
  make_budget_fixture() {
    local dir="$1"
    mkdir -p "$dir/src" "$dir/framework/tools" "$dir/framework/quality"
    cp "$HERE/../tools/lint_budget.py" "$dir/framework/tools/lint_budget.py"
    # The copied tool is itself Python; without this it would be scanned and its own
    # findings would land in the budget the case asserts on.
    cat > "$dir/pyproject.toml" <<'EOF'
[tool.ruff]
extend-exclude = ["framework"]
EOF
    # One genuine finding: an unused import (ruff F401).
    cat > "$dir/src/app.py" <<'EOF'
import os


def add(a, b):
    return a + b
EOF
    ( cd "$dir" && python3 framework/tools/lint_budget.py update --reason "fixture seed" >/dev/null 2>&1 )
  }

  # (a) Findings are recorded, nothing changed: the gate must PASS. This is the
  # falsifiable half -- without it, (b)/(c) could be satisfied by failing every
  # fixture that has a budget, which would prove nothing.
  make_budget_fixture "$TMP/budget_ok"
  expect_exit_saying \
    "Budget: recorded finding passes, reported as debt not failure" \
    "$TMP/budget_ok" 0 "0 file\(s\) with new findings" "NEW finding"

  # (b) A NEW finding above the budget must FAIL the gate, and must say which. Same
  # tree, same budget, one added violation -- the only difference is the new error.
  make_budget_fixture "$TMP/budget_new"
  cat > "$TMP/budget_new/src/app.py" <<'EOF'
import os
import sys


def add(a, b):
    return a + b
EOF
  expect_exit_saying \
    "Budget: a NEW finding above the budget FAILS the gate" \
    "$TMP/budget_new" 1 "NEW finding" 

  # (c) No budget file at all is zero tolerance, not "everything is new debt to
  # accept". This is what keeps the ratchet from being able to raise itself.
  make_budget_fixture "$TMP/budget_absent"
  rm -f "$TMP/budget_absent/framework/quality/baseline.json"
  expect_exit_saying \
    "Budget: absent budget means zero tolerance, same verdict as raw ruff" \
    "$TMP/budget_absent" 1 "NEW finding"

  # (d) A budget produced by a different linter version must BLOCK, never be compared
  # silently. Findings are a function of the linter: an upgraded ruff that adds a rule
  # would otherwise "create" hundreds of findings and read as a developer's mistake.
  make_budget_fixture "$TMP/budget_drift"
  python3 - "$TMP/budget_drift/framework/quality/baseline.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["tool_version"] = "ruff 0.0.0-not-installed"
json.dump(d, open(p, "w"), indent=2, sort_keys=True)
PY
  expect_exit_saying \
    "Budget: linter version drift BLOCKS and is not counted as static coverage" \
    "$TMP/budget_drift" 1 "ruff-budget\("

  # (e) The documented standalone command must resolve the linter ITSELF. The gate
  # sources _toolchain.sh, so the gate working proves nothing about the command the
  # README tells a human to run. Measured bug: under WSL,
  # `python3 framework/tools/lint_budget.py check` printed BLOCKED ("ruff not found on
  # PATH") on a machine where ruff.exe was installed and the gate was green, because
  # shutil.which does not try Windows extensions when it is not on Windows. The stub
  # below is reachable ONLY as `ruff.exe`, and the gate's shim directory is removed
  # from PATH, so this case fails if the tool ever goes back to a bare which().
  mkdir -p "$TMP/standalone_bin" "$TMP/standalone/src" \
           "$TMP/standalone/framework/tools" "$TMP/standalone/framework/quality"
  cp "$HERE/../tools/lint_budget.py" "$TMP/standalone/framework/tools/lint_budget.py"
  cat > "$TMP/standalone_bin/ruff.exe" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  --version) echo "ruff 0.0.1-stub"; exit 0 ;;
esac
echo "[]"
exit 0
STUB
  chmod +x "$TMP/standalone_bin/ruff.exe"
  CLEAN_PATH="$PATH"
  if [ -n "${_FRAMEWORK_TOOLCHAIN_DIR:-}" ]; then
    CLEAN_PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vxF "$_FRAMEWORK_TOOLCHAIN_DIR" | tr '\n' ':')"
  fi
  ( cd "$TMP/standalone" && PATH="$TMP/standalone_bin:$CLEAN_PATH" \
      python3 framework/tools/lint_budget.py update --reason "standalone resolver fixture" ) \
    >/dev/null 2>&1
  standalone_out="$( cd "$TMP/standalone" && PATH="$TMP/standalone_bin:$CLEAN_PATH" \
      python3 framework/tools/lint_budget.py check 2>&1 )"
  standalone_rc=$?
  if [ "$standalone_rc" -eq 0 ] && printf '%s' "$standalone_out" | grep -q '0 file(s) with new findings'; then
    printf 'PASS  %s (exit 0, .exe-only linter resolved without the gate shim)\n' \
      "Budget: the documented standalone command resolves an .exe-only linter"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (exit %d)\n---\n%s\n---\n' \
      "Budget: the documented standalone command resolves an .exe-only linter" \
      "$standalone_rc" "$standalone_out"
    fail=$((fail+1))
  fi
else
  skip_case "static-analysis budget gate integration" ruff
fi

# ── pytest: one run per project, correct attribution ───────────────────────────
# Three failures this block pins down, each measured on a real monorepo:
#   1. a subproject's own pytest config must be the one applied;
#   2. a subproject must not be collected a second time by the repo-root run;
#   3. a pytest config option no installed plugin provides must be reported
#      UNAVAILABLE, never as the failure of every test that plugin would drive.
if have pytest && have python3; then
  CLEAN_PY='def add(a, b):
    return a + b
'

  # (1) Config scope. pytest resolves its configfile from the directory it runs in.
  # The fixture's subproject sets addopts = "-k zzz_nothing", which selects no test.
  # If the gate ran svc from the repo root, that addopts line would never be read and
  # the test would run and pass; the only way to observe "no tests collected" is to
  # have applied svc's own configuration.
  mkdir -p "$TMP/py_config_scope/svc/tests"
  printf '%s' "$CLEAN_PY" > "$TMP/py_config_scope/app.py"
  cat > "$TMP/py_config_scope/svc/pyproject.toml" <<'EOF'
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-k zzz_nothing_matches"
EOF
  cat > "$TMP/py_config_scope/svc/tests/test_x.py" <<'EOF'
def test_x():
    assert True
EOF
  expect_exit_saying \
    "pytest: a subproject is run from its own directory, so its config applies" \
    "$TMP/py_config_scope" 0 "pytest-tests\(svc: no tests collected"

  # (2) A subproject's tests must not also be collected by the root run. The root
  # config here names svc/tests explicitly (the shape that defeated --ignore), so
  # only an --ignore-glob split prevents the double collection.
  mkdir -p "$TMP/py_root_split/svc/tests" "$TMP/py_root_split/tests"
  printf '%s' "$CLEAN_PY" > "$TMP/py_root_split/app.py"
  cat > "$TMP/py_root_split/pyproject.toml" <<'EOF'
[tool.pytest.ini_options]
testpaths = ["tests", "svc/tests"]
EOF
  cat > "$TMP/py_root_split/svc/pyproject.toml" <<'EOF'
[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
  cat > "$TMP/py_root_split/svc/tests/test_s.py" <<'EOF'
def test_s():
    assert True
EOF
  cat > "$TMP/py_root_split/tests/test_r.py" <<'EOF'
def test_r():
    assert True
EOF
  split_out="$(cd "$TMP/py_root_split" && bash "$G4" 2>&1)"; split_rc=$?
  if [ "$split_rc" -eq 0 ] && printf '%s' "$split_out" | grep -q -- '--ignore-glob=svc/\*'; then
    printf 'PASS  %s\n' "pytest: the root run globs out subprojects, so nothing is collected twice"
    pass=$((pass+1))
  else
    printf 'FAIL  %s (exit %d; expected 0 and a --ignore-glob=svc/* argument)\n---\n%s\n---\n' \
      "pytest: the root run globs out subprojects, so nothing is collected twice" "$split_rc" "$split_out"
    fail=$((fail+1))
  fi

  # (3a) Unknown config option + failing test -> UNAVAILABLE, gate stays green. The
  # option name is deliberately one no plugin can provide, so this is deterministic
  # on every host (a real option like asyncio_mode would pass where pytest-asyncio is
  # installed and fail where it is not).
  mkdir -p "$TMP/py_env_gap/svc/tests"
  printf '%s' "$CLEAN_PY" > "$TMP/py_env_gap/app.py"
  cat > "$TMP/py_env_gap/svc/pyproject.toml" <<'EOF'
[tool.pytest.ini_options]
testpaths = ["tests"]
not_a_real_pytest_option = true
EOF
  cat > "$TMP/py_env_gap/svc/tests/test_g.py" <<'EOF'
def test_g():
    assert False
EOF
  expect_exit_saying \
    "pytest: an unhonoured config option is UNAVAILABLE, not N code failures" \
    "$TMP/py_env_gap" 0 "pytest-env\(svc:" "FAIL test:svc"

  # (3b) The counter-test that makes (3a) meaningful: the same failing test under a
  # VALID config must FAIL the gate. Without this pair, (3a) would be satisfied by a
  # gate that never fails on pytest at all.
  mkdir -p "$TMP/py_real_fail/svc/tests"
  printf '%s' "$CLEAN_PY" > "$TMP/py_real_fail/app.py"
  cat > "$TMP/py_real_fail/svc/pyproject.toml" <<'EOF'
[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
  cat > "$TMP/py_real_fail/svc/tests/test_f.py" <<'EOF'
def test_f():
    assert False
EOF
  expect_exit_saying \
    "pytest: a genuine failure under a valid config still FAILS the gate" \
    "$TMP/py_real_fail" 1 "FAIL test:svc" "pytest-env"
else
  skip_case "pytest project scope and attribution" "pytest + python3"
fi

# ── Gate scope contract ────────────────────────────────────────────────────────
# A repository can be both a framework's home and an application. G4 used to answer
# "is there Python in this tree?" for the whole tree, so it judged the application:
# measured here, 1,637 of 1,764 budgeted lint findings and 2,379 of 2,429 collected tests
# were `backend/` -- code with its own CI. framework/gates/scope.json states the boundary.
#
# Every case below is a PAIR: the scoped run and the unscoped run of the SAME fixture.
# The pair is what makes them falsifiable. A single "scoped fixture passes" case would
# also pass against a gate that simply stopped scanning anything it was told to skip,
# including the code it owns.
make_scope_fixture() {
  local dir="$1" token="$2"
  mkdir -p "$dir/framework/tools" "$dir/framework/gates" "$dir/.github/workflows"
  cp "$HERE/../tools/gate_scope.py" "$dir/framework/tools/gate_scope.py"
  # The budget is what turns a finding into a verdict; without it the gate falls back to
  # raw ruff and these cases would be asserting on a different code path.
  cp "$HERE/../tools/lint_budget.py" "$dir/framework/tools/lint_budget.py"
  printf 'run: %s\n' "$token" > "$dir/.github/workflows/ci.yml"
}

SCOPE_JSON='{
  "schema": 1,
  "owned": ["app"],
  "delegated": [{"path": "backend", "tools": ["ruff", "pytest"],
                 "authority": {"file": ".github/workflows/ci.yml", "requires": ["TOKEN"]}}]
}'

if have ruff; then
  for variant in scoped unscoped; do
    d="$TMP/scope_lint_$variant"
    make_scope_fixture "$d" "ruff-token-here"
    # Keep the copied tooling out of the linter's own scan, so the case asserts on the
    # application file and nothing else.
    printf '[tool.ruff]\nextend-exclude = ["framework"]\n' > "$d/pyproject.toml"
    mkdir -p "$d/app" "$d/backend"
    printf 'def add(a, b):\n    return a + b\n' > "$d/app/ok.py"
    printf 'import os\n\ndef sub(a, b):\n    return a - b\n' > "$d/backend/bad.py"
    if [ "$variant" = "scoped" ]; then
      printf '%s\n' "$SCOPE_JSON" | sed 's/TOKEN/ruff-token-here/' > "$d/framework/gates/scope.json"
    fi
  done
  expect_exit_saying \
    "Scope: a delegated path's lint findings are not this gate's, and scope is reported" \
    "$TMP/scope_lint_scoped" 0 "\[scope\] owned: app"
  expect_exit_saying \
    "Scope: the SAME fixture without the contract still fails on that finding" \
    "$TMP/scope_lint_unscoped" 1 "NEW finding"

  # A delegation that can no longer be verified must FAIL, not quietly become coverage.
  # This is the rule that stops scope.json from ageing into a suppression list: the first
  # time the authority stops running the command, the claim is void.
  d="$TMP/scope_void"
  make_scope_fixture "$d" "some-other-command"
  printf '[tool.ruff]\nextend-exclude = ["framework"]\n' > "$d/pyproject.toml"
  mkdir -p "$d/app" "$d/backend"
  printf 'def add(a, b):\n    return a + b\n' > "$d/app/ok.py"
  printf 'def sub(a, b):\n    return a - b\n' > "$d/backend/bad.py"
  printf '%s\n' "$SCOPE_JSON" | sed 's/TOKEN/ruff-token-here/' > "$d/framework/gates/scope.json"
  expect_exit_saying \
    "Scope: a delegation whose authority no longer runs it FAILS the gate" \
    "$d" 1 "FAIL scope"

  # An unreadable contract is a FAIL. Reading it as "no contract" would widen the scan
  # (harmless-ish); reading it as "empty scope" would silently stop judging everything.
  d="$TMP/scope_corrupt"
  make_scope_fixture "$d" "ruff-token-here"
  printf '[tool.ruff]\nextend-exclude = ["framework"]\n' > "$d/pyproject.toml"
  mkdir -p "$d/app" "$d/backend"
  printf 'def add(a, b):\n    return a + b\n' > "$d/app/ok.py"
  printf 'def sub(a, b):\n    return a - b\n' > "$d/backend/bad.py"
  printf '{not json\n' > "$d/framework/gates/scope.json"
  expect_exit_saying \
    "Scope: an unreadable contract FAILS instead of being ignored" \
    "$d" 1 "FAIL scope"
else
  skip_case "gate scope contract (lint half)" ruff
fi

if have pytest && have python3; then
  # The pytest half is the one that mattered most here: the root config's testpaths pointed
  # at the application, so the gate ran 50 application tests and none of the framework's own.
  for variant in scoped unscoped; do
    d="$TMP/scope_pytest_$variant"
    make_scope_fixture "$d" "pytest-token-here"
    mkdir -p "$d/tests" "$d/svc/tests" "$d/backend/tests"
    cat > "$d/pyproject.toml" <<'EOF'
[tool.ruff]
extend-exclude = ["framework"]

[tool.pytest.ini_options]
testpaths = ["tests", "backend/tests"]
EOF
    printf 'def add(a, b):\n    return a + b\n' > "$d/tests/test_ok.py"
    printf 'def test_svc():\n    assert True\n' > "$d/svc/tests/test_svc.py"
    printf '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n' > "$d/backend/pyproject.toml"
    printf 'def test_bad():\n    assert False\n' > "$d/backend/tests/test_bad.py"
    # Owned = svc, so the root run targets svc/ and the delegated project is not run at all.
    printf '%s\n' "$SCOPE_JSON" | sed 's/TOKEN/pytest-token-here/' \
      | sed 's/"owned": \["app"\]/"owned": ["svc"]/' > "$d/framework/gates/scope.json"
    if [ "$variant" = "unscoped" ]; then rm -f "$d/framework/gates/scope.json"; fi
  done
  expect_exit_saying \
    "Scope: a delegated project's tests are not run by this gate" \
    "$TMP/scope_pytest_scoped" 0 "pytest -q svc" "FAIL test"
  expect_exit_saying \
    "Scope: the SAME fixture without the contract runs that project and fails" \
    "$TMP/scope_pytest_unscoped" 1 "FAIL test:backend"
else
  skip_case "gate scope contract (pytest half)" "pytest + python3"
fi

# ── Secrets (language-agnostic) ─────────────────────────────────────────────────
if have gitleaks; then
  mkdir -p "$TMP/secret_bad"
  cat > "$TMP/secret_bad/config.txt" <<'EOF'
stripe_key = sk_live_abc123def456ghi789jkl012mno345
EOF
  expect_exit "Secrets: known-format key fails the gate regardless of extension" "$TMP/secret_bad" 1
else
  skip_case "real-gitleaks secret-shape branch" gitleaks
fi

echo
echo "g4 language-coverage regression: $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]