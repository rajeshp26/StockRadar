# Background task contract

Background tasks use a pub/sub contract, not polling. The only correct flow:

## Correct flow (MANDATORY)

1. `task(run_in_background=true, ...)` returns `bg_xxx` ID
2. **END YOUR RESPONSE.** Do not continue.
3. System sends `<system-reminder>` when task completes.
4. `background_output(task_id="bg_xxx")` collects the result.

## What is a poll (VIOLATION)

A poll is any `background_output` call on a `bg_xxx` task BEFORE the system-reminder:

* `background_output(task_id="bg_xxx", timeout=30000)` - polls with timeout
* `background_output(task_id="bg_xxx", block=true)` - polls with blocking
* Any `background_output` call while `output.status` reports "running" or "pending"

A poll is a framework violation. It wastes tokens and violates the async contract.

## What is a collect (LEGAL)

A collect is `background_output(task_id="bg_xxx")` called AFTER the system-reminder,
where the task output reports completion. This is the only legal use.

## Enforcement

* Telemetry records `bg_poll_total` per session.
* `validate.py` verifies the telemetry record after the session.
* Sessions with `bg_poll_total > 0` are flagged as violating the contract.
* Polling is made loud: the telemetry plugin appends a `POLL_VIOLATION` marker to the
  output of a polled call, so the violating call is visible to the model that made it.
* A session whose last record is `started`/`heartbeat` but never `final` is unfinalized
  (it died before SESSION_FINALIZED); `report.py` exits 1 and names the session.

## Recursive subagents

Subagents spawned via `task()` cannot run `background_output` themselves (they have no
access to parent tasks). If a subagent needs to wait on another subagent, the parent
agent must orchestrate that wait, not the subagent. This is a design constraint of the
pub/sub model.

## Timeout safety valve

`background_output` has a `timeout` parameter for the blocking collect path. Use it
ONLY after receiving the system-reminder when the notification was missed or the
session was interrupted. Never use timeout as a polling mechanism.

## Supervision

The pub/sub contract covers collection; it does not cover liveness. A background task with
no lifecycle events is SPAWNED regardless of what its session label claims, and a session
label is not progress.

Supervision is executable state: register the task, watch its lifecycle events, probe with
status. See `framework/opencode/rules/delegation-protocol.md` for the full protocol; the commands
are `task-register`, `task-event`, `task-status`, `task-list`, `task-cancel` on
`framework/adapters/gsd_state.py`.
