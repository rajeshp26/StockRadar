<command-instruction>
You are implementing a new feature using the gated development workflow.

## Arguments
$ARGUMENTS

## Skill

Load and follow `requirements-authoring` for any requirement capture, refinement, or review in Gate 1.

## Workflow

### Step 1: Gate 1 — Requirements

Before ANY code investigation, document a structured requirement using the `requirements-authoring` skill:

```markdown
## GATE 1: REQUIREMENTS

REQUEST: [What exactly is being requested — from the user's arguments]

REQ-ID: [assigned requirement id]

PERSONA: [who the feature is for]

USER STORY: As a <persona>, I want <goal>, so that <value>.

ENVIRONMENTS: [where behavior must hold]

MAIN SCENARIO (Given/When/Then): ...

ALTERNATE SCENARIOS: ...

NEGATIVE/FAILURE SCENARIOS: ...

BOUNDARY/EDGE SCENARIOS: ...

OUT OF SCOPE: ...

SHAPE: [visible_behaviour | api_contract | business_rule | ...]

ACCEPTANCE CRITERIA: [falsifiable conditions]

VERIFICATION METHOD: [browser verification | contract test | unit test | integration]

UNKNOWN INFORMATION: [what is unclear]
```

If requirements are ambiguous → STOP. Ask the user for clarification.

### Step 2: Gate 2 — Investigation

Use CodeGraph and LSP to understand the codebase:

1. Use `codegraph_explore` to find relevant components, functions, and patterns
2. Use `lsp_symbols` and `lsp_find_references` to trace call paths
3. Read existing tests to understand current behavior

Output:
```markdown
## GATE 2: INVESTIGATION

RELEVANT COMPONENTS: [files, functions, classes]
EXECUTION FLOW: [how the code works]
DATA FLOW: [how data moves]
EXISTING PATTERNS: [established conventions]
EXISTING TESTS: [test coverage]
DEPENDENCIES: [what depends on what]
CONFIDENCE: [HIGH/MEDIUM/LOW]
```

If confidence is LOW → STOP. More investigation needed.

### Step 3: Gate 3 — Impact Analysis

Use CodeGraph to map blast radius:

```markdown
## GATE 3: IMPACT ANALYSIS

DIRECT IMPACT: [files, functions, classes]
INDIRECT IMPACT: [callers, consumers, UI]
POTENTIAL REGRESSION: [what could break]
BACKWARD COMPATIBILITY: [API changes]
RISK: [LOW/MEDIUM/HIGH]
```

If risk is HIGH → STOP. Get approval before proceeding.

### Step 4: Gate 4 — Design

Propose a solution:

```markdown
## GATE 4: DESIGN

CURRENT DESIGN: [what exists]
PROPOSED DESIGN: [what you're proposing]
MODULE BOUNDARIES: [components]
DATA FLOW: [how data moves]
CONTROL FLOW: [how logic flows]
INTERFACES: [APIs, contracts]
DESIGN PRINCIPLES: [SOLID, DRY, etc.]
ALTERNATIVES: [other options considered]
WHY THIS DESIGN: [rationale]
RISKS: [what could go wrong]
```

### Step 5: Gate 5 — Design Review

If using the architect/design-reviewer agents, delegate the review.

Otherwise, self-review using the checklist:
- [ ] Missing dependencies or imports
- [ ] Incorrect assumptions about existing code
- [ ] Duplicate functionality already implemented
- [ ] Over-engineering or unnecessary abstraction
- [ ] Wrong abstraction level
- [ ] API compatibility issues
- [ ] Security vulnerabilities
- [ ] Performance concerns

```markdown
## GATE 5: DESIGN REVIEW

VERDICT: [PASS | REVISE | REJECT]
FINDINGS: [list of issues]
```

If REJECTED → back to Gate 4.

### Step 6: Gate 6 — Implementation

Delegate to the implementer agent or implement directly:

1. Implement EXACTLY the approved design
2. Do not redesign architecture
3. Do not refactor unrelated code
4. Do not add features not in the design

### Step 7: Gate 7 — Static Quality

Run automated checks:

```bash
# Python
python -m ruff check <changed_python_files>
python -m ruff format --check <changed_python_files>

# TypeScript
npx eslint <changed_ts_files>
npx tsc --noEmit
```

Or use the repository validation suite:
```bash
python3 framework/validate.py
```

If any FAIL → fix the issues before proceeding.

### Step 8: Gate 8 — Testing

Run tests:

```bash
# Backend
python -m pytest backend/tests -x --tb=short

# Frontend
npx vitest run
```

Or use the repository validation suite:
```bash
python3 framework/validate.py
```

If any FAIL → fix the issues before proceeding.

### Step 9: Gate 9 — Regression Review

Re-analyze impact after implementation:

1. Re-run CodeGraph impact analysis
2. Compare expected vs actual changes
3. Verify no unintended side effects

```markdown
## GATE 9: REGRESSION REVIEW

EXPECTED CHANGED BEHAVIOR: [what should change]
ACTUAL CHANGED BEHAVIOR: [what actually changed]
CODEGRAPH VERIFICATION: [re-check relationships]
REGRESSION RISK: [LOW/MEDIUM/HIGH]
```

### Step 10: Gate 10 — Final Review

Final quality check:

```markdown
## GATE 10: FINAL REVIEW

CHECKLIST:
- [ ] Requirement satisfied
- [ ] Approved design implemented
- [ ] No unnecessary changes
- [ ] No duplication
- [ ] Modular
- [ ] Correct abstractions
- [ ] Appropriate patterns
- [ ] API compatibility preserved
- [ ] Error handling correct
- [ ] Security considered
- [ ] Performance considered
- [ ] Tests meaningful
- [ ] Static checks pass
- [ ] Regression checks pass
- [ ] Documentation updated

FINAL STATUS: [PASS | FAIL]
```

## Output

Report the final gate status:

```markdown
## FEATURE COMPLETE

GATE 1 (Requirements): PASS
GATE 2 (Investigation): PASS
GATE 3 (Impact Analysis): PASS
GATE 4 (Design): PASS
GATE 5 (Design Review): PASS
GATE 6 (Implementation): PASS
GATE 7 (Static Quality): PASS
GATE 8 (Testing): PASS
GATE 9 (Regression Review): PASS
GATE 10 (Final Review): PASS

FILES MODIFIED: [list]
TESTS ADDED: [list]
```

## Anti-Cheating Rules
