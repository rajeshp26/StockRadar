<command-instruction>
You are fixing a bug using the gated development workflow.

## Arguments
$ARGUMENTS

## Workflow

### Step 1: Gate 1 — Requirements

Before ANY code investigation, document:

```markdown
## GATE 1: REQUIREMENTS

BUG DESCRIPTION: [What exactly is broken — from the user's arguments]
EXPECTED BEHAVIOR: [What should happen]
ACTUAL BEHAVIOR: [What actually happens]
REPRODUCTION STEPS: [How to reproduce the bug]
CONSTRAINTS: [What must not change]
```

If the bug description is unclear → STOP. Ask the user for clarification.

### Step 2: Gate 2 — Investigation

Use CodeGraph and LSP to trace the bug:

1. Use `codegraph_explore` to find the relevant code path
2. Use `lsp_find_references` to trace callers
3. Read existing tests to understand expected behavior
4. Identify the root cause

Output:
```markdown
## GATE 2: INVESTIGATION

ROOT CAUSE: [What is actually broken and why]
AFFECTED CODE: [files, functions, lines]
EXECUTION FLOW: [how the buggy code executes]
EXISTING TESTS: [do tests exist for this area?]
CONFIDENCE: [HIGH/MEDIUM/LOW]
```

If confidence is LOW → STOP. More investigation needed.

### Step 3: Gate 3 — Impact Analysis

Use CodeGraph to map blast radius:

```markdown
## GATE 3: IMPACT ANALYSIS

DIRECT IMPACT: [files being fixed]
INDIRECT IMPACT: [callers, consumers]
POTENTIAL REGRESSION: [what else could break]
RISK: [LOW/MEDIUM/HIGH]
```

### Step 4: Gate 4 — Design

Propose the fix:

```markdown
## GATE 4: FIX DESIGN

CURRENT (BUGGY) CODE: [what exists]
FIXED CODE: [what you're proposing]
WHY THIS FIX: [rationale]
ALTERNATIVES: [other options considered]
RISKS: [what could go wrong]
```

### Step 5: Gate 5 — Design Review

Self-review:
- [ ] Does this fix the root cause, not just symptoms?
- [ ] Is this the minimal fix?
- [ ] Does this introduce new bugs?
- [ ] Does this maintain backward compatibility?
- [ ] Are there security implications?

```markdown
## GATE 5: DESIGN REVIEW

VERDICT: [PASS | REVISE | REJECT]
```

### Step 6: Gate 6 — Implementation

Implement the fix:

1. Fix the root cause
2. Do NOT refactor unrelated code
3. Do NOT add features
4. Keep changes minimal

### Step 7: Gate 7 — Static Quality

Run automated checks on changed files.

### Step 8: Gate 8 — Testing

1. Run existing tests to ensure no regression
2. Add a REGRESSION TEST that specifically tests this bug
3. The regression test MUST:
   - Pass with the fix
   - Fail without the fix (verify this!)
   - Test the specific scenario described in the bug

```bash
# Verify regression test catches the bug
git stash  # temporarily revert
python -m pytest <test_file> -x  # should FAIL
git stash pop  # re-apply fix
python -m pytest <test_file> -x  # should PASS
```

### Step 9: Gate 9 — Regression Review

```markdown
## GATE 9: REGRESSION REVIEW

BUG FIXED: [yes/no]
REGRESSION TEST ADDED: [yes/no]
REGRESSION RISK: [LOW/MEDIUM/HIGH]
```

### Step 10: Gate 10 — Final Review

```markdown
## GATE 10: FINAL REVIEW

- [ ] Root cause fixed
- [ ] Minimal fix applied
- [ ] No unrelated changes
- [ ] Regression test added
- [ ] All tests pass
- [ ] Static checks pass

FINAL STATUS: [PASS | FAIL]
```

## Output

```markdown
## BUGFIX COMPLETE

ROOT CAUSE: [brief description]
FIX: [what was changed]
REGRESSION TEST: [test file and name]
FILES MODIFIED: [list]
```

## Anti-Cheating Rules

- NEVER modify production code to make a test pass
- NEVER weaken assertions to achieve passing tests
- NEVER remove tests
- NEVER skip the regression test
- NEVER claim fixed without verifying the regression test catches the bug
</command-instruction>

<session-context>
Session ID: $SESSION_ID
Timestamp: $TIMESTAMP
</session-context>

<user-request>
$ARGUMENTS
</user-request>
