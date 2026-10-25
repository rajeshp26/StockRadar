# location: eviction of cached location services aborts in-flight executions

## Summary

Eviction of a cached location aborts the work running against it. `@opencode/LocationActivity`
disposes a location's cached services on a TTL and, in the same pass, calls
`interrupt(reason: "inactivity")` on every **active** execution at that location. A tool that is
still running is killed and marked `Tool execution interrupted`. Because the TUI treats
`Step interrupted` as a non-error, the user sees the agent stop mid-task with no explanation.

This is not a timeout-tuning request. A cache entry expiring should cause a re-fetch on next use;
it should not cancel the operations depending on it.

## Impact

- Any execution that runs longer than the location TTL (~60 min) is killed, even while tools are
  actively running and producing output.
- The kill is not attributable after the fact: the `reason` is not persisted, and the UI
  suppresses it. Neither the user nor the harness can distinguish "user cancelled" from
  "we interrupted you".
- Worst hit are long single tool calls — test suites, builds, backfills, migrations — which are
  exactly the operations least able to tolerate an abort mid-flight.

## Environment

- opencode version: 2.1.1
- OS: Windows_NT 10.0.26200 (win32 x64)
- Terminal: VS Code integrated terminal (`TERM_PROGRAM=vscode`, `COLORTERM=truecolor`)
- Shell: `C:\Windows\system32\cmd.exe`
- Install/channel: latest
- Active plugins: `file://framework/opencode/plugin/telemetry.ts`, `oh-my-openagent@latest`
  (both fail to load — reported separately, not relevant to this issue)

## Reproduction

1. Start a session and issue work that keeps one execution running for longer than the TTL —
   e.g. ask for a long test suite or a data backfill as a single tool call.
2. Do not end the turn.
3. At ~60 minutes the step is aborted.

Observed result: the assistant message carries `error.message === "Step interrupted"`, any
in-flight tool carries `Tool execution interrupted`, and the TUI renders nothing.

## Expected Behavior

Eviction of cached services must be semantically transparent to the work using them. At minimum:

- an execution with in-flight/unsettled tools is never interrupted by a resource-expiry timer, or
- the eviction waits for quiescence (or a grace deadline) before disposing, and
- the interruption, if it must happen, is attributed and visible.

## Actual Behavior

Location services register with an absolute expiry and a fixed 60-minute TTL:

```js
_ = _t(e.timeToLive ?? "60 minutes")
q = (N) => D(() => {
  h.set(F(N), { ref: N, expiresAt: a.currentTimeMillisUnsafe() + _ })
})
```

The sweeper runs every minute and interrupts every active execution at an expired location:

```js
let I = Array.from(h.values()).filter((C) => C.expiresAt <= P)
if (I.length === 0) return
let z = yield* Q(yield* l.active, (C) => A.get(C))
yield* Q(I, (C) => s(function* () {
  let Y = z.flatMap((W) => W && F(W.location) === F(C.ref) ? [W] : [])
  yield* Q(Y, (W) => l.interrupt(W.id, { reason: "inactivity", awaitSettlement: !0 }),
           { discard: !0, concurrency: "unbounded" })
  ...
  yield* Kn("location services evicted", { directory: C.ref.directory, ... })
}))
```

### Disposal by itself does not abort — the interrupt call does

This is verifiable in two minutes against a live server and it sharpens the diagnosis. Evicting a
location through the debug endpoint disposes its cached services and returns `204` with **no
interruption of any active step**:

```
$ opencode api get /api/debug/location
[{"directory":"/work/project"},{"directory":"/home/user"}]

$ opencode api delete /api/debug/location --data '{"location":{"directory":"/home/user"}}'
        (HTTP 204, nothing interrupted)

$ opencode api get /api/debug/location
[{"directory":"/work/project"}]
```

So losing cached services is already handled gracefully. The abort is caused by the explicit
`interrupt(…, {reason:"inactivity"})` that the sweeper issues **alongside** disposal — a separate
decision, not a necessary consequence. That is why the ranked fixes are small: the code already
knows how to dispose without killing work.

(Note: `location` is a request body, not a query parameter — `?location=…` fails with
`Expected object | undefined at ["location"]`. The endpoint lists directory names only; it does not
expose `expiresAt`.)

### Three properties make this a defect rather than a policy choice

**1. Eviction cancels work.** The cached-service lifetime is used as a cancellation trigger. In
`net/http` terms this is `Server.Close()` where `Server.Shutdown()` is required: stop admitting
new work, drain in-flight work under a deadline, then dispose.

