#!/usr/bin/env python3
"""Emit the OpenCode-V2 telemetry plugin patch.

WHY A GENERATED PATCH
=====================
`framework/opencode/plugin/**` and `.opencode/**` are enforcement-plane paths: agents may
not edit them directly. The fix still has to be reviewable and reproducible, so this script
is the change set. It rewrites the three files in a temp tree, emits a real `git diff
--no-index`, refuses to continue unless the patch applies, applies it, and then asserts the
result is byte-identical to what it built.

WHAT IT FIXES
=============
OpenCode v2 validates a plugin's DEFAULT export as `{ id, setup }` (or `{ id, effect }`).
`framework/opencode/plugin/telemetry.ts` exported the V1 factory shape and the discovery
bridge exported `{ server: factory }`, so the host logged

    Plugin must export a default definition with an id and an effect or setup function

and the collector never loaded. `.planning/telemetry/records.jsonl` stops at 2026-10-12;
622 rows, every one `skills_loaded: ["unknown"]`. A collector that does not load reports
zero, and zero is indistinguishable from "no work happened" to G-SKILL-USE, G-TELEMETRY-LIVE
and report.py.

The V2 hook payloads differ from V1 in ways that would silently record zeros if the events
were passed through unchanged, so the patch adds an explicit translation layer. Every shape
below was measured against host v2.2.4 with a probe plugin, not inferred:

    tool hook event  { tool, sessionID, agent, messageID, id, input, status, result }
    event stream     { id, created, type, durable, location, data }   (no `properties`)
    tokens           session.step.ended.data.tokens {input,output,reasoning,cache{read,write}}
    model / agent    session.step.started.data.model {id,providerID}, .agent
    terminal         session.execution.succeeded

Usage:
    python3 framework/tools/emit_telemetry_v2_patch.py [--check-only] [--out PATH]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

TS = "framework/opencode/plugin/telemetry.ts"
TEST = "framework/opencode/plugin/telemetry.test.mjs"
BRIDGE = ".opencode/plugins/telemetry.js"
DEFAULT_OUT = ".planning/patches/telemetry-v2-plugin.patch"

# ── telemetry.ts: imports ────────────────────────────────────────────────────────────────
TS_IMPORT_OLD = 'import type { Plugin } from "@opencode-ai/plugin"\n'
TS_IMPORT_NEW = (
    'import type { Plugin } from "@opencode-ai/plugin"\n'
    'import { spawnSync } from "node:child_process"\n'
)

# ── telemetry.ts: replace the V1 default export with the V2 definition ───────────────────
TS_TAIL_OLD = "export default TelemetryPlugin\n"

TS_TAIL_NEW = r'''// ─────────────────────────────────────────────────────────────────────────────────────────
// V2 ENTRYPOINT (OpenCode v2.x plugin API)
// ─────────────────────────────────────────────────────────────────────────────────────────
// WHY THIS EXISTS
// ===============
// v2 validates the default export as a plugin DEFINITION -- `{ id, setup }` or
// `{ id, effect }` -- and rejects the V1 factory shape outright:
//
//   Plugin must export a default definition with an id and an effect or setup function
//
// From the host upgrade onward the collector loaded nothing and records.jsonl stopped being
// written (last row 2026-10-12). A collector that does not load reports zero, and zero is
// indistinguishable from "no work happened" to every consumer: G-SKILL-USE, G-TELEMETRY-LIVE,
// report.py. That is a sensor defect, not a quiet period.
//
// SHAPE
// =====
// v2 registers hooks imperatively inside `setup(ctx)`. The V1 hook bodies above are reused
// unchanged -- they are the collector, and reimplementing them for v2 would create a second
// source of truth for the same facts.
//
// TRANSLATION, NOT PASS-THROUGH
// =============================
// v2 events are `{ id, created, type, durable, location, data }`; the V1 body reads
// `{ type, properties }`. Handing a v2 event straight to it yields `session_id: ""` and a
// record full of zeros -- the same silent-zero failure in a new costume. Every mapping below
// was measured against host v2.2.4 with a probe plugin:
//
//   session.execution.started  data.sessionID                      -> session.created
//   session.step.started       data.model{id,providerID}, .agent    -> chat.params
//   session.step.ended         data.tokens{input,output,reasoning,cache{read,write}}
//                                                                  -> message.updated
//   session.execution.succeeded / .failed / .cancelled / deleted    -> terminal flush
//
// DELIBERATELY UNMAPPED
// =====================
// `session.usage.updated` carries the CUMULATIVE session token figure. Mapping it alongside
// `session.step.ended` would count every token twice, so it is dropped on purpose. Dropping
// is explicit here rather than an accident of a field name that does not exist.

/** v2 `execute.before`/`execute.after` event -> the V1 hook's first parameter. */
export function v2ToolBefore(e: any) {
  const input = e?.input ?? e?.args
  return {
    tool: String(e?.tool ?? e?.name ?? ""),
    // `args` is where the V1 bodies read tool arguments (bash: input.args.command,
    // skill: the unwrapped id). `input` is kept because the task tool has historically
    // delivered its args there.
    args: input,
    input,
    callID: e?.id,
    sessionID: e?.sessionID,
  }
}

/** v2 `execute.after` event -> [V1 input, V1 output]. v2 carries the tool name itself, so
 *  no before/after pairing is needed and a dropped event cannot misattribute a result. */
export function v2ToolAfter(e: any) {
  const r: any = e?.result
  let text = ""
  if (typeof r === "string") text = r
  else if (typeof r?.output?.output === "string") text = r.output.output
  else if (r) {
    try { text = JSON.stringify(r) } catch { text = "" }
  }
  const exit = typeof r?.output?.exit === "number" ? r.output.exit
    : typeof r?.metadata?.exit === "number" ? r.metadata.exit
    : undefined
  return [v2ToolBefore(e), { output: text, title: "", exit }] as const
}

/** One v2 stream event -> the instruction the V1 collector understands.
 *  `null` means "the collector has no counter for this event" and is explicit. */
export function v2Event(ev: any, seen: Set<string>) {
  const t = String(ev?.type ?? "")
  const d: any = ev?.data ?? {}

  if (t === "session.execution.started") {
    const sid = String(d.sessionID ?? "")
    // v2 emits execution.started once PER TURN; V1's session.created fired once per session
    // and starts a 60s heartbeat interval. Passing every turn through would stack intervals
    // and multiply the write rate, so only the first turn creates the session.
    if (!sid || seen.has(sid)) return null
    seen.add(sid)
    return { kind: "event" as const,
             event: { type: "session.created", properties: { info: { id: sid } } } }
  }

  if (t === "session.step.started") {
    // v2 has no `chat.params` hook; model/provider identity rides on the step event.
    return {
      kind: "chat" as const,
      input: {
        model: { modelID: d?.model?.id },
        provider: { providerID: d?.model?.providerID },
        agent: d.agent,
      },
    }
  }

  if (t === "session.step.ended") {
    return {
      kind: "event" as const,
      event: {
        type: "message.updated",
        properties: { info: { id: d.assistantMessageID, tokens: d.tokens } },
      },
    }
  }

  if (t === "session.compacted") {
    return { kind: "event" as const, event: { type: "session.compacted", properties: {} } }
  }

  if (t === "session.execution.succeeded" || t === "session.execution.failed"
      || t === "session.execution.cancelled" || t === "session.deleted") {
    // `emit("final")` is idempotent, so the first turn end writes the record and later
    // terminal events are no-ops; heartbeats keep the series alive in between.
    return { kind: "event" as const, event: { type: "session.idle", properties: {} } }
  }

  return null
}

/** Dispatch one v2 event into the V1 collector. Shared with the test harness so the test
 *  exercises the production path rather than a copy of it. */
export async function dispatchV2(ev: any, hooks: any, seen: Set<string>) {
  const step = v2Event(ev, seen)
  if (!step) return
  if (step.kind === "chat") await hooks?.["chat.params"]?.(step.input)
  else await hooks?.event?.({ event: step.event })
}

/** v2 does not hand the plugin a `$`. The collector uses exactly two chain methods
 *  (`.quiet().nothrow()`), so that is all this needs to provide. Commands are repo-relative,
 *  hence the plugin's own location as cwd.
 *
 *  NO SHELL, ON PURPOSE. The V1 host `$` escapes every interpolated value itself. A naive
 *  reimplementation that concatenates a command string does not, and on Windows cmd.exe
 *  consumes the quotes inside the JSON payload. Measured on the first write after the v2
 *  port landed: the record was appended as `{record_version:3,...}` -- every quote stripped --
 *  which is not JSON and cannot be read back. Building an argv array and spawning without a
 *  shell removes the whole class: no quoting rules, no metacharacter expansion, no
 *  command-length ceiling. */
export function shellFor(cwd: string) {
  return (strings: TemplateStringsArray, ...values: any[]) => {
    const argv: string[] = []
    for (let i = 0; i < strings.length; i++) {
      const chunk = strings[i].trim()
      if (chunk) argv.push(...chunk.split(/\s+/))
      // Each interpolated value is ONE argument, never re-split and never re-quoted.
      if (i < values.length) argv.push(String(values[i] ?? ""))
    }
    const chain = {
      quiet() { return chain },
      nothrow() {
        try {
          const r = spawnSync(argv[0], argv.slice(1), { cwd, encoding: "utf8", timeout: 60_000 })
          return Promise.resolve({
            exitCode: r.status ?? 1,
            text: () => r.stdout ?? "",
            stderr: r.stderr ?? "",
          })
        } catch (err: any) {
          return Promise.resolve({ exitCode: 1, text: () => "", stderr: String(err?.message ?? err) })
        }
      },
    }
    return chain
  }
}

export const TelemetryV2 = {
  id: "telemetry",
  async setup(ctx: any) {
    const hooks: any = await TelemetryPlugin({
      $: shellFor(String(ctx?.location?.directory ?? process.cwd())),
    })

    await ctx?.tool?.hook?.("execute.before", async (e: any) => {
      await hooks["tool.execute.before"]?.(v2ToolBefore(e))
    })

    await ctx?.tool?.hook?.("execute.after", async (e: any) => {
      const [input, output] = v2ToolAfter(e)
      await hooks["tool.execute.after"]?.(input, output)
    })

    const seen = new Set<string>()
    void (async () => {
      try {
        for await (const ev of ctx.event.subscribe()) await dispatchV2(ev, hooks, seen)
      } catch {
        // The subscription ends on host unload and on restart; both are normal.
      }
    })()
  },
}

export default TelemetryV2
'''

# ── telemetry.test.mjs: adapter coverage ─────────────────────────────────────────────────
TEST_IMPORT_OLD = 'import { TelemetryPlugin } from "./telemetry.ts"\n'
TEST_IMPORT_NEW = (
    'import { TelemetryPlugin, dispatchV2, shellFor, v2Event, v2ToolAfter, v2ToolBefore } from "./telemetry.ts"\n'
)

TEST_APPEND = r'''

// ─── V2 adapter ───────────────────────────────────────────────────────────────────────────
// These cases exist because the v2 payload shapes are DIFFERENT from v1 in ways that fail
// silently: a pass-through records `session_id: ""` and zero tokens while every counter still
// looks present. Each shape below was measured on host v2.2.4.
describe("v2 adapter", () => {
  it("captures the skill id from a v2 execute.before event", () => {
    const input = v2ToolBefore({
      tool: "skill", id: "call_1", sessionID: "ses_x", input: { id: "istqb-testing" },
    })
    assert.equal(input.tool, "skill")
    assert.equal(input.args.id, "istqb-testing")
    assert.equal(input.callID, "call_1")
  })

  it("reads v2 bash text and exit from result.output", () => {
    const [input, output] = v2ToolAfter({
      tool: "bash", id: "c1", input: { command: "echo hi" }, status: "success",
      result: { output: { exit: 0, truncated: false, output: "hi\n", status: "success" } },
    })
    assert.equal(input.args.command, "echo hi")
    assert.equal(output.output, "hi\n")
    assert.equal(output.exit, 0)
  })

  it("turns the first execution.started into session.created, later turns into nothing", () => {
    const seen = new Set()
    const first = v2Event({ type: "session.execution.started", data: { sessionID: "ses_a" } }, seen)
    assert.equal(first.event.properties.info.id, "ses_a")
    assert.equal(v2Event({ type: "session.execution.started", data: { sessionID: "ses_a" } }, seen), null)
  })

  it("does NOT map session.usage.updated -- it would double count step tokens", () => {
    assert.equal(
      v2Event({ type: "session.usage.updated", data: { sessionID: "s", tokens: { input: 99 } } }, new Set()),
      null,
    )
  })

  it("maps step tokens to a per-message update", () => {
    const step = v2Event({
      type: "session.step.ended",
      data: { assistantMessageID: "msg_1", tokens: { input: 10, output: 20, reasoning: 0, cache: { read: 0, write: 0 } } },
    }, new Set())
    assert.equal(step.event.type, "message.updated")
    assert.equal(step.event.properties.info.id, "msg_1")
    assert.equal(step.event.properties.info.tokens.input, 10)
  })

  it("spawns with an argv array so a JSON payload keeps its quotes", async () => {
    // The defect this pins: a shell-concatenated command lost every quote inside the payload
    // and the record was appended as `{record_version:3,...}` -- unparsable, unrecoverable.
    const $ = shellFor(process.cwd())
    const payload = JSON.stringify({ text: "a b", quoted: '"x"' })
    const r = await $`python3 -c ${'import json,sys;print(json.loads(sys.argv[1])["quoted"])'} ${payload}`
      .quiet().nothrow()
    assert.equal(r.exitCode, 0, "spawn failed: " + r.stderr)
    assert.equal(r.text().trim(), '"x"')
  })

  it("drives a full v2 session into a final record with real skills and tokens", async () => {
    const { hooks, emitted } = await makePlugin()
    const seen = new Set()
    await dispatchV2({ type: "session.execution.started", data: { sessionID: "ses_v2" } }, hooks, seen)
    await dispatchV2({
      type: "session.step.started",
      data: { sessionID: "ses_v2", agent: "team-lead", model: { id: "big-pickle", providerID: "opencode" } },
    }, hooks, seen)
    await hooks["tool.execute.before"](v2ToolBefore({
      tool: "skill", id: "c1", sessionID: "ses_v2", input: { id: "istqb-testing" },
    }))
    await hooks["tool.execute.after"](...v2ToolAfter({
      tool: "bash", id: "c2", input: { command: "bash framework/gates/g8_state.sh" }, status: "success",
      result: { output: { exit: 0, output: "[g8] PASS\n", status: "success" } },
    }))
    await dispatchV2({
      type: "session.step.ended",
      data: { assistantMessageID: "msg_1", tokens: { input: 10, output: 20, reasoning: 0, cache: { read: 5, write: 0 } } },
    }, hooks, seen)
    await dispatchV2({ type: "session.execution.succeeded", data: { sessionID: "ses_v2" } }, hooks, seen)

    const final = lastPayload(emitted, "final")
    assert.ok(final, "expected a final record")
    assert.equal(final.session_id, "ses_v2")
    assert.ok(final.skills_loaded.includes("istqb-testing"), "skill id must be recorded, not 'unknown'")
    assert.equal(final.tokens.input, 10)
    assert.equal(final.tokens.output, 20)
    assert.equal(final.tokens.cache_read, 5)
    assert.ok(final.models_seen["opencode/big-pickle"] >= 1, "model identity comes from step.started")
    assert.equal(final.gates.g8.result, "pass")
  })
})
'''

# ── discovery bridge ─────────────────────────────────────────────────────────────────────
BRIDGE_NEW = r'''// .opencode/plugins/telemetry.js
// BRIDGE -- not an implementation (validate.py fails discovery files that carry hooks).
//
// OpenCode v2 validates the DEFAULT export as a plugin definition: { id, setup } (or
// { id, effect }). The V1 envelope exported here -- { server: factory } -- was rejected with
// "Plugin must export a default definition with an id and an effect or setup function", so
// the collector never loaded and records.jsonl stopped growing on 2026-10-12. Only the export
// envelope changes; the collector itself still lives in exactly one place, telemetry.ts.
const path = require("node:path")
const IMPL = path.resolve(__dirname, "../../framework/opencode/plugin/telemetry.ts")
const mod = require(IMPL)
const definition = mod && mod.default && typeof mod.default.setup === "function" ? mod.default : null
if (!definition) {
  throw new TypeError(
    "telemetry bridge: " + IMPL + " must default-export a v2 plugin definition { id, setup }",
  )
}
module.exports = definition
'''


def already_applied() -> bool:
    """True when every target already carries the v2 content.

    Checked by marker, before the anchors: the anchors are CONSUMED by the rewrite, so an
    applied tree fails the anchor assertion instead of reaching an empty diff. This script is
    the durable record of a change that lives in gitignored paths (`.opencode/`, `.planning/`),
    so it will be re-run on an applied tree and that must read as success.
    """
    markers = {
        TS: ("export default TelemetryV2", "spawnSync"),
        TEST: ("dispatchV2", "v2 adapter"),
    }
    for rel, needles in markers.items():
        p = REPO / rel
        if not p.exists():
            return False
        text = p.read_text(encoding="utf-8")
        if any(n not in text for n in needles):
            return False
    bridge = REPO / BRIDGE
    # The bridge lives under `.opencode/`, which exists only in a HOST repo. The framework repo
    # (agentic-lifecycle) has no plugin directory at all, so an absent bridge is "not applicable
    # here", never "not applied" -- otherwise the emitter could never run in the repo that owns
    # the collector.
    if not bridge.exists():
        return True
    return bridge.read_text(encoding="utf-8") == BRIDGE_NEW


def build_edits() -> dict:
    """Read the originals, apply each replacement, and fail loudly if an anchor moved."""
    edits = {}

    ts = (REPO / TS).read_text(encoding="utf-8")
    for old, new, label in (
        (TS_IMPORT_OLD, TS_IMPORT_NEW, "telemetry.ts import block"),
        (TS_TAIL_OLD, TS_TAIL_NEW, "telemetry.ts default export"),
    ):
        if ts.count(old) != 1:
            raise SystemExit("anchor occurs %d times, expected 1: %s" % (ts.count(old), label))
        ts = ts.replace(old, new, 1)
    edits[TS] = ts

    test = (REPO / TEST).read_text(encoding="utf-8")
    if test.count(TEST_IMPORT_OLD) != 1:
        raise SystemExit("anchor occurs %d times, expected 1: test import" % test.count(TEST_IMPORT_OLD))
    test = test.replace(TEST_IMPORT_OLD, TEST_IMPORT_NEW, 1) + TEST_APPEND
    edits[TEST] = test

    # Host-only target: present in an app repo, absent in the framework repo. Skipping it keeps
    # the emitter runnable from both, which is the point of shipping it as the change record.
    if (REPO / BRIDGE).exists():
        edits[BRIDGE] = BRIDGE_NEW
    return edits


def emit_patch(edits: dict, out: Path) -> None:
    """Produce a real git diff by materialising OLD/NEW trees and rewriting the headers."""
    with tempfile.TemporaryDirectory(prefix="telemetry-v2-") as td:
        root = Path(td)
        for rel in edits:
            old_src = REPO / rel
            (root / "OLD" / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / "NEW" / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / "OLD" / rel).write_bytes(old_src.read_bytes())
            (root / "NEW" / rel).write_text(edits[rel], encoding="utf-8", newline="")

        proc = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "--no-ext-diff", "--no-prefix", "OLD", "NEW"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode not in (0, 1):
            raise SystemExit("git diff failed: " + (proc.stderr or proc.stdout)[:400])
        if not proc.stdout.strip():
            raise SystemExit("git diff produced empty stdout; nothing to emit")

        lines = []
        for ln in proc.stdout.splitlines(keepends=True):
            nl = "\n" if ln.endswith("\n") else ""
            body = ln[:-1] if nl else ln
            if body.startswith("diff --git "):
                rel = body.split(" b/", 1)[-1][2:]
                body = "diff --git a/%s b/%s" % (rel, rel)
            elif body.startswith("--- OLD/"):
                body = "--- a/" + body[len("--- OLD/"):]
            elif body.startswith("+++ NEW/"):
                body = "+++ b/" + body[len("+++ NEW/"):]
            lines.append(body + nl)
        patch = "".join(lines)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch, encoding="utf-8", newline="")
    print("patch written: %s (%d bytes)" % (out, len(patch)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true",
                    help="emit and verify the patch applies; do not modify the tree")
    ap.add_argument("--out", default=str(REPO / DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)

    if already_applied():
        print("already applied: every target matches the intended content; nothing to do")
        for rel in (TS, TEST, BRIDGE):
            print(("MATCH  " if (REPO / rel).exists() else "N/A    ") + rel)
        return 0

    edits = build_edits()
    emit_patch(edits, out)

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

    ok = True
    for rel, expected in edits.items():
        actual = (REPO / rel).read_text(encoding="utf-8")
        same = actual == expected
        ok = ok and same
        print(("MATCH  " if same else "DIFFER ") + rel)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
