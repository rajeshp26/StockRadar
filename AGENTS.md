# Agent framework rules

Stable global rules only. Requirements, architecture, research, plans, and task history are
retrieved dynamically through the GSD state adapter. Never inline them here.

## Rule zero â€” non-duplication

Do not duplicate capabilities already provided by OpenCode, GSD, the code intelligence provider,
Git, or the host. Extend them through adapters and gates.

## Rule one â€” do not invoke agents gratuitously

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
If something critical is missing, do not guess â€” return `CONTEXT_INSUFFICIENT` naming the item.

## Rule - ambiguity and assumptions
State assumptions explicitly. If uncertain, ask rather than guess. Do NOT guess.
If multiple interpretations exist, present them - don't pick silently. Give at least 2 options with tradeoffs.
If something is unclear, stop. Name what's confusing and ask for clarification.
If a simpler approach exists that satisfies the requirements, say so and push back when warranted.

## Gate evidence persistence

OpenCode prunes old tool outputs and auto-compacts. Write gate and test results to the
verification artifact immediately. Never rely on them remaining in context.

## Safety

Never expose secrets, disable or delete tests to reach green, bypass a gate, change a contract
silently, or modify production without an approved release gate. Credentials live outside the
workspace in environment variables.


## Enforcement plane is agent-immutable

A gate executed from mutable, agent-writable code is not a trustworthy security boundary.
Permissions control tool availability; gates are the authorization layer. Neither replaces the
other. The enforcement plane must be verified independently of any agent that runs it.

Canonical source: `framework/security/enforcement_plane.yaml`. The fence below and the
`permission.edit` deny blocks in `opencode.json` are generated from it by
`framework/security/sync_enforcement_plane.py` (human-run; it only mirrors the YAML) and
verified by `framework/security/check_enforcement_plane.py` (must exit 0 - run it after any
plane change).

<!-- enforcement-plane: begin -->
    .opencode/**        agents, rules, skills, plugin, config
    opencode.json       permission model
    AGENTS.md           stable global rules
    framework.config.jsonframework binding (one config)
    framework/opencode/**agents, rules, skills, plugin, config
    framework/plan/**   plan lint + eval cases (DID-016)
    framework/testing/**system-test harness + policy (DID-017)
    framework/security/**plane source + sync/check (immutable)
<!-- enforcement-plane: end -->

Enforced by edit permissions in opencode.json (narrow allowlists with deny fallback, and an
explicit plane deny after any path-scoped allow - a `*` in a permission pattern spans path
segments). Add a rule that crosses a plane boundary only with a trailing deny for the plane.

Tooling bound to the plane (the sync and check scripts) may be EXECUTED by agents, but every
input, implementation, and configuration that determines the enforcement-plane result is a
plane file - immutable to agents, the checker included. That is what makes the check
trustworthy: nothing that could change its verdict can be changed by an agent.

## Frontend stack is a contract

The mandated stack (shadcn/ui, Tailwind, Lucide, Motion, Playwright) is enforced executably by
`framework/gates/g5_frontend_stack.sh` on files the current task changes. Pre-existing
violations elsewhere are baseline debt: reported, never blocking, and not to be fixed
opportunistically inside an unrelated task.

Magic UI, Aceternity, GSAP, and React Three Fiber are conditional. They require an entry in
`framework/frontend/effect_justifications.yaml` naming a requirement ID, a file scope, and an
approver. GSAP additionally requires a measured reason Motion is insufficient. An empty ledger
means conditional tools are not permitted â€” permission is granted per requirement, not once
per repository.

Visible-behaviour requirements need browser evidence. `g6_browser.sh` exit 3 means
unverifiable, and unverifiable is never a pass.
