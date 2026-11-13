# OpenCode session interruption — root cause analysis

**Status:** root cause identified; two upstream defects, three configuration defects. Causation is
**partially** behaviourally confirmed — disposal was proven not to abort work (`CLM-OPENCODE-A-002`,
FACT/VERIFIED), while the sweep itself remains unobserved (§7)
**Date:** 2026-10-22
**Runtime:** `@opencode/cli` 2.1.1
**Method:** read-only inspection of the installed binary (218 MB, byte-offset citations), the
session store `opencode.db` (SQLite), OpenCode's own `opencode.log`, and live `opencode api` calls
against the running server. No repository code was modified. Probe scripts ran from a temp
directory.

---

## 1. Decision summary

| # | Claim | Action | Owner |
|---|---|---|---|
| A | Location-services eviction **aborts in-flight executions** — and disposal itself does not, so the interrupt call is the cause | fix upstream: drain, don't abort | OpenCode maintainers |
| B | Model emits tool calls as prose, turn ends silently | no repository lever; mitigate via session size | none available |
| C | Legitimate text-only turn endings | **do nothing** — correct behaviour | — |
| D | Telemetry plugin never loads — three defects: UNC path, V1 export shape, no `$` in V2 | apply path fix **and** port, per `OPENCODE_PLUGIN_V2_MIGRATION.md` | human (plane is agent-immutable) |
| E | `gsd-core.js` / `oh-my-openagent` rejected by V2 plugin API | `server` surface has no V2 row — redesign via RPC, not a rename | human |
| F | `compaction.prune` acceptance | **unknown — do not change** | — |

The user-visible symptom ("it stops and I have to type `continue`") is produced by **A**, and
secondarily by **B**.

---

## 2. Claim ledger

Claim classes and verification levels follow this repository's own standard
(`framework/opencode/rules/evidence-provenance.md`).

| Claim | Class | Level | Verified | Does not prove |
|---|---|---|---|---|
| `session.execution.interrupted` reason enum is `user/shutdown/superseded/inactivity` | FACT | L1 | yes | that any specific abort used a given reason |
| Interrupt fails the step as `Step interrupted` and unsettled tools as `Tool execution interrupted` | FACT | L1 | yes | which aborts in the store were interrupts vs. other failures |
| `inactivity` is emitted only by the `LocationActivity` sweeper | FACT | L1 | yes | that the sweeper ran on this machine |
| The sweeper interrupts every **active** execution at an expired location | FACT | L1 | yes | that eviction occurred during any observed abort |
| TTL default is `"60 minutes"`, sole occurrence in the binary, no config key | FACT | L1 | yes | that 60 min is the effective value if a layer override exists at runtime |
| Durable event payloads contain no `location`, so the refresh listener returns early | FACT | L1 | yes | that no other refresh path exists in a different bundle |
| Aborted steps cluster at ~3600 s (28/36 ≥ 660 s; median 3685 s) | FACT | L1 (data) | yes | that the cluster's cause is eviction |
| **Disposal alone does not abort work** (`DELETE /api/debug/location` → 204, nothing interrupted) | **FACT** | **L3 (live)** | **yes** | that the sweeper's interrupt call is what terminates steps |
| Eviction caused the observed aborts | **HYPOTHESIS** | — | **no** | — |
| Tool calls emitted as prose end turns silently | FACT | L1 (data) | yes | that compaction causes it (HYPOTHESIS) |
| `telemetry.ts` resolves to `\\framework\...` on Windows | FACT | L1 (log) | yes | that fixing the path alone makes it load |
| V2 plugin API has no `$` equivalent (`ctx.shell` only hooks, never executes) | **FACT** | L1 (docs) | **yes** | that `import { $ } from "bun"` resolves inside OpenCode 2.1.1 |
| `compaction.prune` is rejected | **UNKNOWN** | — | **no** | — |

---

## 3. The architectural model

The defect is best described by separating three clocks that the current design collapses into
one:

