#!/usr/bin/env python3
"""``framework init`` - bind an application repository to the installed framework.

Creates the one config the framework reads from the app repo (``framework.config.json``),
scaffolds the state tree the app owns (``.framework/state/{decisions,contracts}`` and the
machine-specific ``.framework/.manifest``), materialises the OpenCode plugin that exposes the
packaged framework surface (agents/skills/rules) to the app, and migrates a legacy GSD state
root's committed subsets (``.planning/{decisions,contracts}``) into it.

Migration copies and verifies by content digest and NEVER deletes the source; the whole command
is idempotent and safe to re-run on upgrade. An existing config is never overwritten without
``--force``.

Exit codes (``framework/gates/EXIT_CODES.md``): 0 pass, 1 fail, 2 BLOCKED (bad usage or an
unwritable target), 3 UNVERIFIABLE (a migrated copy failed verification against its source).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from framework import locate

DIST = "agentic-lifecycle"
CONFIG_NAME = locate.CONFIG_NAME
STATE_FOLDER = ".framework/state"
MANIFEST_FOLDER = ".framework/.manifest"
MIGRATED_SUBSETS = ("decisions", "contracts")

# OpenCode install surface. The packaged bootstrap plugin is copied VERBATIM into the app's
# project plugin directory, which OpenCode auto-loads at startup - the app then discovers the
# framework's agents, skills, and rules without any machine-specific path in a committed file.
# `.opencode/plugins/` (plural) is OpenCode's canonical project plugin directory. The copied
# file is generated, not authored: re-running init refreshes it.
OPENCODE_PLUGIN_SRC = Path("plugin") / "bootstrap.ts"                     # under locate.surface_root()
OPENCODE_PLUGIN_DST = Path(".opencode") / "plugins" / "bootstrap.ts"      # under the app root

# GSD's OpenCode install emits @-file-include paths as an ABSOLUTE config dir
# (see gsd-core/bin/lib/runtime-artifact-conversion.cjs _computePathPrefix: for
# OpenCode the prefix is `${resolvedTarget}/`, never the $HOME shorthand). A copy
# vendored into this package therefore froze the SOURCE project's absolute prefix
# into every surface file, which dangles in any other project. init materialises
# the whole surface under the app's `.opencode/` and rewrites that frozen prefix to
# the app root, so each app's includes resolve against its OWN tree.
_GSD_SURFACE_DIRS = ("gsd-core", "skills", "commands", "agents", "rules")
_GSD_TEXT_SUFFIXES = frozenset({
    ".md", ".json", ".jsonc", ".txt", ".cjs", ".js", ".mjs",
    ".ts", ".cts", ".mts", ".sh", ".yaml", ".yml",
})
# Two frozen forms reach the surface: the config-dir include prefix the OpenCode
# install writes (`<root>/.opencode/...`), and source-repo layout paths baked into
# GSD's own workflow/skill prose (`<root>/framework/opencode/...`). Both must land
# on the app's materialised `<app>/.opencode` tree.
_ABS_CONFIG_DIR_RE = re.compile(r"[A-Za-z]:/[^ \t\r\n\"')`]*?[/\\]\.opencode(?![A-Za-z0-9_-])")
_ABS_SURFACE_RE = re.compile(r"[A-Za-z]:/[^ \t\r\n\"')`]*?[/\\]framework[/\\]opencode(?![A-Za-z0-9_-])")

USAGE = """usage: framework init [--app-root DIR] [--force] [--dry-run] [--validate] [--help]

