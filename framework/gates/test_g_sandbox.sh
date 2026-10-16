#!/usr/bin/env bash
# Tests for the sandbox capability (framework/adapters/sandbox.py) and G-SANDBOX.
#
# Runs under WSL/Linux bash -- that is where the gates run, so that is where the
# capability must hold. Exercises pure argv construction, the readiness probe, real
# enforcement (ro target / rw scratch / cleared env / no egress), the CONTAINER backend
# (pure argv, live probe, live enforcement), the gate's exit contract, and the
# NOT_APPLICABLE bypass.
#
# Exit: 0 all pass | 1 a check failed | 2 harness error (repo root not found)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT=""
_p="$HERE"
while [ -n "$_p" ] && [ "$_p" != "/" ]; do
  if [ -f "$_p/framework/adapters/sandbox.py" ]; then ROOT="$_p"; break; fi
  _p="$(dirname "$_p")"
done
[ -n "$ROOT" ] || { echo "HARNESS ERROR: repo root (framework/adapters/sandbox.py) not found" >&2; exit 2; }
cd "$ROOT" || exit 2

fail=0
okmsg() { printf 'ok   %s\n' "$*"; }
bad()   { printf 'FAIL %s\n' "$*"; fail=1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/g-sandbox-test.XXXXXX")"
CROOT=""
trap 'rm -rf "$TMP" "$CROOT"' EXIT
mkdir -p "$TMP/t" "$TMP/s"
echo secret > "$TMP/t/secret.txt"

echo "-- argv construction (pure, no bwrap required) --"
if python3 framework/adapters/sandbox.py argv \
     --target "$TMP/t" --scratch "$TMP/s" --allow-env PATH=/usr/bin:/bin -- /bin/true \
     > "$TMP/argv.json" 2>"$TMP/argv.err"; then
  if python3 - "$TMP/argv.json" "$TMP/t" "$TMP/s" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))["argv"]
tgt, scr = sys.argv[2], sys.argv[3]
need = ["bwrap", "--ro-bind", "--unshare-net", "--clearenv", "--setenv",
        "--die-with-parent", "--unshare-pid", "--tmpfs", "--chdir"]
miss = [x for x in need if x not in a]
assert not miss, f"missing flags: {miss}"
assert tgt in a and scr in a, "target/scratch not bound at their own paths"
assert a[a.index(scr) - 1] == "--bind", "scratch must be a read-write --bind"
assert a[a.index(tgt) - 1] == "--ro-bind", "target must be a read-only --ro-bind"
print("ok   argv: ro target, rw scratch, net/pid isolation, clearenv, allowed env only")
PY
  then :; else bad "argv construction invariants"; fi
else
  bad "argv subcommand failed: $(cat "$TMP/argv.err")"
fi

echo "-- readiness probe --"
python3 framework/adapters/sandbox.py probe >"$TMP/probe.out" 2>&1
prc=$?
if [ "$prc" -eq 0 ]; then
  okmsg "probe reports sandbox ENFORCEABLE (exit 0)"
else
  bad "probe not enforceable (exit $prc):"
  sed 's/^/     /' "$TMP/probe.out"
fi

echo "-- run(): enforcement --"
cat > "$TMP/s/probe.sh" <<EOF
#!/bin/bash
cat "$TMP/t/secret.txt" >/dev/null 2>&1 && echo READ_OK || echo READ_FAIL
echo hi > "$TMP/s/ok.txt" 2>/dev/null && echo WRITE_SCRATCH_OK || echo WRITE_SCRATCH_FAIL
if { echo x > "$TMP/t/evil.txt"; } 2>/dev/null; then echo TARGET_WRITABLE; else echo TARGET_READONLY; fi
if env | grep -q '^HOME='; then echo ENV_LEAK; else echo ENV_CLEAR; fi
EOF
out="$(python3 framework/adapters/sandbox.py run --target "$TMP/t" --scratch "$TMP/s" -- /bin/bash "$TMP/s/probe.sh" 2>&1)"
for want in READ_OK WRITE_SCRATCH_OK TARGET_READONLY ENV_CLEAR; do
  case "$out" in *"$want"*) okmsg "run: $want" ;; *) bad "run expected $want; got: $(printf '%s' "$out" | tr '\n' '|')" ;; esac
done
case "$out" in *TARGET_WRITABLE*) bad "run: target was WRITABLE (isolation broken)" ;; esac

echo "-- run(): no external egress --"
out="$(python3 framework/adapters/sandbox.py run --target "$TMP/t" --scratch "$TMP/s" -- \
      /bin/bash -c 'timeout 4 bash -c "exec 3<>/dev/tcp/1.1.1.1/443" 2>/dev/null && echo EGRESS || echo NO_EGRESS' 2>&1)"
