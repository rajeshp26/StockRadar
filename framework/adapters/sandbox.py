#!/usr/bin/env python3
"""Sandbox capability for target-controlled execution (security-audit).

WHY THIS EXISTS
    The security-audit skill refuses to execute target code without an OS-enforced
    sandbox: no external network, an empty allowlisted environment, a read-only
    target and toolchain, a single writable scratch directory, and bounded resources.
    This module is the framework's half of that contract. It PROBES whether the host
    can actually enforce those controls, and -- only when it can -- launches a
    command inside them.

TWO ENFORCEMENT BACKENDS
    native    -- unprivileged user namespaces (bubblewrap): read-only toolchain roots, an
                 ephemeral /tmp, no egress, a cleared environment, one writable dir.
    container -- an OCI image run with --network=none --read-only --cap-drop=ALL
                 --security-opt no-new-privileges and bounded pids/memory/fsize. The
                 container IS the boundary; it does not nest bubblewrap (a container
                 shares the host kernel, so nesting would add nothing). It also SUPPLIES
                 the POSIX toolchain (node>=18, python3, git) the audit tier needs on
                 hosts that lack it -- see framework/container/Dockerfile.

    probe() tries native first and falls back to container. A host with neither is
    unenforceable and execution is refused: there is no "best effort" backend.

VALIDATION
    Proven on this host by framework/experiments/sandbox-poc/probe.sh (14/14 pass):
    Windows + WSL2 (Linux 6.6.x-microsoft-standard), unprivileged user namespaces
    available, bubblewrap 0.9.0 + socat 1.8.0.0, cgroup limits via systemd-run --user.

CONTRACT
    probe() -> {"ok": bool, "missing": [...], "violations": [...], "unjudged": [...],
                "checks": {name: {status, detail, required}}}
        ok is True only when every REQUIRED control was enforced. `missing` is a
        capability that is absent (refuse execution, degrade to source-only);
        `violations` is a control that failed when attempted (isolation is broken).
        Neither is a pass, and a skipped required check is not a pass either.

    available() -> bool. run() -> CompletedProcess. run() must never be called
        unless probe()["ok"] is True.

CLI
    python3 framework/adapters/sandbox.py probe [--json] [--backend auto|native|container]
    python3 framework/adapters/sandbox.py argv   --target DIR --scratch DIR
             [--backend native|container] -- CMD [ARG...]
    python3 framework/adapters/sandbox.py run    --target DIR --scratch DIR
             [--backend auto|native|container]
             [--allow-env K=V]... [--net] [--mem-mb N] [--pids N] [--fsize-kb N]
             [--wall S] -- CMD [ARG...]
    python3 framework/adapters/sandbox.py engine        # resolved container engine (JSON)
    python3 framework/adapters/sandbox.py image         # the sandbox image reference

Exit (probe/run): 0 enforceable / 1 isolation violation / 3 capability missing.

ENVIRONMENT
    SANDBOX_BACKEND     default backend for probe/run (auto|native|container)
    SANDBOX_IMAGE       override the container image reference
    SANDBOX_ENGINE      force a container engine (e.g. "docker.exe"), skipping resolution
    SANDBOX_TMP         bindable scratch root for the container probe (Windows-reachable
                        when the engine is a Windows binary reached through WSL interop)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

# Read-only roots exposed to the sandbox: the toolchain and system files, never writable.
RO_TOOLCHAIN_ROOTS = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc")
# Controls that MUST be enforced before any target-controlled execution.
REQUIRED_CHECKS = ("bwrap", "userns", "bwrap_start", "fs_ro_scratch_rw", "net_isolation", "env_allowlist")
# /usr/local/bin is on PATH because the sandbox image installs node there (and it is under
# the read-only /usr root natively, so the native backend resolves it too).
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"
# The OCI image that supplies the audit toolchain AND acts as the fallback enforcement
# boundary. Built from framework/container/Dockerfile. Override with SANDBOX_IMAGE.
DEFAULT_IMAGE = os.environ.get("SANDBOX_IMAGE") or "agentic-lifecycle/sandbox:1"
# Container controls that MUST hold before any target-controlled execution.
CONTAINER_REQUIRED_CHECKS = ("container_engine", "container_image", "container_start",
                             "container_binds", "fs_ro_scratch_rw", "net_isolation",
                             "env_allowlist")
# Names a container runtime injects regardless of --env usage; a cleared-environment
# check must tolerate exactly these (and nothing else).
CONTAINER_BASE_ENV = ("PATH", "HOME", "HOSTNAME", "PWD", "SHLVL", "_")
# Engines are tried in this order. docker.exe precedes docker because under WSL interop
# the bare `docker` shim refuses to run without Docker Desktop's WSL integration, while
# docker.exe (the Windows CLI) works against the same engine.
_CONTAINER_ENGINES = ("docker.exe", "docker", "podman")
_WSL_WINDOWS_PATH = re.compile(r"^/mnt/[A-Za-z](/|$)")


def on_linux() -> bool:
    return sys.platform.startswith("linux")


def have(name: str) -> bool:
    """Path-aware lookup, so WSL interop (node.exe) resolves like a native tool."""
    return shutil.which(name) is not None


def _run(argv, timeout=30, cwd=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)


def _tail(text: str, n: int = 160) -> str:
    return " ".join((text or "").split())[:n]


def _version(argv) -> str:
    try:
        p = _run(argv, timeout=10)
        return _tail(p.stdout or p.stderr, 80) or "present"
    except Exception as exc:  # pragma: no cover - defensive
        return f"present ({type(exc).__name__})"


# ─── command construction (pure, unit-testable without bwrap) ────────────────────


@dataclass
class Spec:
    """What the sandbox exposes and how tightly it is bounded."""

    target: str | None = None          # read-only
    scratch: str | None = None         # read-write, the ONLY host-visible writable path
    extra_ro: tuple[str, ...] = ()     # additional read-only binds (e.g. a toolchain cache)
    allow_env: dict[str, str] = field(default_factory=dict)
    network: bool = False              # default: no external network
    mem_mb: int | None = None          # cgroup MemoryMax (via systemd-run --user)
    pids: int | None = None            # cgroup TasksMax + rlimit nproc
    fsize_kb: int | None = None        # rlimit file size (KB)
    wall_seconds: int | None = None    # wall-clock bound enforced by the launcher


def _ro_roots() -> list[str]:
    return [d for d in RO_TOOLCHAIN_ROOTS if os.path.isdir(d)]


def base_argv() -> list[str]:
    argv = ["bwrap"]
    for d in _ro_roots():
        argv += ["--ro-bind", d, d]
    # A private ephemeral /tmp (a fresh tmpfs) and isolated namespaces. /dev and /proc
    # are unshared; --unshare-net removes every interface but loopback.
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
    return argv


def _with_rlimits(spec: Spec, cmd: list[str]) -> list[str]:
    pre = []
    if spec.fsize_kb:
        pre.append(f"ulimit -f {int(spec.fsize_kb)} 2>/dev/null;")
    if spec.pids:
        pre.append(f"ulimit -u {int(spec.pids)} 2>/dev/null;")
    if not pre:
        return list(cmd)
    return ["/bin/bash", "-c", " ".join(pre) + ' exec "$@"', "_", *cmd]


def build_argv(spec: Spec, cmd: list[str]) -> list[str]:
    """Build the full argv. Pure: safe to assert on without a sandbox present."""
    argv = base_argv()
    if spec.target:
        t = os.path.abspath(spec.target)
        argv += ["--ro-bind", t, t]
    if spec.scratch:
        s = os.path.abspath(spec.scratch)
        argv += ["--bind", s, s, "--chdir", s]
    for d in spec.extra_ro:
        d = os.path.abspath(d)
        argv += ["--ro-bind", d, d]
    if not spec.network:
        argv += ["--unshare-net"]
    argv += ["--clearenv"]
    for key, val in spec.allow_env.items():
        argv += ["--setenv", key, val]
    argv += ["--die-with-parent", "--", *_with_rlimits(spec, cmd)]
    if spec.mem_mb or spec.pids:
        scope = ["systemd-run", "--user", "--scope", "--quiet"]
        if spec.mem_mb:
            scope += ["-p", f"MemoryMax={int(spec.mem_mb)}M"]
        if spec.pids:
            scope += ["-p", f"TasksMax={int(spec.pids)}"]
        argv = scope + ["--", *argv]
    return argv


def run(spec: Spec, cmd: list[str], check: bool = False, backend: str = "native",
        engine: list[str] | None = None):
    """Execute cmd inside the sandbox. Caller MUST have confirmed probe()['ok']."""
    argv = (build_container_argv(spec, cmd, engine=engine) if backend == "container"
            else build_argv(spec, cmd))
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=spec.wall_seconds, check=check)


# ─── container backend (fallback boundary + toolchain provider) ──────────────────


def container_engine(validate: bool = True) -> list[str] | None:
    """Resolve a usable container CLI, or None. Path-aware, so WSL interop resolves.

    validate=True confirms the engine can actually run LINUX containers (`info`), because
    under WSL the bare `docker` shim exists on PATH yet refuses to run without Docker
    Desktop's WSL integration -- a present-but-unusable engine must not read as present.
    """
    forced = os.environ.get("SANDBOX_ENGINE")
    if forced:
        return forced.split()
    for name in _CONTAINER_ENGINES:
        path = shutil.which(name)
        if not path:
            continue
        if not validate:
            return [path]
        try:
            p = _run([path, "info", "--format", "{{.OSType}}"], timeout=30)
        except Exception:
            continue
        if p.returncode == 0 and "linux" in (p.stdout or "").lower():
            return [path]
    return None


def engine_needs_windows_paths(engine: list[str]) -> bool:
    """A Windows engine reached through WSL interop needs Windows bind sources."""
    if not engine:
        return False
    exe = engine[0].replace("\\", "/")
    return exe.lower().endswith(".exe") or bool(_WSL_WINDOWS_PATH.match(exe))


def to_engine_path(path: str, windows: bool) -> str:
    """Translate a bind source to the engine's dialect (Windows path under WSL interop)."""
    p = os.path.abspath(path)
    if not windows:
        return p
    try:
        r = _run(["wslpath", "-w", p], timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return p


def _sandbox_user() -> str | None:
    """Run the container as the invoking uid so a bind-mounted scratch stays writable."""
    if os.environ.get("SANDBOX_UID"):
        return os.environ["SANDBOX_UID"]
    if hasattr(os, "getuid"):
        return f"{os.getuid()}:{os.getgid()}"
    return None


def build_container_argv(spec: Spec, cmd: list[str], image: str | None = None,
                         engine: list[str] | None = None) -> list[str]:
    """Build `docker run` argv. Deterministic given an engine (pass one to unit-test)."""
    engine = engine if engine is not None else container_engine()
    if not engine:
        raise RuntimeError("no container engine (docker/podman) on PATH")
    win = engine_needs_windows_paths(engine)
    img = image or DEFAULT_IMAGE
    argv = [*engine, "run", "--rm", "--init"]
    if not spec.network:
        argv += ["--network=none"]
    argv += ["--read-only", "--cap-drop=ALL",
             "--security-opt", "no-new-privileges",
             "--pids-limit", str(int(spec.pids or 512)),
             "--tmpfs", "/tmp", "--workdir", "/tmp"]
    if spec.mem_mb:
        argv += ["--memory", f"{int(spec.mem_mb)}m"]
    if spec.fsize_kb:
        argv += ["--ulimit", f"fsize={int(spec.fsize_kb) * 1024}"]
    user = _sandbox_user()
    if user:
        argv += ["--user", user]
    # Path-preserving binds: the destination equals the host path, so a command that
    # names a host absolute path works unchanged inside the container.
    if spec.target:
        t = os.path.abspath(spec.target)
        argv += ["-v", f"{to_engine_path(t, win)}:{t}:ro"]
    for d in spec.extra_ro:
        d = os.path.abspath(d)
        argv += ["-v", f"{to_engine_path(d, win)}:{d}:ro"]
    if spec.scratch:
        s = os.path.abspath(spec.scratch)
        argv += ["-v", f"{to_engine_path(s, win)}:{s}:rw", "--workdir", s]
    for key, val in spec.allow_env.items():
        argv += ["-e", f"{key}={val}"]
    # A genuinely emptied environment. Docker cannot unset the image's own ENV
    # (NODE_VERSION, DEBIAN_FRONTEND, ...), so the target is started under `env -i` with
    # only the allowlist -- the container's equivalent of the native --clearenv. `env` is
    # also the entrypoint, which bypasses the image's own ENTRYPOINT for the same reason.
    env_pairs = dict(spec.allow_env)
    env_pairs.setdefault("PATH", DEFAULT_PATH)
    argv += ["--entrypoint", "/usr/bin/env"]
    argv += [img, "-i", *[f"{k}={v}" for k, v in env_pairs.items()], *cmd]
    return argv


def binds_reachable(spec: Spec, engine: list[str]) -> bool:
    """True when the engine can mount every path this Spec binds.

    Under WSL interop the engine is a Windows binary and only Windows-drive sources are
    reachable; a /tmp or /home source fails with the engine's "distro mount service" error.
    Detecting it here turns an opaque engine failure into a MISSING-capability verdict.
    """
    if not engine_needs_windows_paths(engine):
        return True
    for p in (spec.target, spec.scratch, *spec.extra_ro):
        if p and not _WSL_WINDOWS_PATH.match(os.path.abspath(p)):
            return False
    return True


def _bindable_root(engine: list[str]) -> str | None:
    """A directory the engine can bind-mount from, or None when there is none.

    Under WSL interop the engine is a Windows binary and only Windows-drive paths are
    reachable: a \\\\wsl.localhost source (i.e. /tmp or /home) fails with "distro mount
    service". A probe that must judge the filesystem therefore needs a bindable root;
    when there is none the caller reports a MISSING capability, never a violated one --
    the isolation is not broken, the probe simply cannot measure it here.
    """
    import tempfile
    if not engine_needs_windows_paths(engine):
        return tempfile.gettempdir()
    override = os.environ.get("SANDBOX_TMP")
    if override and os.path.isdir(override) and _WSL_WINDOWS_PATH.match(os.path.abspath(override)):
        return override
    cwd = os.getcwd()
    if _WSL_WINDOWS_PATH.match(cwd):
        return cwd
    return None


# ─── readiness probe ─────────────────────────────────────────────────────────────


def _report(checks: dict) -> dict:
    missing = [n for n, c in checks.items() if c["required"] and c["status"] == "missing"]
    violations = [n for n, c in checks.items() if c["required"] and c["status"] == "violation"]
    unjudged = [n for n, c in checks.items() if c["required"] and c["status"] == "skip"]
    return {
        "ok": not missing and not violations and not unjudged,
        "missing": sorted(missing),
        "violations": sorted(violations),
        "unjudged": sorted(unjudged),
        "checks": checks,
    }


def _probe_native(timeout: int = 40) -> dict:
    checks: dict[str, dict] = {}

    def rec(name, status, detail, required=True):
        checks[name] = {"status": status, "detail": detail, "required": bool(required)}

    if not on_linux():
        rec("platform", "missing",
            f"not a Linux/WSL host (sys.platform={sys.platform}); no OS-enforced sandbox")
        return _report(checks)
    rec("platform", "pass", f"{platform.system()} {platform.release()}")

    bwrap_ok = have("bwrap")
    rec("bwrap", "pass" if bwrap_ok else "missing",
        _version(["bwrap", "--version"]) if bwrap_ok else "bubblewrap (bwrap) not installed")
    rec("socat", "pass" if have("socat") else "missing",
        "socat present" if have("socat") else "socat absent (needed only for loopback relays)",
        required=False)

    # The single prerequisite that could not be assumed: unprivileged user namespaces.
    if not have("unshare"):
        rec("userns", "missing", "unshare(1) not installed")
    else:
        p = _run(["unshare", "--user", "--map-root-user", "--mount", "--net", "--pid", "--fork", "true"], timeout)
        rec("userns", "pass" if p.returncode == 0 else "violation",
            "unprivileged user+mount+net+pid namespaces create"
            if p.returncode == 0 else f"namespace creation denied: {_tail(p.stderr)}")

    if have("systemd-run"):
        p = _run(["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=268435456", "true"], timeout)
        rec("cgroup_user", "pass" if p.returncode == 0 else "violation",
            "systemd-run --user scope MemoryMax works" if p.returncode == 0
            else "systemd-run --user unavailable; limits fall back to rlimits", required=False)
    else:
        rec("cgroup_user", "missing", "systemd-run absent; limits fall back to rlimits", required=False)

    if not bwrap_ok:
        for name in ("bwrap_start", "fs_ro_scratch_rw", "net_isolation", "env_allowlist"):
            rec(name, "skip", "bwrap not installed")
        return _report(checks)

    # bwrap starts at all.
    try:
        p = _run([*base_argv(), "--unshare-net", "--die-with-parent", "/bin/true"], timeout)
        rec("bwrap_start", "pass" if p.returncode == 0 else "violation",
            "sandbox entered and exited cleanly" if p.returncode == 0
            else f"bwrap start failed: {_tail(p.stderr)}")
    except Exception as exc:
        rec("bwrap_start", "violation", f"bwrap start raised {type(exc).__name__}: {exc}")

    # Filesystem: target read-only, scratch writable, write to target blocked.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="sbx-probe.") as tmp:
        target = os.path.join(tmp, "target")
        scratch = os.path.join(tmp, "scratch")
        os.makedirs(target)
        os.makedirs(scratch)
        with open(os.path.join(target, "secret.txt"), "w", encoding="utf-8") as fh:
            fh.write("secret")
        spec = Spec(target=target, scratch=scratch, allow_env={"PATH": DEFAULT_PATH})
        probe_cmd = ["/bin/bash", "-c",
                     f'cat {target}/secret.txt >/dev/null 2>&1 || {{ echo RO_READ_FAIL; exit 21; }}; '
                     f'echo ok > {scratch}/ok.txt 2>/dev/null || {{ echo SCRATCH_WRITE_FAIL; exit 22; }}; '
                     f'if {{ echo x > {target}/evil.txt; }} 2>/dev/null; then echo TARGET_WRITE_SUCCEEDED; exit 23; fi; '
                     f'echo OK']
        try:
            p = run(spec, probe_cmd, check=False)
            out = (p.stdout or "") + (p.stderr or "")
            if "TARGET_WRITE_SUCCEEDED" in out:
                rec("fs_ro_scratch_rw", "violation", "target directory was writable")
            elif "OK" in out:
                rec("fs_ro_scratch_rw", "pass", "target read-only, scratch writable, target write blocked")
            else:
                rec("fs_ro_scratch_rw", "violation", f"unexpected: {_tail(out)}")
        except Exception as exc:
            rec("fs_ro_scratch_rw", "violation", f"probe raised {type(exc).__name__}: {exc}")

        net_cmd = ["/bin/bash", "-c",
                   'timeout 4 bash -c "exec 3<>/dev/tcp/1.1.1.1/443" 2>/dev/null && { echo EGRESS_OK; exit 32; }; echo OK']
        try:
            p = run(Spec(network=False, allow_env={"PATH": DEFAULT_PATH}), net_cmd, check=False)
            out = (p.stdout or "") + (p.stderr or "")
            rec("net_isolation", "violation" if "EGRESS_OK" in out else "pass",
                "outbound connect blocked (loopback-only namespace)" if "EGRESS_OK" not in out
                else "external network reachable from the sandbox")
        except Exception as exc:
            rec("net_isolation", "violation", f"probe raised {type(exc).__name__}: {exc}")

        env_cmd = ["/bin/bash", "-c", 'env | sed "s/=.*//" | sort -u']
        try:
            p = run(Spec(allow_env={"PATH": DEFAULT_PATH}), env_cmd, check=False)
            names = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
            extra = [n for n in names if n not in ("PATH", "PWD", "SHLVL", "_", "OLDPWD")]
            rec("env_allowlist", "violation" if extra else "pass",
                f"unexpected inherited vars: {extra}" if extra
                else f"only allowlisted names present: {names}")
        except Exception as exc:
            rec("env_allowlist", "violation", f"probe raised {type(exc).__name__}: {exc}")

    return _report(checks)


# A container's egress control is judged by POSITIVE evidence: enumerate interfaces
# (--network=none leaves only `lo`) AND attempt a connect. Node is used because the
# sandbox image always ships it, so the check can never pass vacuously for want of a tool.
_NET_PROBE_JS = (
    'const os=require("os"),net=require("net");'
    'const ext=Object.keys(os.networkInterfaces()).filter(n=>n!=="lo");'
    'const pre=ext.length?("EXTERNAL_IFACES:"+ext.join(",")):"";'
    'const done=(m)=>{console.log(pre?pre+"|"+m:m);process.exit(0)};'
    'const s=net.connect({host:"1.1.1.1",port:443});s.setTimeout(4000);'
    's.on("connect",()=>{s.destroy();done("EGRESS_OK")});'
    's.on("timeout",()=>{s.destroy();done("NO_EGRESS")});'
    's.on("error",()=>done("NO_EGRESS"));'
)


def _probe_container(timeout: int = 120, image: str | None = None) -> dict:
    """Measure whether an OCI container can enforce the required controls HERE."""
    import tempfile
    checks: dict[str, dict] = {}

    def rec(name, status, detail, required=True):
        checks[name] = {"status": status, "detail": detail, "required": bool(required)}

    engine = container_engine()
    if not engine:
        rec("container_engine", "missing",
            "no usable container engine (docker/podman) on PATH")
    else:
        try:
            p = _run([*engine, "info", "--format", "{{.OSType}}"], timeout=min(timeout, 30))
            if p.returncode == 0 and "linux" in (p.stdout or "").lower():
                rec("container_engine", "pass", f"{os.path.basename(engine[0])} (linux containers)")
            else:
                rec("container_engine", "violation",
                    f"engine present but unusable: {_tail(p.stderr) or _tail(p.stdout) or 'no linux engine'}")
        except Exception as exc:
            rec("container_engine", "violation", f"engine probe raised {type(exc).__name__}: {exc}")

    img = image or DEFAULT_IMAGE
    if engine and checks["container_engine"]["status"] == "pass":
        try:
            p = _run([*engine, "image", "inspect", img], timeout=min(timeout, 30))
            rec("container_image", "pass" if p.returncode == 0 else "missing",
                f"image {img} present" if p.returncode == 0
                else f"image {img} absent (build it: bash framework/container/build.sh)")
        except Exception as exc:
            rec("container_image", "violation", f"image inspect raised {type(exc).__name__}: {exc}")
    else:
        rec("container_image", "skip", "no usable engine")

    root = _bindable_root(engine) if engine else None
    rec("container_binds", "pass" if root else "missing",
        f"bindable root {root}" if root
        else "no bindable path for the engine (under WSL interop set SANDBOX_TMP to a "
             "directory on /mnt/<drive>: a \\\\wsl.localhost source cannot be mounted)")

    ready = all(checks.get(n, {}).get("status") == "pass"
                for n in ("container_engine", "container_image", "container_binds"))
    if not ready:
        for name in ("container_start", "fs_ro_scratch_rw", "net_isolation", "env_allowlist"):
            rec(name, "skip", "engine, image, or bindable root unavailable")
        return _report(checks)

    try:
        p = run(Spec(network=False, wall_seconds=timeout), ["/bin/true"],
                backend="container", engine=engine)
        rec("container_start", "pass" if p.returncode == 0 else "violation",
            "container started and exited cleanly" if p.returncode == 0
            else f"container start failed: {_tail(p.stderr)}")
    except Exception as exc:
        rec("container_start", "violation", f"container start raised {type(exc).__name__}: {exc}")

    try:
        ctx = tempfile.TemporaryDirectory(prefix="sbx-probe.", dir=root)
    except Exception as exc:
        rec("fs_ro_scratch_rw", "violation", f"probe scratch unavailable: {exc}")
        rec("net_isolation", "skip", "probe scratch unavailable")
        rec("env_allowlist", "skip", "probe scratch unavailable")
        return _report(checks)

    with ctx:
        target = os.path.join(ctx.name, "target")
        scratch = os.path.join(ctx.name, "scratch")
        os.makedirs(target)
        os.makedirs(scratch)
        with open(os.path.join(target, "secret.txt"), "w", encoding="utf-8") as fh:
            fh.write("secret")

        spec = Spec(target=target, scratch=scratch, allow_env={"PATH": DEFAULT_PATH},
                    wall_seconds=timeout)
        probe_cmd = ["/bin/bash", "-c",
                     f'cat {target}/secret.txt >/dev/null 2>&1 || {{ echo RO_READ_FAIL; exit 21; }}; '
                     f'echo ok > {scratch}/ok.txt 2>/dev/null || {{ echo SCRATCH_WRITE_FAIL; exit 22; }}; '
                     f'if {{ echo x > {target}/evil.txt; }} 2>/dev/null; then echo TARGET_WRITE_SUCCEEDED; exit 23; fi; '
                     f'echo OK']
        try:
            p = run(spec, probe_cmd, backend="container", engine=engine)
            out = (p.stdout or "") + (p.stderr or "")
            if "TARGET_WRITE_SUCCEEDED" in out:
                rec("fs_ro_scratch_rw", "violation", "target directory was writable")
            elif "OK" in out:
                rec("fs_ro_scratch_rw", "pass",
                    "target read-only, scratch writable, target write blocked")
            else:
                rec("fs_ro_scratch_rw", "violation", f"unexpected: {_tail(out)}")
        except Exception as exc:
            rec("fs_ro_scratch_rw", "violation", f"probe raised {type(exc).__name__}: {exc}")

        try:
            p = run(Spec(allow_env={"PATH": DEFAULT_PATH}, wall_seconds=timeout),
                    ["node", "-e", _NET_PROBE_JS], backend="container", engine=engine)
            out = (p.stdout or "") + (p.stderr or "")
            if "EXTERNAL_IFACES" in out:
                rec("net_isolation", "violation",
                    f"non-loopback interface present: {_tail(out)}")
            elif "EGRESS_OK" in out:
                rec("net_isolation", "violation", "external network reachable from the sandbox")
            elif "NO_EGRESS" in out:
                rec("net_isolation", "pass", "loopback-only namespace; outbound connect blocked")
            else:
                rec("net_isolation", "violation", f"egress probe inconclusive: {_tail(out)}")
        except Exception as exc:
            rec("net_isolation", "violation", f"probe raised {type(exc).__name__}: {exc}")

        try:
            p = run(Spec(allow_env={"PATH": DEFAULT_PATH}, wall_seconds=timeout),
                    ["/bin/bash", "-c", 'env | sed "s/=.*//" | sort -u'],
                    backend="container", engine=engine)
            names = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
            allowed = set(CONTAINER_BASE_ENV) | {"PATH"}
            extra = [n for n in names if n not in allowed]
            if not names:
                rec("env_allowlist", "violation",
                    f"env probe produced no output: {_tail((p.stdout or '') + (p.stderr or ''))}")
            elif extra:
                rec("env_allowlist", "violation", f"unexpected inherited vars: {extra}")
            else:
                rec("env_allowlist", "pass",
                    f"only runtime-injected names present: {names}")
        except Exception as exc:
            rec("env_allowlist", "violation", f"probe raised {type(exc).__name__}: {exc}")

    return _report(checks)


def probe(backend: str = "auto", timeout: int = 40, image: str | None = None) -> dict:
    """Choose an enforcement backend and report its measured verdict.

    auto tries native first (no daemon, no image, unprivileged namespaces) and falls back
    to container. When neither is enforceable the report carries the more severe signal --
    a broken control (violations) outranks an absent one -- plus the other backend's
    verdict under `alternatives`, so a reader can see both.
    """
    backend = backend or os.environ.get("SANDBOX_BACKEND") or "auto"
    if backend == "native":
        rep = _probe_native(timeout)
        rep["backend"] = "native"
        return rep
    if backend == "container":
        rep = _probe_container(max(timeout, 120), image)
        rep["backend"] = "container"
        return rep
    if backend != "auto":
        raise SystemExit(f"unknown backend {backend!r} (auto|native|container)")

    native = _probe_native(timeout)
    if native["ok"]:
        native["backend"] = "native"
        return native
    container = _probe_container(120, image)
    if container["ok"]:
        container["backend"] = "container"
        return container

    pick, other = ((native, container) if (native["violations"] or not container["violations"])
                   else (container, native))
    pick = dict(pick)
    pick["backend"] = "native" if pick is native else "container"
    pick["alternatives"] = {"backend": "container" if other is container else "native",
                            "missing": other["missing"], "violations": other["violations"]}
    return pick


def available() -> bool:
    return bool(probe().get("ok"))


# ─── CLI ─────────────────────────────────────────────────────────────────────────


def _split_cmd(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    i = argv.index("--")
    return argv[:i], argv[i + 1:]


def _spec_from_args(ns) -> Spec:
    env = {}
    for pair in ns.allow_env or []:
        if "=" not in pair:
            raise SystemExit(f"--allow-env expects KEY=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        env[k] = v
    if not env:
        env = {"PATH": DEFAULT_PATH}
    return Spec(target=ns.target, scratch=ns.scratch, allow_env=env, network=ns.net,
                mem_mb=ns.mem_mb, pids=ns.pids, fsize_kb=ns.fsize_kb, wall_seconds=ns.wall)


def _print_report(rep: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return
    for name, c in rep["checks"].items():
        flag = "" if c["required"] else " (optional)"
        print(f"{name:<20} {c['status']:<9} {c['detail']}{flag}")
    print(f"\nok={rep['ok']} backend={rep.get('backend')} missing={rep['missing']} "
          f"violations={rep['violations']} unjudged={rep['unjudged']}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    sub, rest = argv[0], argv[1:]

    if sub == "probe":
        ap = argparse.ArgumentParser(prog="sandbox.py probe", add_help=True)
        ap.add_argument("--json", action="store_true")
        ap.add_argument("--backend", default=None, choices=["auto", "native", "container"])
        ap.add_argument("--image", default=None)
        ns = ap.parse_args(rest)
        rep = probe(backend=ns.backend or "auto", image=ns.image)
        _print_report(rep, ns.json)
        if rep["violations"]:
            return 1
        if rep["missing"] or rep["unjudged"]:
            return 3
        return 0 if rep["ok"] else 3

    if sub in ("argv", "run"):
        head, cmd = _split_cmd(rest)
        ap = argparse.ArgumentParser(prog=f"sandbox.py {sub}", add_help=True)
        ap.add_argument("--target")
        ap.add_argument("--scratch")
        ap.add_argument("--extra-ro", action="append", default=[])
        ap.add_argument("--allow-env", action="append", default=[])
        ap.add_argument("--net", action="store_true")
        ap.add_argument("--mem-mb", type=int)
        ap.add_argument("--pids", type=int)
        ap.add_argument("--fsize-kb", type=int)
        ap.add_argument("--wall", type=int)
        ap.add_argument("--backend", default=None, choices=["auto", "native", "container"])
        ap.add_argument("--image", default=None)
        ns = ap.parse_args(head)
        if not cmd:
            raise SystemExit("no command after '--'")
        spec = _spec_from_args(ns)
        spec.extra_ro = tuple(ns.extra_ro)
        want = ns.backend or os.environ.get("SANDBOX_BACKEND") or "auto"
        if sub == "argv":
            if want == "auto":
                want = "native"
            built = (build_container_argv(spec, cmd, image=ns.image) if want == "container"
                     else build_argv(spec, cmd))
            print(json.dumps({"argv": built, "backend": want}))
            return 0
        # Fail closed BEFORE probing when a container run is impossible by construction:
        # a missing engine, or a bind source the engine cannot reach. The verdict is
        # "capability missing" (exit 3), never a violated control.
        if want == "container":
            engine = container_engine()
            if not engine:
                print(json.dumps({"ok": False, "reason": "no container engine",
                                  "backend": "container", "missing": ["container_engine"],
                                  "violations": [], "unjudged": []}))
                return 3
            if not binds_reachable(spec, engine):
                print(json.dumps({"ok": False, "reason": "container cannot bind the requested paths",
                                  "backend": "container", "missing": ["container_binds"],
                                  "violations": [], "unjudged": [],
                                  "detail": "the engine needs Windows-drive (/mnt/<drive>) sources"}))
                return 3
        rep = probe(backend=want, image=ns.image)
        if not rep["ok"]:
            print(json.dumps({"ok": False, "reason": "sandbox not enforceable",
                              "backend": rep.get("backend"),
                              "missing": rep["missing"], "violations": rep["violations"],
                              "unjudged": rep["unjudged"]}))
            return 3 if (rep["missing"] or rep["unjudged"]) and not rep["violations"] else 1
        p = run(spec, cmd, backend=rep.get("backend", "native"))
        sys.stdout.write(p.stdout or "")
        sys.stderr.write(p.stderr or "")
        return p.returncode

    if sub == "engine":
        engine = container_engine()
        print(json.dumps({"engine": engine,
                          "windows_paths": engine_needs_windows_paths(engine) if engine else False,
                          "image": DEFAULT_IMAGE}))
        return 0 if engine else 3

    if sub == "image":
        print(DEFAULT_IMAGE)
        return 0

    print(f"unknown subcommand: {sub}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
