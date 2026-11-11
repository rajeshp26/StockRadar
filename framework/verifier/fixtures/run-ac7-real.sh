#!/usr/bin/env bash
# AC-7, positive direction, on the REAL stack.
#
# The negative direction (a criterion with no evidence refuses closure) is proven by run-ac7.sh.
# This proves the other half: a real browser driving the real product against real Supabase data
# produces an artifact, the artifact is recorded against the criterion, and g19 judges it.
#
# Nothing here is mocked. web/e2e/portfolio-performance-realdata.spec.ts reads the live
# /performance payload and asserts the DOM against it, so "real DB data" is the ground truth
# rather than a fixture.
#
# Exit: 0 the chain behaved as declared | 1 the chain is broken | 3 the stack is unreachable,
# which is UNVERIFIABLE and never a pass.
set -u
cd "$(dirname "$0")/../../.." || exit 9

PLAN=verification_output/fixtures/AC7-REAL-PLAN.md
MATRIX=verification_output/fixtures/AC7-REAL-PLAN.matrix.json
# The fixture's OWN state root. `emit --state-root` exists so a fixture emit never repoints the
# live closure pointer; the live root is read separately below, when the gate records are located.
FIXTURE_STATE=/mnt/c/Users/rajes/AppData/Local/Temp/opencode/ac7-real-state

BASE_URL="$(sed -n 's/^E2E_BASE_URL=//p' web/.env.e2e | tr -d '\r' | head -1)"
BASE_URL="${BASE_URL:-http://localhost:3000}"

# The backend address is read from the app's OWN config, not from a second variable that can
# drift from it. `BACKEND_ORIGIN` is what the Next.js proxy dials; if it is wrong the page 502s
# and the spec fails on a dead upstream, so it is the dependency that must be probed. A separate
# E2E_API_URL is only a fallback for a checkout that has no .env.local.
BACKEND_ORIGIN="$(sed -n 's/^BACKEND_ORIGIN=//p' web/.env.local 2>/dev/null | tr -d '\r' | head -1)"
if [ -z "$BACKEND_ORIGIN" ]; then
  BACKEND_ORIGIN="$(sed -n 's/^E2E_API_URL=//p' web/.env.e2e | tr -d '\r' | head -1)"
fi
BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://127.0.0.1:8001}"

# Supabase is the THIRD dependency, and the one that produces the "real data" this criterion is
# about. Global setup logs in through Supabase Auth directly (not through the app's proxy), so if
# Supabase is down the login fails and the suite reports a product failure. Measured: with local
# Supabase stopped, global setup logged three "did not navigate" attempts and the browser console
# showed `AuthRetryableFetchError: Failed to fetch` from supabase-js -- the app and the backend
# were both healthy. A two-dependency probe calls that a broken product.
SUPABASE_URL="$(sed -n 's/^NEXT_PUBLIC_SUPABASE_URL=//p' web/.env.local 2>/dev/null | tr -d '\r' | head -1)"

echo "== stack probe (from the side the browser runs on) =="
echo "web      $BASE_URL"
echo "backend  $BACKEND_ORIGIN   (BACKEND_ORIGIN from web/.env.local)"
echo "supabase ${SUPABASE_URL:-<not configured>}   (NEXT_PUBLIC_SUPABASE_URL)"

# The probe runs on Windows via node.exe, NOT via curl in WSL. Measured: curl inside WSL
# reported the backend reachable (localhost:8001 -> 200) while the Windows Next.js proxy
# answered 502 "fetch failed" on every call -- because WSL's localhost and Windows' localhost are
# different namespaces. The browser is Windows node.exe, so the probe must be too.
PROBE_URLS=("$BASE_URL/" "$BACKEND_ORIGIN/health")
if [ -n "$SUPABASE_URL" ]; then
  PROBE_URLS+=("$SUPABASE_URL/auth/v1/health")
fi
if ! node.exe framework/verifier/fixtures/probe-stack.js "${PROBE_URLS[@]}"; then
  echo "UNVERIFIABLE: a dependency is not reachable from the browser's side -- not a pass"
  echo "(the real-data spec reads the live /performance payload and logs in through Supabase;"
  echo " without either there is nothing to assert the DOM against, so a green browser run would"
  echo " prove nothing)"
  exit 3
fi

echo
echo "== emit (fixture state root: the live closure pointer is not repointed) =="
rm -rf "$FIXTURE_STATE"
mkdir -p "$FIXTURE_STATE"
python3 framework/verifier/matrix.py emit --plan "$PLAN" --state-root "$FIXTURE_STATE" || exit 1

echo
echo "== warm the dev server =="
# Next.js compiles a route on first request. Global setup fills and submits the login form within
# 20s per attempt, and on a cold `next dev --turbopack` the /login bundle is still compiling at
# that point, so the form is not hydrated and every submit is a silent no-op. Measured: three
# attempts, all "did not navigate", `URL at failure: http://localhost:3000/login`. Requesting the
# routes first makes the compile happen before the timed login starts.
node.exe framework/verifier/fixtures/probe-stack.js "$BASE_URL/login" "$BASE_URL/portfolio" >/dev/null
echo "warmed /login and /portfolio"

echo
echo "== real-stack browser run: the GATE runs the browser, not this script =="
# This script used to run Playwright itself and then file the result under `--gate g6`. That was
# the last hole in the chain (VERIFICATION-CONTRACT-DESIGN.md 12.4): the caller named the gate, so
# any artifact could be attributed to a routed gate. Now g6 runs, judges, and writes its own
# record; this script only names the criterion. g6 owns visible behaviour, which is what a
# Playwright run proves. g17 owns the frozen system-test suite, so AC-1 ([browser] -> [g6, g17])
# stays open until g17 has a result of its own -- browser evidence alone cannot close it.
# CLOSURE_MATRIX names the fixture matrix, exactly as g19 is given it below. The routing
# DECISION still comes from the matrix's required_gates, not from this variable.
CLOSURE_MATRIX="$MATRIX" CLOSURE_PLAN="$PLAN" \
  bash framework/gates/g6_browser.sh portfolio-performance-realdata
