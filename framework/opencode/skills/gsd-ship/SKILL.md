---
name: gsd-ship
description: "Create PR, run review, and prepare for merge after verification passes"
---

<objective>
Bridge local completion → merged PR. After /gsd-verify-work passes, ship the work: push branch, create PR with auto-generated body, optionally trigger review, and track the merge.

Closes the plan → execute → verify → ship loop.
</objective>

<execution_context>
@C:/Project/StockerPro/StockerPro/framework/opencode/gsd-core/workflows/ship.md
</execution_context>

Execute the ship workflow from @C:/Project/StockerPro/StockerPro/framework/opencode/gsd-core/workflows/ship.md end-to-end.

<runtime_note>
**Merge review is decided by the change class, not asked.** The workflow's `optional_review`
step offers Skip / Self-review / Request review. Answer it from the merge acceptance tiers in
`framework/opencode/agents/team-lead.md` - read the tier from the actual diff and re-derive it
like impact; a lower tier never overrides a higher one:

- tier 1 -> Skip or Self-review. CI green plus the recorded verifier evidence is the acceptance.
- tier 2 -> Request review. An identity that did not author the change reviews before merge.
- tier 3 -> do not merge until the security or H2 human gate is recorded.
- tier 4 -> do not merge here. G8 part B hands a recommendation to H3, which decides.

An identity never merges or certifies its own work at tier 2 or above.

This binding lives in the wrapper skill and not in `gsd-core/workflows/ship.md`: that file is
vendored GSD-core, and local divergence from upstream is a rebase cost paid on every pull.
</runtime_note>
