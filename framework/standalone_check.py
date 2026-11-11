#!/usr/bin/env python3
"""Prove the framework stands alone: install the built wheel into a throwaway venv, bind the
reference application with `framework init`, and validate it with `validate --profile app`.

A green validate.py in the framework's own working tree is not evidence of distribution. That
tree is imported from source rather than from an installed wheel, and it carries the framework
surface next to the reference app - either can mask a package-data file the wheel forgot to
ship, or a path that only resolves in-tree. The only run that can fail on those is one where the
framework is an INSTALLED wheel and the application holds none of the framework tree. That is
the run this performs:

  1. build the wheel from this tree (or accept one passed with --wheel);
  2. create a throwaway virtualenv and install the wheel into it (no deps - the venv shares this
     interpreter's site-packages, so the run stays offline);
  3. stage the reference application - the framework-owned fixture at
     `framework/reference-app/` (plan 4.1): src/, package.json, the
     vite/playwright/tsconfig/components/index.html scaffold, tests/, and contracts/ (staged
     into .planning/contracts) - into a scratch directory, deliberately WITHOUT framework/,
     .opencode/ or .lifecycle/;
  4. `framework init` there - the real bind path: writes framework.config.json, scaffolds the
     state tree, and migrates .planning/{decisions,contracts};
  5. `framework validate --profile app` - exit 0 proves the installed package can bind and
     validate a bare consumer.

Exit codes: 0 standalone | 1 not standalone | 2 prerequisite unusable (reference app, wheel,
virtualenv or install failed).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_S = 1800
BIN = "Scripts" if sys.platform == "win32" else "bin"

# The reference application - the `--profile app` self-fixture (plan 4.1). It lives INSIDE the
# framework package (`framework/reference-app/`) because the framework owns it: it is not
# application code, and the repository root must not carry it. Staging ONLY these paths is the
# point: the framework tree (framework/, .opencode/, .lifecycle/) is exactly what the installed
# package must replace, so none of it is copied into the scratch app.
REQUIRED = (
    "src",
    "package.json",
    "vite.config.ts",
    "playwright.config.ts",
    "tsconfig.json",
    "components.json",
    "index.html",
    "tests",
)
OPTIONAL = (".gitattributes",)

# The fixture keeps its contract under `contracts/` so the fixture tree contains no `.planning/`
# directory (that name is runtime state and is gitignored at the repository root). `framework
# init` migrates `.planning/contracts` in the staged app, so staging maps one layout to the other.
STATE_SEED = ("contracts",)
REFERENCE_APP_NAME = "reference-app"

_IGNORED = shutil.ignore_patterns(".manifest", "__pycache__", "*.pyc", "node_modules")


def _reference_app() -> Path:
    """The fixture directory: `<parent-of-package>/framework/reference-app`.

    ROOT is the directory that CONTAINS the `framework` package - the repository root in-tree,
    site-packages when installed. Appending `framework/<name>` therefore resolves in both
    layouts, and keeps the tests' ROOT override as the single seam.
    """
    return ROOT / "framework" / REFERENCE_APP_NAME

USAGE = """usage: framework standalone [--keep] [--wheel PATH] [--help]

Build the wheel, install it into a throwaway virtualenv, bind the reference application with
`framework init`, and run `validate --profile app` against it. Exit 0 only when the installed
package validates a consumer app with no framework tree on disk.

  --keep        keep the temp workspace and print its path
  --wheel PATH  use a prebuilt wheel instead of building one from this tree
  -h, --help    show this help
