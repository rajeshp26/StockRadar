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