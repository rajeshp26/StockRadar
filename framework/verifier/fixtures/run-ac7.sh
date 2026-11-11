#!/usr/bin/env bash
# AC-7 regression: a plan whose goal criterion is [e2e] cannot reach COMPLETED when no system
# test exists to prove it.
#
# Why a wrapper: the gate's inputs are environment variables, and on a Windows host the only bash
# is WSL, which does NOT inherit the caller's environment (measured: a PowerShell `$env:X` is
# empty inside `bash -c`). Exporting here is what makes the run reproducible; `matrix.py emit
# --state-root` keeps the fixture from repointing the live closure pointer.
#
# Exit 0 = the defect stays fixed. Exit 1 = the plan reached closure without evidence.
set -u
cd "$(dirname "$0")/../../.." || exit 9

PLAN=verification_output/fixtures/AC7-PLAN.md
STATE=/mnt/c/Users/rajes/AppData/Local/Temp/opencode/ac7-state
rm -rf "$STATE"
mkdir -p "$STATE"

echo "== emit =="
python3 framework/verifier/matrix.py emit --plan "$PLAN" --state-root "$STATE"
emit_rc=$?
echo "emit_exit=$emit_rc"
[ "$emit_rc" -eq 0 ] || { echo "AC-7 FAIL: emit did not build a matrix"; exit 1; }

echo
echo "== g19 closure (expect exit 1: AC-1 is pending, so completion is refused) =="
export CLOSURE_MATRIX="verification_output/fixtures/AC7-PLAN.matrix.json"
export CLOSURE_PLAN="$PLAN"
out="$(bash framework/gates/g19_closure.sh 2>&1)"
g19_rc=$?
printf '%s\n' "$out"
echo "g19_exit=$g19_rc"

echo
if [ "$g19_rc" -ne 1 ]; then
  echo "AC-7 FAIL: expected g19 exit 1 (refused), got $g19_rc"
  exit 1
fi
if ! printf '%s' "$out" | grep -q 'AC-1 \[e2e\].*pending'; then
  echo "AC-7 FAIL: g19 refused but did not name AC-1 [e2e] as the open criterion"
  exit 1
fi
echo "AC-7 PASS: an [e2e] criterion with no evidence refuses closure and names AC-1"
