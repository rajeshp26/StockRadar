# Delegated Task Execution Protocol

A delegation is executable state, not conversation. Every supervised `task(...)` is
registered in `<state_root>/tasks/` as an immutable contract plus an append-only lifecycle
event stream, and health is derived from that stream against the contract deadlines.
`session_info` is not progress: a session can exist while its worker is silent.

## Contract

`task-register --id T-01 --json '{...}'` creates `<state_root>/tasks/T-01.json`. Contracts
are immutable: a second register for the same id fails with EXISTS, and the suggested fix
is a fresh id carrying `retry_of: T-01`. Required fields:

| Field | Meaning |
| --- | --- |
| `agent` | worker agent type (explore, research, implement, ...) |
| `objective` | one goal, stated as a deliverable |
| `expected_artifact` | what "done" looks like - file, command result, report |

Recommended fields: `type` (task type), `session_id` (the `ses_...` continuation id),
`background_task_id` (the `bg_xxx` id from `task(run_in_background=true, ...)`),
`checkpoints`, `allowed_tools`, `completion_criteria`, `failure_criteria`,
`progress_timeout_s`, `max_duration_s`, `retry_of`, `headless` (contract flag:
background/supervised tasks must not hit interactive asks; see
"Headless-interaction firewall").

Time budgets come from `framework/tasks/task_types.yaml` (type entry over `defaults`),
overridable per contract. A type that declares `null` (verify) requires the contract to
name the budget - it is never inherited from defaults.

## Checkpoints

Lifecycle checkpoints use the shared C0-C8 vocabulary declared in
`framework/tasks/task_types.yaml` (`checkpoint_vocabulary`):

| Checkpoint | Meaning |
| --- | --- |
| C0-TASK_ACCEPTED | worker accepted the contract and objective |
| C1-CONTEXT_READ | plan, requirements, contracts and tests read |
| C2-PLAN_CONFIRMED | plan confirmed against the contract before work |
| C3-IMPLEMENTATION_STARTED | first change landed |
| C4-IMPLEMENTATION_COMPLETE | implementation done, tests not yet green |
| C5-TESTS_GREEN | applicable tests pass |
| C6-REVIEW_READY | work ready for review |
| C7-VERIFICATION_DONE | verification evidence recorded |
| C8-HANDOFF_READY | handoff written, task complete |

Each task type declares a default checkpoint progression in `task_types.yaml`; a contract
that names its own `checkpoints` overrides the type default. Events may carry any
checkpoint string, but the vocabulary is what the protocol documents and what
`task-status` surfaces as `checkpoints_reached`.

## Background task identity

`task-register` accepts `background_task_id` (the `bg_xxx` id returned by
`task(run_in_background=true, ...)`) and `task-status` surfaces it. Capture it at register
time: the bg id is the durable mapping between the supervised contract and the runtime
background task, and it is lost if it lives only in conversation.

## Lifecycle

Events are appended to `<state_root>/tasks/T-01.events.jsonl` by `task-event`:

```
SPAWNED (implicit on register)
  -> ACK         worker acknowledged the contract
  -> STARTED     worker began work
  -> PROGRESS    named checkpoint reached (or routine heartbeat)
  -> BLOCKED     worker stopped on a resolvable obstacle; carries a detail
  -> COMPLETED   worker claims the deliverable
  -> FAILED     worker is giving up; REQUIRES failure_class (else TASK_INVALID_FAILURE_CLASS)
  -> LOST       supervisor declares the worker session lost, no failure recorded; REQUIRES a non-empty detail
CANCELLED        supervisor terminates the task (task-cancel)
```

Terminal states are final: no event is accepted after COMPLETED, FAILED, LOST or CANCELLED.
LOST is supervisor-declared only: task-event refuses a worker-emitted LOST and a LOST
without detail.
Transitions are enforced - anything outside the legal next states is INVALID_TRANSITION
and the error names the legal next states. The `emitter` field records who wrote each
event: the worker by default, the supervisor when it writes on the worker's behalf.

### Failure classification

`FAILED` is a routing decision, not a confession. The `failure_class` field is REQUIRED on
every FAILED event; a FAILED without it is refused (TASK_INVALID_FAILURE_CLASS) and the task
stays in its prior state. The class comes from the closed taxonomy in
`framework/providers/healthcheck.py` (`ALL_CLASSES`); a value outside it is refused.

