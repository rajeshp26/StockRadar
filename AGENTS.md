# Agent framework rules

Stable global rules only. Requirements, architecture, research, plans, and task history are
retrieved dynamically through the GSD state adapter. Never inline them here.

## Rule zero — non-duplication

Do not duplicate capabilities already provided by OpenCode, GSD, the code intelligence provider,
Git, or the host. Extend them through adapters and gates.

## Rule one — do not invoke agents gratuitously

An agent must not be invoked merely because it exists. Name the specific information or execution
need that cannot be satisfied by the active agent, an existing skill, GSD, the code intelligence
provider, or an executable gate. Record the need in the task record before delegating.

## Delegation

Only `team-lead` delegates. All subagents have `task` denied. Communicate through structured
handoffs written to GSD state. Never pass raw reasoning between agents.

## Evidence

Use the strongest **applicable** executable evidence for the requirement. Reasoning cannot
substitute for applicable executable evidence. An applicable evidence class that was available
but skipped is a verification failure, not a pass with a caveat.

Cite in-repo discrete values as `[VERIFIED: path:line-start-line-end]`, and only after opening
the file in this run.

## Context

Prefer pointers over copied content. Retrieve what you need; do not read broadly. Before acting,
confirm the plan, referenced requirements, touched contracts, and relevant tests are readable.
If something critical is missing, do not guess — return `CONTEXT_INSUFFICIENT` naming the item.

## Gate evidence persistence

OpenCode prunes old tool outputs and auto-compacts. Write gate and test results to the
verification artifact immediately. Never rely on them remaining in context.

## Safety

Never expose secrets, disable or delete tests to reach green, bypass a gate, change a contract
silently, or modify production without an approved release gate. Credentials live outside the
workspace in environment variables.


## Frontend stack is a contract

The mandated stack (shadcn/ui, Tailwind, Lucide, Motion, Playwright) is enforced executably by
`framework/gates/g5_frontend_stack.sh` on files the current task changes. Pre-existing
violations elsewhere are baseline debt: reported, never blocking, and not to be fixed
opportunistically inside an unrelated task.

Magic UI, Aceternity, GSAP, and React Three Fiber are conditional. They require an entry in
`framework/frontend/effect_justifications.yaml` naming a requirement ID, a file scope, and an
approver. GSAP additionally requires a measured reason Motion is insufficient. An empty ledger
means conditional tools are not permitted — permission is granted per requirement, not once
per repository.

Visible-behaviour requirements need browser evidence. `g6_browser.sh` exit 3 means
unverifiable, and unverifiable is never a pass.
