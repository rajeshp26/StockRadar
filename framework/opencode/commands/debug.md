<command-instruction>
You are investigating a bug using the disciplined 10-gate debugging workflow.

## Arguments
$ARGUMENTS

## Workflow

### Step 1: DEBUG GATE 1 — Understand the Problem

Before ANY code investigation, document:

```markdown
## DEBUG GATE 1: PROBLEM STATEMENT

REPORTED BEHAVIOR: [exactly what the user reported]
EXPECTED BEHAVIOR: [what should happen]
FREQUENCY: [always / sometimes / once / unknown]
ENVIRONMENT: [where it occurs]
REPRODUCTION INFO: [any known steps]
KNOWN CONSTRAINTS: [what must not change]
UNKNOWN INFORMATION: [what we don't yet know]
```

If critical information is missing → BLOCKED. Ask the user.

### Step 2: DEBUG GATE 2 — Reproduce

Attempt to reproduce the problem. This is a HARD REQUIREMENT.

For React: Playwright, browser console, network requests
For Python: pytest, logs, debugger, API calls, DB queries

```markdown
## DEBUG GATE 2: REPRODUCTION

ENVIRONMENT: [exact setup]
STEPS:
1. ...
2. ...

EXPECTED: [what should happen]
OBSERVED: [what actually happens]
REPRODUCED: YES / NO / PARTIAL
EVIDENCE: [screenshots, logs, output]
```

**If unable to reproduce:**
```markdown
STATUS: BLOCKED

Unable to reproduce.
ATTEMPTS: [what was tried]
ADDITIONAL INFORMATION REQUIRED: [what's needed]
```

**NEVER invent a root cause when reproduction fails.**

### Step 3: DEBUG GATE 3 — Capture Evidence

Record actual behavior at system boundaries.

For each layer tested:
```markdown
LAYER: [frontend / API / service / DB]
ENTRY: [was this layer reached? YES/NO]
INPUT: [what it received]
OUTPUT: [what it returned]
STATE: [relevant state]
```

### Step 4: DEBUG GATE 4 — Trace Complete Stack

**CodeGraph is MANDATORY for non-trivial bugs.**

Use `codegraph_explore` to trace the full execution path.

```markdown
## DEBUG GATE 4: STACK TRACE

ENTRY POINT: [where execution starts]
CALL CHAIN: [CodeGraph trace]
DATA FLOW: [how data moves]
CONTROL FLOW: [branching, conditionals]
STATE TRANSITIONS: [relevant state changes]
ERROR HANDLING: [catch blocks, error paths]
ASYNC BOUNDARIES: [promises, callbacks, events]
EXTERNAL DEPENDENCIES: [APIs, DB, services]
```

### Step 5: DEBUG GATE 5 — Establish Expected Behavior

Distinguish "what the code does" from "what it's supposed to do."

Source from:
1. Explicit user requirement
2. API contract / spec
3. Architecture docs
4. Existing tests
5. Established system behavior

```markdown
## DEBUG GATE 5: EXPECTED BEHAVIOR

REQUIREMENT: [source + content] — STATUS: VERIFIED / ASSUMED
API CONTRACT: [source + content] — STATUS: VERIFIED / ASSUMED
EXISTING TEST: [source + content] — STATUS: VERIFIED / ASSUMED
```

### Step 6: DEBUG GATE 6 — Expected vs Observed

Produce a comparison table. The RCA must explain the **first divergence**.

```markdown
## DEBUG GATE 6: EXPECTED VS OBSERVED

| Stage | Expected | Observed | Evidence | Match |
|-------|----------|----------|----------|-------|
| ... | ... | ... | ... | ✅/❌ |
```

### Step 7: DEBUG GATE 7 — Generate Hypotheses

Only after evidence is collected.

```markdown
## DEBUG GATE 7: HYPOTHESES

H1: [description]
  SUPPORTING: [evidence]
  AGAINST: [evidence]
  EXPERIMENT: [how to prove/disprove]
  STATUS: UNPROVEN

H2: [description]
  ...
```

### Step 8: DEBUG GATE 8 — Fact-Check / Falsify

Actively try to disprove each hypothesis. Run experiments.

```markdown
## DEBUG GATE 8: FALSIFICATION

H1: [hypothesis]
  EXPERIMENT: [what was done]
  RESULT: [what was observed]
  CONCLUSION: PROVEN / DISPROVEN / INCONCLUSIVE
```

### Step 9: DEBUG GATE 9 — Root Cause

Only if evidence supports it.

```markdown
## DEBUG GATE 9: ROOT CAUSE

COMPONENT: [what is broken]
FAILURE: [how it fails]
EVIDENCE:
1. ...
2. ...
3. ...
CONFIDENCE: HIGH / MEDIUM / LOW
ROOT CAUSE STATUS: PROVEN / UNPROVEN
```

**If UNPROVEN → STOP. Report what's missing. Do not guess.**

### Step 10: DEBUG GATE 10 — Package for RCA Review

```markdown
## DEBUG GATE 10: RCA PACKAGE

PROBLEM STATEMENT: [from Gate 1]
REPRODUCTION: [from Gate 2]
EVIDENCE: [from Gate 3]
STACK TRACE: [from Gate 4]
EXPECTED BEHAVIOR: [from Gate 5]
EXPECTED VS OBSERVED: [from Gate 6]
HYPOTHESES: [from Gate 7]
FALSIFICATION: [from Gate 8]
PROPOSED ROOT CAUSE: [from Gate 9]
```

## Output

```markdown
## DEBUGGING COMPLETE

ROOT CAUSE: [brief description or UNPROVEN/BLOCKED]
EVIDENCE SUMMARY: [key evidence]
FILES INVOLVED: [list]
RECOMMENDATION: [next steps]
```

## Non-Negotiable Rules

- **Root cause is not a hypothesis.** Never present suspected cause as root cause without evidence.
- **Never fix forward.** Do not modify production code to test a theory.
- **CodeGraph is mandatory** for non-trivial bugs.
- **If reproduction fails, say so.** Do not invent explanations.
- **If evidence is insufficient, report UNRESOLVED.** Never guess.
- NEVER modify production code as an experiment
- NEVER present hypothesis as root cause
- NEVER skip evidence collection
- NEVER guess at root cause when blocked
</command-instruction>

<session-context>
Session ID: $SESSION_ID
Timestamp: $TIMESTAMP
</session-context>

<user-request>
$ARGUMENTS
</user-request>
