#!/usr/bin/env python3
"""Make a HOST repo load the telemetry collector: materialise the bridge, drop the dead entry.

WHAT IS WRONG WITHOUT IT
========================
There are exactly two ways a local plugin reaches OpenCode:

  1. a `plugin: [...]` entry in `opencode.json`
  2. a file in `.opencode/plugins/`

Route 1 is unusable here. OpenCode parses the entry as a URL first, so

    file://framework/opencode/plugin/telemetry.ts

has `framework` as its HOST and resolves to `\\\\framework\\...`. The file exists, the string
looks right, and the plugin never loads -- the collector wrote nothing from 2026-10-12 onward
while `validate.py` reported it as declared. Route 2 is what actually works, and it is what
StockerPro uses.

So a repo that carries route 1 and no bridge is registered-but-dead: the config names a
plugin that cannot load, and there is no discovery copy to fall back on. That is exactly the
state `agentic-lifecycle` was in, and it is why its own validate reported three failures.

WHAT THIS DOES
==============
  * writes `.opencode/plugins/telemetry.js` from the packaged template
    (`framework/opencode/plugin/telemetry.bridge.js`) -- the same file `framework init`
    installs into an app, so a host repo and an app cannot end up with different bridges
  * removes the dead `plugin` array from `opencode.json`

Removal rather than repair is deliberate: rewriting the entry to an absolute `file:///C:/...`
would commit a machine-specific path, and a bare relative path is resolved as an npm package.

Both targets are enforcement-plane, so the change is emitted as a patch, checked with
`git apply --check`, applied, and verified byte-for-byte.

Refuses rather than guesses: an existing bridge with different content, or a `plugin` key
holding anything other than the known dead entry, stops the run for a human to look at.

Usage:
    python3 framework/tools/emit_opencode_telemetry_bridge.py [--check-only] [--out PATH]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _patch_util import modify_patch, new_file_patch  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REGISTRY = "opencode.json"
BRIDGE = ".opencode/plugins/telemetry.js"
TEMPLATE = "framework/opencode/plugin/telemetry.bridge.js"
DEFAULT_OUT = ".planning/patches/opencode-telemetry-bridge.patch"

# The exact block a host repo carries when it registered the collector by config entry and
# never materialised a bridge. Byte-for-byte, including the two-space indent.
DEAD_BLOCK = (
    '  "plugin": [\n'
    '    "file://framework/opencode/plugin/telemetry.ts"\n'
    '  ],\n'
)


def _template() -> str:
    p = REPO / TEMPLATE
    if not p.is_file():
        raise SystemExit(
            "missing %s -- run framework/tools/emit_telemetry_bridge_template.py first" % TEMPLATE
        )
    return p.read_text(encoding="utf-8")


def _registry_text() -> str:
    return (REPO / REGISTRY).read_text(encoding="utf-8", newline="")


def plan() -> tuple[dict, list[str]]:
    """Return {rel: (old, new)} for the changes needed, plus the targets already satisfied."""
    tmpl = _template()
    changes: dict[str, tuple[str | None, str]] = {}
    satisfied: list[str] = []

    reg = _registry_text()
    if DEAD_BLOCK in reg:
        changes[REGISTRY] = (reg, reg.replace(DEAD_BLOCK, "", 1))
    elif '"plugin"' in reg:
        raise SystemExit(
            'REFUSING: %s has a "plugin" key this script does not recognise. Inspect it by '
            "hand -- replacing an unknown entry silently could disable a working plugin."
            % REGISTRY
        )
    else:
        satisfied.append(REGISTRY + " (no plugin key)")

    bridge = REPO / BRIDGE
    if not bridge.exists():
        changes[BRIDGE] = (None, tmpl)
    else:
        current = bridge.read_text(encoding="utf-8")
        if current != tmpl:
            raise SystemExit(
                "REFUSING: %s exists with content that differs from %s. Reconcile by hand -- "
                "two bridge bodies is the drift this template exists to prevent."
                % (BRIDGE, TEMPLATE)
            )
        satisfied.append(BRIDGE + " (matches template)")

    return changes, satisfied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true",
                    help="emit and verify the patch applies; do not modify the tree")
    ap.add_argument("--out", default=str(REPO / DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)

    changes, satisfied = plan()
    if not changes:
        print("already applied: nothing to do")
        for s in satisfied:
            print("MATCH  " + s)
        return 0

    fragments = []
    for rel in sorted(changes):
        old, new = changes[rel]
        fragments.append(new_file_patch(rel, new) if old is None else modify_patch(rel, old, new))
    patch = "".join(fragments)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8", newline="")
    print("patch written: %s (%d bytes)" % (out, len(patch)))

    check = subprocess.run(["git", "apply", "--check", str(out)], cwd=REPO,
                           capture_output=True, text=True)
    print("git apply --check exit:", check.returncode)
    if check.returncode != 0:
        print(check.stderr.strip()[:800], file=sys.stderr)
        return check.returncode
    if args.check_only:
        print("check-only: tree not modified")
        return 0

    applied = subprocess.run(["git", "apply", str(out)], cwd=REPO, capture_output=True, text=True)
    print("git apply exit:", applied.returncode)
    if applied.returncode != 0:
        print(applied.stderr.strip()[:800], file=sys.stderr)
        return applied.returncode

    rc = 0
    for rel, (_old, new) in sorted(changes.items()):
        actual = (REPO / rel).read_text(encoding="utf-8", newline="")
        same = actual == (new if new.endswith("\n") else new + "\n") or actual == new
        print(("MATCH  " if same else "DIFFER ") + rel)
        rc = rc or (0 if same else 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