The class decides where recovery goes:

| class | route |
| --- | --- |
| AUTH_FAILURE, QUOTA_FAILURE, MODEL_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_NETWORK_FAILURE | **provider route**: run g12 provider pre-flight (`framework/gates/g12_provider.sh`), record provider health, dispatch via a fallback provider - no dispatch to this provider (BLOCKED - ENVIRONMENT) |
| AGENT_FAILURE, SUSPECTED_STALL | **worker route**: `record_blocker` WORKER_STALLED, retry once narrower, then take over |

Worker-level classes are never provider failures and provider classes are never worker
stalls - misclassifying one as the other is the defect this protocol exists to prevent.

## Health

`task-status` derives health from the last event timestamp against the contract deadlines:

| Health | Level | Condition | Recovery action |
| --- | --- | --- | --- |
| HEALTHY | 0 | silent_s < progress_timeout_s | continue |
| WARNING | 1 | silent_s >= progress_timeout_s | query_worker: ask for current checkpoint and blockers |
| STALLED | 2 | silent_s >= 2 * progress_timeout_s | inspect_session: read the session state; cancel only if frozen |
| OVERDUE | 3 | elapsed_s >= max_duration_s | cancel_and_retry: cancel the bg task, retry with a narrowed prompt |
| FAILED | 4 | worker event FAILED (failure_class REQUIRED) | blocking class -> g12 pre-flight, fallback provider, no dispatch to this provider; worker class -> record_blocker WORKER_STALLED, retry once narrower, then take over |
| LOST | 4 | state LOST (supervisor-declared, no failure recorded) | re-dispatch a fresh attempt on a narrowed contract; never a failure class (recovery_policy route `LOST`) |
| COMPLETE | 0 | state COMPLETED | accept only after checking the deliverable |
| CANCELLED | 0 | supervisor cancel | never quietly forgotten |

A stale-looking task is inspected with `task-status`, never re-invoked blindly - probing
is the WARNING action, not the STALLED one.

The per-type recovery routes (defaults plus type overrides) are declared in
`framework/tasks/task_types.yaml` (`recovery` blocks) and surfaced as
`recovery_policy` by `task-status` and by `task-summary` for every unhealthy task -
the supervisor acts on the declared policy, never on an invented one.

## Rules

- Register before you delegate. A task that is never registered cannot be supervised.
- The supervisor (team-lead) owns the contract; only it may cancel.
- A silent worker is a blocker with signal WORKER_STALLED (count `worker_stalled: 1` in
  `framework/retry_policy.yaml`) - a stall that lives only in conversation repeats.
- Accept nothing without `task-status` health COMPLETE and your own check of the
  deliverable (read the diff or output, run the gate, record the exit code).
- Never blanket-cancel a stalled worker's siblings - queued tasks are innocent.
- A FAILED event without `failure_class` is refused; a blocking provider class routes to
  the g12 pre-flight, never to WORKER_STALLED (see "Failure classification").
- A LOST event is supervisor-declared only: a worker cannot self-declare LOST, and a LOST
  without a non-empty detail is refused. LOST is not a failure class and never routes
  through the failure ladder (see "Failure classification").
- Headless-interaction firewall: a contract flagged `headless: true` - and every
  background/supervised task - must not issue interactive asks (permission prompts,
  clarifying questions, human gates). If a headless task needs a decision it emits
  BLOCKED with a detail naming the decision. g10 asserts the permission-policy
  structure, but a gate cannot drive opencode's interactive ask/allow engine, so the
  firewall is a contract-level declaration enforced at the point of delegation
  (team-lead), not by a gate.
- Supervisor survival: losing the supervisor (crash, cancel, ended session) never
  cascades to a worker. Contracts and events are durable rows on disk; a task
  continues against its contract and a successor supervisor reconciles via
  task-status. Supervisor loss is a supervision gap to repair, never a worker
  failure to record.

## Cross-references

- `framework/opencode/rules/background-tasks.md` - the pub/sub contract; supervision is its
  enforcement half
- `framework/adapters/gsd_state.py` - the `task-*` commands
- `framework/retry_policy.yaml` - the `worker_stalled` count and `WORKER_STALLED` route
- `framework/telemetry/report.py` and `<state_root>/telemetry/records.jsonl` - the
  supervision counters