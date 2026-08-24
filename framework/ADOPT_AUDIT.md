# Adopt-before-extend audit (required install step)

GSD already exposes capabilities that overlap this framework. Record a decision per row before
implementing Reviewer, Verifier profiles, or code intelligence access. An unexamined overlap is
how a 7-agent framework silently becomes a 13-agent one.

| GSD capability | Covers | Overlaps our | Decision (adopt / wrap / replace) | Justification |
| --- | --- | --- | --- | --- |
| quality: code review | independent review | Reviewer | | |
| quality: debug | root cause analysis | Implementer debug mode | | |
| quality: security | security review | Verifier security profile | | |
| quality: UI audit | visual inspection | Verifier browser profile | | |
| context: map | codebase structure | Architect inputs | | |
| context: graphify | dependency data | code intelligence tier 1 | | |
| context: learnings | durable lessons | decisions / research | | |
| workflow: plan | atomic plans, plan-checker | Planner | | |
| workflow: verify | goal-backward check | Verifier functional | | |
| quality: UI audit | frontend conventions | G5 stack conformance | | |
| quality: UI audit | browser inspection | G6 browser gate | | |
| workflow: state consistency | state vs filesystem drift | gate persist / handoffs | | |

Rules. `replace` requires a named defect class the GSD capability cannot catch. `adopt` means we
call it and add nothing. `wrap` means we call it and add only the delta.

If `context: graphify` already yields usable dependency data, the CodeGraph provider drops to a
tier-3 accelerator and is not a dependency. Write that decision down.

Write each decision via:
`python3 framework/adapters/gsd_state.py write-decision --id D001 --json "<yaml>"`


## Resolving the `gsd-*` agents and skills

A file map that lists `.opencode/agents/gsd-*.md` and `.opencode/skills/gsd-*/SKILL.md`
without a decision per row is the overlap, not a resolution. Each such file must map to a
row above and carry a decision, or be deleted.

Concretely: if `quality: code review` is `adopt`, there is no Reviewer prompt to maintain and
no `gsd-review` wrapper — the Team Lead calls the GSD command. If it is `wrap`, the Reviewer
definition keeps only the delta and cites the row. Two prompts that both review a diff will
disagree, and the disagreement surfaces as review-rejection churn.

## Why this blocks install

`bootstrap.sh` stage 3 shows this file. Leaving every Decision cell empty means the framework
was installed without checking whether it duplicates the workflow engine underneath it. That
is the single most likely way this drops below seven agents — and the reason the audit is a
required step rather than documentation.

Validation enforces presence, not content: it checks that every row has a decision recorded.
It cannot check that the decision is right.