**2. There is no quiescence gate and no reference counting.** `l.active` is non-empty while tools
are unsettled, and nothing checks it. The codebase already ships the correct primitive — `RcMap`
with `refCount` and `idleTimeToLive`, and `ScopedCache` with `timeToLive` — but LocationActivity
hand-rolls a plain `Map` whose entries are stamped once and never renewed.

**3. It is neither configurable nor attributable.** `"60 minutes"` occurs exactly once in the
binary; the layer is constructed as `kt({ service: kc, layer: KV(), deps: [...] })` with no
arguments; there is no `locationActivity` config key. The interrupt reason is not persisted, and
the TUI suppresses this specific message:

```js
w = i.message.error?.message === "Step interrupted"
// error box renders only when !w
```

### The expiry is never renewed during real work

The only refreshing listener requires a `location` field on a durable event:

```js
T = yield* i.listen((N) => {
  if (!HV(N)) return g
  let O = N.location
  if (!O) return g                      // never reached with a value
  return ahe(r.rcMap, O).pipe(m((P) => (P ? q(O) : g)))
})
```

The durable event payloads carry no `location`:

| type | top-level keys | has `location` |
|---|---|---|
| `message.part.updated.1` | `['part','sessionID','time']` | no |
| `message.updated.1` | `['info','sessionID']` | no |
| `session.updated.1` | `['info','sessionID']` | no |

So `expiresAt` is stamped at registration and never renewed, and the wall is a fixed 60 minutes
from registration regardless of activity. Note that an **absolute** TTL is defensible as a lease
policy; the defect is that expiry reaches through into in-flight work. Fixing the drain makes the
renewal question moot.

## Evidence

Measured across the last 4000 assistant messages in the reporter's `session_message` table:

- 36 aborted steps; **28 ran >= 660 s**
- dense cluster at **3636-3879 s** (median 3685 s) — 3600 s plus sweep granularity and the offset
  between step start and location registration
- in-flight tools at interrupt time carry `Tool execution interrupted` and **never** a timeout
  message, even where the tool's own timeout was 60 s — an external kill, not a tool timeout

Store-wide: 45 `Step interrupted`, 38 `Tool execution interrupted`.

## Suggested fixes (ranked, smallest first)

1. **Do not interrupt while work is unsettled.** Gate the eviction on `l.active` being empty (or
   on in-flight tool count being zero); defer to a later sweep. Smallest change, removes the
   entire failure class.
2. **Drain instead of abort.** Mark the location evicting, stop admitting new executions, wait
   for in-flight work under a bounded grace period, then dispose. Mirrors `Server.Shutdown`.
3. **Evict by reference count.** Use the existing `RcMap` (`refCount` + `idleTimeToLive`) so
   disposal is structurally impossible while a reference is held.
4. **Make the timer honest.** Refresh `expiresAt` on tool `execute.before`/`execute.after` or on
   message parts, or advance it unconditionally while `l.active` is non-empty.
5. **Make failure visible and attributable.** Persist the interrupt `reason` on the step; render
   `Step interrupted` in the TUI instead of suppressing it; expose `timeToLive` /
   `sweepInterval` as configuration.

1 and 5 are independent and cheap. 1 alone removes the user-visible symptom.

## Verification

The binary exposes the machinery for direct inspection:

- `GET /api/debug/location` — "List loaded locations"
- `DELETE /api/debug/location?location=...` — "Evict a loaded location. Dispose the requested
  location's cached services so its next use boots them fresh"

Reading it requires no token recovery — the CLI authenticates for you:

```
opencode api get /api/debug/location
```

To confirm the TTL and the interrupt-on-evict relationship:

1. `opencode api get /api/debug/location` — list loaded locations (directory names only).
2. Start an execution with a long tool running on the same server, then evict that location with
   `opencode api delete /api/debug/location --data '{"location":{"directory":"…"}}'` and observe
   whether the step is aborted.

Step 2 is the decisive test of the invariant: it is fast, needs no 60-minute wait, and does not
depend on the sweep timer. Note that step 2 requires the in-flight tool to be on the **same**
server being evicted from — evicting a server with no sessions proves nothing.

## Workaround

Keep single foreground tool calls short, chunk long work, and `continue` after a stop — eviction
re-registers the location, starting a fresh window. This is containment, not a cure.

## Non-goals

This report is not a request for a longer timeout. A 90-minute backfill would fail identically at
90 minutes under the current design.