case "$out" in
  *NO_EGRESS*) okmsg "run: external egress blocked" ;;
  *EGRESS*)    bad "run: external network reachable from the sandbox" ;;
  *)           bad "run egress probe inconclusive: $(printf '%s' "$out" | tr '\n' '|')" ;;
esac

echo "-- container backend: argv construction (pure; engine forced) --"
if SANDBOX_ENGINE="docker.exe" python3 framework/adapters/sandbox.py argv --backend container \
     --target "$TMP/t" --scratch "$TMP/s" --allow-env PATH=/usr/bin:/bin -- /bin/true \
     > "$TMP/cargv.json" 2>"$TMP/cargv.err"; then
  if python3 - "$TMP/cargv.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))["argv"]
need = ["run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "--tmpfs"]
miss = [x for x in need if x not in a]
assert not miss, f"missing controls: {miss}"
assert a[a.index("--security-opt") + 1] == "no-new-privileges"
# Docker cannot unset the image's own ENV, so the target starts under `env -i` with only
# the allowlist -- the container's --clearenv equivalent. `env` is also the entrypoint,
# which bypasses the image's own ENTRYPOINT.
assert a[a.index("--entrypoint") + 1] == "/usr/bin/env", "entrypoint must be env"
assert "-i" in a, "env -i expected (cleared environment)"
binds = [a[i + 1] for i, x in enumerate(a) if x == "-v"]
assert any(b.endswith(":ro") for b in binds), "no read-only bind"
assert any(b.endswith(":rw") for b in binds), "no read-write bind"
print("ok   container argv: net/ro/caps/no-new-privileges/limits/env -i/entrypoint")
PY
  then :; else bad "container argv invariants"; fi
else
  bad "container argv subcommand failed: $(cat "$TMP/cargv.err")"
fi

echo "-- container backend: live probe + enforcement (skipped when unavailable) --"
python3 framework/adapters/sandbox.py probe --backend container >"$TMP/cprobe.out" 2>&1
cprc=$?
if [ "$cprc" -eq 0 ]; then
  okmsg "container probe reports ENFORCEABLE (exit 0)"
  # /tmp is not bindable by a Windows engine reached through WSL interop, so the live
  # container checks use a scratch on the drive the repo lives on.
  CROOT="$ROOT/.g-sandbox-ctr.$$"
  mkdir -p "$CROOT/t" "$CROOT/s"
  echo secret > "$CROOT/t/secret.txt"
  out="$(python3 framework/adapters/sandbox.py run --backend container \
        --target "$CROOT/t" --scratch "$CROOT/s" -- \
        /bin/bash -c "cat $CROOT/t/secret.txt >/dev/null 2>&1 && echo READ_OK || echo READ_FAIL;
                      echo hi > $CROOT/s/ok.txt 2>/dev/null && echo WRITE_SCRATCH_OK || echo WRITE_SCRATCH_FAIL;
                      if { echo x > $CROOT/t/evil.txt; } 2>/dev/null; then echo TARGET_WRITABLE; else echo TARGET_READONLY; fi;
                      if env | grep -q '^HOME='; then echo ENV_LEAK; else echo ENV_CLEAR; fi" 2>&1)"
  for want in READ_OK WRITE_SCRATCH_OK TARGET_READONLY ENV_CLEAR; do
    case "$out" in *"$want"*) okmsg "container run: $want" ;; *) bad "container run expected $want; got: $(printf '%s' "$out" | tr '\n' '|')" ;; esac
  done
  case "$out" in *TARGET_WRITABLE*) bad "container run: target was WRITABLE (isolation broken)" ;; esac
  rm -rf "$CROOT"; CROOT=""
elif [ "$cprc" -eq 3 ]; then
  echo "skip container live checks (engine/image/bindable root unavailable here):"
  sed 's/^/     /' "$TMP/cprobe.out" | head -8
else
  bad "container probe not enforceable (exit $cprc):"
  sed 's/^/     /' "$TMP/cprobe.out" | head -8
fi

echo "-- G-SANDBOX gate contract --"
bash framework/gates/g_sandbox.sh >"$TMP/g.out" 2>&1; grc=$?
if [ "$grc" -eq 0 ]; then okmsg "g_sandbox exit 0 (enforceable -> execution permitted)"
else bad "g_sandbox expected 0 got $grc: $(tail -n3 "$TMP/g.out" 2>/dev/null | tr '\n' '|')"; fi

SANDBOX_EXEC_REQUIRED=0 bash framework/gates/g_sandbox.sh >"$TMP/g2.out" 2>&1; grc=$?
if [ "$grc" -eq 4 ]; then okmsg "g_sandbox exit 4 (NOT_APPLICABLE: execution not required)"
else bad "g_sandbox expected 4 got $grc"; fi

echo
if [ "$fail" -ne 0 ]; then echo "FAIL: sandbox capability tests failed."; exit 1; fi
echo "PASS: sandbox capability tests hold."
exit 0
