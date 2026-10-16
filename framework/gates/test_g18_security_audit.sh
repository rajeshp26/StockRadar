#!/usr/bin/env bash
# Tests for G18 (framework/gates/g18_security_audit.sh).
#
# G18's happy path depends on the vendored skill (a plane file), so this test drives it
# with STUB validators: it proves G18's own logic -- path resolution, node interpreter
# selection + path dialect, exit-code mapping, and completion refusal on an open
# confirmed high/critical finding. The real validators are proven separately by the
# skill's own node:test suites.
#
# Exit: 0 all pass | 1 a check failed | 2 harness error
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=""
_p="$HERE"
while [ -n "$_p" ] && [ "$_p" != "/" ]; do
  if [ -f "$_p/framework/gates/g18_security_audit.sh" ]; then ROOT="$_p"; break; fi
  _p="$(dirname "$_p")"
done
[ -n "$ROOT" ] || { echo "HARNESS ERROR: repo root not found" >&2; exit 2; }
cd "$ROOT" || exit 2

fail=0
okmsg() { printf 'ok   %s\n' "$*"; }
bad()   { printf 'FAIL %s\n' "$*"; fail=1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/g18-test.XXXXXX")"
CROOT=""
trap 'rm -rf "$TMP" "$CROOT"' EXIT
RUN="$TMP/run"; SKILL="$TMP/skill"; NOSKILL="$TMP/noskill"
mkdir -p "$RUN" "$SKILL" "$NOSKILL"

STUB='const fs=require("fs");let s="";try{s=fs.readFileSync(process.argv[2],"utf8");}catch(e){console.error("stub: cannot read artifact");process.exit(11);}if(s.includes("SCHEMA_INVALID")){console.error("stub: schema invalid");process.exit(1);}process.exit(0);'
printf '%s\n' "$STUB" > "$SKILL/validate-findings.cjs"
printf '%s\n' "$STUB" > "$SKILL/validate-coverage-ledger.cjs"

# A stub that reproduces the Windows node.exe refusal: it rejects EVERY input with the
# POSIX-protection message, which must be read as unverifiable, not as an invalid artifact.
NONPOSIX="$TMP/skill-nonposix"; mkdir -p "$NONPOSIX"
NSTUB='console.error("Failed to read findings JSON: OS no-follow and nonblocking input protection is unavailable");process.exit(2);'
printf '%s\n' "$NSTUB" > "$NONPOSIX/validate-findings.cjs"
printf '%s\n' "$NSTUB" > "$NONPOSIX/validate-coverage-ledger.cjs"

write_valid() { # <findings-json-content>
  printf '%s\n' "$1" > "$RUN/findings.json"
  printf '[{"note":"stub ledger"}]\n' > "$RUN/coverage-ledger.json"
}

expect() { # <want-rc> <label> <cmd...>
  local want="$1" label="$2"; shift 2
  "$@" >"$TMP/out" 2>&1
  local rc=$?
  if [ "$rc" = "$want" ]; then okmsg "$label (exit $rc)"
  else bad "$label: expected $want got $rc :: $(tail -n2 "$TMP/out" | tr '\n' '|')"; fi
}

G18="bash framework/gates/g18_security_audit.sh"

echo "-- exit-code contract --"
expect 4 "no audit run dir -> NOT_APPLICABLE" env AUDIT_RUN_DIR= $G18
expect 2 "run dir does not exist -> BLOCKED" env AUDIT_RUN_DIR="$TMP/nope" $G18

rm -f "$RUN/findings.json" "$RUN/coverage-ledger.json"
expect 2 "findings.json absent -> BLOCKED" env AUDIT_RUN_DIR="$RUN" $G18

printf '[{"verdict":"confirmed"}]\n' > "$RUN/findings.json"
expect 2 "coverage-ledger.json absent -> BLOCKED" env AUDIT_RUN_DIR="$RUN" $G18

write_valid '[{"verdict":"confirmed","fingerprint":"fp-1","title":"demo","severity":{"overall_severity":"low"}}]'
expect 3 "validators not installed -> UNVERIFIABLE" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$NOSKILL" $G18

expect 3 "non-POSIX interpreter cannot judge -> UNVERIFIABLE, never FAIL" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$NONPOSIX" $G18

echo "-- validator verdict --"
expect 0 "valid artifacts, confirmed low -> pass" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

write_valid 'SCHEMA_INVALID [{"verdict":"confirmed"}]'
expect 1 "findings.json fails validation -> FAIL" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

echo "-- completion refusal on open confirmed high/critical --"
write_valid '[{"verdict":"confirmed","fingerprint":"fp-high","title":"sql injection","severity":{"overall_severity":"high"}}]'
expect 1 "confirmed high -> blocked" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

write_valid '[{"verdict":"confirmed","fingerprint":"fp-crit","title":"auth bypass","severity":{"overall_severity":"critical"}}]'
expect 1 "confirmed critical -> blocked" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

write_valid '[{"verdict":"needs_validation","fingerprint":"fp-nv","title":"maybe","severity":{"overall_severity":"critical"}}]'
expect 0 "needs_validation critical is NOT a confirmed finding -> pass" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

write_valid '[{"verdict":"confirmed","fingerprint":"fp-h2","title":"a","severity":{"overall_severity":"high"}},{"verdict":"confirmed","fingerprint":"fp-l2","title":"b","severity":{"overall_severity":"medium"}}]'
expect 1 "one confirmed high among many -> blocked" \
  env AUDIT_RUN_DIR="$RUN" AUDIT_SKILL_DIR="$SKILL" $G18

echo "-- container fallback: a POSIX node supplied by the sandbox image --"
python3 framework/adapters/sandbox.py probe --backend container >"$TMP/cprobe.out" 2>&1
cprc=$?
if [ "$cprc" -eq 0 ]; then
  # Repo-side paths: the container backend binds these at their own paths, and /tmp is
  # not bindable by a Windows engine reached through WSL interop.
  CROOT="$ROOT/.g18-ctr.$$"
  CRUN="$CROOT/run"; CSKILL="$CROOT/skill"; FAKE="$CROOT/fakebin"
  mkdir -p "$CRUN" "$CSKILL" "$FAKE"
  printf '%s\n' "$STUB" > "$CSKILL/validate-findings.cjs"
  printf '%s\n' "$STUB" > "$CSKILL/validate-coverage-ledger.cjs"
  # Shadow every native interpreter with one that always refuses input protection, so the
  # ONLY candidate that can judge is the container's POSIX node.
  printf '%s\n' '#!/bin/sh' \
    'echo "Failed to read findings JSON: OS no-follow and nonblocking input protection is unavailable" >&2' \
    'exit 2' > "$FAKE/node"
  cp "$FAKE/node" "$FAKE/node.exe"
  chmod +x "$FAKE/node" "$FAKE/node.exe"

  printf '[{"verdict":"confirmed","fingerprint":"fp-low","title":"demo","severity":{"overall_severity":"low"}}]\n' > "$CRUN/findings.json"
  printf '[{"note":"stub ledger"}]\n' > "$CRUN/coverage-ledger.json"
  PATH="$FAKE:$PATH" AUDIT_RUN_DIR="$CRUN" AUDIT_SKILL_DIR="$CSKILL" \
    bash framework/gates/g18_security_audit.sh >"$TMP/cout" 2>&1; rc=$?
  if [ "$rc" = 0 ]; then okmsg "container POSIX node judges valid artifacts (exit 0)"
  else bad "container fallback expected 0 got $rc :: $(tail -n3 "$TMP/cout" | tr '\n' '|')"; fi

  printf '[{"verdict":"confirmed","fingerprint":"fp-high","title":"sql injection","severity":{"overall_severity":"high"}}]\n' > "$CRUN/findings.json"
  PATH="$FAKE:$PATH" AUDIT_RUN_DIR="$CRUN" AUDIT_SKILL_DIR="$CSKILL" \
    bash framework/gates/g18_security_audit.sh >"$TMP/cout" 2>&1; rc=$?
  if [ "$rc" = 1 ]; then okmsg "container POSIX node refuses completion on a confirmed high (exit 1)"
  else bad "container fallback expected 1 got $rc :: $(tail -n3 "$TMP/cout" | tr '\n' '|')"; fi

  rm -rf "$CROOT"; CROOT=""
else
  echo "skip container fallback checks (container backend unavailable here)"
fi

echo
if [ "$fail" -ne 0 ]; then echo "FAIL: G18 tests failed."; exit 1; fi
echo "PASS: G18 tests hold."
exit 0
