#!/usr/bin/env bash
# G6 — browser verification. Fills the browser verifier profile that previously had
# commands: [] and could therefore only ever report unverifiable.
#
# The gate drives the app the config BINDS, not the repository root. Before readiness was
# wired in it ran the root `playwright.config.ts` over `tests/e2e` -- the Vite reference
# scaffold -- while the product lived in `web/`. A visible-behaviour requirement could pass
# against a mocked scaffold spec and prove nothing about the application.
#
# Contract: exit 0 pass, 1 fail, 3 UNVERIFIABLE (driver, app or specs absent).
# Exit 3 is deliberately NOT 0. "We could not look" must never read as "it looks right".
GATE_NAME=g6-browser
source "$(dirname "$0")/_lib.sh"

UNVERIFIABLE=3

# Resolved app binding (framework/locate.py). Every value is cwd-relative and POSIX-shaped,
# because this gate runs under bash on Windows via WSL interop.
where() { python3 framework/locate.py --get "$1" 2>/dev/null | tr -d '\r'; }

MANIFEST="$(where frontend_manifest)"
PW_CONFIG="$(where playwright_config)"
SPECS_DIR="$(where browser_specs)"
FE_GLOBS_RE="$(where frontend_globs_regex)"
APP_DIR="$(dirname "${MANIFEST:-package.json}")"
[ -n "$APP_DIR" ] || APP_DIR="."

# Does this task even have a visible-behaviour requirement? Two sources, in order:
#   1. REQUIREMENT_SHAPE, passed in by the Verifier;
#   2. the verification matrix's required_gates, written by `matrix.py emit` at dispatch.
# The second source exists because the first is unreliable: on a Windows host the only bash
# is WSL, which does NOT inherit the caller's environment, so an env-only input silently
# reads as absent (measured: `PROBE_VAR=hello` in PowerShell is empty inside `bash -c`).
# The matrix is the durable carrier -- g6 being in required_gates IS the visible-behaviour
# decision, recorded against an acceptance criterion.
shape="${REQUIREMENT_SHAPE:-}"
shape_src="env"
if [ -z "$shape" ]; then
  shape_src="none"
  # CLOSURE_MATRIX names the artifact for an out-of-band run (a harness verifying a fixture
  # plan), exactly as g19 accepts it. The routing DECISION still comes from the matrix's
  # required_gates -- the variable only says which matrix to read, never whether g6 was routed.
  rg_args=()
  [ -n "${CLOSURE_MATRIX:-}" ] && rg_args+=(--matrix "$CLOSURE_MATRIX")
  routed="$(python3 framework/verifier/matrix.py required-gates "${rg_args[@]+"${rg_args[@]}"}" 2>/dev/null | tr -d '\r' || true)"
  case ",${routed}," in
    *,g6,*) shape="visible_behaviour"; shape_src="matrix" ;;
  esac
fi
fe_changed="$(changed_source_files | grep -E "$FE_GLOBS_RE" || true)"

# Logged BEFORE the early exit: a run that decides not to verify must still record the shape
# it decided on and where that shape came from, or "why didn't g6 run?" has no answer.
log "requirement shape: ${shape:-none} (source: ${shape_src}), frontend files changed: $(printf '%s' "$fe_changed" | grep -c . || true)"

if [ -z "$fe_changed" ] && [ "$shape" != "visible_behaviour" ]; then
  persist unverifiable "no visible-behaviour requirement and no frontend source changed"
  # G6 emits ONLY 0/1/3 (EXIT_CODES.md:14 row, :29). Exit 4 is outside its
  # vocabulary and a vacuous exit 0 is forbidden, so nothing-to-judge maps to
  # UNVERIFIABLE. This overstates the gap rather than passing vacuously.
  unverifiable \
    "no visible-behaviour requirement and no frontend source changed" \
    "{\"requirement_shape\":\"${shape:-null}\",\"shape_source\":\"${shape_src}\",\"frontend_files_changed\":0,\"globs\":\"${FE_GLOBS_RE}\"}"
fi

# --- app + driver availability -------------------------------------------------
# Every "cannot judge" path routes through `unverifiable`, never through a bare `exit 3`. A bare
# exit produced no `[gate]` line and no gate record, so the telemetry classifier saw nothing and
# `matrix.py record --from-gate` reported "the gate has not judged" -- turning "we could not
# look" into a hard failure instead of an unverifiable criterion.
if [ -z "$MANIFEST" ] || [ ! -f "$MANIFEST" ]; then
  persist unverifiable "no frontend manifest (${MANIFEST:-unset}); cannot run browser verification"
  unverifiable "no frontend manifest (${MANIFEST:-unset}) — browser evidence unavailable, NOT a pass" \
    "{\"manifest\":\"${MANIFEST:-null}\"}"
fi

if ! grep -q '"@playwright/test"' "$MANIFEST" 2>/dev/null; then
  persist unverifiable "@playwright/test not a dependency of $MANIFEST"
  unverifiable "@playwright/test absent from $MANIFEST — install it before claiming UI requirements verified" \
    "{\"manifest\":\"$MANIFEST\",\"dependency\":\"@playwright/test\"}"