| Clock | Question | Correct expiry behaviour |
|---|---|---|
| Resource TTL | is this cached handle stale? | dispose the handle; work continues; next use re-creates |
| Liveness / progress | is the work advancing? | report, restart, or hand off |
| Work completion | is the task done? | finish, checkpoint, or fail |

`LocationActivity` uses **clock 1 to cancel clock 3**. Everything below follows from that.

The invariants a mature system upholds, and the state of this code:

| Invariant | Professional anchor | Here |
|---|---|---|
| Cache eviction is semantically transparent | Redis `maxmemory` evicts keys, never clients | **violated** — eviction aborts work |
| Eviction drains before disposal | Go `Server.Shutdown` vs `Close`; k8s grace period + PDB | **violated** — immediate `interrupt` |
| Dispose only at `refCount == 0` | `RcMap` (`refCount`, `idleTimeToLive`) — shipped in this binary | **violated** — plain `Map`, no refcount |
| Leases renewed by the holder | Temporal `heartbeatTimeout`; k8s `Lease` | **violated** — stamped once, never renewed |
| Cancellation is attributable | structured concurrency: reason propagates and surfaces | **violated** — reason unpersisted, UI suppresses |
| Activity gates eviction | Chrome tab discard skips audio/downloads/capture | **violated** — no activity gate |

The sharpest statement of the bug is therefore not "the timeout is too short" but:

> A resource-cache eviction is used as a cancellation mechanism, and it reaches through to
> in-flight work with no quiescence gate.

That ordering matters. My earlier draft led with "the TTL is never refreshed", which reads as a
tuning request and invites a `wontfix`. Corrected here: **the missing drain is the defect; the
absolute TTL is a design smell that becomes harmless once the drain exists.**

---

## 4. Finding A — eviction interrupts in-flight executions

### 4.1 Mechanism

```js
_ = _t(e.timeToLive ?? "60 minutes")
q = (N) => D(() => { h.set(F(N), { ref: N, expiresAt: a.currentTimeMillisUnsafe() + _ }) })
```

```js
let I = Array.from(h.values()).filter((C) => C.expiresAt <= P)
if (I.length === 0) return
let z = yield* Q(yield* l.active, (C) => A.get(C))
yield* Q(I, (C) => s(function* () {
  let Y = z.flatMap((W) => W && F(W.location) === F(C.ref) ? [W] : [])
  yield* Q(Y, (W) => l.interrupt(W.id, { reason: "inactivity", awaitSettlement: !0 }),
           { discard: !0, concurrency: "unbounded" })
}))
```

Sweep interval `sweepInterval ?? "1 minute"`. `l.active` selects **active** executions, so this
is not an idle timeout.

On interrupt: `failAssistant({ type:"aborted", message:"Step interrupted" })` and every unsettled
tool becomes `{ type:"aborted", message:"Tool execution interrupted" }`.

### 4.1b Disposal alone does not abort — proven

This matters for reading the code correctly. `DELETE /api/debug/location` disposes a location's
cached services. Executed against a live location it returned **HTTP 204 and interrupted nothing**;
the location disappeared from the loaded set and the calling session kept running
(`CLM-OPENCODE-A-002`, FACT/VERIFIED).

So the abort is **not** an emergent consequence of tearing down cached services. It comes from the
explicit `l.interrupt(…, {reason:"inactivity"})` sitting on the line immediately after disposal.
That distinction is the whole argument of the upstream report: the machinery already tolerates
disposal without aborting, so a drain (or simply skipping the interrupt while `l.active` is
non-empty) is a local, low-risk change rather than a redesign.

### 4.2 Not configurable

| Probe | Result |
|---|---|
| `"60 minutes"` in the 218 MB binary | **1** occurrence |
| `locationActivity` config key | **0** occurrences |
| Construction | `kt({ service: kc, layer: KV(), deps: [...] })` — no arguments |

### 4.3 Never renewed

