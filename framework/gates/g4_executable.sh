#!/usr/bin/env bash
# G4 — Executable validation. Always runs. Lint, types, tests, build, static analysis.
#
# Four rules this gate must never break:
#   1. It cannot pass vacuously overall. Zero checks executed anywhere = FAIL.
#   2. A missing tool is never a pass. It is either substituted or reported as unavailable.
#   3. It cannot pass vacuously PER LANGUAGE either. A repo with Python files and a repo
#      with React files must each get their own static analysis coverage — one language's
#      checks (or the language-agnostic secrets scan) passing does not excuse another
#      detected language having zero checks run against it. This was a real, reproduced
#      gap in an earlier revision of this file: a package.json with no "lint" script and
#      no node_modules, sitting next to real .jsx source, produced a PASS on the strength
#      of the secrets scan alone -- the React code itself was never actually linted.
#      Fixed here by tracking per-language coverage explicitly (see "Verdict" below) and
#      failing when a detected language has zero real checks, rather than only checking
#      whether *any* check anywhere succeeded. This stays inside G4's existing exit-code
#      contract (0/1 only, per framework/gates/EXIT_CODES.md) -- it is a stricter FAIL
#      condition, not a new exit code.
#   4. Nor can it pass on tests alone. A language whose only coverage is a test runner
#      or a build step, with every lint/type/security tool unavailable, is not "checked"
#      in the sense this gate exists for -- a passing test proves the behavior it
#      asserts, not the absence of a hardcoded credential nobody wrote a test for.
#      Reproduced: ruff/mypy/bandit all unavailable + one trivial passing pytest test
#      let a file with a hardcoded password and shell=True pass G4. Static analysis
#      (lint/types/security-scan) and dynamic checks (tests/build) are now tracked
#      separately; a present language needs at least one of the former, not just
#      any of the latter.
#
# Language coverage as of this revision: JS/TS, Python, C/C++, Java, and a
# language-agnostic secrets scan. Each branch is independently gated on file
# presence (does this language appear in the tree?) and tool presence (is the
# binary/jar actually available?) -- never both at once, per rule 2 above.
#
# Pre-existing findings are DEBT, not a verdict on today's change. Static analysis runs
# through framework/tools/lint_budget.py: a committed, reviewable budget records how many
# findings exist per (file, rule) plus the linter version that produced them. Findings
# above the budget fail this gate; findings within it are reported as debt. The budget can
# only shrink unless a human passes --allow-increase with a stated reason, so it is a
# standing burndown obligation rather than an exclusion list. See framework/quality/README.md.
#
# Rule 5: scope is stated, never assumed. A repository can BE both a framework's home and
# an application. "Does this language appear in the tree?" then answers a question nobody
# asked: whether the APPLICATION is checked. framework/gates/scope.json names the paths this
# gate owns and the paths another authority judges, and that authority's commands are
# re-verified on every run. Paths owned by neither are reported with a file count rather
# than dropped. No scope.json means the whole tree -- absence is never narrower scope.
# See framework/tools/gate_scope.py.
GATE_NAME=g4_executable
source "$(dirname "$0")/_lib.sh"
rc=0; ran=0; unavailable=""
present=""; covered=""; static_covered=""

run() {
  local label="$1"; shift
  log "run $label: $*"
  ran=$((ran+1))
  "$@"
  LAST_RUN_RC=$?
  [ "$LAST_RUN_RC" -eq 0 ] || { log "FAIL $label"; rc=1; }
  return "$LAST_RUN_RC"
}
note_missing() { unavailable="${unavailable:+$unavailable }$1"; }
mark_present() { case " $present " in *" $1 "*) ;; *) present="${present:+$present }$1";; esac; }
mark_covered() { case " $covered " in *" $1 "*) ;; *) covered="${covered:+$covered }$1";; esac; }
# Static analysis specifically: lint / type-check / security-scan tools that inspect
# code without running it -- ruff, mypy, bandit, eslint, tsc, cppcheck, checkstyle, pmd.
# NOT test runners, NOT build steps: a passing test suite proves the behavior it
# asserts, it does not inspect the rest of the file for a hardcoded credential or a
# magic number nobody wrote a test for. This distinction exists because a weaker
# version of this gate (tracking only "was ANY check run") was verified to let a
# language pass on a passing test suite alone with zero lint/security tooling
# present -- functionally correct code with a hardcoded password in it, unflagged.
mark_static() { mark_covered "$1"; case " $static_covered " in *" $1 "*) ;; *) static_covered="${static_covered:+$static_covered }$1";; esac; }

