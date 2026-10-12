# Team Status Command

Display the current team status dashboard — project state, active phases, agent assignments, and blockers.

## Usage

```
/team-status
/team-status --phase N
/team-status --verbose
```

## Workflow

### Step 1: Read GSD State

Read `.planning/STATE.md` to understand current project state:

- Current phase and status
- Active milestones
- Recent completions
- Open blockers

### Step 2: Read Phase Details

If a phase is in progress, read:
- `.planning/phases/{phase}/{phase}-*-PLAN.md` — planned work
- `.planning/phases/{phase}/{phase}-*-SUMMARY.md` — completed work
- `.planning/phases/{phase}/{phase}-VERIFICATION.md` — verification status

### Step 3: Display Dashboard

Output a structured status report:

```markdown
## Team Status — {date}

### Project: {project name from STATE.md}

### Current Phase: {N} — {phase title}
- Status: {planning | in_progress | verifying | complete}
- Progress: {completed tasks} / {total tasks} tasks

### Active Work
| Agent | Task | Status |
|-------|------|--------|
| {agent} | {task description} | {in_progress | done | blocked} |

### Blockers
- {blocker description}

### Recent Completions
- {completed item 1}
- {completed item 2}

### Quality Gates
- [ ] Tests passing
- [ ] Type check clean
- [ ] Lint clean
- [ ] Security review complete
- [ ] Code review complete

### Next Steps
- {recommended next action}
```

### Step 4: Suggest Actions

Based on the status, suggest the next appropriate GSD command:
- If phase needs planning: suggest `/gsd-plan-phase N`
- If phase needs execution: suggest `/gsd-execute-phase N`
- If phase needs verification: suggest `/gsd-verify-work N`
- If phase is complete: suggest `/gsd-ship N` or next phase

## Constraints

- Read-only operation — does not modify state
- Must read from actual GSD state files, not assume
- If state files don't exist, say so clearly