fi

# Resolve a runnable playwright invocation from the APP's node_modules. The .bin shim is a
# POSIX script that execs `node`, which WSL-only hosts may not have on PATH while Windows
# `node.exe` (interop) can still run the CLI. Prefer the shim; fall back to node.exe with a
# RELATIVE CLI path — Windows node cannot open /mnt/c/... absolute paths, and this gate
# always runs from the repo root like every other path here.
PW="$APP_DIR/node_modules/.bin/playwright"
PW_CLI="$APP_DIR/node_modules/@playwright/test/cli.js"

if [ ! -x "$PW" ] && ! { have node.exe && [ -f "$PW_CLI" ]; }; then
  persist unverifiable "playwright binary not installed under $APP_DIR (run: npm ci)"
  unverifiable "playwright binary not installed under $APP_DIR (run: npm ci) — refusing to fetch at gate time" \
    "{\"app_dir\":\"$APP_DIR\",\"binary\":\"$PW\"}"
fi

PW_RUN=("$PW")
if ! "$PW" --version >/dev/null 2>&1; then
  # Browser binaries are a separate download from the npm package; a shim that
  # exists but cannot exec node is a different failure than an absent package.
  if have node.exe && [ -f "$PW_CLI" ] && node.exe "$PW_CLI" --version >/dev/null 2>&1; then
    PW_RUN=(node.exe "$PW_CLI")
    log "driver resolved via node.exe interop (bin shim has no node on PATH)"
  elif [ -x "$PW" ]; then
    persist unverifiable "playwright present but not runnable"
    unverifiable "playwright present but not runnable — check: npx playwright install" \
      "{\"app_dir\":\"$APP_DIR\",\"binary\":\"$PW\"}"
  else
    persist unverifiable "playwright binary not installed (run: npm ci)"
    unverifiable "playwright binary not installed (run: npm ci)" \
      "{\"app_dir\":\"$APP_DIR\",\"binary\":\"$PW\"}"
  fi
fi

if [ -z "$PW_CONFIG" ] || [ ! -f "$PW_CONFIG" ]; then
  persist unverifiable "no playwright config at ${PW_CONFIG:-unset}"
  unverifiable "no playwright config at ${PW_CONFIG:-unset} — cannot establish viewports or baseURL" \
    "{\"playwright_config\":\"${PW_CONFIG:-null}\"}"
fi

# --- are there any browser specs to run? ---------------------------------------
# Playwright resolves `testDir` relative to the CONFIG file, so the gate can run from the
# repo root and still drive the bound app. Untracked specs count: the product suite is
# git-ignored in some checkouts, and "not committed yet" is not "no specs".
shopt -s globstar nullglob
specs=("$SPECS_DIR"/**/*.spec.ts)
shopt -u globstar nullglob
if [ ${#specs[@]} -eq 0 ]; then
  persist unverifiable "no browser specs found under $SPECS_DIR"
  unverifiable "no browser specs under $SPECS_DIR — a visible-behaviour requirement needs one" \
    "{\"specs_dir\":\"$SPECS_DIR\",\"specs\":0}"
fi
log "specs: ${#specs[@]} file(s) under $SPECS_DIR"

ART="framework/telemetry/browser"
# Per-run, immutable: a fixed `last-run.txt` is rewritten by the next run, which silently
# invalidates every matrix record bound to its hash. `last-run.txt` is kept as a convenience
# copy for humans; the artifact the record binds is the timestamped one.
RUN_DIR="$ART/runs/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
# The selection is what this run judged. Recorded in the gate result so a reader can tell a
# whole-suite run from a filtered one -- a filtered run that is not named is an unstated scope.
GATE_SELECTION="$*"

log "running playwright against $PW_CONFIG (all configured projects/viewports)${GATE_SELECTION:+ selection: $GATE_SELECTION}"
set +e
"${PW_RUN[@]}" test --config "$PW_CONFIG" --reporter=list --output="$RUN_DIR/artifacts" "$@" 2>&1 \
  | tee "$RUN_DIR/run.txt"
rc=${PIPESTATUS[0]}
set -e
cp "$RUN_DIR/run.txt" "$ART/last-run.txt" 2>/dev/null || true

# Screenshot/trace evidence must actually exist for a pass to mean anything.
shots=$(find "$RUN_DIR/artifacts" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')

# The gate names its own evidence before it judges, so both the pass and the fail record
# carry the artifact the verdict was made from.
gate_artifact "$RUN_DIR/run.txt"

if [ "$rc" -ne 0 ]; then
  persist fail "browser specs failed (see $RUN_DIR/run.txt)"
  fail "browser verification failed — $RUN_DIR/run.txt, $shots screenshot(s)"
fi

persist pass "browser specs passed, $shots screenshot(s) captured"
pass "browser verification passed ($shots screenshot artefact(s) in $RUN_DIR/artifacts)"
