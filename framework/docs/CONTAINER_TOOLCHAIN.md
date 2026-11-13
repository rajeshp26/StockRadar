# Container toolchain — how the audit tier's native dependencies are provisioned

## The problem

The security-audit tier has two native dependencies the framework cannot satisfy with Python:

1. **A POSIX toolchain.** The vendored validators (`validate-findings.cjs`,
   `validate-coverage-ledger.cjs`) are Node programs that require `O_NOFOLLOW` and non-blocking
   opens. A Windows `node.exe` cannot provide them, so it reports
   `OS no-follow and nonblocking input protection is unavailable` for *every* input — a valid one
   included. It cannot judge, and a non-judgement must never read as a pass.
2. **An OS-enforced sandbox.** Target-controlled execution is refused unless the host can enforce
   no egress, a read-only target, a cleared environment and bounded resources.

The framework already handles absent *capabilities* by detecting them and failing closed
(`framework/adapters/host.py` "reports capability; it does not grant it"). That is the right
runtime posture, but it left a fresh project with no *provisioning* story: install the framework
into a new repo on a host without `node` or `bubblewrap`, and the audit silently degrades to
source-only.

## The decision

Ship **one OCI image** and treat it as the provisioning unit, selected by capability probe:

- **Toolchain provider.** It carries `node` >=18, `python3` and `git`.
- **Second enforcement backend.** When unprivileged user namespaces / bubblewrap are unavailable,
  the container *is* the sandbox.

The framework does not assume the container works. `probe --backend container` **measures** the
controls and only then permits execution; otherwise the audit stays source-only.

## What ships

| Path | Role |
| --- | --- |
| `framework/container/Dockerfile` | the image: `node:22-bookworm-slim` + `python3`, `git`, `socat`; non-root `audit` user |
| `framework/container/build.sh` | builds and tags it (`agentic-lifecycle/sandbox:1`), engine- and path-aware |
| `framework/container/README.md` | build/use notes |
| `.devcontainer/devcontainer.json` | optional whole-environment variant using the same image |
| `framework/adapters/sandbox.py` | `probe`/`run`/`argv` with the `container` backend |
| `framework/security/sandbox_policy.yaml` | the declared controls (plane file) |

## Build

```bash
bash framework/container/build.sh
```

Requires Docker or Podman able to run Linux containers, and network access to pull the base image.
Under WSL the script resolves `docker.exe` (the Windows CLI) when Docker Desktop's WSL integration
is off, and translates bind sources to Windows paths automatically.

## How it is used

```bash
python3 framework/adapters/sandbox.py probe                      # auto: native, else container
python3 framework/adapters/sandbox.py probe --backend container   # measure the container only
python3 framework/adapters/sandbox.py run --backend container \
    --target <ro dir> --scratch <rw dir> -- <cmd> [args...]
```

`G-SANDBOX` (`framework/gates/g_sandbox.sh`) runs the auto probe; it reports the chosen backend
and maps the same exit codes (`0` enforceable / `1` violated / `3` missing / `4` N/A).
`G18` (`framework/gates/g18_security_audit.sh`) tries native `node` first and falls through to the
container, so it reaches a real verdict instead of `UNVERIFIABLE` on hosts whose `node` cannot
judge.

## Enforcement controls (container backend)

The image is run as:

```
docker run --rm --init --network=none --read-only --cap-drop=ALL \
  --security-opt no-new-privileges --pids-limit N --memory Mm --ulimit fsize=… \
  --tmpfs /tmp --user <uid>:<gid> \
  -v <host target>:<same path>:ro -v <host scratch>:<same path>:rw \
  --entrypoint /usr/bin/env <image> -i PATH=… <cmd...>
```

Notes that cost real debugging:

- **Binds are path-preserving** (destination equals the host absolute path), so a command that
  names a host path works unchanged inside the container.
- **`env -i` is the cleared environment.** Docker cannot unset an image's own `ENV`
  (`NODE_VERSION`, `DEBIAN_FRONTEND`, …), so the target is started under `env -i` with only the
  allowlist — the container's equivalent of the native `--clearenv`.
- **`/usr/bin/env` is the entrypoint**, which also bypasses the image's own `ENTRYPOINT`
  (the node image ships a bare `docker-entrypoint.sh`, resolvable only through `PATH`).
- **PATH must include `/usr/local/bin`**, where the node image installs `node`.

Verified controls on this host (`probe --backend container` → `ok=True`): engine usable, image
present, container starts, target read-only, scratch writable, rootfs read-only, non-loopback
interfaces absent and outbound connect blocked, and only allowlisted environment names present.

## Limitations

- **Windows-drive binds only under WSL interop.** The engine is a Windows binary; it can bind
  `/mnt/<drive>` sources but not `\\wsl.localhost` (i.e. `/tmp`, `/home`) — it fails with
  *distro mount service*. The adapter detects this and reports a **missing** capability (exit `3`),
  never a violated control. Override the bindable root with `SANDBOX_TMP`.
- **A container shares the host kernel.** It is weaker than bubblewrap's user-namespace boundary
  and is therefore the *fallback*, not the default. Native remains preferred when available.
- **Images are not signed or pinned here.** Production use should pin the base image by digest and
  publish the built image to a registry; `SANDBOX_IMAGE` overrides the reference.
- **The `.devcontainer` variant is optional** and not required for the container backend.
