#!/usr/bin/env bash
# g_telemetry_live.sh -- prove the telemetry collector is running, not just configured.
#
# WHY: validate.py asserts the plugin is declared and its path exists. Both held for five
# weeks while the plugin never loaded (a relative file:// URL resolved "framework" as the URL
# host) and records.jsonl stopped growing. Existence is not liveness.
#
# EXIT CONTRACT (framework/gates/EXIT_CODES.md):
#   0  PASS            a heartbeat landed within the budget
#   1  FAIL            declared but never wrote, or the last write is stale
#   2  BLOCKED         records exist but are unreadable/unparseable
#   4  NOT_APPLICABLE  no collector declared
#
# Usage: bash framework/gates/g_telemetry_live.sh [--max-age-s N]
set -uo pipefail

gate="g_telemetry_live"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
tool="$repo/framework/tools/telemetry_live.py"

if [ ! -f "$tool" ]; then
  echo "$gate: BLOCKED - $tool is missing; liveness cannot be judged" >&2
  exit 2
fi

py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ]; then
  echo "$gate: BLOCKED - no python interpreter; liveness cannot be judged" >&2
  exit 2
fi

out="$("$py" "$tool" --root "$repo" "$@" 2>&1)"
rc=$?
echo "$gate: $out"
exit "$rc"
