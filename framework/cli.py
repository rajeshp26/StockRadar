#!/usr/bin/env python3
"""``framework`` - the lifecycle framework's command-line entry point.

A thin dispatcher, not an implementation: each subcommand runs an existing framework tool. The
package is built to be installed (``pip install`` from the pinned ref) and driven from an
application repository, so every command resolves the *application* root and runs there rather
than assuming it sits inside the framework tree.

Exit codes are the framework's own contract (``framework/gates/EXIT_CODES.md``): 0 pass,
1 fail, 2 BLOCKED, 3 UNVERIFIABLE. Each command returns its tool's real code unchanged.

Present in the core package: ``validate``, ``standalone``, and ``init``. ``bootstrap`` is the
friendly alias for ``init`` - the one-shot "install into this application repository" step.
"""
from __future__ import annotations

import subprocess
import sys
from importlib import metadata
from pathlib import Path

DIST = "agentic-lifecycle"

# command -> packaged script run as ``python <script>`` with CWD pinned to the app root.
SCRIPTS = {
    "validate": "validate.py",
    "standalone": "standalone_check.py",
}


def version() -> str:
    """Distribution version when installed, else the package `__version__` constant."""
    try:
        return metadata.version(DIST)
    except metadata.PackageNotFoundError:
        pass
    try:
        from framework import __version__

        return __version__
    except ImportError:
        return "0.0.0+unknown"


def app_root() -> Path:
    """Application repository root the command runs in.

    A ``framework.config.json`` (found by walking up from here) names the root explicitly, so
    ``locate`` is authoritative whenever a config exists. Without one - a bare framework
    checkout, or an app not yet initialised - the invocation directory IS the root, exactly what
    ``python framework/<script>.py`` assumed before this CLI existed.

    ``locate.app_root()``'s own legacy fallback is deliberately NOT used here: from an installed
    package it resolves to site-packages (where the package lives), not to the tree the user is
    standing in. Only a found config makes the config-driven path trustworthy.
    """
    try:
        from framework import locate

        if locate.find_config() is not None:
            return Path(locate.app_root())
    except Exception:
        pass
    return Path.cwd()


def run_script(script_name: str, argv: list[str]) -> int:
    """Run a packaged framework script, CWD pinned to the app root.

    A subprocess - not an in-process import - preserves each tool's ``__main__`` semantics (its
    relative-path contract and its own ``sys.exit``) exactly as the documented
    ``python framework/<script>.py`` invocation, while the package owns the script's real path.

    UTF-8 mode (``-X utf8``) is pinned because the framework's tools read UTF-8 sources and do
    not all pass ``encoding=`` explicitly; on Windows the default locale codec (cp1252) aborts
    them. The README documents ``-X utf8`` as required - this makes the CLI honour it so a user
    never has to remember it.
    """
    script = Path(__file__).resolve().parent / script_name
    if not script.exists():
        print(f"framework: packaged script missing: {script}", file=sys.stderr)
        return 2
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(script), *argv], cwd=str(app_root())
    ).returncode


def usage() -> str:
    return (
        "usage: framework <command> [args...]\n"
        "\n"
        "commands:\n"
        "  validate    run the validation suite (validate.py --profile framework|app)\n"
        "  standalone  prove the package validates holding only its own surface\n"
        "  init        initialise an application repository (framework.init)\n"
        "  bootstrap   alias of init - the one-shot install-into-this-repo step\n"
        "  --version   print the installed distribution version\n"
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(usage(), file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help"):
        print(usage())
        return 0
    if cmd in ("-V", "--version"):
        print(version())
        return 0
    if cmd in SCRIPTS:
        return run_script(SCRIPTS[cmd], rest)
    if cmd in ("init", "bootstrap"):
        try:
            from framework import init as init_mod
        except ImportError:
            print(
                f"framework: `{cmd}` is not available in this build (framework.init missing)",
                file=sys.stderr,
            )
            return 2
        return init_mod.main(rest)
    print(f"framework: unknown command {cmd!r}\n\n{usage()}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