The refresh listener requires `N.location` on a durable event; the durable payloads
(`['part','sessionID','time']`, `['info','sessionID']`, `['info','sessionID']`) have no
`location`. `expiresAt` is therefore stamped once at registration.

### 4.4 Measurement

Reproducible by command — this is the regression signal, not a one-off query:

```
python framework/tools/diagnose_opencode_step_interruptions.py
```

Exit `0` = no interruption at the wall (fix effective); `1` = still present; `2` = unverifiable
(never a pass). Current reading:

```
scanned 4000 assistant messages
'Step interrupted' events: 41
  at the eviction wall [3600s, 3960s]: 19
  below the wall (user/superseded-class): 22
RESULT: FAIL - steps are still being interrupted at the ~60 minute wall
```

The wall hits run 60.4-63.8 min (median ~61.3), tail to 7522 s; below-wall aborts are spread at
25 s-15 min and are consistent with `user`/`superseded`. In-flight tools show
`Tool execution interrupted`, never a timeout message, including cases where the tool's own
timeout was 60 s — an external kill.

Counts drift as the store grows (an earlier reading of the same query gave 36 aborts, 28 ≥ 660 s,
cluster 3636-3879 s); the ratio, not the absolute number, is the signal.

Short aborts (25/58/85/195/268/506/818 s) are consistent with `user`/`superseded` instead.

### 4.5 Not visible

```js
w = i.message.error?.message === "Step interrupted"
// error box only when !w
```

---

## 5. Finding B — tool call emitted as prose

Turn ends `finish = "stop"`; content is a single `text` part containing the call as markup:

```
<parameter name="write">
<|DSML|parameter name="path">...
```

Counts: 19 such turns in `ses_ea9081bb…` (762 messages), 12 in `ses_eb327d8e…` (1016 tool calls).

The harness only validates calls that parsed (`tool.input-json`, `tool.input-incomplete`); a fully
prose-ified call is never parsed, so nothing flags it.

Association with auto-compaction summaries containing **escaped** tool markup
(`<parameter name=\"write\">`) is a **HYPOTHESIS** (adjacency, not a controlled replay).

## 6. Finding C — not a defect

18 turns ended `finish = "stop"` with text only and no attempted call. Correct end-of-turn
behaviour; must not be changed.

---

## 7. Verification status

The binary exposes:

- `GET /api/debug/location` — "List loaded locations"
- `DELETE /api/debug/location?location=…` — "Evict a loaded location. Dispose the requested
  location's cached services so its next use boots them fresh"

**Reached through the CLI's own auth flow.** An earlier revision of this document reported the
debug endpoint as blocked by `HTTP 401 {"_tag":"UnauthorizedError","message":"Authentication required"}`
and concluded the TTL could not be inspected. That was half right and half wrong.

`opencode api` "uses the same discovery and authentication flow as the TUI", so no token needs to
be recovered at all:

```
$ opencode api get /api/debug/location
[{"directory":"C:\\Project\\StockerPro\\StockerPro"},{"directory":"C:\\Users\\rajes"}]
```

What this establishes, and what it does not:

| Question | Answer |
|---|---|
| Can loaded locations be listed? | **yes** — directory names only |
| Does it expose `expiresAt` / TTL? | **no** — an earlier draft wrongly predicted it would |
| Does disposal interrupt active work? | **no** — see A-002 |
| Did the sweeper fire during an observed abort? | **still unobserved** |

The decisive experiment is therefore half-done: `DELETE /api/debug/location` was executed against a
live location and interrupted nothing, which isolates causation to the sweeper's explicit
`interrupt` call rather than to disposal itself. What remains unobserved is the sweep reaching
expiry, because that requires either a 60-minute wait or a location with an in-flight tool on the
same server — and the reporter's work runs on the shared service, not on a server with a chosen
password.

So A-001 stays `HYPOTHESIS`/`PARTIALLY_VERIFIED`: not for lack of a token (solved), but because the
sweep itself was never observed executing.