# A pytest configuration option that no installed plugin provides. The signal is pytest's
# own `PytestConfigWarning: Unknown config option: <name>` -- the repository stating that the
# configuration it declares was not in effect -- not a guess at a traceback. Reporting it as
# UNAVAILABLE rather than FAIL is the difference between "your environment is incomplete"
# and "your change broke tests"; the option name is extracted only to make the report
# actionable. Deliberate tradeoff: a permanently unknown option means that project's tests
# never fail this gate, which is why the notice is loud rather than a quiet note.
pytest_env_gap() {
  local proj="$1" logfile="$2" opt
  opt="$(sed -n 's/.*Unknown config option: *\([A-Za-z0-9_-]*\).*/\1/p' "$logfile" | head -1)"
  note_missing "pytest-env($proj: pytest option '${opt:-unknown}' is unknown, so the plugin that provides it is not installed and this project's own pytest configuration was never applied. Install the declared dev requirements (e.g. '$proj/requirements-dev.txt' or '$proj/requirements-dev.in') and re-run -- these are not code failures.)"
  log "not counting $proj failures as code failures: the declared pytest configuration was not in effect"
}

# Shared exclusion set for every per-language `find` below. This exists because an
# earlier revision gave each language its own independently-typed exclusion list,
# and only Python's happened to exclude `.venv` -- a real virtualenv sitting in the
# repo (routine: CPython itself, plus any compiled extension package, ships C
# headers under <venv>/*/include or <venv>/*/site-packages) got picked up by the
# C/C++ branch as "project source," which with cppcheck unavailable hit the new
# per-language FAIL tier on every run. Reproduced: a `.venv` + `backend/venv` with
# ~30 fake headers each yielded 62 "C files" from a project with zero C code of its
# own. `site-packages`/`dist-packages` are included because they catch a virtualenv
# regardless of what its outer directory is named (venv, .venv, env, myenv, ...);
# naming the common directory names too is belt-and-suspenders, not reliance on
# guessing the name right.
COMMON_PRUNE=(
  -not -path './.git/*'       -not -path '*/node_modules/*'
  -not -path '*/.venv/*'      -not -path '*/venv/*'
  -not -path '*/site-packages/*' -not -path '*/dist-packages/*'
  -not -path '*/.tox/*'       -not -path '*/__pycache__/*'
  -not -path '*/build/*'      -not -path '*/dist/*'
  -not -path '*/target/*'
)

# ── Assertion integrity: test-only changes that weaken assertions ──────────────
# The "make the failing test pass by editing the test" failure leaves a specific
# shape in the change set: net assertion lines REMOVED from test files while no
# non-test source changed anywhere. A legitimate fix touches the source, and a
# legitimate test update keeps the assertion count level or higher (removed
# lines balance added ones); a net removal against a static codebase has no
# honest reading. This guards the change set rather than executing a check, so
# it never inflates `ran` -- but a violation sets the same rc=1 verdict.
is_test_path() {
  case "$1" in
    tests/*|test/*|*/tests/*|*/test/*) return 0 ;;
    test_*.py|*/test_*.py|*_test.py|*_test.go|*.spec.ts|*.spec.tsx|*.test.ts|*.test.tsx) return 0 ;;
    *) return 1 ;;
  esac
}
_ASSERT_RE='expect\(|(^|[^A-Za-z])assert|\.toBe\(|\.toEqual\(|\.toHave[A-Z]|raises\('
test_changed=""
src_changed=""
for f in $(changed_source_files); do
  if is_test_path "$f"; then
    test_changed="${test_changed}${test_changed:+ }$f"
  else
    src_changed="${src_changed}${src_changed:+ }$f"
  fi
done
if [ -n "$test_changed" ] && [ -z "$src_changed" ]; then
  for f in $test_changed; do
    # Untracked new files diff to nothing (additions only cannot weaken) and
    # deleted files diff to all-removed; both are handled by the same comparison.
    removed=$(git diff HEAD -U0 -- "$f" 2>/dev/null | grep -E '^-[^-]' | grep -cE "$_ASSERT_RE")
    added=$(git diff HEAD -U0 -- "$f" 2>/dev/null | grep -E '^\+[^+]' | grep -cE "$_ASSERT_RE")
    if [ "${removed:-0}" -gt "${added:-0}" ] 2>/dev/null; then
      log "FAIL assertion-integrity: $f nets $((removed - added)) removed assertion line(s) with no non-test source change -- restore the assertion and fix the source, or justify the removal in the task record"
      rc=1
    fi
  done
