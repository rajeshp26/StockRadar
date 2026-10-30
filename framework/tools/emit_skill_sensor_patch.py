#!/usr/bin/env python3
"""Emit the corrected skill-sensor patch for human approval.

WHY A SECOND PATCH
==================
The first patch (remaining-plane-patches.patch) changed the recorder to

    const skillArgs = normalizeTaskArgs(input)
    rec.skills_loaded.add(String(skillArgs?.id ?? skillArgs?.name ?? "unknown"))

That only works when the args are FLAT on input.args. Driven end-to-end, the real plugin
still records "unknown" for the nested shape the telemetry harness itself calls the REAL
runtime shape (`input.input.args`), because normalizeTaskArgs returns the merged object one
level up: `{args:{id:"apple-ui"}}`, so `skillArgs?.id` is undefined.

The task line is not affected because resolveExecutionAgent normalises a SECOND time, which
unwraps the `args` key. The skill line normalises once. Reasoning about that gap is exactly
what produced the wrong first patch, so this fix does not reason about the shape at all: it
unwraps until the id or name appears, wherever the harness put them.

VERIFIED BEFORE APPLYING
========================
`--verify` copies the whole plugin directory to a throwaway location, writes the intended
post-image of telemetry.ts there, and drives the REAL plugin with node --test-free probes:
every arg shape must record the real skill id. That is a pre-apply proof of the bytes this
patch contains, not a hope.

Emits docs/designer-agent/skill-sensor-patch.patch
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from emit_design_skills_integration_patch import (  # noqa: E402
    apply_hunks,
    generate,
    parse,
    read_exact,
    style_of,
)

OUT = REPO / "docs" / "designer-agent" / "skill-sensor-patch.patch"
SENSOR = "framework/opencode/plugin/telemetry.ts"

ANCHOR = (
    '      if (input?.tool === "skill") {\n'
    "        // Args are NOT on input.args in this harness (see the task-tool note above):\n"
    "        // reading them there recorded every skill call as \"unknown\", so skills_loaded\n"
    "        // said nothing and G-SKILL-USE could not judge. normalizeTaskArgs reads the shape\n"
    "        // the harness actually delivers; `id` is the skill tool's parameter, `name` is\n"
    "        // kept as a fallback so this line is correct under either shape.\n"
    "        const skillArgs = normalizeTaskArgs(input)\n"
    '        rec.skills_loaded.add(String(skillArgs?.id ?? skillArgs?.name ?? "unknown"))\n'
    "      }\n"
)

REPLACEMENT = (
    '      if (input?.tool === "skill") {\n'
    "        // The skill tool's args are not in one fixed place: the task tool delivers them at\n"
    "        // input.input.args (see the note above), other tools at input.args, and a caller may\n"
    "        // pass a plain args object. Reading a single location recorded EVERY skill call as\n"
    '        // "unknown", so skills_loaded said nothing and G-SKILL-USE could never judge. Two\n'
    "        // attempts to guess the shape both got it wrong -- so unwrap until the id (the skill\n"
    "        // tool's parameter) or name appears, at any of those depths.\n"
    "        const skillIdOf = (o: any, depth = 0): any => {\n"
    "          if (!o || typeof o !== \"object\" || depth > 3) return undefined\n"
    "          return o.id || o.name || skillIdOf(o.args, depth + 1) || skillIdOf(o.input, depth + 1)\n"
    "        }\n"
    '        rec.skills_loaded.add(String(skillIdOf(input) ?? "unknown"))\n'
    "      }\n"
)

EDITS = {SENSOR: [(ANCHOR, REPLACEMENT)]}


def build() -> dict[str, dict]:
    """repo-relative path -> {original, updated, style}."""
    built: dict[str, dict] = {}
    for rel, pairs in EDITS.items():
        path = REPO / rel
        if not path.exists():
            raise SystemExit("%s: target does not exist" % rel)
        original = read_exact(path)
        style = style_of(original)
        current = original
        for anchor, replacement in pairs:
            old = anchor.replace("\n", style)
            new = replacement.replace("\n", style)
            hits = current.count(old)
            if hits != 1:
                raise SystemExit("%s: anchor occurs %d times, expected exactly 1 "
                                 "(has the first patch been applied?)" % (rel, hits))
            if new == old:
                raise SystemExit("%s: replacement equals anchor" % rel)
            current = current.replace(old, new)
        restored = current
        for anchor, replacement in reversed(pairs):
            restored = restored.replace(
                replacement.replace("\n", style), anchor.replace("\n", style)
            )
        if restored != original:
            raise SystemExit("%s: replacement is not reversible - more changed than intended" % rel)
        built[rel] = {"original": original, "updated": current, "style": style}
    return built


PROBE = r"""
import { TelemetryPlugin } from "file:///%s"