Reproduction for a maintainer:

1. `opencode api get /api/debug/location` — list loaded locations (directory names only; there is
   no `expiresAt` field, so the TTL cannot be read from here);
2. run a long tool **on the same server**, then
   `opencode api delete /api/debug/location --data '{"location":{"directory":"…"}}'` mid-tool and
   observe whether the step aborts;
3. to observe the sweep itself, leave a location idle past the TTL and watch for
   `location services evicted` at `OPENCODE_LOG_LEVEL=DEBUG` — note that this literal was not found
   in 36 days of INFO-level logs, and its absence is not evidence either way (§9).

---

## 8. Configuration defects (verified)

All three sit inside the agent-immutable enforcement plane, so they are **prepared, not applied**.

### 8.1 Telemetry plugin — verified never loaded

```
level=WARN message="failed to load plugin" target="\\framework\opencode\plugin\telemetry.ts"
  cause="EUNKNOWN: unknown error, stat '\\framework\opencode\plugin\telemetry.ts'"
level=ERROR message="configured plugin watch failed" target="\\framework\opencode\plugin\telemetry.ts"
```

`opencode.json:489-491` registers `"file://framework/opencode/plugin/telemetry.ts"`. A `file://`
URL with a relative path parses as host `framework`, which Windows turns into
`\\framework\opencode\plugin\telemetry.ts`.

**Two-part fix.** Path alone is insufficient: the 2.x loader requires a default export with `id`
plus `effect` or `setup`, while `framework/opencode/plugin/telemetry.ts:31` is
`export const TelemetryPlugin: Plugin = async ({ $ }) => {` and `:547` is
`export default TelemetryPlugin` — the V1 shape. With the path fixed, the error becomes the same
`PluginModule.LoadError` as §8.2.

```diff
   "plugin": [
-    "file://framework/opencode/plugin/telemetry.ts"
+    "./framework/opencode/plugin/telemetry.ts"
   ],
```

Consequence of doing nothing: framework telemetry has never recorded, so `report.py` and
`bg_poll_total` checks have had no data.

### 8.2 V1 → V2 plugin API — verified

```
target="C:\Project\StockerPro\StockerPro\.opencode\plugins\gsd-core.js"
cause="PluginModule.LoadError: Plugin must export a default definition with an id and an effect
        or setup function. (cause: SchemaError(Missing key at ["default"]["effect"] …))"
```

`gsd-core.js:775-782` exports `{ server: GsdCorePlugin, id: "gsd-core" }` (non-enumerable `id`).
Same error for `oh-my-openagent@latest`.

**Do not delete the plugin entries to silence the warnings** — that removes the enforcement
telemetry the framework depends on.

There are **three** independent defects, not two, and fixing any one alone still leaves the plugin
unloaded:

| # | Defect | Fix |
|---|---|---|
| 1 | `file://` + relative path parses as UNC host `framework` | `"file://framework/…"` → `"./framework/…"` |
| 2 | V1 export shape rejected by the 2.x loader | `Plugin.define({ id, setup })` |
| 3 | **`$` has no V2 equivalent** | `import { $ } from "bun"` |

Defect 3 is the one that makes this a real port rather than a rename. The v2.1.2 migration guide
maps *"`$` Bun shell helper → import and manage the process API your plugin uses"*, and the V2
`ctx.shell` domain exposes only `hook("create.before", …)` — it observes and mutates a command, it
does not execute one. Since `telemetry.ts` routes every record through `$`
(`write-telemetry`, `intake.py`, `healthcheck.py`), the port must self-import a process API.

Full design, per-hook payload deltas, and the registration test:
`framework/docs/OPENCODE_PLUGIN_V2_MIGRATION.md`.

Port `telemetry.ts` and `gsd-core.js` as a separate task with a test that asserts a record is
**written**, not merely that the `LoadError` disappeared. `gsd-core.js` is larger still: the V1→V2
table has no row for a `server` extension point, so it needs the RPC surface and is a redesign,
not a migration.

