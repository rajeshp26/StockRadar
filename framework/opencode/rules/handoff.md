# Handoff shape

Write via `framework/adapters/gsd_state.py write-summary`. Never pass reasoning transcripts.

```yaml
task_id: 03-02
agent: implementer
summary: <= 5 lines
files_changed: []
symbols_changed: []
contracts_touched: []
decisions_created: []
tests: {added: [], run: [], result: pass|fail}
evidence: ["[VERIFIED: src/auth/service.py:41-58]"]
impact_rederived: {scope: local, contract_change: false, public_api_change: false}
risks: []
blockers: []
actions_to_avoid_until_clarified: []   # named actions a successor must NOT take until a question is answered

```

`status`, `position`, `derived_state`, and `next_action` are **derived** by the
execution-position adapter (`execute.py render-summary`, DID-012 I8) from the task's
lifecycle events - never authored in this payload. A payload that authors any of them is
rejected (exit 1) and the SUMMARY is not written. The task must be registered first
(`task-register`). A blocking or failed outcome is recorded via lifecycle events
(`task-event` BLOCKED / FAILED with `failure_class`) plus a `write-blocker` call naming
the signal, the specific missing item, what was tried, and the returned blocker id; the
render derives `status: blocked | failed` from those records. G8 refuses completion while
any open blocker exists; resolve before reporting complete.


`actions_to_avoid_until_clarified` lists actions that would be wrong or destructive if taken
before an open question is answered (e.g. "do not remove the fallback path", "do not delete
the deprecated endpoint until the consumer audit is confirmed"). A successor reads this list
first: while an item is present, the named action is withheld regardless of how complete the
rest of the handoff looks. When the question is answered, the Team Lead clears the items and
the successor proceeds. Absence of the key means no withheld actions.

The SUMMARY.md fence is a RENDER, not a verbatim copy: the adapter renders `task_id` and the
derived fields (`status`, `position`, `terminal`, `next_action`), each marked
`# derived (I8)`, then passes the remaining payload fields through unchanged. A payload that
authors any derived field is rejected (exit 1, no write). Adding a non-authoritative field is
documentation-only - no schema change required - provided the task is registered first.