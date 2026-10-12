#!/usr/bin/env python3
"""Vendored-surface include-path portability tool.

GSD's OpenCode install emits @-file-include paths as the ABSOLUTE runtime config
dir (runtime-artifact-conversion.cjs _computePathPrefix -> `${posixTarget}/`;
isOpencode skips the $HOME shorthand). A vendored copy that ships inside a wheel
therefore freezes the SOURCE machine's absolute prefix into every skill, command,
agent, and gsd-core markdown file. Installing that wheel into another project
leaves every include dangling.

This tool makes the frozen prefix explicit and rewrites it to a portable token
(`{{PROJECT_ROOT}}`) that `framework init` substitutes with the target project's
absolute root at install time. Byte-preserving so line endings and encoding are
never altered.

Modes:
  scan    report distinct frozen prefixes and their file/match counts (read-only)
  rewrite replace a frozen prefix with the portable token (byte-preserving)

Usage:
  python framework/tools/surface_paths.py scan  [--root framework/opencode]
  python framework/tools/surface_paths.py rewrite --from <prefix> [--root ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# The portable token init substitutes. Kept here as the single source of truth
# so the scanner and the rewriter can never disagree on its spelling.
PORTABLE_TOKEN = "{{PROJECT_ROOT}}"

TEXT_SUFFIXES = {
    ".md", ".cjs", ".mjs", ".js", ".ts", ".cts", ".mts",
    ".json", ".jsonc", ".txt", ".yaml", ".yml", ".sh",
}

# A Windows drive-absolute prefix ending in `/.opencode`. The trailing
# `/`-anchored segment list is possessive-ish via non-greedy + lookahead so we
# capture the shortest stable prefix that still ends in `.opencode`.
FROZEN_PREFIX_RE = re.compile(r"([A-Za-z]:/[^ \t\r\n\"')`]*?/\.opencode)(?=[/\\])")


def iter_text_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def scan(root: Path) -> int:
    counter: Counter[str] = Counter()
    files: dict[str, set[str]] = {}
    # What follows the frozen prefix tells us WHICH surface the include targets
    # (`gsd-core/...` vs `skills/...`): the rewrite must preserve that segment.
    segment_after: Counter[str] = Counter()
    tail_re = re.compile(r"([A-Za-z]:/[^ \t\r\n\"')`]*?/\.opencode/)([A-Za-z0-9._-]+)")
    for f in iter_text_files(root):
        try:
            text = f.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in FROZEN_PREFIX_RE.finditer(text):
            prefix = m.group(1)
            counter[prefix] += 1
            files.setdefault(prefix, set()).add(str(f.relative_to(root)))
        for m in tail_re.finditer(text):
            segment_after[m.group(2)] += 1
    if not counter:
        print(f"scan: no frozen `.opencode` absolute prefixes under {root}")
        return 0
    print(f"scan: {sum(counter.values())} match(es) across {len(counter)} distinct prefix(es)")
    for prefix, n in counter.most_common():
        print(f"  {n:5d} match, {len(files[prefix]):4d} file(s): {prefix}/")
    print("  segment following '/.opencode/':")
    for seg, n in segment_after.most_common(20):
        print(f"    {n:5d}  {seg}/")
    return 0


def rewrite(root: Path, frozen: str, dry_run: bool) -> int:
    needle = frozen.encode("utf-8")
    changed = 0
    total = 0
    for f in iter_text_files(root):
        raw = f.read_bytes()
        n = raw.count(needle)
        if n == 0:
            continue
        changed += 1
        total += n
        if dry_run:
            continue
        # Byte-preserving: operate on bytes so CRLF/LF and encoding are untouched.
        raw = raw.replace(needle, PORTABLE_TOKEN.encode("utf-8"))
        f.write_bytes(raw)
    verb = "would rewrite" if dry_run else "rewrote"
    print(f"{verb} {total} occurrence(s) in {changed} file(s): {frozen} -> {PORTABLE_TOKEN}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["scan", "rewrite"])
    ap.add_argument("--root", default="framework/opencode")
    ap.add_argument("--from", dest="frozen", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root not found: {root}", file=sys.stderr)
        return 2

    if args.mode == "scan":
        return scan(root)
    if not args.frozen:
        print("error: rewrite requires --from <frozen-prefix>", file=sys.stderr)
        return 2
    return rewrite(root, args.frozen, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
