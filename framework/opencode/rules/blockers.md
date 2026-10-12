# Blocker escalation

A non-complete stop must land as a visible record, not vanish into a quiet agent's context.

## Stopping rule

An agent that stops without completing its task writes a blocker record FIRST, then stops.
Stopping without a record is a framework violation, not a style preference.

Signals come from the escalation routes in `framework/retry_policy.yaml`: CONTEXT_INSUFFICIENT,
BLOCKED, UNKNOWN_IMPACT, TEST_FAILED, REVIEW_REJECTED, INTEGRATION_FAILED,
CONTRACT_CONFLICT, ARCHITECTURE_CONFLICT, SECURITY_FAILURE, PERFORMANCE_FAILURE,
RELEASE_BLOCKED, RETRO_RECURRENCE, RETRO_INCOMPLETE.

## Writing a blocker

    python3 framework/adapters/gsd_state.py write-blocker --json '{"signal": "CONTEXT_INSUFFICIENT", "task_id": "03-02", "agent": "implementer", "missing_item": "...", "tried": "..."}'

| Field | Meaning |
|---|---|
| signal | retry_policy.yaml route name |
| task_id | current task |
| agent | writing agent |
| missing_item | the specific thing absent - never just "context" |
| tried | what was attempted first |

Upsert semantics: repeating `(task_id, signal)` raises `retries` to max(existing, incoming),
so the retry count survives agent restarts. IDs are `BLK-nnn`.

## Resolving

    python3 framework/adapters/gsd_state.py resolve-blocker --id BLK-nnn

Unknown ids fail loudly (`NOT_FOUND`). Never hand-edit `<state_root>/blockers.yaml`.

## Enforcement

G8 fails completion while any open blocker exists. An unreadable store reports exit 2
(blocked) - it never reads as zero open blockers.
