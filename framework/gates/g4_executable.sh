#!/usr/bin/env bash
# G4 — Executable validation. Always runs. Lint, types, tests, build, static analysis.
#
# Two rules this gate must never break:
#   1. It cannot pass vacuously. Zero checks executed = FAIL, not pass.
#   2. A missing tool is never a pass. It is either substituted or reported as unavailable.
GATE_NAME=g4_executable
source "$(dirname "$0")/_lib.sh"
rc=0; ran=0; unavailable=""

run() { local label="$1"; shift; log "run $label: $*"; ran=$((ran+1)); "$@" || { log "FAIL $label"; rc=1; }; }
note_missing() { unavailable="${unavailable:+$unavailable }$1"; }

# ── JS / TS ────────────────────────────────────────────────────────────────────
if [ -f package.json ]; then
  if have npm; then
    # A declared npm script whose binaries are not installed is UNAVAILABLE, not FAILING.
    # Running `npm run lint` with no node_modules yields "eslint: not found" and exit 1,
    # which is indistinguishable from a real lint error — the same class of bug as a missing
    # pyyaml reading as architectural compliance. Require node_modules before believing the
    # exit code, and report the gap explicitly.
    if [ -d node_modules ]; then
      grep -q '"lint"'  package.json && run lint  npm run lint  --silent
      grep -q '"test"'  package.json && run test  npm test      --silent
      grep -q '"build"' package.json && run build npm run build --silent
    else
      note_missing "node_modules(npm scripts: run 'npm ci')"
    fi
  else
    note_missing npm
  fi
  # Only use a locally installed tsc. `npx --yes` reaches the network and a fetch failure
  # would otherwise be indistinguishable from a type error.
  if [ -f tsconfig.json ]; then
    if [ -x node_modules/.bin/tsc ]; then run types node_modules/.bin/tsc --noEmit
    elif have tsc;                   then run types tsc --noEmit
    else note_missing tsc; fi
  fi
fi

# ── Python ─────────────────────────────────────────────────────────────────────
# Discover sources ANYWHERE, not just the repo root. Root-only globbing misses the
# conventional src/ + tests/ layout and silently reports "no checks available".
# `git ls-files` also lists tracked-but-deleted paths, so filter to files that exist.
PY_FILES=$(
  { git ls-files '*.py' 2>/dev/null
    find . -name '*.py' -not -path './.git/*' -not -path '*/node_modules/*' \
      -not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null | sed 's|^\./||'
  } | sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done | head -400
)

if [ -n "$PY_FILES" ]; then
  if have ruff;   then run lint ruff check .; else note_missing ruff; fi
  if have mypy;   then run types mypy .;      else note_missing mypy; fi

  if have pytest; then
    run test pytest -q
  else
    note_missing pytest
    # Substitute, do not skip. Contract and unit tests are written to run standalone.
    STANDALONE=$(find tests -name 'test_*.py' 2>/dev/null | sort)
    if [ -n "$STANDALONE" ]; then
      log "pytest unavailable; executing tests standalone"
      for t in $STANDALONE; do run "test:$t" python3 "$t"; done
    fi
    # Byte-compilation is a genuine static check: it catches syntax and import-time errors.
    # shellcheck disable=SC2086
    run syntax python3 -m py_compile $PY_FILES
  fi
fi

# ── Verdict ────────────────────────────────────────────────────────────────────
if [ -n "$unavailable" ]; then
  log "tools unavailable (not treated as pass): $unavailable"
fi

if [ "$ran" -eq 0 ]; then
  persist fail "no executable checks available; unavailable: ${unavailable:-none}"
  fail "no executable checks found — G4 cannot pass vacuously"
fi

if [ $rc -eq 0 ]; then
  persist pass "$ran checks green; unavailable: ${unavailable:-none}"
  pass "$ran executable checks green"
fi
persist fail "executable checks failed"
fail "executable checks failed"
