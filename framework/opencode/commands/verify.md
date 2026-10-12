<command-instruction>
You are verifying a completed implementation. This is the final quality gate.

## Arguments
$ARGUMENTS

## What to Verify

Check the recent changes (or specified files) against ALL quality criteria.

### Step 1: Static Quality

Run linting and type checking on all changed files.

```bash
# Python
cd backend && python -m py_compile <file>
cd backend && python -m ruff check <file>

# TypeScript
cd web && npx tsc --noEmit
cd web && npx eslint <file>
```

Record results:
```markdown
STATIC ANALYSIS:
- Python lint: PASS / FAIL
- TypeScript type check: PASS / FAIL
- ESLint: PASS / FAIL
```

### Step 2: Test Verification

Run all relevant tests.

```bash
# Python
cd backend && python -m pytest <test_file> -v

# TypeScript
cd web && npm test
```

Record results:
```markdown
TESTS:
- Unit tests: PASS / FAIL
- Integration tests: PASS / FAIL
- Test count: X passed, Y failed
```

### Step 3: Regression Check

Verify no existing behavior was broken.

```markdown
REGRESSION:
- Existing tests still pass: YES / NO
- No unrelated changes: YES / NO
- Backward compatible: YES / NO
```

### Step 4: Implementation Quality

Review the actual code changes.

```markdown
CODE QUALITY:
- Follows existing patterns: YES / NO
- No type suppressions (as any, @ts-ignore): YES / NO
- No silent failures: YES / NO
- Error handling present: YES / NO
- No hardcoded values: YES / NO
- No dead code: YES / NO
- No TODO/FIXME without ticket: YES / NO
```

### Step 5: Security Quick Check

```markdown
SECURITY:
- No secrets in code: YES / NO
- Input validation present: YES / NO
- No SQL injection risk: YES / NO
- No XSS risk: YES / NO
- Auth checks maintained: YES / NO
```

### Step 6: Documentation Check

```markdown
DOCUMENTATION:
- Public functions have docstrings: YES / NO
- Complex logic has comments: YES / NO
- README updated if needed: YES / NO
```

## Output

```markdown
## VERIFICATION REPORT

STATIC ANALYSIS: PASS / FAIL
TESTS: PASS / FAIL
REGRESSION: PASS / FAIL
CODE QUALITY: PASS / FAIL
SECURITY: PASS / FAIL
DOCUMENTATION: PASS / FAIL

OVERALL: PASS / FAIL

ISSUES FOUND:
[If any]
```

## Rules

- Do NOT modify code — this is read-only verification
- Do NOT suppress errors
- Do NOT skip checks
- If any check fails, report it honestly
</command-instruction>

<session-context>
Session ID: $SESSION_ID
Timestamp: $TIMESTAMP
</session-context>

<user-request>
$ARGUMENTS
</user-request>