g6_rc=$?
echo "g6_exit=$g6_rc"

echo
echo "== record the gate's own record against AC-1 =="
# `--from-gate` reads the gate identity, the exit code and the artifact hashes FROM the record
# g6 just wrote. Nothing on this line can change what the gate concluded.
STATE="$(python3 framework/adapters/gsd_state.py state-root 2>/dev/null | tr -d '\r')"
GATE_RECORD="$STATE/verification/gates/g6.json"
[ -f "$GATE_RECORD" ] || { echo "AC-7 FAIL: g6 judged but wrote no record at $GATE_RECORD"; exit 1; }
# `--stack-reached` is the one field the gate cannot know: it is the outcome of the probe above,
# and the probe is what the harness owns. It is not a claim about the product.
python3 framework/verifier/matrix.py record --matrix "$MATRIX" --ac AC-1 \
  --from-gate "$GATE_RECORD" --stack-reached
rec_rc=$?
echo "record_g6_exit=$rec_rc"
[ "$rec_rc" -eq 0 ] || { echo "AC-7 FAIL: record refused"; exit 1; }

echo
echo "== g17: the frozen system-test suite, on the same live stack =="
# The other half of AC-1. g6 proves the chart renders the payload; g17 proves the payload is a
# real series from the real database, produced by a suite frozen before it ran. Neither can
# substitute for the other, which is why the row stays open until both have a result.
#
# The harness RUNS here and the gate JUDGES next. Two separate acts on purpose:
#   * `run` cannot launder an edit. It refuses to start unless the frozen suite and the data
#     manifest are byte-identical to the freeze lock, so re-running is not re-freezing. Freezing
#     is the author's deliberate act and is deliberately NOT part of this script.
#   * `verify` (inside g17) then re-checks the result: hashes, plan digest, and `code_state` --
#     HEAD + the working-tree diff + every untracked, non-ignored file. That is why the run sits
#     here, immediately before the gate: any edit in between invalidates it, by design.
#
# Credentials come from the app's own dotenv files through one helper, because WSL bash does not
# inherit the caller's environment and a second copy of the addresses would drift.
. framework/verifier/stack_env.sh || { echo "AC-7 FAIL: stack contract incomplete (see above)"; exit 2; }
echo "system tests -> $SYSTEM_TEST_BASE_URL (BACKEND_ORIGIN), auth via $SYSTEM_TEST_SUPABASE_URL"
python3 framework/testing/run_system_tests.py run --plan "$PLAN" --phase green
run_rc=$?
echo "green_run_exit=$run_rc"
if [ "$run_rc" -eq 2 ]; then
  # BLOCKED: the stack was not reachable from the runner. Unverifiable, never a pass.
  echo "AC-7 REAL: the system-test harness could not reach the stack -- UNVERIFIABLE"
  exit 3
fi

SYSTEM_PLAN="$PLAN" bash framework/gates/g17_system_tests.sh
g17_rc=$?
echo "g17_exit=$g17_rc"

echo
echo "== record the g17 record against AC-1 =="
G17_RECORD="$STATE/verification/gates/g17.json"
[ -f "$G17_RECORD" ] || { echo "AC-7 FAIL: g17 judged but wrote no record at $G17_RECORD"; exit 1; }
python3 framework/verifier/matrix.py record --matrix "$MATRIX" --ac AC-1 \
  --from-gate "$G17_RECORD" --stack-reached
rec17_rc=$?
echo "record_g17_exit=$rec17_rc"
[ "$rec17_rc" -eq 0 ] || { echo "AC-7 FAIL: record refused"; exit 1; }

echo
echo "== g19 closure =="
CLOSURE_MATRIX="$MATRIX" CLOSURE_PLAN="$PLAN" bash framework/gates/g19_closure.sh
g19_rc=$?
echo "g19_exit=$g19_rc"

echo
if [ "$g6_rc" -eq 3 ] || [ "$g17_rc" -eq 3 ]; then
  # Exit 3 is "we could not look". It must never be reported as a product failure, and it must
  # never close the criterion -- g19 refusing is the correct companion outcome.
  echo "AC-7 REAL: a gate could not produce evidence (g6=$g6_rc g17=$g17_rc) -- UNVERIFIABLE"
  [ "$g19_rc" -ne 0 ] || { echo "AC-7 FAIL: g19 closed a criterion whose gate could not judge"; exit 1; }
  exit 3
fi
if [ "$g6_rc" -ne 0 ] || [ "$g17_rc" -ne 0 ]; then
  echo "AC-7 REAL: a gate failed on the live stack (g6=$g6_rc g17=$g17_rc); g19 must refuse (got $g19_rc)"
  [ "$g19_rc" -ne 0 ] || { echo "AC-7 FAIL: g19 passed a criterion with a failing gate"; exit 1; }
  exit 1
fi
if [ "$g19_rc" -eq 0 ]; then
  echo "AC-7 REAL PASS: real browser + real Supabase data + frozen system suite -> g19 exit 0"
  exit 0
fi
# Both gates passed and closure was still refused: the matrix disagrees with its own gates.
echo "AC-7 FAIL: g6 and g17 both passed but g19 refused closure (g19_exit=$g19_rc)"
exit 1