fi

# ── JS / TS ────────────────────────────────────────────────────────────────────
JS_FILES=$(
  { git ls-files '*.js' '*.jsx' '*.ts' '*.tsx' 2>/dev/null
    find . \( -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' \) \
      "${COMMON_PRUNE[@]}" \
      2>/dev/null | sed 's|^\./||'
  } | sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done | head -400
)

if [ -f package.json ]; then
  # "Present" (needs coverage) if there's actual JS/TS/JSX/TSX source, OR the project
  # declares scripts to run even with none found yet (e.g. a fresh scaffold). A bare
  # package.json with no scripts and no source files (a minimal tooling manifest) is
  # not held to this -- there is nothing to check yet, not a gap to report.
  HAS_JS_SCRIPTS=$(grep -qE '"(lint|test|build)"' package.json && echo 1 || echo 0)
  if [ -n "$JS_FILES" ] || [ "$HAS_JS_SCRIPTS" = "1" ]; then
    mark_present javascript
  fi

  if have npm; then
    # A declared npm script whose BINARY is not installed is UNAVAILABLE, not FAILING --
    # and that distinction cannot be recovered from the exit code. Measured on the
    # platform this gate's own consumers run on: `npm run lint` with eslint absent
    # exits 1, and `cmd /c <nonexistent>` exits 1; exit 127 is the POSIX shell
    # convention for command-not-found and never appears on Windows. An earlier
    # revision of this file therefore branched on `LAST_RUN_RC = 127`, a condition
    # that can never be true on Windows -- the "unavailable" diagnostic never fired,
    # mark_static javascript ran unconditionally, and the exact bug the branch was
    # added to close (a declared-but-uninstalled linter counted as static coverage)
    # stayed live on the platform it was written for. Worse, `run` had already set
    # rc=1 by that point, so the branch would have printed a tool as "unavailable"
    # while simultaneously failing the gate because of it -- unavailable and failing
    # are different states and rule 2 requires them to be distinguishable.
    #
    # Resolve the linter BEFORE launching it instead: read the first token of the
    # "lint" script and check that it is actually installed. Only then run it, and
    # only then count it as static coverage. A linter that genuinely ran and found
    # real problems still fails the gate through `run` (rc=1) exactly as before.
    if [ -d node_modules ]; then
      if grep -q '"lint"' package.json; then
        LINT_CMD=$(sed -n 's/.*"lint"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' package.json | head -1)
        LINT_BIN=""
        [ -n "$LINT_CMD" ] && LINT_BIN="${LINT_CMD%% *}"
        if [ -n "$LINT_BIN" ] && { [ -x "node_modules/.bin/$LINT_BIN" ] || have "$LINT_BIN"; }; then
          run lint npm run lint --silent
          mark_static javascript
        elif [ -n "$LINT_BIN" ]; then
          note_missing "lint-binary('$LINT_BIN' declared in package.json but not installed; run 'npm i -D $LINT_BIN')"
        else
          # Script declared but its command line could not be parsed by the sed above
          # (multi-line, interpolated, or an unusual form). Run it for real and claim
          # static coverage only if it actually came back green -- never assume.
          run lint npm run lint --silent
          [ "$LAST_RUN_RC" -eq 0 ] && mark_static javascript
        fi
      fi
      # test/build genuinely executed whenever npm ran them: coverage is credited for
      # the attempt, and a missing or failing runner surfaces as rc=1 through `run`,
      # which is a loud failure rather than a silent pass.
      grep -q '"test"'  package.json && { run test  npm test      --silent; mark_covered javascript; }
      grep -q '"build"' package.json && { run build npm run build --silent; mark_covered javascript; }
    else
      note_missing "node_modules(npm scripts: run 'npm ci')"
    fi
  else
    note_missing npm
  fi
  # Only use a locally installed tsc. `npx --yes` reaches the network and a fetch failure
  # would otherwise be indistinguishable from a type error.
  if [ -f tsconfig.json ]; then
    if [ -x node_modules/.bin/tsc ]; then run types node_modules/.bin/tsc --noEmit; mark_static javascript
    elif have tsc;                   then run types tsc --noEmit;                  mark_static javascript
    else note_missing tsc; fi
  fi
elif [ -n "$JS_FILES" ]; then
  # JS/TS/JSX/TSX source with no package.json at all: still real code, still needs
  # coverage tracked, even though there's no npm script machinery to hang a check off.
  mark_present javascript
fi

# ── Gate scope: which paths this gate judges, and who judges the rest ──────────
# G4 asks a repo-wide question ("does this language appear in the tree?"). When the repo is
# both a framework's home and an application, that question silently includes the
# application -- measured here: 1,637 of 1,764 budgeted lint findings and 2,379 of 2,429
# collected tests were `backend/`, which has its own CI, its own pinned dev environment, and
# credentials this machine does not have.
#
# The contract governs the dimensions where a competing authority exists: Python static
# analysis (ruff/mypy/bandit) and pytest. The JS branch above deliberately stays repo-wide --
# it runs the project's OWN declared npm scripts, and nothing else runs them, so narrowing
# it would be a coverage hole with a tidy explanation.
#
# Three states, and the third is why this is not a suppression list:
#   owned      -> judged here
#   delegated  -> judged elsewhere, and that claim is re-verified against the authority
#                 file on every run; when it stops being true this gate FAILS
#   neither    -> reported with a file count ("judged by nobody"), never dropped
#
# No scope.json => every path. An unreadable contract FAILS rather than being ignored: it
# cannot be evaluated, so it must not be guessed at. The fallback is the whole tree, which
# is the strict direction -- a contract that cannot be read can never buy silence.
SCOPE_OWNED=""; SCOPE_SUMMARY=""
if [ -f framework/tools/gate_scope.py ] && [ -f framework/gates/scope.json ]; then
  scope_out="$(python3 framework/tools/gate_scope.py check 2>&1)"; scope_rc=$?
  echo "$scope_out"
  if [ "$scope_rc" -ne 0 ]; then
    log "FAIL scope: framework/gates/scope.json could not be honoured (gate_scope.py exit $scope_rc) -- a delegation that can no longer be verified is a suppression list, not coverage"
    rc=1
  fi
  if scope_paths="$(python3 framework/tools/gate_scope.py paths 2>/dev/null)"; then
    SCOPE_OWNED="$scope_paths"
    SCOPE_SUMMARY="$(python3 framework/tools/gate_scope.py unjudged 2>/dev/null)"
  else
    log "FAIL scope: the owned paths could not be determined; falling back to the whole tree, which cannot yield a pass the contract would have forbidden"
    rc=1
  fi
fi

# Is this repo-relative path one this gate judges? No contract (or one that could not be
# read -- already failed above) means everything is in scope.
in_scope() {
  local f="$1" p
  [ -n "$SCOPE_OWNED" ] || return 0
  for p in $SCOPE_OWNED; do
    [ "$p" = "." ] && return 0
    case "$f" in "$p"|"$p"/*) return 0 ;; esac
  done
  return 1
}
# What mypy/bandit are pointed at: the owned paths, or the whole tree without a contract.
SCOPE_TARGETS="${SCOPE_OWNED:-.}"

# ── Python ─────────────────────────────────────────────────────────────────────
# Discover sources ANYWHERE, not just the repo root. Root-only globbing misses the
# conventional src/ + tests/ layout and silently reports "no checks available".
# `git ls-files` also lists tracked-but-deleted paths, so filter to files that exist.
# The scope filter runs last, so "python is present" is answered about the code this gate
# owns: a repository whose only Python is delegated must not claim Python coverage.
PY_FILES=$(
  { git ls-files '*.py' 2>/dev/null
    find . -name '*.py' "${COMMON_PRUNE[@]}" 2>/dev/null | sed 's|^\./||'
  } | sort -u | while IFS= read -r f; do
        [ -f "$f" ] || continue
        in_scope "$f" || continue
        printf '%s\n' "$f"
      done | head -400
)

# Directories whose own pytest configuration would be loaded if pytest ran there. Each is
# an independent test project and must be run separately (see the call site for why).
# A directory that configures pytest but holds no tests is not a project: running there
# only produces pytest exit 5, which adds noise rather than coverage.
pytest_projects() {
  local cfg d
  for cfg in $(find . -maxdepth 3 \
        \( -name 'pytest.ini' -o -name 'tox.ini' -o -name 'pyproject.toml' \) \
        "${COMMON_PRUNE[@]}" 2>/dev/null | sed 's|^\./||' | sort); do
    case "$cfg" in
      *.toml) grep -q '\[tool\.pytest\.ini_options\]' "$cfg" 2>/dev/null || continue ;;
    esac
    d="$(dirname "$cfg")"
    { [ -d "$d/tests" ] || [ -d "$d/test" ] || [ -f "$d/conftest.py" ]; } || continue
    printf '%s\n' "$d"
  done | sort -u
}

if [ -n "$PY_FILES" ]; then
  mark_present python
  # ruff's *default* rule selection is pyflakes + basic pycodestyle only -- it will
  # not catch a hardcoded password or a magic-value comparison unless the project's
  # own pyproject.toml enables the S (bandit-equivalent) and PLR categories. See
  # framework/quality/python/pyproject.ruff.toml for the baseline this framework
  # ships; G4 runs whatever config the project actually has, same as it does for
  # eslint -- it does not silently inject one.
  # Static analysis runs through the budget ratchet (framework/tools/lint_budget.py) when
  # the module is present. Why: a tree-wide linter on a repository with history reports
  # every pre-existing finding, so the gate could never pass and therefore never ran in
  # practice -- the same failure this framework already solved once for the frontend stack
  # (framework/frontend/stack_check.py: "Ratchet, not sweep"), which ships
  # framework/frontend/baseline.json. G4 was the only gate without a ratchet.
  #
  # The budget allows exactly the recorded findings and fails on anything above them, so
  # this is strictly no weaker than `ruff check .`:
  #   * no budget file           -> every finding is new -> same verdict as raw ruff
  #   * budget present           -> budgeted findings are debt, new ones fail the gate
  #   * budget for another tool  -> BLOCKED, never a silent comparison (see below)
  # Exit 2 from the budget means it could not judge (tool missing, unreadable budget, or a
  # linter version change). That is reported as unavailable, NOT as static coverage, and
  # `run` has already failed the gate -- a "could not judge" must never read as a pass.
  if have ruff; then
    if [ -f framework/tools/lint_budget.py ]; then
      run lint python3 framework/tools/lint_budget.py check
      case "$LAST_RUN_RC" in
        0|1) mark_static python ;;
        *)   note_missing "ruff-budget(could not judge — see [lint_budget] above; refresh deliberately with 'python3 framework/tools/lint_budget.py update --reason ...')" ;;
      esac
    else
      # Stricter fallback, not a weakening: without the budget module every finding counts,
      # which is exactly what the raw linter does.
      run lint ruff check .; mark_static python
    fi
  else
    note_missing ruff
  fi
  if have mypy;   then run types mypy $SCOPE_TARGETS;          mark_static python; else note_missing mypy; fi
  # bandit overlaps with ruff's S rules but is kept as a second, independent pass:
  # they don't agree on every finding (measured: ruff's S105 caught a hardcoded
  # password bandit's B105 profile missed on the same file), and this is a
  # security-adjacent check where a second opinion is worth the runtime.
  if have bandit; then run security bandit -q -r $SCOPE_TARGETS -x '*/node_modules/*,*/.venv/*'; mark_static python; else note_missing bandit; fi

  if have pytest; then
    # ── Test execution: one pytest run per pytest project ───────────────────────
    # Two failures this shape exists to prevent, both measured on a real monorepo.
    #
    # 1. CONFIG SCOPE. pytest reads its configuration from the rootdir it discovers. With
    #    a bare `pytest` that rootdir is the directory it was invoked in, so a root-level
    #    run in a repo whose subproject configures pytest (backend/pyproject.toml:
    #    `asyncio_mode = "auto"`, `testpaths = ["tests"]`) never loads that config. The
    #    measured consequence was not a subtle one: 407 async tests errored with "async
    #    def functions are not natively supported" instead of executing, purely because
    #    the option that tells pytest how to run them was never read. Running each
    #    project from its own directory is the only correct scope for a monorepo, and
    #    pytest resolves that directory's configfile as the rootdir (verified:
    #    rootdir=backend, configfile=pyproject.toml).
    #
    # 2. MISATTRIBUTION. When a pytest plugin the config depends on is not installed,
    #    pytest reports `PytestConfigWarning: Unknown config option: <name>` and then
    #    fails every test that plugin was there to drive. Those are not code defects.
    #    Counting them as failures blames a change for an incomplete environment, which
    #    rule 2 forbids -- a missing tool is UNAVAILABLE, never FAIL. The signal used is
    #    pytest's own warning that the repo's declared configuration is not in effect,
    #    not a guess about a traceback.
    #
    # Exit 5 is "no tests collected": that is a coverage hole to report, not a failure of
    # code that does not exist.
    PYTEST_LOG="${TMPDIR:-/tmp}/g4-pytest-$$.log"
    # Scope filter: a subproject is this gate's only if it owns it. Running the delegated
    # project from its own directory would duplicate the authority that already judges it --
    # with a worse environment, which is what produced 407 bogus async errors here. The repo
    # root always stays (if it configures pytest); its TARGETS are narrowed below.
    PYTEST_ROOTS="$(pytest_projects | while IFS= read -r d; do
      [ -n "$d" ] || continue
      if [ "$d" = "." ] || in_scope "$d"; then printf '%s\n' "$d"; fi
    done)"
    if [ -d tests ] || [ -d test ]; then
      printf '%s\n' "$PYTEST_ROOTS" | grep -qx '\.' \
        || PYTEST_ROOTS="$(printf '.\n%s\n' "$PYTEST_ROOTS" | sed '/^$/d')"
    fi
    [ -n "$PYTEST_ROOTS" ] || PYTEST_ROOTS="."
    # A subproject's tests must be collected ONCE, by the run that applies its config. A
    # root-level run would collect them again (measured: root collected 2429 tests, of
    # which 2379 belonged to backend) with the wrong configuration -- the same 407 bogus
    # async errors, arriving through the back door. So the root run ignores each subproject.
    PYTEST_SUBPROJECTS="$(printf '%s\n' "$PYTEST_ROOTS" | grep -vx '\.' || true)"

    while IFS= read -r proj; do
      [ -n "$proj" ] || continue
      # --ignore-glob, not --ignore: measured, --ignore=backend did NOT prevent collection
      # when the root config's own `testpaths` names backend/tests explicitly (2429 tests
      # still collected), while --ignore-glob='backend/*' reduced the root run to its own
      # 50. The glob is what actually splits the two projects.
      PYTEST_ARGS=(-q)
      if [ "$proj" = "." ]; then
        for sub in $PYTEST_SUBPROJECTS; do PYTEST_ARGS+=("--ignore-glob=$sub/*"); done
        # The root run targets the paths this gate OWNS, not the root config's testpaths.
        # Measured here: the root testpaths are ["tests", "backend/tests"] -- the application
        # -- so the gate ran 50 application tests (43 skipped) and reached NONE of the
        # framework's own 240. A gate that judges a repository while executing none of that
        # repository's tests is the coverage hole this whole exercise started from.
        if [ -n "$SCOPE_OWNED" ]; then
          root_targets=""
          for p in $SCOPE_OWNED; do
            [ -d "$p" ] && root_targets="${root_targets:+$root_targets }$p"
          done
          [ -n "$root_targets" ] && PYTEST_ARGS+=($root_targets)
        fi
      fi

      # Preflight, collect only. An option no installed plugin provides is visible at
      # collection time, so there is no reason to spend the suite's full runtime finding
      # out: measured on the repo this gate was fixed against, the environment gap was
      # visible in the 5 s collection step while the suite itself took ~17 min to run.
      # This is a preflight, not a check, so it does not count toward `ran`.
      pre_rc=0
      ( cd "$proj" && pytest --co -q "${PYTEST_ARGS[@]}" ) </dev/null >"$PYTEST_LOG" 2>&1 || pre_rc=$?
      if grep -q 'Unknown config option' "$PYTEST_LOG"; then
        pytest_env_gap "$proj" "$PYTEST_LOG"
        continue
      fi
      if [ "$pre_rc" -eq 5 ]; then
        note_missing "pytest-tests($proj: no tests collected)"
        continue
      fi

      ran=$((ran+1))
      log "run test:$proj: (cd $proj && pytest ${PYTEST_ARGS[*]})"
      proj_rc=0
      ( cd "$proj" && pytest "${PYTEST_ARGS[@]}" ) </dev/null >"$PYTEST_LOG" 2>&1 || proj_rc=$?
      case "$proj_rc" in
        0)
          mark_covered python
          ;;
        5)
          note_missing "pytest-tests($proj: no tests collected)"
          ;;
        *)
          # Belt and braces: if the warning only surfaced during the run rather than at
          # collection, attribute it the same way instead of inventing failures.
          if grep -q 'Unknown config option' "$PYTEST_LOG"; then
            pytest_env_gap "$proj" "$PYTEST_LOG"
          else
            log "FAIL test:$proj (pytest exit $proj_rc)"
            tail -n 25 "$PYTEST_LOG"
            rc=1
          fi
          ;;
      esac
    done <<EOF
$PYTEST_ROOTS
EOF
    rm -f "$PYTEST_LOG"

    # A project whose suite could not be judged must not leave the test dimension silently
    # empty. Same substitute the `pytest unavailable` path below uses.
    case " $covered " in
      *" python "*) ;;
      *) # shellcheck disable=SC2086
         run syntax python3 -m py_compile $PY_FILES; mark_covered python ;;
    esac
  else
    note_missing pytest
    # Substitute, do not skip. Contract and unit tests are written to run standalone.
    # Scoped like everything else: without a contract this looks where it always did.
    STANDALONE=$(find ${SCOPE_OWNED:-tests test} -name 'test_*.py' 2>/dev/null | sort)
    if [ -n "$STANDALONE" ]; then
      log "pytest unavailable; executing tests standalone"
      for t in $STANDALONE; do run "test:$t" python3 "$t"; mark_covered python; done
    fi
    # Byte-compilation is a genuine static check, but a weak one: it only catches
    # syntax and import-time errors, not hardcoding or magic values. It counts
    # toward "something ran" (mark_covered) but deliberately NOT toward the
    # static-analysis-specifically bar (mark_static) -- see the header comment.
    # shellcheck disable=SC2086
    run syntax python3 -m py_compile $PY_FILES; mark_covered python
  fi
fi

# ── C / C++ ────────────────────────────────────────────────────────────────────
C_FILES=$(
  { git ls-files '*.c' '*.h' '*.cpp' '*.cc' '*.cxx' '*.hpp' '*.hh' 2>/dev/null
    find . \( -name '*.c' -o -name '*.h' -o -name '*.cpp' -o -name '*.cc' \
              -o -name '*.cxx' -o -name '*.hpp' -o -name '*.hh' \) \
      "${COMMON_PRUNE[@]}" \
      2>/dev/null | sed 's|^\./||'
  } | sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done | head -400
)

if [ -n "$C_FILES" ]; then
  mark_present "c/c++"
  if have cppcheck; then
    # --error-exitcode=1 with --enable=style is required for a MISRA-only finding to
    # fail the run (measured: MISRA violations are reported at "style" severity, and
    # a plain `cppcheck file.c` with no --enable/--error-exitcode exits 0 even with
    # violations present -- that combination would be a silent pass, not a check).
    #
    # MISRA C 2012's rule *text* is proprietary (MISRA Ltd copyright); this command
    # reports violated rule numbers only (e.g. [misra-c2012-8.4]). To see full rule
    # descriptions, pass --rule-texts=<file> pointing at a legally obtained copy —
    # this framework does not ship or fetch that text.
    # shellcheck disable=SC2086
    run lint cppcheck --enable=warning,style,performance,portability \
      --error-exitcode=1 --addon=misra --inline-suppr $C_FILES
    mark_static "c/c++"
  else
    note_missing cppcheck
  fi
fi

# ── Java ───────────────────────────────────────────────────────────────────────
JAVA_FILES=$(
  { git ls-files '*.java' 2>/dev/null
    find . -name '*.java' "${COMMON_PRUNE[@]}" 2>/dev/null | sed 's|^\./||'
  } | sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done | head -400
)

if [ -n "$JAVA_FILES" ]; then
  mark_present java
  if have java; then
    # Checkstyle and PMD ship as jars/scripts, not PATH-resolvable binaries, so
    # discovery is via env vars the runtime environment sets, same convention as
    # anywhere else this codebase needs an external, non-package-manager tool.
    # A project's own ruleset (checkstyle.xml / pmd-ruleset.xml at the repo root)
    # takes precedence; framework/quality/java/*.xml is the fallback baseline.
    CHECKSTYLE_RULES="checkstyle.xml"
    [ -f "$CHECKSTYLE_RULES" ] || CHECKSTYLE_RULES="$(dirname "$0")/../quality/java/checkstyle-magic-numbers.xml"
    if [ -n "${CHECKSTYLE_JAR:-}" ] && [ -f "$CHECKSTYLE_JAR" ]; then
      if [ -f "$CHECKSTYLE_RULES" ]; then
        # shellcheck disable=SC2086
        run lint java -jar "$CHECKSTYLE_JAR" -c "$CHECKSTYLE_RULES" $JAVA_FILES
        mark_static java
      else
        # Fails safe either way (a missing ruleset makes checkstyle itself error
        # out, which `run` already catches), but a generic "config XML not found"
        # java stack trace doesn't tell a human what to actually do about it. This
        # specifically means framework/quality/ (PR-QUALITY-GATES, the base patch)
        # wasn't applied alongside this gate script -- say so.
        note_missing "checkstyle-ruleset(apply PR-QUALITY-GATES' framework/quality/ alongside this gate)"
      fi
    else
      note_missing "checkstyle(set CHECKSTYLE_JAR)"
    fi

    PMD_RULES="pmd-ruleset.xml"
    [ -f "$PMD_RULES" ] || PMD_RULES="$(dirname "$0")/../quality/java/pmd-ruleset.xml"
    if [ -n "${PMD_BIN:-}" ] && [ -x "$PMD_BIN" ]; then
      if [ -f "$PMD_RULES" ]; then
        run lint "$PMD_BIN" check -d . -R "$PMD_RULES" -f text --no-progress
        mark_static java
      else
        note_missing "pmd-ruleset(apply PR-QUALITY-GATES' framework/quality/ alongside this gate)"
      fi
    else
      note_missing "pmd(set PMD_BIN)"
    fi
  else
    note_missing java
  fi
fi

# ── Secrets (language-agnostic) ─────────────────────────────────────────────────
# Runs regardless of which language branches above fired: a hardcoded credential
# doesn't care what language it's embedded in, and gitleaks catches known secret
# *formats* (AWS/Stripe/GitHub-token shapes, private keys, high-entropy strings)
# that a per-language linter's variable-name heuristic (e.g. ruff S105, checking
# for a variable named "password") will miss on a differently-named variable.
#
# Deliberately NOT counted via mark_covered for any specific language: this check
# does not inspect JS/Python/C/Java quality, only secret shapes, so it must never
# be able to stand in for a missing language-specific check in the verdict below.
if have gitleaks; then
  run secrets gitleaks detect --no-git --source . --exit-code 1 -v
else
  note_missing gitleaks
fi

# ── Verdict ────────────────────────────────────────────────────────────────────
# Scope is part of the verdict, not a footnote: "green" means green for the owned paths,
# and the line below says which paths those are and whose the rest are.
if [ -n "$SCOPE_SUMMARY" ]; then
  log "scope: $SCOPE_SUMMARY"
fi

if [ -n "$unavailable" ]; then
  log "tools unavailable (not treated as pass): $unavailable"
fi

if [ "$ran" -eq 0 ]; then
  persist fail "no executable checks available; unavailable: ${unavailable:-none}"
  fail "no executable checks found — G4 cannot pass vacuously"
fi

# A language with source present but zero real checks executed against it is a FAIL,
# not a pass earned by an unrelated language or the language-agnostic secrets scan.
# Reproduced before this fix: package.json + real .jsx source, no lint script, no
# node_modules -> only the secrets scan ran, found nothing, and G4 reported PASS.
uncovered=""
for lang in $present; do
  case " $covered " in
    *" $lang "*) ;;
    *) uncovered="${uncovered:+$uncovered }$lang" ;;
  esac
done

if [ -n "$uncovered" ]; then
  persist fail "language(s) detected with zero checks executed: $uncovered; unavailable: ${unavailable:-none}"
  fail "language(s) present but never checked: $uncovered — set up the tooling in framework/quality/README.md, or this is a real coverage gap, not a pass"
fi

# Stricter tier: a language checked ONLY by tests/build, with no static analysis at
# all, is not a pass either. Reproduced before this fix: ruff/mypy/bandit all
# unavailable, one trivial passing pytest test elsewhere in the repo -> a file with
# a hardcoded password and subprocess(shell=True) passed G4. Tests prove the
# behavior they assert; they do not inspect the rest of the file. A language with
# real static tools all unavailable belongs in "unavailable", loudly, not folded
# into a silent pass because something else ran.
no_static=""
for lang in $present; do
  case " $static_covered " in
    *" $lang "*) ;;
    *) no_static="${no_static:+$no_static }$lang" ;;
  esac
done

if [ -n "$no_static" ]; then
  persist fail "language(s) with no static analysis executed (tests/build only, or nothing): $no_static; unavailable: ${unavailable:-none}"
  fail "language(s) present with zero static analysis: $no_static — a passing test suite is not a substitute for lint/type/security tooling; install the tools in framework/quality/README.md"
fi

if [ $rc -eq 0 ]; then
  persist pass "$ran checks green; unavailable: ${unavailable:-none}"
  pass "$ran executable checks green"
fi
persist fail "executable checks failed"
fail "executable checks failed"