# Audit sandbox container

One OCI image (`agentic-lifecycle/sandbox:1`) is the framework's provisioning unit for
the security-audit tier. It does two jobs:

1. **Toolchain.** It carries the POSIX toolchain that tier needs: `node` >=18, `python3`,
   `git`. The vendored validators (`validate-findings.cjs`, `validate-coverage-ledger.cjs`)
   require `O_NOFOLLOW`; a Windows `node.exe` cannot provide it, so a host without a POSIX
   `node` gets the interpreter from here instead of from the host.
2. **Isolation boundary.** When unprivileged user namespaces / bubblewrap are unavailable,
   the container *is* the sandbox for target-controlled execution:
   `--network=none --read-only --cap-drop=ALL --security-opt no-new-privileges` with
   bounded pids/memory/fsize. `framework/adapters/sandbox.py` runs it and then **proves**
   those controls hold (`probe --backend container`). It does not nest bubblewrap — a
   container shares the host kernel, so nesting would add nothing.

The policy that declares these controls is `framework/security/sandbox_policy.yaml`.

## Build

```bash
bash framework/container/build.sh          # builds/tags agentic-lifecycle/sandbox:1
```

Requires a usable **Docker or Podman** engine able to run Linux containers. Under WSL the
script resolves `docker.exe` (the Windows CLI) when Docker Desktop's WSL integration is
off; bind sources are then translated to Windows paths automatically.

## Use

```bash
# measure whether the container can enforce the controls on THIS host
python3 framework/adapters/sandbox.py probe --backend container

# which backend does the framework pick? (native bubblewrap, else container)
python3 framework/adapters/sandbox.py probe

# run a command inside the container boundary
python3 framework/adapters/sandbox.py run --backend container \
    --target <read-only dir> --scratch <writable dir> -- <cmd> [args...]
```

Backends report through `G-SANDBOX` (`framework/gates/g_sandbox.sh`) and the audit gate
`G18`. A host with neither backend is unenforceable: execution is refused and the audit
stays source-only. There is no "best effort" mode.

## Notes

- The `devcontainer` variant (`.devcontainer/devcontainer.json`) opens the whole
  development environment, with this image as its base, so the toolchain is present
  without touching the host. It is optional; the container backend above works without it.
- Under WSL interop the engine is a Windows binary and can only bind-mount Windows-drive
  paths (`/mnt/<drive>`). Point `SANDBOX_TMP` at such a directory if the framework is run
  from elsewhere.
