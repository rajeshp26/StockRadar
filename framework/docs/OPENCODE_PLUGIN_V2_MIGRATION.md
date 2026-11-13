# OpenCode plugin V1 → V2 migration (telemetry.ts, gsd-core.js)

**Status:** design verified against the v2.1.2 documentation; **not applied and not runtime-tested**
**Owner:** human (both files are inside the agent-immutable enforcement plane)
**Blocks:** framework telemetry has never recorded, so `report.py` and `bg_poll_total` have had no
data. Fixing the path alone does not fix this.

---

## 1. Three independent defects

| # | Defect | Evidence |
|---|---|---|
| 1 | Plugin path parses as a UNC share | `EUNKNOWN: unknown error, stat '\\framework\opencode\plugin\telemetry.ts'` |
| 2 | V1 export shape rejected by the 2.x loader | `PluginModule.LoadError: Plugin must export a default definition with an id and an effect or setup function` |
| 3 | `$` has no V2 equivalent | migration guide: "`$` Bun shell helper → import and manage the process API your plugin uses" |

Fixing only #1 changes the error from #1 to #2. All three must be fixed together, or the plugin
still does not load.

---

## 2. The verified V2 contract

```ts
import { Plugin } from "@opencode/plugin"

export default Plugin.define({
  id: "stockerpro.telemetry",
  async setup(ctx) {
    // register hooks / transforms here
    return () => { /* cleanup (replaces V1 dispose) */ }
  },
})
```

`{ id, setup }` is the shape the loader's schema demands; `effect` is the Effect-flavoured
alternative. A plain default-exported object carrying `id` + `setup` satisfies the same schema.

### Hook mapping (authoritative, from the v2.1.2 migration guide)

| V1 (used here) | V2 |
|---|---|
| `event` | `ctx.event.subscribe({ signal })` — async iterable |
| `dispose` | function returned by `setup` |
| `tool.execute.before` | `ctx.tool.hook("execute.before", cb)` |
| `tool.execute.after` | `ctx.tool.hook("execute.after", cb)` |
| `chat.params` | `ctx.session.hook("context", cb)` |

Context properties migrated: `directory` → `ctx.location.directory`, `project` →
`ctx.location.project`, `client` → the `ctx.<domain>` methods, options argument → `ctx.options`.

---

## 3. This is not a mechanical rename — the payloads differ

The guide is explicit: *"These are migration destinations, not always exact renames."* Concretely,
`telemetry.ts` currently destructures positional V1 arguments:

| Hook | V1 signature used today | V2 callback receives | Consequence if passed through unchanged |
|---|---|---|---|
| `tool.execute.before` | `(input)` — `input.tool`, `input.sessionID`, `input.callID` | one `event` — `event.tool`, `event.input` | `input.tool` is `undefined` → every tool recorded as `"unknown"` |
| `tool.execute.after` | `(input, output)` — `output.exit`, `output.output` | one `event` — `event.status`, `event.result` / `event.error` | exit codes and outputs never read → gate/blocker counters stay 0 |
| `chat.params` | `(input)` mutating V1 params | `event.options` (e.g. `event.options.temperature`) | temperature/model asserts silently no-op |
| `event` | `({ event })` | `event` directly from the iterable | `event?.type` becomes `undefined` → **zero records written** |

That last row is the exact failure mode this plugin already suffered once, documented in its own
header comment:

> `session.idle` is an EVENT TYPE delivered through the `event` hook, not a hook key. A previous
> version registered "session.idle" as a top-level key; it never fired, so no record was ever
> written.

A wrapper that registers the existing handlers verbatim would load successfully and then record
nothing — which is worse than failing to load, because the failure is silent. **The port must adapt
each payload access, not just the registration call.**

---

## 4. Required body changes

Only three regions of `framework/opencode/plugin/telemetry.ts` change mechanically:

```diff
-import type { Plugin } from "@opencode-ai/plugin"
+import { $ } from "bun"
+import { Plugin } from "@opencode/plugin"
```

```diff
-export const TelemetryPlugin: Plugin = async ({ $ }) => {
+const createTelemetryHooks = async () => {
```

```diff
-}
-export default TelemetryPlugin
+}
+
+export default Plugin.define({
+  id: "stockerpro.telemetry",
+  async setup(ctx) {
+    const hooks = await createTelemetryHooks()
+    const controller = new AbortController()
+
+    // --- payload adaptation is REQUIRED here, see section 3 ---
+    await ctx.tool.hook("execute.before", (event) => hooks["tool.execute.before"](event))
+    await ctx.tool.hook("execute.after", (event) => hooks["tool.execute.after"](event, event))
+    await ctx.session.hook("context", (event) => hooks["chat.params"](event))
+
+    void (async () => {
+      for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
+        await hooks.event({ event })
+      }
+    })()
+
+    return () => controller.abort()
+  },
+})
```

`import { $ } from "bun"` is the documented replacement for the injected helper ("import and
manage the process API your plugin uses"). OpenCode runs on Bun, so the import resolves; if the
runtime ever drops Bun, `node:child_process` is the fallback.

**The three handler adapters in that block are placeholders, not finished code.** Each must be
rewritten to read the V2 event shape listed in section 3. Shipping them as written would compile
and silently record nothing.

## 5. `gsd-core.js` is a different, larger job

It exports `{ server: GsdCorePlugin, id: "gsd-core" }`. The V1→V2 migration table has **no row for
a `server` extension point** — that surface moved to the RPC API (`/build/plugins/rpc`). This is not
a rename; it is a redesign and needs the RPC guide before any code is written.

Do not delete the plugin entry to silence the warning: that removes enforcement telemetry.

---

## 6. Test that proves registration (not just "no error")

A plugin that loads but registers nothing is indistinguishable from a working one at startup. The
test must assert a *record is written*:

1. point the plugin at a temporary state root (`GSD_STATE_ROOT`) so the test cannot pollute real
   telemetry;
2. start a server, run one short session, end it;
3. assert a `final` record appears in `<state_root>/telemetry/records.jsonl`;
4. assert `report.py` exits 0 and the session is not listed as unfinalized.

Step 3 is the real assertion. "The LoadError went away" proves nothing about recording.

### Probe result (honest)

I attempted to verify the V2 load shape empirically with a throwaway project
(`%TEMP%\v2probe`, registered through the `plugin` config array rather than `.opencode/`). The
attempt was **inconclusive**: `opencode api get /api/info` in that directory returned the existing
shared service (`pid 14212`), the new location never booted, and the probe marker never appeared in
`opencode.log`. So the load shape above rests on the official migration documentation, not on an
observed load. Treat section 2 as documented-contract, not runtime-verified.

---

## 7. Sequencing

These are three defects in one file, not three independent tasks — fix all three or the plugin
still does not load.

1. Apply the path fix (`file://` → `./`) — necessary for all three defects, sufficient for none.
2. Port `telemetry.ts` with the payload adaptations in section 3, and the section 6 test.
3. Leave `gsd-core.js` until the RPC surface has been read; it is not a rename.
4. Only then does framework telemetry begin to have data — until it does, `report.py` and
   `bg_poll_total` are measuring nothing.

**This workstream is independent of the session-interruption defect.** It is framework hygiene: the
enforcement telemetry has never recorded, so its counters have been reports about nothing. It does
not cause the stops and fixing it will not stop them. Do not sequence it ahead of containment.
