# Security Audit Command

Run an on-demand security audit of a scope and block on confirmed high/critical findings.

## Usage

```
/security-audit
/security-audit <path or ref-range>
/security-audit --diff
```

## Arguments

$ARGUMENTS

## Workflow

### Step 1: Fix the scope

Determine what is in scope: a path, a ref range (`scoped_run` audits the diff between two
source refs), or the current diff. If it is ambiguous, ask one focused question. Do not widen
scope silently.

### Step 2: Load the method

Follow `framework/opencode/skills/security-audit/SKILL.md`. Prioritise by the skill's
attack-class taxonomy (`ATTACK-CLASSES.md`) over hunches.

### Step 3: Dispatch an independent hunter

`team-lead` dispatches a **fresh `security-auditor`** subagent. Never the implementer.

### Step 4: Establish the sandbox first

Before any target-controlled execution, require:

```bash
bash framework/gates/g_sandbox.sh
```

If it does not exit `0`, the audit is **source-only**. Record that; never execute anyway.

### Step 5: Produce artifacts

Write `findings.json` and `coverage-ledger.json` under `.planning/audits/<id>/`. A finding
is `confirmed` only with a non-empty `observed_result`.

### Step 6: Judge the artifacts

```bash
AUDIT_RUN_DIR=.planning/audits/<id> bash framework/gates/g18_security_audit.sh
```

### Step 7: Report

Report each finding with severity and the smallest effective fix. A confirmed high/critical
finding **blocks completion** until resolved or explicitly accepted by a human.