function makeDollar() {
  const emitted = []
  const dollar = (strings, ...values) => {
    let cmd = ""
    for (let i = 0; i < strings.length; i++) {
      cmd += strings[i]
      if (i < values.length) cmd += String(values[i])
    }
    let payload = null
    const m = cmd.match(/--json\s+(\{.*\})\s*$/)
    if (m) { try { payload = JSON.parse(m[1]) } catch { payload = null } }
    emitted.push({ cmd, payload })
    return { quiet() { return this }, nothrow() { return Promise.resolve({ exit: 0 }) } }
  }
  return { dollar, emitted }
}

async function drive(input) {
  const { dollar, emitted } = makeDollar()
  const hooks = await TelemetryPlugin({ $: dollar })
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_probe" } } } })
  await hooks["tool.execute.before"](input)
  await hooks.event({ event: { type: "session.idle", properties: {} } })
  const finals = emitted.filter((e) => e.payload && e.payload.kind === "final")
  return finals.length ? finals[finals.length - 1].payload.skills_loaded : null
}

const shapes = {
  "nested input.input.args.id":  { tool: "skill", callID: "c1", input: { args: { id: "apple-ui" } } },
  "flat input.args.id":          { tool: "skill", callID: "c2", args: { id: "apple-ui" } },
  "nested input.input.args.name":{ tool: "skill", callID: "c3", input: { args: { name: "apple-ui" } } },
  "triple input.input.input.args.id": { tool: "skill", callID: "c4", input: { input: { args: { id: "apple-ui" } } } },
  "plain args object":           { tool: "skill", callID: "c5", id: "apple-ui" },
  "no args at all":              { tool: "skill", callID: "c6" },
}

let bad = 0
for (const [label, input] of Object.entries(shapes)) {
  const got = await drive(input)
  const want = label === "no args at all" ? ["unknown"] : ["apple-ui"]
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (!ok) bad++
  console.log(`${ok ? "PASS" : "FAIL"}  ${label} -> ${JSON.stringify(got)} (want ${JSON.stringify(want)})`)
}
console.log(bad === 0 ? "verify: every arg shape records the real skill id" : `verify: ${bad} shape(s) wrong`)
process.exit(bad === 0 ? 0 : 1)
"""


def verify(built: dict[str, dict]) -> None:
    """Copy the plugin dir, write the post-image, drive the REAL plugin, assert every shape."""
    tmp = Path(tempfile.mkdtemp(prefix="skill-sensor-"))
    try:
        src = REPO / "framework" / "opencode" / "plugin"
        dst = tmp / "plugin"
        shutil.copytree(src, dst)
        # Intended post-image, written byte-for-byte from the same string the patch carries.
        (dst / "telemetry.ts").write_text(built[SENSOR]["updated"], encoding="utf-8", newline="")
        probe = tmp / "probe.mjs"
        url = (dst / "telemetry.ts").as_posix()
        probe.write_text(PROBE % url, encoding="utf-8", newline="")
        r = subprocess.run(["node", str(probe)], capture_output=True, text=True)
        print(r.stdout.rstrip())
        if r.returncode != 0:
            raise SystemExit("verify FAILED (node exit %d)\n%s" % (r.returncode, r.stderr[-1200:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    built = build()
    patch = generate(built)
    files = parse(patch)
    if set(files) != set(built):
        raise SystemExit("patch touches %s, expected %s" % (sorted(files), sorted(built)))
    for rel, info in files.items():
        if apply_hunks(built[rel]["original"], info["hunks"]) != built[rel]["updated"]:
            raise SystemExit("self-check FAILED: rebuilt %s != intended post-image" % rel)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patch, encoding="utf-8", newline="")
    hunks = sum(len(v["hunks"]) for v in files.values())
    print("wrote %s (%d bytes)" % (OUT.relative_to(REPO).as_posix(), len(patch)))
    print("files: %d, hunks: %d, self-check: OK" % (len(files), hunks))
    verify(built)
    print("\napply with:  git apply %s" % OUT.relative_to(REPO).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
