# StockerPro Engineering Constitution

## Codebase Understanding

You have two knowledge tools. Use them correctly.

### CodeGraph (code structure)
- **Use for:** symbols, call graphs, blast radius, dependencies, "what calls X", "what breaks if I change Y"
- **Tool:** `codegraph_explore`
- **This is your primary tool for code questions**

### Graphify (docs + architecture)
- **Use for:** design docs, architecture decisions, PDFs, diagrams, "how does authentication work", "what was the migration plan"
- **Tool:** `graphify query "question"` or `graphify explain "concept"`
- **Fallback when CodeGraph returns nothing useful**

### Simple Rule
1. Try CodeGraph first
2. If no useful answer → try Graphify
3. Still nothing → read files directly

### Quick Reference
```
# Code questions
codegraph_explore "authentication flow"

# Doc/architecture questions  
graphify query "how does auth migration work"
graphify explain "background scheduler"

# Check what's indexed
graphify status
codegraph_status (via MCP)
```

---

## Non-Negotiable Rules

### ROOT CAUSE INTEGRITY

Never present a hypothesis as a root cause.

The following classifications MUST remain distinct:

**OBSERVED** — Directly observed behavior.
**VERIFIED** — Confirmed by reliable evidence.
**HYPOTHESIS** — A possible explanation that has not been proven.
**ROOT CAUSE** — An explanation supported by evidence and surviving reasonable attempts to disprove it.
**UNRESOLVED** — Evidence is insufficient to determine the cause.

If the evidence is insufficient: STOP and report UNRESOLVED.

Never guess.
Never infer certainty from plausibility.
Never call something a root cause merely because it is the most likely explanation.

### NO FIX-FORWARD DEBUGGING

Do not modify production code to determine whether a suspected root cause is correct.

Debugging changes must not be used as experiments unless explicitly approved by the user.

First establish:
1. Reproduction
2. Evidence
3. Execution flow
4. Expected behavior
5. Observed behavior
6. Hypotheses
7. Falsification
8. Root cause

Only after RCA approval may corrective implementation begin.

### CODEGRAPH MANDATORY

For non-trivial changes and debugging, CodeGraph MUST be consulted before impact analysis is considered complete.

```
Simple:
Change button text → CodeGraph probably unnecessary

Non-trivial:
Change authentication flow → CodeGraph mandatory

Bug:
API returns stale data → CodeGraph mandatory

Refactor:
Change service architecture → CodeGraph mandatory
```

### HUMAN GATES ARE REQUIRED

Two decisions require explicit human approval:

1. **RCA Approval** — Do you agree this is the root cause?
2. **Design Approval** — Do you agree this is the right way to fix it?

The AI is never allowed to move from diagnosis → implementation automatically.

### MINIMAL CHANGES ONLY

- Fix the bug. Do not refactor unrelated code.
- Add the feature. Do not redesign the system.
- One concern per change.
- Never suppress type errors (`as any`, `@ts-ignore`).
- Never leave code in a broken state.

### TESTING IS MANDATORY

- Every feature must have tests
- Every bugfix must have a regression test
- Tests must pass before completion
- Never delete or weaken tests to pass
- Never skip the regression test

### EVIDENCE OVER ASSUMPTION

- Never guess at call chains — use CodeGraph
- Never assume behavior — verify with tests/logs
- Never claim completion without evidence
- If uncertain, say so and ask
