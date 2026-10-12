# Team Ship Command

Orchestrate the final ship process — quality gates, review, and GSD ship.

## Usage

```
/team-ship
/team-ship --phase N
/team-ship --draft
/team-ship --skip-review
```

## Workflow

### Step 1: Pre-Ship Quality Gates

Before any review, verify automated gates pass:

```
Gate 7: Static Quality
  - Python: ruff check, ruff format
  - TypeScript: eslint, tsc --noEmit

Gate 8: Testing
  - Backend: pytest
  - Frontend: vitest
```

Run `python3 framework/validate.py` or execute checks directly.

**If any gate fails: SHIP BLOCKED.** Fix issues first.

### Step 2: Verify GSD State

Read `.planning/STATE.md`:
- Confirm the phase has been executed
- Confirm verification has been done (or do it now)

If verification not done: run `/gsd-verify-work N` first.

### Step 3: Run Team Review

Unless `--skip-review` is passed, run `/team-review` to get independent review.

**If review returns BLOCKED: SHIP BLOCKED.** Resolve issues first.

### Step 4: Security Gate

If the phase involves auth, payments, or sensitive data:
- Run security review if not already done
- Confirm no open security findings

### Step 5: User Confirmation

Before proceeding with ship, confirm with user:

```
Phase {N} is ready to ship.

Quality Gates: ✅ PASS
Team Review: ✅ APPROVED
Security: ✅ CLEAR (or N/A)

Proceed with /gsd-ship {N}?
```

### Step 6: Execute Ship

If user confirms, run:

```
/gsd-ship {N}
```

With optional flags:
- `--draft` for draft PR
- Standard for production PR

### Step 7: Post-Ship

After successful ship:
1. Confirm PR created
2. Update team status
3. Suggest next phase if applicable

## Constraints

- Quality gates must pass before ship
- Team review must pass before ship (unless --skip-review with user approval)
- Security concerns block ship until resolved
- User must approve ship — never auto-ship
- Cannot ship without GSD verification complete