### 8.3 `compaction.prune` — unknown

No `Unrecognized key` line exists in 36 days of logs, and the config schema resolves through
minified names that are shadowed per bundle (confirmed: `zj` resolves to the Plan agent in one
region and to the compaction schema in another). **Status unknown; no change recommended.**

### 8.4 Startup latency

MCP servers (`memory`, `context7`, `playwright`, `gsd`) time out for ~55 s before connecting;
`models.dev` times out at 10 s; `opencode.ai` returns `ENOTFOUND`. Every session pays it. Not
related to the stops; tracked separately.

---

## 9. Corrections to this analysis

Recorded deliberately, because both were plausible and both were wrong:

1. **"The log proves the sweeper never fired."** Not supportable. The sweeper's
   `Kn("location services evicted", …)` is absent from 36 days of logs, but the same is true of a
   sibling literal from the same string table (`"failed to refresh skill"`), and minified
   identifiers are shadowed across bundles, so the sweeper's `Kn` cannot be shown to be the
   file-sink logger. **Absence is inconclusive in both directions.** This is why §4.1 is L1.
2. **"`compaction.prune` is unsupported."** Could not be verified; downgraded to UNKNOWN.
3. **Priority inversion.** The first draft led with the un-refreshed TTL. The dominant defect is
   the missing drain. A fix that only extends or renews the TTL leaves a 90-minute job to die at
   90 minutes.

---

## 10. Recommended sequence

Ranked by what actually changes the user-visible symptom, not by what is most thorough.

**Required — the lever available locally:**

1. **Run the lease-refresh watchdog (works now).** `python framework/tools/opencode_ttl_refresh.py --once` to
   test; run in background with the default 45-minute interval to keep the lease fresh. **Evidence:**
   evicting a location mid-tool did not abort the running tool and an actively-used location
   re-registered immediately (v2.1.4). Use the real CLI — the `opencode.EXE` shim on PATH is
   v1.3.14 and lacks the `api` subcommand. Eviction forces re-registration; resetting the absolute
   `expiresAt` is inferred (not exposed by the debug API). If you prefer to chunk long steps, that
   also works, but is a workaround; the watchdog is an automation of the re-registration that
   `continue` already does.

**Optional — the only route to a permanent fix, but not a prerequisite for working:**

2. File the upstream issue (`OPENCODE_ISSUE_DRAFT_60MIN_INACTIVITY_INTERRUPT.md`) when convenient.
   It does not fix anything on this machine; it creates the possibility of a fix. No tooling is
   needed — paste the body into the repository's new-issue page. **Verify the repository identity
   first:** `anomalyco/opencode` was derived from the installed package's `repository.url`, which
   can lag or point at a fork.

**Separate workstream — do not bundle with the above:**

3. Port `telemetry.ts` / `gsd-core.js` to V2 per `framework/docs/OPENCODE_PLUGIN_V2_MIGRATION.md`. Three
   defects must be fixed together, and the test must assert a record is *written*. This is
   framework hygiene with no bearing on session interruption.
4. Re-measure: `python framework/tools/diagnose_opencode_step_interruptions.py` is the regression signal
   (exit `1` today). If upstream lands a drain fix, the ~3600 s cluster must disappear.

---

## 11. Claim ledger and gate evidence

The three findings are recorded in the repository claim ledger, not only in prose:

