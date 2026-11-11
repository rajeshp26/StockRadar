#!/usr/bin/env bash
# One place that turns the app's own configuration into the SYSTEM_TEST_* contract.
#
# WHY THIS FILE EXISTS
#   * WSL bash does not inherit the caller's PowerShell environment (measured: a variable set in
#     PowerShell is empty inside `bash -c`), so the harness cannot be given its stack address by
#     the operator's shell.
#   * The addresses already exist in `web/.env.local` and `web/.env.e2e`. Copying them into a
#     second variable is exactly the drift this framework is being fixed to remove, so they are
#     READ here, not restated.
#   * The dotenv files are not shell: a value containing a space breaks `. file`, and a value
#     containing `$` would be expanded. They are parsed as KEY=VALUE and exported.
#
# The addresses are the app's, not this file's:
#   SYSTEM_TEST_BASE_URL      <- BACKEND_ORIGIN   (what the Next.js proxy dials; reachable from
#                                both Windows and WSL, unlike localhost:8001 which is one side only)
#                                fallback: E2E_API_URL
#   SYSTEM_TEST_SUPABASE_URL  <- NEXT_PUBLIC_SUPABASE_URL  (global setup logs in here directly)
#   SYSTEM_TEST_EMAIL/PASSWORD <- E2E_TEST_EMAIL / E2E_TEST_PASSWORD (the seeded test account)
#
# Usage: . framework/verifier/stack_env.sh   (returns 2 and prints what is missing if incomplete)
#
# A missing value is a configuration gap, never a skip: the caller must fail, not pass.

STACK_ENV_ROOT="${STACK_ENV_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

stack_env_export() {
  local script
  script="$(STACK_ENV_ROOT="$STACK_ENV_ROOT" python3 - <<'PY'
import os
import shlex
import sys

root = os.environ["STACK_ENV_ROOT"]
vals = {}
for rel in ("web/.env.local", "web/.env.e2e"):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        continue
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        vals.setdefault(key.strip(), value.strip().strip('"').strip("'"))

base = vals.get("BACKEND_ORIGIN") or vals.get("E2E_API_URL")
mapping = {
    "SYSTEM_TEST_BASE_URL": base,
    "SYSTEM_TEST_SUPABASE_URL": vals.get("NEXT_PUBLIC_SUPABASE_URL"),
    "SYSTEM_TEST_SUPABASE_ANON_KEY": vals.get("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    "SYSTEM_TEST_EMAIL": vals.get("E2E_TEST_EMAIL"),
    "SYSTEM_TEST_PASSWORD": vals.get("E2E_TEST_PASSWORD"),
}
missing = sorted(k for k, v in mapping.items() if not (v or "").strip())
if missing:
    # stderr, because the caller captures stdout: a message captured into a variable is invisible.
    print("STACK_ENV_MISSING " + " ".join(missing), file=sys.stderr)
    raise SystemExit(2)
print("export " + " ".join("%s=%s" % (k, shlex.quote(v)) for k, v in mapping.items()))
PY
)" || { echo "stack_env: cannot derive the stack contract (see STACK_ENV_MISSING above)" >&2; return 2; }
  eval "$script"
  export SYSTEM_TEST_BASE_URL SYSTEM_TEST_SUPABASE_URL SYSTEM_TEST_SUPABASE_ANON_KEY \
         SYSTEM_TEST_EMAIL SYSTEM_TEST_PASSWORD
  return 0
}

stack_env_export
