#!/usr/bin/env bash
# G6 — browser verification. Fills the browser verifier profile that previously had
# commands: [] and could therefore only ever report unverifiable.
#
# Contract: exit 0 pass, 1 fail, 3 UNVERIFIABLE (driver or app absent).
# Exit 3 is deliberately NOT 0. "We could not look" must never read as "it looks right".
GATE_NAME=g6-browser
source "$(dirname "$0")/_lib.sh"

UNVERIFIABLE=3

# Does this task even have a visible-behaviour requirement? The Verifier passes the
# requirement shape in; absent that, fall back to whether frontend files changed.
shape="${REQUIREMENT_SHAPE:-}"
fe_changed="$(changed_source_files | grep -E '^src/frontend/.*\.(tsx|ts|css)$' || true)"

if [ -z "$fe_changed" ] && [ "$shape" != "visible_behaviour" ]; then
  persist skip "no visible-behaviour requirement and no frontend source changed"
  # G6 emits ONLY 0/1/3 (EXIT_CODES.md:14 row, :29). Exit 4 is outside its
  # vocabulary and a vacuous exit 0 is forbidden, so nothing-to-judge maps to
  # UNVERIFIABLE. This overstates the gap rather than passing vacuously.
  unverifiable \
    "no visible-behaviour requirement and no frontend source changed" \
    "{\"requirement_shape\":\"${shape:-null}\",\"frontend_files_changed\":0}"
fi

# --- driver availability -------------------------------------------------------
if [ ! -f package.json ]; then
  persist unverifiable "no package.json; cannot run browser verification"
  log "UNVERIFIABLE  no package.json — browser evidence unavailable, NOT a pass"
  exit $UNVERIFIABLE
fi

if ! grep -q '"@playwright/test"' package.json 2>/dev/null; then
  persist unverifiable "@playwright/test not a dependency"
  log "UNVERIFIABLE  @playwright/test absent — install it before claiming UI requirements verified"
  exit $UNVERIFIABLE
fi

PW="node_modules/.bin/playwright"
if [ ! -x "$PW" ]; then
  persist unverifiable "playwright binary not installed (run: npm ci)"
  log "UNVERIFIABLE  playwright not installed locally — refusing to fetch at gate time"
  exit $UNVERIFIABLE
fi

# Browser binaries are a separate download from the npm package.
if ! "$PW" --version >/dev/null 2>&1; then
  persist unverifiable "playwright present but not runnable"
  log "UNVERIFIABLE  playwright not runnable — check: npx playwright install"
  exit $UNVERIFIABLE
fi

if [ ! -f playwright.config.ts ] && [ ! -f playwright.config.js ]; then
  persist unverifiable "no playwright.config"
  log "UNVERIFIABLE  no playwright.config — cannot establish viewports or baseURL"
  exit $UNVERIFIABLE
fi

# --- are there any browser specs to run? ---------------------------------------
specs="$(git ls-files 'tests/e2e/*' 'tests/browser/*' '*.spec.ts' 2>/dev/null | head -20)"
if [ -z "$specs" ]; then
  persist unverifiable "no browser specs found under tests/e2e or tests/browser"
  log "UNVERIFIABLE  no browser specs — a visible-behaviour requirement needs one"
  exit $UNVERIFIABLE
fi

ART="framework/telemetry/browser"
mkdir -p "$ART"

log "running playwright (all configured projects/viewports)"
set +e
"$PW" test --reporter=list --output="$ART/artifacts" 2>&1 | tee "$ART/last-run.txt"
rc=${PIPESTATUS[0]}
set -e

# Screenshot/trace evidence must actually exist for a pass to mean anything.
shots=$(find "$ART/artifacts" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')

if [ "$rc" -ne 0 ]; then
  persist fail "browser specs failed (see $ART/last-run.txt)"
  fail "browser verification failed — $ART/last-run.txt, $shots screenshot(s)"
fi

persist pass "browser specs passed, $shots screenshot(s) captured"
pass "browser verification passed ($shots screenshot artefact(s) in $ART/artifacts)"
