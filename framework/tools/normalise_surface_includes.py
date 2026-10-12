#!/usr/bin/env python3
"""Repoint the framework's own surface includes from `<root>/.opencode` to `<root>/framework/opencode`.

WHY this exists
---------------
The framework surface (gsd-core, agents, skills, commands, rules, hooks, plugin, scripts,
tools, skill-routing.md, skill-integration-matrix.md) is AUTHORED in `framework/opencode/`
and, at app-install time, materialised into `<app>/.opencode/` by `framework/init.py`,
which rewrites BOTH absolute prefixes (`<root>/.opencode` and `<root>/framework/opencode`)
to `<app>/.opencode` (see init.py `_ABS_CONFIG_DIR_RE` / `_ABS_SURFACE_RE`).

Inside the framework's OWN repository OpenCode reads the surface IN PLACE from
`framework/opencode/` (opencode.json: skills.paths / instructions / plugin). A surface file
whose `@`-include still reads `<root>/.opencode/gsd-core/...` therefore DANGLES: the target
lives at `framework/opencode/gsd-core/...`, not `.opencode/gsd-core/...`.

This tool rewrites ONLY those surface references. It deliberately LEAVES the GSD
RUNTIME-HOME references (`.opencode/notes`, `.opencode/tasks`, `.opencode/settings.json`,
`.opencode/mcp.json`, `.opencode/.gsd-surface.json`, `.opencode/.gsd-profile`,
`.opencode/AGENTS.md`, `.opencode/USER-PROFILE.backup.md`, ...) alone: those live under
`.opencode/` at runtime and must stay there.

Classification is by EVIDENCE, not a hard-coded list: a reference is a surface reference iff
the first path segment after `.opencode` is an entry that actually exists under
`framework/opencode/`. The one non-path exception is the GSD tools shim's config-dir
fallback `${CLAUDE_CONFIG_DIR:-<root>/.opencode}` (`.opencode` immediately followed by `}`),
which the shim resolves against `<root>/framework/opencode/gsd-core/bin/gsd-tools.cjs`.

App installs are unaffected: init.py rewrites both forms to `<app>/.opencode` regardless.

Byte-preserving (raw UTF-8 read/write - line endings untouched) and idempotent (a reference
already in `framework/opencode` form never matches). Default is a dry-run report.

Usage:
    python framework/tools/normalise_surface_includes.py            # dry-run (default)
    python framework/tools/normalise_surface_includes.py --apply
    python framework/tools/normalise_surface_includes.py --root framework/opencode
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Own-root first: run from anywhere (and via `python -m framework ...`) without an installed
# package. Mirrors framework/validate.py's isolation prepend.
_BOOTSTRAP = str(Path(__file__).resolve().parents[2])
if _BOOTSTRAP not in sys.path:
    sys.path.insert(0, _BOOTSTRAP)

from framework import locate  # noqa: E402

# Matches init.py `_ABS_CONFIG_DIR_RE`: a DRIVE-LETTER-ABSOLUTE prefix ending in `.opencode`.
# Anchoring on `[A-Za-z]:/` is what keeps `~/.opencode` and `$HOME/.opencode` (global config)
# from being rewritten, while still catching any frozen build root on any drive.
_ABS_OC = re.compile(r"([A-Za-z]:/[^ \t\r\n\"')`]*?)([/\\])\.opencode(?![A-Za-z0-9_-])")
# First path segment following a match, if any (`/gsd-core`, `\agents`, ...).
_SEG = re.compile(r"[/\\]?([^/\\ \t\r\n\"')`]+)")

_TEXT_SUFFIXES = frozenset({
    ".md", ".markdown", ".mdx", ".txt", ".rst",
    ".json", ".jsonc", ".json5", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".pyi",
    ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
    ".sh", ".bash", ".zsh", ".ps1", ".psm1", ".bat", ".cmd",
    ".html", ".htm", ".css", ".scss", ".svelte", ".vue", ".sql", ".xml",
})


def _surface_children(surface_root: Path) -> set[str]:
    # Every top-level entry under framework/opencode/ is a "surface" name; anything else
    # after `.opencode` is a runtime-home name and is preserved.
    return {p.name for p in surface_root.iterdir()}


def _make_repl(children: set[str], stats: dict):
    def repl(m: re.Match) -> str:
        tail = m.string[m.end():]
        if tail[:1] == "}":
            is_surface = True
        else:
            seg = _SEG.match(tail)
            is_surface = bool(seg) and seg.group(1) in children
        if is_surface:
            stats["rewritten"] += 1
            return f"{m.group(1)}{m.group(2)}framework{m.group(2)}opencode"
        stats["kept"] += 1
        return m.group(0)
    return repl


def normalise(surface_root: Path, apply: bool) -> dict:
    children = _surface_children(surface_root)
    totals = {"files_scanned": 0, "files_changed": 0, "rewritten": 0, "kept": 0}
    kept_refs: list[str] = []
    changed_files: list[str] = []
    for path in sorted(surface_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        totals["files_scanned"] += 1
        stats = {"rewritten": 0, "kept": 0}
        new_text = _ABS_OC.sub(_make_repl(children, stats), text)
        totals["rewritten"] += stats["rewritten"]
        totals["kept"] += stats["kept"]
        if stats["kept"]:
            rel = path.relative_to(surface_root).as_posix()
            for ln, line in enumerate(text.splitlines(), 1):
                for m in _ABS_OC.finditer(line):
                    tail = line[m.end():]
                    seg = _SEG.match(tail)
                    if tail[:1] != "}" and not (seg and seg.group(1) in children):
                        kept_refs.append(f"{rel}:{ln}: {line.strip()[:160]}")
                        break
        if new_text != text:
            totals["files_changed"] += 1
            changed_files.append(path.relative_to(surface_root).as_posix())
            if apply:
                # Byte-preserving: encode back to UTF-8 with no newline translation.
                path.write_bytes(new_text.encode("utf-8"))
    return {"totals": totals, "kept_refs": kept_refs, "changed_files": changed_files}


def main(argv: list[str] | None = None) -> int:
    # Source files carry non-ASCII (em-dashes); the Windows console defaults to cp1252 and
    # would crash mid-report. Reconfigure to UTF-8 with replacement so reporting never aborts.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="surface root (default: <framework>/opencode)")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--list-kept", action="store_true", help="print every preserved runtime-home reference")
    args = parser.parse_args(argv)

    surface_root = Path(args.root) if args.root else locate.surface_root()
    if not surface_root.is_dir():
        print(f"error: surface root not found: {surface_root}", file=sys.stderr)
        return 2

    result = normalise(surface_root, args.apply)
    t = result["totals"]
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] root={surface_root}")
    print(f"  files scanned  : {t['files_scanned']}")
    print(f"  files changed  : {t['files_changed']}")
    print(f"  refs rewritten : {t['rewritten']}  (.opencode/<surface> -> framework/opencode/<surface>)")
    print(f"  refs kept      : {t['kept']}  (runtime-home: notes/tasks/settings.json/.gsd-*/...)")
    if result["changed_files"]:
        head = result["changed_files"][:20]
        print("  first changed  : " + ", ".join(head) + (" ..." if len(result["changed_files"]) > len(head) else ""))
    if args.list_kept and result["kept_refs"]:
        print("  preserved runtime-home references:")
        for ref in result["kept_refs"]:
            print("    " + ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
