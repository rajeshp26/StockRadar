# Adopt-before-extend audit (required install step)

GSD already exposes capabilities that overlap this framework. Record a decision per row before
implementing Reviewer, Verifier profiles, or code intelligence access. An unexamined overlap is
how a 7-agent framework silently becomes a 13-agent one.

| GSD capability | Covers | Overlaps our | Decision (adopt / wrap / replace) | Justification |
| --- | --- | --- | --- | --- |
| quality: code review | independent review | Reviewer | wrap | reviewer agent routes to gsd-code-review; delta = read-only agent + verdict-to-gate routing |
| quality: debug | root cause analysis | Implementer debug mode | wrap | implementer debug discipline wraps gsd-debug for stateful sessions |
| quality: security | security review | Verifier security profile | wrap | verifier security profile invokes gsd-secure-phase; delta = exit-code verdict |
| quality: UI audit | visual inspection | Verifier browser profile | wrap | verifier browser profile invokes gsd-ui-review; delta = G6 evidence requirement |
| context: map | codebase structure | Architect inputs | adopt | architect consumes gsd-map-codebase output directly; nothing added |
| context: graphify | dependency data | code intelligence tier 1 | adopt | GSD graphify is adapter tier 1 by design; CodeGraph stays a tier-3 accelerator |
| context: learnings | durable lessons | decisions / research | adopt | gsd-extract-learnings / mempalace is the lesson store; framework cites it |
| workflow: plan | atomic plans, plan-checker | Planner | wrap | planner agent adds impact/complexity scoping; gsd-plan-phase owns PLAN.md |
| workflow: verify | goal-backward check | Verifier functional | wrap | verifier agent adds the gate evidence ledger; gsd-verify-work owns UAT |
| quality: UI audit | frontend conventions | G5 stack conformance | replace | GSD ships no executable stack-conformance gate; unproven claims pass silently |
| quality: UI audit | browser inspection | G6 browser gate | replace | GSD has no browser gate; MCP transcripts are pruned, so committed specs + exit code are required |
| workflow: state consistency | state vs filesystem drift | gate persist / handoffs | wrap | gsd-health detects drift; framework gates persist verdicts and g8 refuses completion |
| workflow: delegation | delegated-task lifecycle and liveness | team-lead supervision role | replace | GSD ships no delegated-task registry, lifecycle enforcement, or health ladder; silent workers that live only in conversation repeat — the named defect class |

Rules. `replace` requires a named defect class the GSD capability cannot catch. `adopt` means we
call it and add nothing. `wrap` means we call it and add only the delta.

If `context: graphify` already yields usable dependency data, the CodeGraph provider drops to a
tier-3 accelerator and is not a dependency. Write that decision down.

Write each decision via:
`python3 framework/adapters/gsd_state.py write-decision --id D001 --json "<yaml>"`


## Resolving the `gsd-*` agents and skills

A file map that lists `framework/opencode/agents/gsd-*.md` and `framework/opencode/skills/gsd-*/SKILL.md`
without a decision per row is the overlap, not a resolution. Each such file must map to a
row above and carry a decision, or be deleted.

Concretely: if `quality: code review` is `adopt`, there is no Reviewer prompt to maintain and
no `gsd-review` wrapper — the Team Lead calls the GSD command. If it is `wrap`, the Reviewer
definition keeps only the delta and cites the row. Two prompts that both review a diff will
disagree, and the disagreement surfaces as review-rejection churn.

### File map resolution (2026-09-04)

Every `framework/opencode/agents/gsd-*.md` and `framework/opencode/skills/gsd-*/SKILL.md` is a GSD-distribution
thin wrapper invoking the mapped GSD command under the decision recorded above. `adopt` rows
call the command with no delta; `wrap` rows add only the named delta (read-only agent,
permission wrapper, gate exit code); `replace` rows (G5, G6) own the capability outright and no
GSD command of the same class exists. No parallel review prompt is maintained.

## Why this blocks install

`bootstrap.sh` stage 3 shows this file. Leaving every Decision cell empty means the framework
was installed without checking whether it duplicates the workflow engine underneath it. That
is the single most likely way this drops below seven agents — and the reason the audit is a
required step rather than documentation.

Validation enforces presence, not content: it checks that every row has a decision recorded.
It cannot check that the decision is right.
