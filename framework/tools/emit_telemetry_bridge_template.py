#!/usr/bin/env python3
"""Emit the telemetry bridge TEMPLATE into the framework surface.

WHY THIS EXISTS
===============
`framework init` copies the packaged bootstrap plugin into an app's `.opencode/plugins/`,
which is the only route by which OpenCode loads a local plugin. It never copied the
telemetry bridge, so every freshly initialised app shipped a collector that was registered
nowhere.

An `opencode.json` entry of

    file://framework/opencode/plugin/telemetry.ts

is parsed as a URL BEFORE it is treated as a path. Its host is `framework`, so it resolves
to `\\\\framework\\...`, never loads, and logs only a watcher error. That is not theory: the
collector wrote nothing from 2026-10-12 onward (622 rows, every `skills_loaded` `["unknown"]`)
while every static check stayed green. StockerPro recovered only because the bridge had been
written by hand-run tooling; a fresh clone had no telemetry until someone re-ran it.

So the bridge has to ship with the surface and be materialised by init.

WHY A GENERATED PATCH
=====================
The template lives under `framework/opencode/**`, which is enforcement-plane and edit-denied
to agents. It reaches the tree the same way the collector did (see
`emit_telemetry_v2_patch.py`): a real, reviewable `git diff` that is checked with
`git apply --check`, applied, and then verified byte-for-byte against the content built here.

CONTENT IS NOT DUPLICATED
=========================
`BRIDGE_NEW` in `emit_telemetry_v2_patch.py` stays the single authority for what a bridge
contains. This script imports it and writes it verbatim, so the template and the live bridge
cannot drift apart into two implementations of the same thing.

Usage:
    python3 framework/tools/emit_telemetry_bridge_template.py [--check-only] [--out PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = "framework/opencode/plugin/telemetry.bridge.js"
DEFAULT_OUT = ".planning/patches/telemetry-bridge-template.patch"


def _bridge_content() -> str:
    """The bridge body, imported from the emitter that owns it.

    Imported rather than copied on purpose: a second literal here would be a second source of
    truth for the same file, and the two would diverge the first time one was edited.
    """
    spec = importlib.util.spec_from_file_location(
        "_emit_telemetry_v2_patch", Path(__file__).with_name("emit_telemetry_v2_patch.py")
    )
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load emit_telemetry_v2_patch.py next to this script")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    content = getattr(mod, "BRIDGE_NEW", None)
    if not isinstance(content, str) or "module.exports" not in content:
        raise SystemExit("BRIDGE_NEW missing or not a bridge: refusing to emit")
    return content


def already_applied(content: str) -> bool:
    p = REPO / TEMPLATE
    return p.is_file() and p.read_text(encoding="utf-8") == content


def build_patch(rel: str, content: str) -> str:
    """A valid new-file unified diff, built rather than shelled out to `git diff`.

    `git diff --no-index` needs an OLD tree that contains the file, which a new file does not
    have; constructing the hunk directly keeps the emitter independent of that asymmetry.
    """
    if not content.endswith("\n"):
        content += "\n"
    body = content.splitlines(keepends=True)
    lines = [
        "diff --git a/%s b/%s\n" % (rel, rel),
        "new file mode 100644\n",
        "--- /dev/null\n",
        "+++ b/%s\n" % rel,
        "@@ -0,0 +1,%d @@\n" % len(body),
    ]
    lines.extend("+" + ln for ln in body)
    if not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true",
                    help="emit and verify the patch applies; do not modify the tree")
    ap.add_argument("--out", default=str(REPO / DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)

    content = _bridge_content()

    if already_applied(content):
        print("already applied: %s matches BRIDGE_NEW; nothing to do" % TEMPLATE)
        print("MATCH  " + TEMPLATE)
        return 0

    if (REPO / TEMPLATE).exists():
        print("REFUSING: %s exists with different content. Reconcile it by hand first -- "
              "overwriting a plane file silently is how two bridges start." % TEMPLATE,
              file=sys.stderr)
        return 1

    patch = build_patch(TEMPLATE, content)
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

    actual = (REPO / TEMPLATE).read_text(encoding="utf-8")
    same = actual == content
    print(("MATCH  " if same else "DIFFER ") + TEMPLATE)
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