| Claim | Type | Classification | Status | Impact |
|---|---|---|---|---|
| `CLM-OPENCODE-A-001` — eviction aborts in-flight work | causal | HYPOTHESIS | PARTIALLY_VERIFIED | high |
| `CLM-OPENCODE-A-002` — disposal alone does NOT abort | behavioral | **FACT** | **VERIFIED** | high |
| `CLM-OPENCODE-A-003` — mid-tool eviction safe; busy location re-registers | behavioral | **FACT** | **VERIFIED** | high |
| `CLM-OPENCODE-B-001` — tool call emitted as prose | behavioral | HYPOTHESIS | PARTIALLY_VERIFIED | medium |
| `CLM-OPENCODE-C-001` — "log absence proves no sweep" | environment | HYPOTHESIS | **REFUTED** | medium |
| `CLM-OPENCODE-D-001` — V2 has no `$` helper | environment | **FACT** | **VERIFIED** | medium |

Gate evidence, run in this workspace:

```
$ python framework/claims/ledger.py analyse
{"status": "ok", "entries": 99, "claims": 96, "invalid": []}

$ bash framework/gates/g11_evidence.sh
[g11_evidence] PASS  claim ledger valid: 96 claim(s), provenance present
[gate] g11 result=pass exit=0 ms=322
```

### Correction: `VERIFIED` is reachable, and A-002 reached it

An earlier revision of this document claimed `VERIFIED` was structurally unreachable because
`ledger.py:244` reads `<state_root>/contexts/execution.jsonl`, which has no producer. That was
**wrong**, and the error was in reading the rule as requiring an `RT-` id in every case. It does
not:

```python
# framework/claims/ledger.py:472-479
# 2b. Runtime-scope integrity: an evidence runtime that names a canonical RT- id
# must resolve to a recorded execution context. A free-form runtime (legacy, e.g.
# 'local-wsl') stays legal - it names a runtime without claiming a binding.
if isinstance(rt, str) and re.match(r"^RT-\d+$", rt) and not _runtime_recorded(rt):
```

Only ids matching `^RT-\d+$` must resolve. A free-form runtime string is explicitly legal, so
`_has_provenance` is satisfiable without any execution-context registry. `CLM-OPENCODE-A-002` was
recorded as `FACT`/`VERIFIED` with runtime
`"opencode-cli-2.1.1 win32-x64, live server pid 14212 at 127.0.0.1:45278"` and passed every rule,
including the scope limit and the high-impact `independent_check`.

What remains true from the earlier reasoning: `FACT` still requires `VERIFIED`, so the two claims
that are genuinely inference-bound (A-001 causal, B-001 behavioral) correctly stay
`HYPOTHESIS`/`PARTIALLY_VERIFIED`. They are not under-claimed for lack of a registry — they are
under-claimed because the evidence does not reach the standard.

The `contexts/execution.jsonl` gap is real but has a narrower consequence than stated: it blocks
*canonical binding* of a claim to a specific provider/model execution context. It does not block
verification.

### How A-002 was established (the decisive discriminator)

The debug endpoint is reachable through the CLI's own auth flow — `opencode api` "uses the same
discovery and authentication flow as the TUI", so the missing token never mattered:

```
$ opencode api get /api/debug/location
[{"directory":"C:\\Project\\StockerPro\\StockerPro"},{"directory":"C:\\Users\\rajes"}]

$ opencode api delete /api/debug/location --data '{"location":{"directory":"C:\\Users\\rajes"}}'
        (HTTP 204, no interruption)

$ opencode api get /api/debug/location
[{"directory":"C:\\Project\\StockerPro\\StockerPro"}]
```

Disposal removed the location and interrupted nothing. Two consequences:

1. **The abort is not emergent from disposal.** It must come from the explicit
   `interrupt(id, {reason:"inactivity"})` the sweeper issues alongside it. That is a design choice
   layered on top of disposal, which is precisely why fix #1 and #2 in the upstream report are
   viable — the machinery already tolerates disposal without aborting.
2. **`GET /api/debug/location` exposes only directory names, not `expiresAt`.** An earlier draft
   planned to read the TTL from this endpoint; it cannot. The TTL evidence remains code-level plus
   the duration cluster.

Note `?location=…` as a flat query string fails with
`Expected object | undefined at ["location"]`; the parameter is a request body
(`{"location":{"directory":…}}`), not a query parameter.