Bind an application repository: write framework.config.json, scaffold the state tree, and
migrate .planning/{decisions,contracts} into it (copy + verify; source retained).

  --app-root DIR   application root to bind (default: the config's app_root, else the CWD)
  --source REF     framework pin recorded in the config (git+https URL or index ref)
  --force          overwrite an existing framework.config.json and re-copy migrated files
  --dry-run        report the actions without changing anything
  --validate       run `validate --profile app` after binding and return its exit code
  -h, --help       show this help
"""

GITIGNORE_LINES = """  .framework/*
  !.framework/state/
  .framework/state/*
  !.framework/state/decisions/
  !.framework/state/contracts/"""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _installed_version() -> str | None:
    try:
        return metadata.version(DIST)
    except metadata.PackageNotFoundError:
        return None


def _default_app_root() -> Path:
    if locate.find_config() is not None:
        return Path(locate.app_root())
    return Path.cwd()


def _config_template(source: str | None) -> dict:
    meta: dict = {"distribution": DIST}
    version = _installed_version()
    if version:
        meta["version"] = version
    if source:
        meta["source"] = source
    return {"framework": meta, "app_root": ".", "state_folder": STATE_FOLDER}


def _parse(argv: list[str]) -> dict | None:
    opts: dict = {
        "app_root": None, "source": None, "force": False,
        "dry_run": False, "validate": False, "help": False,
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            opts["help"] = True
        elif arg == "--force":
            opts["force"] = True
        elif arg == "--dry-run":
            opts["dry_run"] = True
        elif arg == "--validate":
            opts["validate"] = True
        elif arg == "--app-root":
            i += 1
            if i >= len(argv):
                return None
            opts["app_root"] = argv[i]
        elif arg.startswith("--app-root="):
            opts["app_root"] = arg.split("=", 1)[1]
        elif arg == "--source":
            i += 1
            if i >= len(argv):
                return None
            opts["source"] = argv[i]
        elif arg.startswith("--source="):
            opts["source"] = arg.split("=", 1)[1]
        else:
            return None
        i += 1
    return opts


def _write_config(app_root: Path, template: dict, force: bool, dry_run: bool) -> str:
    target = app_root / CONFIG_NAME
    if target.exists() and not force:
        return f"kept existing {target}"
    if dry_run:
        return f"would write {target}"
    target.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return f"wrote {target}"


def _scaffold(app_root: Path, dry_run: bool) -> list[str]:
    dirs = [app_root / STATE_FOLDER / subset for subset in MIGRATED_SUBSETS]
    dirs.append(app_root / MANIFEST_FOLDER)
    lines: list[str] = []
    for directory in dirs:
        if directory.is_dir():
            continue
        if dry_run:
            lines.append(f"would create {directory}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            lines.append(f"created {directory}")
    return lines


def _materialise_opencode(app_root: Path, dry_run: bool) -> list[str]:
    """Copy the packaged bootstrap plugin into the app's OpenCode project plugin directory.

    Idempotent: an identical file is left untouched, a changed one is refreshed (the file is
    generated by init - see bootstrap.ts's header), a missing one is written. A missing source
    is reported, never fatal: the app still binds, it simply will not see the framework surface.
    """
    src = locate.surface_root() / OPENCODE_PLUGIN_SRC
    dst = app_root / OPENCODE_PLUGIN_DST
    if not src.is_file():
        return [f"OpenCode plugin source missing: {src}"]
    if dst.is_file() and dst.read_bytes() == src.read_bytes():
        return [f"kept {dst}"]
    if dry_run:
        return [f"would write {dst}"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return [f"{'refreshed' if dst.exists() else 'wrote'} {dst}"]


def _rewrite_includes(raw: bytes, app_posix: str) -> bytes:
    """Rewrite frozen `<drive>/.../.opencode` and `<drive>/.../framework/opencode`
    prefixes to `<app_posix>/.opencode`.

    Byte-preserving (no re-encoding of line endings); a file with no match is returned
    unchanged, and an undecodable file is left untouched so binary payloads are safe.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    original = text
    text = _ABS_CONFIG_DIR_RE.sub(f"{app_posix}/.opencode", text)
    text = _ABS_SURFACE_RE.sub(f"{app_posix}/.opencode", text)
    return raw if text == original else text.encode("utf-8")


def _materialise_gsd_surface(app_root: Path, dry_run: bool) -> list[str]:
    """Materialise the packaged GSD surface under `<app>/.opencode/`, rewriting each
    frozen absolute include prefix to the app root so the app's includes resolve.

    Idempotent (re-running refreshes); a missing source directory is reported, never fatal.
    """
    src_root = locate.surface_root()
    app_posix = app_root.as_posix()
    lines: list[str] = []
    for name in _GSD_SURFACE_DIRS:
        src = src_root / name
        if not src.is_dir():
            lines.append(f"GSD surface source missing: {src}")
            continue
        dst = app_root / ".opencode" / name
        if dry_run:
            lines.append(f"would materialise {src} -> {dst}")
            continue
        for f in src.rglob("*"):
            if not f.is_file():
                continue
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix.lower() in _GSD_TEXT_SUFFIXES:
                target.write_bytes(_rewrite_includes(f.read_bytes(), app_posix))
            else:
                shutil.copy2(f, target)
        lines.append(f"materialised {dst}")
    return lines


def _migrate(app_root: Path, force: bool, dry_run: bool) -> tuple[list[str], int]:
    legacy = app_root / locate.LEGACY_STATE_FOLDER
    state_root = app_root / STATE_FOLDER
    lines: list[str] = []
    unverified = 0
    for subset in MIGRATED_SUBSETS:
        src_dir = legacy / subset
        if not src_dir.is_dir():
            continue
        sources = sorted(p for p in src_dir.rglob("*") if p.is_file())
        for src in sources:
            dst = state_root / subset / src.relative_to(src_dir)
            if dst.exists() and not force:
                lines.append(f"kept {dst}")
                continue
            if dry_run:
                lines.append(f"would copy {src} -> {dst}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if _digest(src) != _digest(dst):
                unverified += 1
                lines.append(f"UNVERIFIED {dst}")
            else:
                lines.append(f"copied {src} -> {dst}")
    return lines, unverified


def _run_validate(app_root: Path) -> int:
    script = locate.framework_root() / "validate.py"
    if not script.is_file():
        print(f"framework init: validate.py not found at {script}", file=sys.stderr)
        return 2
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--profile", "app"], cwd=str(app_root)
    ).returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = _parse(argv)
    if opts is None:
        print(USAGE, file=sys.stderr)
        return 2
    if opts["help"]:
        print(USAGE)
        return 0

    app_root = Path(opts["app_root"]).resolve() if opts["app_root"] else _default_app_root()
    if not app_root.is_dir():
        print(f"framework init: app root is not a directory: {app_root}", file=sys.stderr)
        return 2

    try:
        report = [f"app root: {app_root}"]
        report.append(_write_config(app_root, _config_template(opts["source"]),
                                    opts["force"], opts["dry_run"]))
        report.extend(_scaffold(app_root, opts["dry_run"]))
        report.extend(_materialise_opencode(app_root, opts["dry_run"]))
        report.extend(_materialise_gsd_surface(app_root, opts["dry_run"]))
        migrated, unverified = _migrate(app_root, opts["force"], opts["dry_run"])
        report.extend(migrated)
    except OSError as exc:
        print(f"framework init: {exc}", file=sys.stderr)
        return 2

    print("\n".join(report))
    if unverified:
        print(f"framework init: {unverified} file(s) failed verification", file=sys.stderr)
        return 3

    if not opts["dry_run"]:
        print("\nnext steps:")
        print("  1. review framework.config.json and set framework.source to your release ref")
        print("  2. add these lines to .gitignore (keep state/decisions and state/contracts committed):")
        print(GITIGNORE_LINES)
        print("  3. run: framework validate --profile app")
        print("  4. restart opencode here: .opencode/plugins/bootstrap.ts exposes the framework's")
        print("     agents, skills, and rules (it resolves the installed package at startup)")

    if opts["validate"]:
        return _run_validate(app_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
