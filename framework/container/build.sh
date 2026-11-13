#!/usr/bin/env bash
# Build the audit sandbox image (framework/container/Dockerfile).
#
# The image is the framework's provisioning unit for the security-audit tier. It carries
# the POSIX toolchain the vendored validators need -- node >=18 (they require O_NOFOLLOW,
# which a Windows node.exe lacks), python3, git -- and it is the fallback isolation
# boundary for target-controlled execution when bubblewrap/user-namespaces are absent.
# See framework/security/sandbox_policy.yaml and framework/docs/CONTAINER_TOOLCHAIN.md.
#
# Idempotent. Run it once after installing (or when the Dockerfile changes).
#
# Exit: 0 built | 2 BLOCKED (no usable container engine, or the build failed)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE="${SANDBOX_IMAGE:-agentic-lifecycle/sandbox:1}"

cd "$REPO" || exit 2

if ! command -v python3 >/dev/null 2>&1; then
  echo "BLOCKED: python3 is required to resolve the container engine" >&2
  exit 2
fi

ENGINE_JSON="$(python3 framework/adapters/sandbox.py engine 2>/dev/null)"
if [ -z "$ENGINE_JSON" ]; then
  echo "BLOCKED: could not read the container engine (framework/adapters/sandbox.py engine)" >&2
  exit 2
fi
ENGINE="$(printf '%s' "$ENGINE_JSON" | python3 -c 'import json,sys;e=json.load(sys.stdin).get("engine");print(e[0] if e else "")')"
WINDOWS="$(printf '%s' "$ENGINE_JSON" | python3 -c 'import json,sys;print("1" if json.load(sys.stdin).get("windows_paths") else "0")')"

if [ -z "$ENGINE" ]; then
  echo "BLOCKED: no usable container engine (docker/podman) -- install Docker or Podman," >&2
  echo "         or run without the container backend (native bubblewrap only)." >&2
  exit 2
fi

# A Windows engine reached through WSL interop needs Windows source paths.
epath() {
  if [ "$WINDOWS" = "1" ] && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1" 2>/dev/null || printf '%s' "$1"
  else
    printf '%s' "$1"
  fi
}

CTX="$(epath "$HERE")"
echo "engine : $ENGINE"
echo "image  : $IMAGE"
echo "context: $CTX"

"$ENGINE" build -t "$IMAGE" "$CTX"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "BLOCKED: image build failed (exit $rc)" >&2
  exit 2
fi

echo "built  : $IMAGE"
"$ENGINE" image inspect "$IMAGE" --format '{{.Id}} ({{.Size}} bytes)' 2>/dev/null || true
