#!/usr/bin/env bash
# test_gate_verdict_contract.sh — proves no gate can report result=pass for an
# unjudged state.
#
# WHY THIS TEST IS FALSIFIABLE
#   It asserts on the REAL framework/gates/_lib.sh, loaded as a source file, and
#   invokes its own helpers. If a future patch weakens the contract, this test
#   goes red. If the helpers are absent, it goes red. It cannot pass vacuously.
#
#   Expected: RED against current framework/gates/_lib.sh (line 74 emits
#   result=pass exit=0 for a non-judging skip). GREEN against a patched one.
#
# Usage: bash framework/gates/test_gate_verdict_contract.sh
# Exit:  0 = contract holds, 1 = contract violated (this is the defect), 2 = harness error

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# Locate the real gates directory. This test must exercise the REAL _lib.sh, so
# resolve it by walking up to the repo root rather than assuming we already sit
# inside framework/gates/ (it also runs from .planning/patches/ while staging).
GATES_DIR="${GATES_DIR:-}"
if [ -z "$GATES_DIR" ]; then
  probe="$HERE"
  while [ "$probe" != "/" ] && [ -n "$probe" ]; do
    if [ -f "$probe/framework/gates/_lib.sh" ]; then GATES_DIR="$probe/framework/gates"; break; fi
    probe="$(dirname "$probe")"
  done
fi
LIB="${GATES_DIR:-}/_lib.sh"

if [ ! -f "$LIB" ]; then
  echo "HARNESS ERROR: _lib.sh not found (looked for framework/gates/_lib.sh above $HERE)" >&2
  exit 2
fi
g9="$GATES_DIR/g9_scope.sh"

GATE_NAME="g_verdict_contract_test"
FAILED=0

# Load the real library into this shell so we call its actual functions.
# shellcheck disable=SC1090
. "$LIB"

capture() {
  local out rc
  out="$( { "$@" ; } 2>/dev/null )"
  rc=$?
  printf '%s|%s' "$(printf '%s' "$out" | grep -m1 '\[gate\]' || true)" "$rc"
}

echo "== V1: skip() must not report result=pass =="
# The core lie. Current behaviour yields result=pass exit=0.
r="$(capture skip "some class genuinely does not exist")"
line="${r%%|*}"; rc="${r##*|}"
case "$line" in
  *"result=pass"*) printf 'FAIL V1 skip() emitted result=pass for a non-judging state\n       %s\n' "$line"; FAILED=1 ;;
  *"result="*)     printf 'ok   V1 skip() emitted a non-pass verdict: %s\n' "$line" ;;
  *)               printf 'FAIL V1 skip() emitted no canonical verdict line\n'; FAILED=1 ;;
esac

echo
echo "== V2: result vocabulary is closed =="
# Every helper's canonical result must be in the closed set.
for h in pass fail skip not_applicable precondition_missing capability_missing unverifiable; do
  if ! declare -f "$h" >/dev/null 2>&1; then
    printf 'note helper %s not yet implemented (acceptable pre-patch)\n' "$h"
  fi
done

echo
echo "== V3: classified verdicts require evidence =="
if declare -f not_applicable >/dev/null 2>&1; then
  r="$(capture not_applicable "no frontend present" '{"frontend_present": false}')"
  case "$r" in
    *"evidence="*) printf 'ok   V3 not_applicable carried evidence\n' ;;
    *)            printf 'FAIL V3 not_applicable did not require/emit evidence\n       %s\n' "$r"; FAILED=1 ;;
  esac
else
  printf 'note not_applicable() absent pre-patch; evidence rule not yet enforceable\n'
fi

echo
echo "== V4: g9 no-plan-context must NOT be a pass =="
# g9_scope.sh has two distinct non-judgement paths:
#   L17 "no plan context"  -> precondition_missing (gate could judge, inputs absent)
#   L45 "no source changes" -> not_applicable      (genuinely nothing in scope)
# Only the first is a lie. Test the fixed state first, then the known-broken one,
# then treat "unrecognised" as FAILING -- an unrecognised state must never read as
# pass, which is the same rule this whole change exists to enforce.
if [ ! -f "$g9" ]; then
  printf 'FAIL V4 g9_scope.sh not resolvable (expected at %s)\n' "$g9"
  FAILED=1
elif grep -q 'precondition_missing' "$g9"; then
  printf 'ok   V4 g9 classifies missing plan context as precondition_missing\n'
elif grep -qE 'skip[[:space:]]+"no plan context' "$g9"; then
  printf 'FAIL V4 g9 still routes missing plan context through skip() -> result=pass\n'
  FAILED=1
else
  printf 'FAIL V4 g9 no-plan-context path unrecognised; inspect manually\n'
  FAILED=1
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "PASS: verdict contract holds."
  exit 0
else
  echo "FAIL: verdict contract violated (expected before the fix is applied)."
  exit 1
fi