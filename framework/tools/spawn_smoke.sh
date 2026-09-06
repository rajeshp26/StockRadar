#!/usr/bin/env bash
# Fresh-session spawn smoke test for the agentic framework.
#
# Spawns a real opencode agent in a fresh session and proves the model
# resolution path end to end: an agent whose model id cannot be resolved
# stalls for the inactivity timeout, so a passing smoke test is the cheapest
# proof that failures close loudly instead.
#
# Usage: bash framework/tools/spawn_smoke.sh [--agent NAME] [--timeout SECS]
# Exit 0 iff the agent replies with the SMOKE_OK marker.
set -euo pipefail

AGENT="verifier"
TMO="180"

usage() {
  echo "usage: bash framework/tools/spawn_smoke.sh [--agent NAME] [--timeout SECS]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)   AGENT="$2"; shift 2 ;;
    --timeout) TMO="$2";   shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PROMPT="Reply with exactly: SMOKE_OK"

if command -v timeout >/dev/null 2>&1; then
  raw="$(timeout "$TMO" opencode run "$PROMPT" --agent "$AGENT" 2>&1 || true)"
else
  raw="$(opencode run "$PROMPT" --agent "$AGENT" 2>&1 || true)"
fi

case "$raw" in
  *SMOKE_OK*) echo "SMOKE_OK"; exit 0 ;;
  *) echo "SMOKE_FAIL: no SMOKE_OK marker from agent '$AGENT' after ${TMO}s" >&2; exit 1 ;;
esac