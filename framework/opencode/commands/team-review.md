# Team Review Command

Orchestrate a comprehensive team review of completed work before ship.

## Usage

```
/team-review
/team-review --phase N
/team-review --files file1.ts file2.py
```

## Workflow

### Step 1: Identify Scope

Determine what needs review:
- If `--phase N` provided: review all work in phase N
- If `--files` provided: review those specific files
- Otherwise: review current phase or ask for clarification

### Step 2: Read GSD State

Read `.planning/STATE.md` and phase summaries to understand what was built.

### Step 3: Assign Review Agents

Spawn independent review agents in parallel:

1. **Code Review** — Spawn `reviewer` agent to review code quality
2. **Security Review** — Spawn `security` agent if auth/payment/data changes
3. **Test Review** — Verify test coverage and quality

### Step 4: Collect Reviews

Each reviewer provides a structured verdict:

```markdown
## Review: [Feature]

### Verdict: PASS | PASS_WITH_COMMENTS | FAIL

### Blocking Issues
- [Issues that must be fixed]

### Suggestions
- [Improvements to consider]

### Risk Assessment
- Regression: [LOW/MEDIUM/HIGH]
- Security: [LOW/MEDIUM/HIGH]
```

### Step 5: Synthesize Results

Combine all reviews into a unified verdict:

- If ANY reviewer returns FAIL: ship is BLOCKED
- If all reviewers return PASS or PASS_WITH_COMMENTS: ship is APPROVED
- Summarize blocking issues and required fixes

### Step 6: Output

```markdown
## Team Review Summary — Phase {N}

### Overall Verdict: APPROVED | BLOCKED

### Review Results
| Reviewer | Verdict | Blocking Issues |
|----------|---------|----------------|
| Code Review | {verdict} | {count} |
| Security | {verdict} | {count} |

### Required Actions Before Ship
- [ ] {action 1}
- [ ] {action 2}

### Recommended Improvements (non-blocking)
- {improvement 1}
- {improvement 2}
```

## Constraints

- Reviews must be independent (different agents for different reviews)
- Security review is mandatory for auth/payment/data changes
- All blocking issues must be resolved before ship
- Cannot override a FAIL verdict without user approval
