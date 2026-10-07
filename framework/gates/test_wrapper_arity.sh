#!/usr/bin/env bash
# Locks the argument arity and exit contract of every non-judgement wrapper.
#
# WHY THIS EXISTS
#     Routing `unverifiable` through `non_judgement` made it require a second
#     argument. Six live call sites (g6_browser.sh:23,29,36,43,49,57) pass a
#     message only, so under `set -u` every one of them died on
#     `$2: unbound variable`. G6 is the one gate whose contract
#     (EXIT_CODES.md:14) declares BLOCKED "NEVER EMITTED", so silently turning
#     its exit-3 paths into exit-2 paths would have violated that contract.
#
#     Nothing else covered this: the conformance test supplies evidence to every
#     wrapper, so it passed while the one-argument form was broken. This test
#     exercises the arity that production actually uses.
#
# EXIT
#     0 every wrapper honours its contract, 1 otherwise
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${GATES_DIR:-}" ]; then
    LIB="$GATES_DIR/_lib.sh"
else
    LIB=""
    probe="$HERE"
    while [ -n "$probe" ] && [ "$probe" != "/" ]; do
        if [ -f "$probe/framework/gates/_lib.sh" ]; then
            LIB="$probe/framework/gates/_lib.sh"
            break
        fi
        probe="$(dirname "$probe")"
    done
fi

# No fallback to the staged copy. An earlier version resolved one level too high,
# found nothing, silently substituted the staged _lib.sh and reported PASS while
# testing the wrong file -- the "unverifiable reads as a pass" shape, in the
# harness that exists to detect it. If the library cannot be located, that is a
# harness error (exit 2), never a pass.
if [ ! -f "$LIB" ]; then
    echo "HARNESS ERROR: _lib.sh not found (GATES_DIR=${GATES_DIR:-unset}); refusing to guess." >&2
    exit 2
fi

fail=0

ERRFILE="$HERE/.arity_probe.err"

probe() {
    # probe <wrapper> <message> [evidence]  -> sets P_LINE / P_RC / P_ERR
    local wrapper="$1"; shift
    local out rc
    out="$(GATE_NAME=g_arity bash -c '
        set -uo pipefail
        . "$1"; shift
        "$@"
    ' _ "$LIB" "$wrapper" "$@" 2>"$ERRFILE")"
    rc=$?
    P_RC=$rc
    P_LINE="$(printf '%s' "$out" | grep '^\[gate\] ' | head -n1)"
    P_ERR="$(cat "$ERRFILE")"
    rm -f "$ERRFILE"
}

check() {
    # check <label> <expected_rc> <expect_evidence:yes|no>
    local label="$1" want_rc="$2" want_ev="$3"
    local problems=""

    [ "$P_RC" = "$want_rc" ] || problems="$problems rc=$P_RC want=$want_rc"
    [ -n "$P_LINE" ] || problems="$problems no-[gate]-line"
    case "$P_ERR" in
        *unbound*) problems="$problems unbound-variable" ;;
    esac
    if [ "$want_ev" = yes ]; then
        case "$P_LINE" in
            *evidence=*) ;;
            *) problems="$problems missing-evidence" ;;
        esac
    else
        case "$P_LINE" in
            *evidence=*) problems="$problems unexpected-evidence" ;;
        esac
    fi

    if [ -n "$problems" ]; then
        printf 'FAIL %-46s %s\n' "$label" "$problems"
        fail=1
    else
        printf 'ok   %-46s rc=%s %s\n' "$label" "$P_RC" "$P_LINE"
    fi
}

echo "lib: $LIB"
echo

echo "-- new wrappers: evidence mandatory, refused loudly when absent --"
probe not_applicable "no changed source files" '{"changed_source_files": 0}'
check "not_applicable/2-arg -> exit 4 + evidence" 4 yes

probe not_applicable "no changed source files"
check "not_applicable/1-arg -> refused (no silent pass)" 1 no

probe precondition_missing "no plan" '{"changed_source_files": 9}'
check "precondition_missing/2-arg -> exit 2 + evidence" 2 yes

probe capability_missing "no tool" '{"tool": "playwright"}'
check "capability_missing/2-arg -> exit 3 + evidence" 3 yes

echo
echo "-- unverifiable: evidence OPTIONAL, exit 3 always (G6 contract) --"
probe unverifiable "playwright binary not installed"
check "unverifiable/1-arg (g6 pattern) -> exit 3, no evidence" 3 no

probe unverifiable "playwright present but not runnable"
check "unverifiable/1-arg variant -> exit 3, no evidence" 3 no

probe unverifiable "no browser specs" '{"checked": "tests/e2o"}'
check "unverifiable/2-arg -> exit 3 + evidence" 3 yes

echo
echo "-- no non-judgement path may exit 0 --"
for w in not_applicable precondition_missing capability_missing unverifiable; do
    probe "$w" "m" '{"k": 1}'
    if [ "$P_RC" = 0 ]; then
        printf 'FAIL %-46s exited 0\n' "$w with evidence"
        fail=1
    fi
done
[ "$fail" -eq 0 ] && echo "ok   no non-judgement wrapper exits 0"

echo
if [ "$fail" -ne 0 ]; then
    echo "FAIL: wrapper arity/exit contract violated."
    exit 1
fi
echo "PASS: wrapper arity and exit contract hold."
exit 0