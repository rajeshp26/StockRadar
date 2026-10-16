# Agentic-lifecycle audit sandbox image.
#
# ONE artifact, two jobs (declared in framework/security/sandbox_policy.yaml):
#
#   1. TOOLCHAIN -- supplies the POSIX toolchain the audit tier needs on hosts that lack
#      it: node >=18 (the vendored .cjs validators require O_NOFOLLOW, which a Windows
#      node.exe lacks), python3, and git. This is why the image exists at all: a fresh
#      project gets the toolchain by pulling/building the image instead of provisioning
#      the host.
#
#   2. ISOLATION -- the container IS the enforcement boundary for target-controlled
#      execution when unprivileged user namespaces / bubblewrap are unavailable. The
#      sandbox adapter runs it with --network=none --read-only --cap-drop=ALL
#      --security-opt no-new-privileges and bounded pids/memory/fsize, then PROVES those
#      controls hold (framework/adapters/sandbox.py probe --backend container).
#
# It is NOT a nested sandbox: bubblewrap is deliberately absent. A container already
# shares the host kernel; nesting bwrap inside it would add nothing and require
# privileges that defeat the point.
FROM node:22-bookworm-slim

LABEL org.opencontainers.image.title="agentic-lifecycle sandbox" \
      org.opencontainers.image.description="Audit toolchain + target-execution sandbox for the agentic-lifecycle framework" \
      org.opencontainers.image.source="https://github.com/rajeshp26/agentic-lifecycle" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 \
      git \
      socat \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# A dedicated unprivileged user, so a bare `docker run` (without --user) is already
# non-root. uid 10001 avoids the base image's `node` user (uid 1000). The sandbox
# adapter overrides this with the invoking uid so a bind-mounted scratch stays writable.
RUN groupadd --gid 10001 audit \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin audit

# A stable, minimal environment. HOME is /tmp because the rootfs is mounted read-only
# and /tmp is the only writable mount (a tmpfs).
ENV PATH="/usr/local/bin:/usr/bin:/bin" \
    HOME=/tmp
WORKDIR /tmp
USER 10001:10001