"""


def _run(args, cwd, timeout=None, env=None):
    # UTF-8 capture with errors replaced: on Windows the default locale codec (cp1252) aborts on
    # the em-dash the framework prints, and a stray byte must never crash the check.
    argv = [str(a) for a in args]
    try:
        return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"timeout after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 126, "", repr(exc))


def _tail(text, n=1):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[:280]


def _stage(scaffold):
    app = _reference_app()
    staged, missing = [], []
    for name in REQUIRED:
        src = app / name
        if not src.exists():
            missing.append(name)
        elif src.is_dir():
            shutil.copytree(src, scaffold / name, ignore=_IGNORED)
            staged.append(name)
        else:
            shutil.copy2(src, scaffold / name)
            staged.append(name)
    for name in STATE_SEED:
        src = app / name
        if not src.exists():
            missing.append(f".planning/{name}")
            continue
        shutil.copytree(src, scaffold / ".planning" / name, ignore=_IGNORED)
        staged.append(f".planning/{name}")
    for name in OPTIONAL:
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, scaffold / name)
            staged.append(name)
    return staged, missing


# Runs INSIDE the staged app after `framework init`. It loads the materialised plugin and calls
# its config hook exactly as OpenCode would, then reports what was injected. It proves the whole
# install chain - installed wheel -> the plugin's own python resolution -> injected surface - so a
# passing validate.py in a framework tree (where the surface is on disk) cannot fake it.
PROBE_JS = """const { resolveSurface, makeBootstrap } = await import("./.opencode/plugins/bootstrap.ts")
const input = { worktree: process.cwd(), directory: process.cwd() }
const surface = resolveSurface(input)
const hooks = await makeBootstrap(() => surface)(input)
const cfg = {}
await hooks.config(cfg)
process.stdout.write(JSON.stringify({
  surface,
  skills: cfg.skills?.paths ?? [],
  instructions: cfg.instructions ?? [],
  agents: Object.keys(cfg.agent ?? {}),
}))
"""


def _probe_surface(scaffold, venv_dir):
    """Prove the materialised plugin injects the INSTALLED package's surface.

    The venv's bin goes first on PATH so the plugin's `python` resolution finds the installed
    wheel rather than any interpreter on the host. Returns (report, None) or (None, reason); a
    missing node is a reason, not a failure - the file-materialisation assertion still stands.
    """
    plugin = scaffold / ".opencode" / "plugins" / "bootstrap.ts"
    if not plugin.is_file():
        return None, "init did not materialise .opencode/plugins/bootstrap.ts"
    node = shutil.which("node")
    if node is None:
        return None, "node not on PATH"
    probe = scaffold / "_surface_probe.mjs"
    probe.write_text(PROBE_JS, encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = str(venv_dir / BIN) + os.pathsep + env.get("PATH", "")
    env.pop("FRAMEWORK_SURFACE", None)
    r = _run([node, str(probe)], scaffold, timeout=120, env=env)
    if r.returncode != 0:
        return None, _tail(r.stderr or r.stdout, 3)
    try:
        return json.loads(r.stdout.strip()), None
    except (ValueError, AttributeError):
        return None, "probe produced no JSON: " + _tail(r.stdout, 1)


def _build_wheel(dist):
    attempts = (
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "-o", str(dist)],
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
         "--no-build-isolation", "-w", str(dist)],
    )
    last = None
    for args in attempts:
        last = _run(args, ROOT, timeout=TIMEOUT_S)
        wheels = sorted(dist.glob("agentic_lifecycle-*.whl"))
        if last.returncode == 0 and wheels:
            return wheels[-1], last
    return None, last


def _wheel_ships_reference_app(wheel):
    """(ok, reason): does the wheel actually carry the reference application?

    Staging reads the fixture from the SOURCE tree, so a wheel that forgot it would still let
    every other step pass -- and `framework standalone` run from the installed package would
    then fail for a reason this guard exists to catch. The fixture travels as package data,
    which is exactly the kind of entry a glob in pyproject.toml can silently miss, so it is
    asserted against the built artefact rather than assumed.
    """
    import zipfile
    want = ("framework/" + REFERENCE_APP_NAME + "/package.json",
            "framework/" + REFERENCE_APP_NAME + "/src/frontend/main.tsx")
    try:
        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        return False, repr(exc)
    missing = [n for n in want if n not in names]
    if missing:
        return False, "wheel is missing " + ", ".join(missing)
    return True, ""


def _make_venv(tmp):
    venv_dir = tmp / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(venv_dir)
    py = venv_dir / BIN / ("python.exe" if sys.platform == "win32" else "python")
    if not py.exists():
        py = venv_dir / BIN / "python"
    return venv_dir, py


def _framework_cmd(venv_dir, vpy):
    console = venv_dir / BIN / ("framework.exe" if sys.platform == "win32" else "framework")
    if console.exists():
        return [str(console)]
    return [str(vpy), "-m", "framework"]


def _parse(argv):
    keep = False
    wheel = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--keep":
            keep = True
        elif arg == "--wheel":
            i += 1
            if i >= len(argv):
                return None
            wheel = argv[i]
        elif arg.startswith("--wheel="):
            wheel = arg.split("=", 1)[1]
        else:
            return None
        i += 1
    return keep, wheel


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    opts = _parse(argv)
    if opts is None:
        print(USAGE, file=sys.stderr)
        return 2
    keep, wheel_arg = opts

    tmp = Path(tempfile.mkdtemp(prefix="standalone-"))
    try:
        scaffold = tmp / "app"
        scaffold.mkdir()
        staged, missing = _stage(scaffold)
        if missing:
            print("BLOCKED: reference application incomplete: " + ", ".join(sorted(missing)))
            return 2
        print("staged reference app: " + ", ".join(staged))

        if wheel_arg is not None:
            wheel = Path(wheel_arg)
            if not wheel.is_absolute():
                wheel = (Path.cwd() / wheel).resolve()
            if not wheel.is_file():
                print(f"BLOCKED: wheel not found: {wheel}")
                return 2
        else:
            dist = tmp / "dist"
            dist.mkdir()
            wheel, r = _build_wheel(dist)
            if wheel is None:
                print("BLOCKED: wheel build failed :: " + _tail(r.stderr or r.stdout, 2))
                return 2
        print("wheel: " + wheel.name)

        ships, reason = _wheel_ships_reference_app(wheel)
        if not ships:
            print("BLOCKED: the wheel does not ship the reference application :: " + reason)
            return 2
        print("  wheel ships the reference application (package data present)")

        venv_dir, vpy = _make_venv(tmp)
        if not vpy.exists():
            print(f"BLOCKED: virtualenv interpreter missing: {vpy}")
            return 2
        r = _run([vpy, "-m", "pip", "install", "--no-deps",
                  "--no-build-isolation", str(wheel)], tmp, timeout=TIMEOUT_S)
        if r.returncode != 0:
            print("BLOCKED: wheel install failed :: " + _tail(r.stderr or r.stdout, 2))
            return 2

        fw = _framework_cmd(venv_dir, vpy)
        r = _run(fw + ["init"], scaffold, timeout=TIMEOUT_S)
        if r.returncode != 0:
            print(f"BLOCKED: `framework init` failed (exit {r.returncode}) :: "
                  + _tail(r.stderr or r.stdout, 2))
            return 2
        print("  " + _tail(r.stdout, 1))

        data, reason = _probe_surface(scaffold, venv_dir)
        if reason is not None:
            print("  NOTE: surface-injection probe not run (" + reason + ")")
        else:
            print("  surface resolved from: " + str(data.get("surface")))
            print("  injected: {} skill root(s), {} rule(s), {} agent(s)".format(
                len(data.get("skills", [])), len(data.get("instructions", [])),
                len(data.get("agents", []))))
            if not data.get("skills") or not data.get("agents"):
                print("NOT STANDALONE: the materialised plugin injected no framework surface")
                return 1

        r = _run(fw + ["validate", "--profile", "app"], scaffold, timeout=TIMEOUT_S)
        out = (r.stdout or "") + (r.stderr or "")
        for ln in out.splitlines():
            s = ln.strip()
            if s.startswith("[app]") or s.startswith("VALIDATION PASSED"):
                print("  " + s)
        if r.returncode != 0:
            for ln in out.splitlines():
                if ln.strip().startswith("FAIL"):
                    print("  " + ln.strip())
            if r.returncode in (124, 126):
                print(f"BLOCKED: validate could not run (exit {r.returncode}): {_tail(out, 1)}")
                return 2
            print("NOT STANDALONE: the installed package could not bind and validate a bare app")
            return 1
        print("STANDALONE: the installed wheel binds and validates the reference app")
        return 0
    finally:
        if keep:
            print(f"kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
