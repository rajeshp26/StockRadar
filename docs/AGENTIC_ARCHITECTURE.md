# StockerPro Agentic Architecture - Complete Reference

Every detail, every file, every rule, every exit code. If it exists in the framework, it is
documented here.

---

## Table of Contents

1. What This Is
2. The Big Picture
3. The Seven Agents
4. How Agents Talk to Each Other
5. The Two-Axis Classification System
6. The Eight Gates (G1-G8)
7. The Three Adapters
8. The Five Skills
9. The Four Rules
10. The Context Builder Tool
11. The Telemetry Plugin
12. The Verifier Profiles
13. The Retry and Escalation Policy
14. The Frontend Stack Contract
15. The Architecture Rules
16. The State Directory (.planning/)
17. The Validation Suite
18. The Bootstrap Script
19. Permission Model
20. Every Use Case, Step by Step
21. File Map
21a. Lifecycle Integration (v1.1)
22. Exit Code Reference
23. Glossary
24. Practical How-To Guide
25. Telemetry and Model Tuning
26. Lifecycle v1.1 Adoption Plan

---

## 1. What This Is

StockerPro uses an **agentic engineering framework** - a system where seven AI agents work
together like a software team. One agent leads, six specialize. They follow rules. They run
automated checks (called "gates") that prove code is correct before it ships. They never
guess - they prove.

**Why does this exist?** Without it, an AI coding assistant might:
- Ship code that breaks a contract it never checked
- Pass a test it never ran
- Claim a UI looks right without ever opening a browser
- Refactor an architecture boundary it did not know existed

The framework prevents all of that. Every claim needs evidence. Every gate has an exit code.
Every agent has a job description.

When a defect escapes anyway - caught after the change that introduced it was accepted - the
retrospective subsystem computes how it slipped through, files the lesson where it can actually
bite (a gate exit code, a declared rule, or an explicit design-time judgement), and escalates a
recurrence to a human instead of retrying.

---

## 2. The Big Picture

```
                      HUMAN (you)
                Gives requirements, approves
                           |
                           v
                     TEAM-LEAD
           Classifies. Delegates. Enforces.
        The ONLY agent that can call other agents.
         Cannot write code. Cannot review code.
    +----------+----------+----------+----------+
    |          |          |          |          |
    v          v          v          v          v
RESEARCHER ARCHITECT  PLANNER   REVIEWER  VERIFIER
Finds      Designs    Breaks    Reviews   Proves
unknowns   structure  into      the diff  things
before     owns       tasks     never     work with
design     contracts            edits     evidence
                                              |
                                              v
                                       IMPLEMENTER
                                        Writes code
                                        Loads skills
                                        Debugs
```

**Key principle:** Only the Team Lead can delegate. Every other agent has `task` permission
set to `deny`. This creates a **star topology** - depth 1, no agent-to-agent delegation.

---

## 3. The Seven Agents

Each agent is defined in two places:
1. `opencode.json` - permissions (what it can and cannot do)
2. `.opencode/agents/<name>.md` - instructions (what it should do and how)

### 3.1 Team Lead

**File:** `.opencode/agents/team-lead.md`
**Role:** Orchestrator. The conductor.
**Can edit code?** No.
**Can delegate?** Yes - the only one.

**What it does, in order:**

1. **Reads position:** Runs `python3 framework/adapters/gsd_state.py current-phase` to find
   out where the project is.

2. **Classifies the task** on two axes:

```yaml
complexity: L0 | L1 | L2 | L3 | L4
impact:
  scope: local | component | cross_component | system
  contract_change: false
  public_api_change: false
  data_change: false
  security_sensitive: false
```

3. **Decides if delegation is needed.** Before each delegation, it must state the specific
   need that it, a skill, GSD, the code intelligence provider, or a gate cannot satisfy.
   No need = no delegation.

4. **Builds a pointer set** using the `context-builder` tool. Passes pointers, never content.

5. **Routes based on complexity:**

| Complexity | Route |
|---|---|
| L0 | Implementer, targeted verify |
| L1 | Implementer then Verifier |
| L2 | Planner then Implementer then Reviewer then Verifier |
| L3/L4 | Researcher then Architect then H1 then Planner then Implementer(s) then Reviewer then Verifier then gates |

6. **After implementation,** re-derives impact from the actual diff. A wider class than
   assigned triggers context expansion and the gates that class requires.

7. **Enforces completion:** Definition of Done asserted, independently verified, gate exit
   codes recorded, no critical blocker, every activated profile passed.
8. **On escape, opens the retrospective:** when one of the six trigger signals fires against
   work already accepted (`TEST_FAILED_ON_PREVIOUSLY_GREEN`, `PRODUCTION_DEFECT`, ...), records
   the trigger via `python3 framework/retro/ledger.py`, computes the escape path, lands the
   lesson at the destination tier the analyser names, and runs
   `./framework/gates/g7_retro.sh`. A second occurrence of the same structural signature
   escalates to a human with zero retries.

**Human gates it can trigger:**
- **H1** - Architecture approval (L3/L4 or new boundary)
- **H2** - Incompatible contract change
- **H3** - Release approval

**What it must NOT do:** Perform technical work. Become the sole knowledge store. Pass every
agent output to every other agent. Skip gates. Treat provider results as complete truth.

### 3.2 Researcher

**File:** `.opencode/agents/researcher.md`
**Role:** Investigator. Finds answers before design starts.
**Can edit code?** No.
**Can delegate?** No.
**Can access the web?** Yes (`webfetch: allow`).

**What it does:**
- Investigates only what blocks design or implementation
- Stops when the question is answered
- Writes findings through the state adapter's research path

**Output format (mandatory):**

```yaml
research_id:
question:
findings:        # 10 bullets max
evidence:        # paths with line ranges, or URLs
recommendation:  # opinionated: "use X because Y"
alternatives:
risks:
confidence: high | medium | low
```

For in-repo values (enums, schemas, error codes), it tags
`[VERIFIED: path:line-start-line-end]` only after opening the file in this run.

**What it must NOT do:** Dump reports into downstream context. Promote only findings that
change a decision.

### 3.3 Architect

**File:** `.opencode/agents/architect.md`
**Role:** System designer. Owns contracts.
**Can edit code?** Only `.planning/contracts/**` (with approval).
**Can delegate?** No.

**What it produces:**

```yaml
architecture:
  components:
  interfaces:
  data_flow:
  constraints:
  risks:
  decisions:          # written via state adapter, each gets an ID
  contracts_required: # HTTP APIs only in v1
  integration_points:
```

**Contract ownership rules:**
- Architect owns contract versions
- Implementer may propose but not merge a contract change
- For incompatible changes: bump version, mark prior version superseded, list consumers,
  route to Team Lead for human gate H2 plus consumer re-planning
- V1 enforces HTTP API contracts only (OpenAPI + generated types + contract tests)
- Event, database, and service-interface contracts are documentation-only

**What it considers:** Existing architecture from GSD's codebase analysis, dependency
relationships from the code intelligence provider, security, performance, testability,
deployment.

**Design checklist dispositions:** Architecture output is a decision with no artefact for a
gate to execute against. For tasks routed through the Architect (`ARCHITECTURE_TASK=1`, task id
in `RETRO_TASK`), each item in `framework/architecture/design_checklist.yaml` gets a recorded
verdict written to `<state_root>/retro/checklist/<task>.json`;
`python3 framework/architecture/checklist_check.py dispositions --task <id>` verifies them and
G3 blocks completion when a disposition is owed but missing. Dispositions are reachable only
from architecture work - a checklist item that should be a check stays a check.

### 3.4 Planner

**File:** `.opencode/agents/planner.md`
**Role:** Task decomposer. Turns architecture into bite-sized work.
**Can edit code?** No.
**Can delegate?** No.

**What it produces for each task:**

```yaml
task_id:
phase:
objective:
requirements:        # REQ IDs, never copied text
dependencies:
files_or_components:
contracts:           # contract IDs
acceptance_criteria: # observable, testable
evidence_classes:    # applicable evidence per criterion
complexity: L0-L4
impact: {scope:, contract_change:, public_api_change:, data_change:, security_sensitive:}
assigned_agent: implementer
```

**Key rule:** Tasks must be small enough for one agent to execute in a fresh context. Sequence
work into waves only when files, symbols, contracts, migrations, and configuration do not
overlap. Otherwise serialize. Prefer isolated worktrees for parallel waves.

Defers to GSD's planner and plan-checker where the installed distribution provides them.

### 3.5 Implementer

**File:** `.opencode/agents/implementer.md`
**Role:** Coder. The one that writes and modifies code.
**Can edit code?** Yes - the only one with `edit: allow`.
**Can delegate?** No.

**Before acting:**
- Confirms the plan, referenced requirements, touched contracts, and relevant tests are
  readable
- Missing something critical? Returns `CONTEXT_INSUFFICIENT` naming the item. Does not guess.
- Asks the code intelligence provider for edit context and impact before editing

**While implementing:**
- Respects contracts as given. Proposes changes, never merges them.
- Adds tests for acceptance criteria using the applicable evidence class
- Runs what it can and records exit codes

**Debug mode:** When routed a `TEST_FAILED`, loads the debugging skill and produces:

```yaml
symptom:
root_cause:
contributing_factor:
fix:
verification:        # how the fix was demonstrated, with exit codes
```

Reproduces before fixing. Adds a regression test. Never disables or deletes a test.

**Skills it can load:**
- `frontend-react` - anything under `src/frontend`
- `backend-python` - anything under `src/backend`
- `contract-authoring` - adding or changing an HTTP contract
- `browser-verification` - authoring a Playwright spec
- `retrospective` - analysing a defect escape after the fix has landed

**After a fix:** When the bug is an escape (nothing caught it before acceptance), loads the
retrospective skill and records the trigger with
`python3 framework/retro/ledger.py append ...`; the Team Lead owns the analysis and G7 discharge.

**Finish:** Writes a handoff per `.opencode/rules/handoff.md`, including re-derived impact.
States Definition of Done as claims - does not assert verification.

### 3.6 Reviewer

**File:** `.opencode/agents/reviewer.md`
**Role:** Independent judge. Reads the diff. Never edits.
**Can edit code?** No.
**Can delegate?** No.
**Can run bash?** Only `git diff`, `git log`, `git show`, `grep`.

**What it evaluates:**
- Correctness
- Requirements compliance
- Architecture compliance
- Contract compliance
- Quality and maintainability
- Error handling
- Security concerns
- Performance concerns
- Test adequacy against the applicable evidence class
- Integration risk

**Output format:**

```yaml
review:
  status: approved | changes_required | blocked
  findings:
    - severity: critical | major | minor
      claim:
      evidence: "[VERIFIED: path:lines]"
      affected_files:
      affected_components:
      required_change:
  integration_risks:
```

**Key rule:** Every finding needs a file and line reference. A finding without evidence is a
question, not a finding. Does not restate what a gate already proved.

### 3.7 Verifier

**File:** `.opencode/agents/verifier.md`
**Role:** Proof machine. Produces evidence, not opinions.
**Can edit code?** Only `.planning/**/VERIFICATION.md` and `tests/**` (with approval).
**Can delegate?** No.
**Can run gates?** Yes (`./framework/gates/*`).

**What it does:**

1. Reads the verification profile from the task record
2. For each acceptance criterion, names the applicable evidence class before running anything
3. Records why any class is inapplicable - a skipped applicable class is a failure
4. Runs the gates the impact class requires
5. Writes results to the verification artifact **immediately** (tool output gets pruned; state
   does not)
6. Verifies claims, not intentions - a test that exists but did not execute is not evidence

**Output format:**

```yaml
verification:
  status: pass | fail | unverifiable
  criteria:
    - requirement: REQ-017
      evidence_class: contract_test
      command:
      exit_code: 0
      artifact:
  gates: {g1:, g2:, g3:, g4:}
  profiles_run: []
  unverifiable: []
```

**Browser profile (critical rules):**
- Mandatory for visible-behaviour requirements
- Build, start, navigate, interact, read console, capture screenshots, assert
- If no driver is available, reports `unverifiable` - never as passed
- **Exit 3 from G6 means UNVERIFIABLE, not pass**

**Retrospective completeness:** Before reporting complete, runs
`./framework/gates/g7_retro.sh`: exit 0 = all open triggers discharged; exit 1 = analysis
incomplete or recurrence - block; exit 4 = NOT_APPLICABLE (no escape trigger) - record it as
such, never as a passed retrospective.

**What it must NOT do:** Edit source. Round unverifiable up to pass.
---

## 4. How Agents Talk to Each Other

Agents never pass raw reasoning to each other. They communicate through **structured handoffs**
written to GSD state.

### Handoff Format

Written via `python3 framework/adapters/gsd_state.py write-summary`:

```yaml
task_id: 03-02
agent: implementer
status: complete | blocked | failed
summary: <= 5 lines
files_changed: []
symbols_changed: []
contracts_touched: []
decisions_created: []
tests: {added: [], run: [], result: pass|fail}
evidence: ["[VERIFIED: src/auth/service.py:41-58]"]
impact_rederived: {scope: local, contract_change: false, public_api_change: false}
risks: []
blockers: []
next_action: review | verify | escalate
```

### Why This Matters

OpenCode prunes old tool outputs and auto-compacts context. If agents passed reasoning as
conversation text, it would be lost. Handoffs written to disk survive compaction.

---

## 5. The Two-Axis Classification System

Every task is classified on two independent axes. This determines everything: how much
planning is needed, which gates run, how wide the context window is, and whether a human
needs to approve.

### Axis 1: Complexity

Determines **planning depth** - how much decomposition is needed before coding starts.

| Level | Name | Planning Needed | Example |
|---|---|---|---|
| L0 | Trivial | None | Fix a typo, change a constant |
| L1 | Simple | Minimal | Add a field to a form, write a single endpoint |
| L2 | Moderate | Full decomposition | Add a new feature with frontend + backend |
| L3 | Complex | Research + architecture + decomposition | New authentication system |
| L4 | Very Complex | Full pipeline with human gates | Payment processing, data migration |

### Axis 2: Impact

Determines **which gates run** and **how wide the context window is**.

| Dimension | Values | Effect |
|---|---|---|
| scope | local, component, cross_component, system | Determines gate set |
| contract_change | true/false | If true, routes to Architect + H2 |
| public_api_change | true/false | Forces at least `cross_component` scope |
| data_change | true/false | Activates release profile (H3) |
| security_sensitive | true/false | Activates security profile |

**Impact is re-derived after implementation** from the actual diff. If the real impact is
wider than originally classified, context expands and additional gates activate.

---

## 6. The Eight Gates (G1-G8)

Gates are **executable shell scripts** that return exit codes. The model interprets results;
it does not decide whether a gate passed. Each gate is independent.

### 6.0 Shared Library (framework/gates/_lib.sh)

Every gate sources this file first. It provides:

| Helper | What it does |
|---|---|
| `log()` | Prints `[gate_name] message` |
| `skip()` | Logs SKIP and exits 0 (not applicable) |
| `pass()` | Logs PASS and exits 0 |
| `fail()` | Logs FAIL and exits 1 |
| `persist()` | Writes result to GSD state immediately |
| `have()` | Checks if a command exists |
| `changed_files()` | Lists modified + new files (cwd-relative) |
| `changed_source_files()` | Same but excludes framework bookkeeping |

**Python detection:** If `python3` is not found but `python` is (Windows), creates a shim
function so all gates work unchanged.

**State root normalization:** Converts absolute state root paths to cwd-relative so they
can be compared against `changed_files()` output.

### 6.1 G1 - Contract Validation

**File:** `framework/gates/g1_contract.sh`
**When it runs:** `contract_change: true` in the impact class
**What it checks:**

1. **Schema validity** - Runs `python3 framework/contracts/validate_schema.py` on every
   `*.openapi.y*ml` file in `.planning/contracts/`
2. **Generated type drift** - Runs `python3 framework/contracts/gen_types.py --check` to
   ensure committed types match the schema
3. **Contract change detection** - Diffs contracts against HEAD to distinguish a legitimate
   change (route to Architect + H2) from a violation (route to Implementer)
4. **Contract tests** - Runs `pytest tests/contract/` or executes test files standalone

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Schemas valid, types in sync, contract tests green |
| 1 | Contract validation failed |
| 2 | BLOCKED (python3 unavailable) |

**Special behavior:**
- `CONTRACT_CHANGE` outranks test failure - a schema change causes test failures by
  definition, so the root cause (the change) routes to Architect, not the symptom (test failure)
- A missing `tests/contract/` directory = automatic FAIL
- Missing tools report BLOCKED, never PASS

### 6.2 G2 - Impact Validation

**File:** `framework/gates/g2_impact.sh`
**When it runs:** Always (but skips if no source changes)
**What it checks:**

1. **Index freshness** - If the code intelligence index is stale, reindexes
2. **Changed file count** - Skips if zero changes
3. **Affected tests** - Asks the code intelligence adapter which tests are affected. Tier-4
   search prunes `node_modules`, `.git`, `.venv`, `dist`, `build` and friends during the walk,
   so a large dependency tree cannot stall the gate
4. **Unknown impact** - If provider returns zero tests at tier 4 (search fallback), reports
   UNKNOWN_IMPACT

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Impact mapped to N tests |
| 1 | UNKNOWN_IMPACT - search fallback found no tests |

**Key rule:** Unknown impact is never read as no impact.

### 6.3 G3 - Architecture Validation

**File:** `framework/gates/g3_architecture.sh`
**When it runs:** `scope: cross_component` or `scope: system`
**What it checks:**

1. **Forbidden imports** - Reads `framework/architecture_rules.yaml` and checks changed files
   for forbidden import edges
2. **Decision records** - Counts active decisions in `.planning/decisions/`

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Boundaries respected |
| 1 | Architecture boundary violation |
| 2 | BLOCKED (pyyaml missing) |

**Key rule:** Boundaries are declared, never inferred. A rule not in the YAML is not enforced.

### 6.4 G4 - Executable Validation

**File:** `framework/gates/g4_executable.sh`
**When it runs:** Always - every task
**What it checks:**

**JavaScript/TypeScript (if `package.json` exists):**
- `npm run lint` (if script exists)
- `npm test` (if script exists)
- `npm run build` (if script exists)
- `tsc --noEmit` (if tsconfig.json exists)

**Python (if `.py` files exist):**
- `ruff check .` (lint)
- `mypy .` (types)
- `pytest -q` (tests) - or standalone execution if pytest is missing
- `python3 -m py_compile` (syntax check as fallback)

**Two inviolable rules:**
1. **Cannot pass vacuously.** Zero checks executed = FAIL, not pass.
2. **Missing tool is never a pass.** It is either substituted or reported as unavailable.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | N executable checks green |
| 1 | One or more checks failed |

### 6.5 G5 - Frontend Stack Conformance

**File:** `framework/gates/g5_frontend_stack.sh`
**When it runs:** `frontend_files_changed: true`
**What it checks:**

Delegates to `python3 framework/frontend/stack_check.py`, which verifies:

1. **Required tools present** - shadcn/ui, Tailwind v4, Lucide, Motion, Playwright
2. **Forbidden alternates absent** - MUI, Chakra, styled-components, framer-motion, etc.
3. **shadcn config correct** - icon library is `lucide`, tailwind config is empty
4. **Responsive validation** - Playwright config has at least 2 distinct viewport widths
5. **Conditional tool ledger** - Magic UI, Aceternity, GSAP, React Three Fiber need entries in
   `framework/frontend/effect_justifications.yaml`
6. **File rules (ratchet)** - Only changed files are judged:
   - No `style={{ ... }}` (use Tailwind)
   - No raw `<button>`, `<input>`, etc. outside `components/ui/`
   - No inline `<svg>` outside `components/ui/`
   - No `framer-motion` imports (use `motion/react`)

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Frontend stack conformant |
| 1 | Violations found |
| 2 | BLOCKED (could not evaluate) |
| 4 | NOT_APPLICABLE (no frontend present) |

**Key behavior:** Ratchet, not sweep. Pre-existing violations elsewhere are baseline debt -
reported, never blocking, not to be fixed opportunistically.

### 6.6 G6 - Browser Verification

**File:** `framework/gates/g6_browser.sh`
**When it runs:** Requirements with `visible_behaviour` shape
**What it checks:**

1. **Driver availability** - `package.json` exists, `@playwright/test` is a dependency,
   `node_modules/.bin/playwright` is executable
2. **Config exists** - `playwright.config.ts` or `.js`
3. **Specs exist** - At least one spec under `tests/e2e/` or `tests/browser/`
4. **Specs pass** - Runs `playwright test --reporter=list`
5. **Evidence exists** - Counts screenshot artifacts

**Exit codes (THE MOST IMPORTANT PART):**

| Code | Meaning | What you may claim |
|---|---|---|
| 0 | Specs ran and passed | Requirement verified |
| 1 | Specs ran and failed | Requirement violated |
| 3 | UNVERIFIABLE - no driver, config, or specs | **Nothing** |

**Exit 3 is deliberately not 0.** "We could not look" must never read as "it looks right."
This is the single most important rule in the entire framework.

**Artefacts:** Screenshots and traces land in `framework/telemetry/browser/artifacts/`,
run log in `last-run.txt`.

### 6.7 G7 - Retrospective Completeness

**File:** `framework/gates/g7_retro.sh`
**When it runs:** On task completion when a defect-escape trigger is open

**What it checks:**
1. Every open trigger under `<state_root>/retro/triggers/` has a recorded analysis
2. Each recommendation names exactly one target from `framework/retro/containment_map.yaml`
   (falsifiable, with a command that proves the change landed), or is explicitly
   `none_human_judgement` with a stated reason
3. Claimed fixes carry `fix_verified_by`: a command plus its result
4. Recurrences - the same structural signature twice - are present and blocking

**Exit codes:**

| Code | Meaning | What you may claim |
|---|---|---|
| 0 | All open triggers discharged correctly | Retrospective complete |
| 1 | Analysis incomplete or recurrence unhandled | Nothing - fix first |
| 2 | BLOCKED (python3/pyyaml absent) | Nothing |
| 4 | NOT_APPLICABLE - no escape trigger recorded | Nothing (normal clean-task case) |

**Exit 4 is not a pass.** No trigger means nothing escaped *this time*; it is not evidence the
framework is learning.

**Supporting modules:** `framework/retro/ledger.py` (trigger recording, structural signature
matching, recurrence detection) and `framework/retro/escape_path.py` (computes the checkpoints
a defect passed through - arithmetic, not argument).

### 6.8 G8 - Blocker Escalation

**File:** `framework/gates/g8_blockers.sh`
**When:** Always runs alongside G4 in the functional profile
**Purpose:** A non-complete stop must land as a visible record, not vanish into a quiet agent

An agent that stops without completing (CONTEXT_INSUFFICIENT, BLOCKED, UNKNOWN_IMPACT) writes a
record first: `python3 framework/adapters/gsd_state.py write-blocker --json '{"signal": "CONTEXT_INSUFFICIENT", "task_id": "03-02", "agent": "implementer", "missing_item": "...", "tried": "..."}'`.
The store is `<state_root>/blockers.yaml`. A repeat of the same `(task_id, signal)` pair upserts --
retries rise to max(existing, incoming), so the retry count survives agent restarts.

**Exit codes:**

| Code | Meaning | What you may claim |
|---|---|---|
| 0 | No open blockers | Nothing blocked completion |
| 1 | Open blockers exist, listed with id/signal/retries | Completion refused until resolved |
| 2 | BLOCKED - no python3/pyyaml, adapter failure, or unparsable listing | Nothing. An unreadable store never reads as zero |

Resolve with `python3 framework/adapters/gsd_state.py resolve-blocker --id BLK-nnn`; an unknown id
fails loudly (`NOT_FOUND`). G7 refuses completion on an incomplete retrospective -- G8 applies the
same enforcement shape to escalation debt.

---

## 7. The Three Adapters

Adapters bridge the framework to external systems. They are the only place that touches
GSD state, code intelligence, or OpenCode detection.

### 7.1 GSD State Adapter

**File:** `framework/adapters/gsd_state.py`
**Purpose:** Read/write project state stored in `.planning/` (GSD Core) or `.gsd/` (GSD-PI)

**Commands:**

| Command | What it does |
|---|---|
| `detect` | Identifies installed GSD distribution |
| `manifest` | Returns cached detection result. The cache is environment-specific (absolute paths); bootstrap purges it at start so detection always reflects THIS machine. A cached entry missing required keys is treated as invalid and detection re-runs |
| `state-root` | Returns the state directory path |
| `health` | Checks expected files exist, counts dirty files |
| `selftest` | Round-trip write/read test |
| `current-phase` | Lists phases, returns current one |
| `project` | Reads `PROJECT.md` |
| `requirements` | Reads `REQUIREMENTS.md` |
| `requirement --id X` | Reads a single requirement block |
| `roadmap` | Reads `ROADMAP.md` |
| `plan-path --task X` | Finds the plan file for a task |
| `contract --id X` | Reads a contract schema |
| `write-summary --task X --json Y` | Writes a task handoff |
| `write-verification --phase X --json Y` | Appends verification results |
| `write-decision --id X --json Y` | Writes an architecture decision |
| `write-contract --id X --json Y` | Writes an OpenAPI schema |
| `write-telemetry --json Y` | Appends a telemetry record |
| `write-blocker --json Y` | Upserts an open escalation blocker keyed by (task_id, signal); retries = max(existing, incoming) |
| `resolve-blocker --id X` | Marks one open blocker resolved; unknown id fails loudly |
| `list-blockers [--text]` | Lists OPEN blockers as JSON; `--text` prints one line each for gate output |

**Without GSD:** Returns `{"distribution": "none"}`. Falls back to `.planning/` as a plain
directory. State-dependent features return empty until populated.

### 7.2 Code Intelligence Adapter

**File:** `framework/adapters/code_intel.py`
**Purpose:** Provide code analysis capabilities through a tiered priority system

**Priority ladder:**

| Tier | Source | When available |
|---|---|---|
| 1 | Native GSD capability | `gsd` binary on PATH |
| 2 | LSP / ripgrep | `rg` binary available |
| 3 | CodeGraph provider | `codegraph`, `code-graph-mcp`, or `symgraph` |
| 4 | Grep + path conventions | Always (fallback) |

**Capabilities:**

| Capability | What it does |
|---|---|
| `symbol_search` | Find where a symbol is defined |
| `relationships` | Find callers, callees, dependencies |
| `impact` | Blast radius of changing a symbol |
| `affected_tests` | Which tests are affected by changed files |
| `freshness` | Is the index stale? |
| `reindex` | Force a reindex |
| `edit_context` | What the agent needs before editing |
| `locate` | Find a symbol's file and line |

**Key behavior:** The framework must remain functional with the provider absent, degrading
to tier 4 with a logged warning.

### 7.3 OpenCode Detection Adapter

**File:** `framework/adapters/opencode_detect.py`
**Purpose:** Detect the OpenCode host version and directory naming conventions

**What it detects:**
- OpenCode version (from `opencode --version`)
- Directory naming (plural vs singular: `agents/` vs `agent/`)
- Permission schema version
- Compaction behavior (auto, prune, hazard)
- Config precedence order

---

## 8. The Five Skills

Skills are loaded by the Implementer when a task requires domain-specific knowledge. The five
framework-authored skills are documented below; the installed GSD distribution additionally ships
~70 `gsd-*` skills under `.opencode/skills/` (run `ls .opencode/skills` for ground truth).
Each skill is a `SKILL.md` file with YAML frontmatter.

### 8.1 frontend-react

**File:** `.opencode/skills/frontend-react/SKILL.md`
**When to load:** Task touches `src/frontend`, components, styling, icons, animation

**Required stack:**

| Concern | Tool |
|---|---|
| Component library | shadcn/ui |
| Styling | Tailwind v4 |
| Icons | lucide-react |
| Animation | motion (from `motion/react`) |
| Browser testing | @playwright/test |

**File rules:**
- No `style={{ ... }}` - use Tailwind (escape: `// stack-allow: inline-style`)
- No raw HTML form elements outside `components/ui/`
- No inline `<svg>` outside `components/ui/`
- No `framer-motion` imports

**Contracts:** Never redeclare a request/response type that a contract already defines.
Import from `src/frontend/contracts/` (generated, do-not-edit).

### 8.2 backend-python

**File:** `.opencode/skills/backend-python/SKILL.md`
**When to load:** Task touches `src/backend`, API endpoints, business logic, persistence

**Rules:**
- Never widen a response beyond what the contract declares
- Never remove boundary validation to make a test pass
- A required field stays required (tightening/loosening = contract change -> Architect + H2)

**Contract tests:** Live in `tests/contract/`, run under pytest or standalone. No import
of a library that may be absent without a fallback.

**Architecture boundaries:** `src/domain/` may not import `requests`, `axios`, `psycopg`,
or `fetch` - domain logic stays transport-free.

### 8.3 contract-authoring

**File:** `.opencode/skills/contract-authoring/SKILL.md`
**When to load:** Adding or changing an HTTP contract, or when G1 reports CONTRACT_CHANGE

**Anatomy of a contract:**
- `api-NNN.openapi.yaml` - the schema (single source of truth)
- `api-NNN.meta.yaml` - id, version, status, owner, consumers
- Generated types in `src/backend/contracts/` and `src/frontend/contracts/`

**Changing an existing contract:**
1. Routes to Architect (owns contract versions)
2. Requires human gate H2 when incompatible
3. Invalidates in-flight parallel work - Team Lead re-plans
4. Bump version in meta file. Never edit a shipped version in place.

### 8.4 browser-verification

**File:** `.opencode/skills/browser-verification/SKILL.md`
**When to load:** Requirement concerns visual alignment, interaction flow, responsive layout

**Gate:** `bash framework/gates/g6_browser.sh`

**Writing good assertions:**
- Alignment: compare `boundingBox()` gaps against viewport with stated tolerance
- Responsive: branch on `page.viewportSize()`, assert different expectations per width
- Console: collect `console` errors and `pageerror`, assert array is empty
- Prefer `getByTestId` / roles over CSS selectors

**Playwright MCP:** Available for exploration and diagnosis. Use MCP to author or debug a
spec. Do not use it as evidence - MCP output is a conversation transcript that gets pruned.
Committed specs plus G6 exit code are the durable artefact.

### 8.5 retrospective

**File:** `.opencode/skills/retrospective/SKILL.md`
**When to load:** A defect was found after the change that introduced it was accepted - a
previously-green test failing, a review rejection, a reopened task, an integration failure, or
a production defect.

**Method:**
1. Classify against the six trigger signals in `retry_policy.yaml: retro_triggers`
2. Run `python3 framework/retro/escape_path.py`: injected where, caught where, which checkpoints
   did it pass through?
3. Routing gap (checkpoint would have caught it but never ran) outranks containment miss
   (checkpoint ran and missed) - activating an existing gate beats making one smarter
4. Name exactly one target from `framework/retro/containment_map.yaml` - falsifiable, with the
   command that proves the change landed - or `none_human_judgement` with a stated reason

**Hard rules:** Unfalsifiable recommendations are rejected ("be more careful" cannot fail, so
cannot be verified). A claimed fix needs an exit code. Recurrence escalates to a human with
zero retries - filing a third variant of the same fix is the failure mode.

---

## 9. The Four Rules

Rules are loaded as instructions but never inlined into agent definitions.

### 9.1 Evidence Applicability

**File:** `.opencode/rules/evidence.md`

Maps requirement shapes to the strongest applicable evidence:

| Requirement shape | Strongest evidence |
|---|---|
| API returns a status for given input | Contract test or integration test |
| Business rule produces a value | Unit test |
| Type or interface correctness | Type check and build |
| Visual alignment or styling | Browser screenshot + DOM inspection |
| Interaction flow end to end | Browser navigation + console output |
| No unauthorized dependency | Dependency and security scanner |
| Authorization denies a role | Integration test against running system |
| Latency budget | Measured benchmark |
| Migration applies and rolls back | Executed migration in disposable environment |
| Responsive layout at a width | Playwright with that viewport |
| Mandated tool/library is used | G5 stack conformance exit code |
| Conditional visual tool is permitted | Ledger entry naming requirement + approver |

**Key principle:** Unverifiable is not pass. When evidence cannot be produced, record the
requirement as unverifiable and name what is missing.

### 9.2 Definition of Done

**File:** `.opencode/rules/definition-of-done.md`

**Definition of Done** = claims asserted by the Implementer (requirements addressed, code
implemented, tests added, contracts updated, review passed, gates invoked).

**Verification** = evidence that each claim is true in this run (test executed, exit code
zero, artifact exists).

A test that exists but was not executed is not evidence. A gate configured but skipped is
not a pass. Never mark work complete on an implementation agent's report alone.

### 9.3 Handoff

**File:** `.opencode/rules/handoff.md`

Defines the structured YAML format that agents use to communicate. (See Section 4.)

### 9.4 Retrospective Intelligence

**File:** `.opencode/rules/retrospective.md`

A defect that reaches production is two failures: the defect, and the framework that passed it.
Key points:
- A retro is owed on the six trigger signals; NOT owed when a checkpoint catches the defect at
  the first place it could have been caught (that is the framework working)
- The escape path is computed, not argued; recommendations must name one target from the
  containment map or be explicitly `none_human_judgement`
- Lessons land at the tier the analyser names - executable_check, declared_rule,
  design_checklist (architecture only), agent_instruction, unmapped_combination, accepted -
  never lower for convenience
- A checklist item that should be a check stays a check; recurrence outranks any single retro
---

## 10. The Context Builder Tool

**File:** `.opencode/tools/context-builder.ts`
**Purpose:** Resolve a task's pointer set into paths, symbol locations, contracts, and impact

**What it returns:**

```json
{
  "task_id": "03-02",
  "level": "targeted",
  "pointers": {
    "plan": "path/to/plan.md",
    "requirements": [{"id": "REQ-001", "resolve": "gsd_state.py requirement --id REQ-001"}],
    "contracts": [{"id": "api-001", "schema": ".planning/contracts/api-001.openapi.yaml"}],
    "decisions": [{"id": "DEC-001", "path": ".planning/decisions/DEC-001.md"}]
  },
  "symbols": [{"symbol": "UserService", "location": "src/backend/user_service.py:42"}],
  "impact": { "set": "...", "affected_tests": "...", "freshness": "..." },
  "materialised_chars": 1200,
  "truncated": [],
  "provider_tier": "4"
}
```

**Hard constraints:**
- `EXCERPT_CAP_CHARS = 2000` per materialized excerpt
- `TOTAL_MATERIALISE_CAP = 8000` per invocation
- Prefers pointers over copied content
- Materializes only contract schemas (which agents must match exactly)
- Returns `CONTEXT_INSUFFICIENT` if critical items are unreadable

---

## 11. The Telemetry Plugin

**File:** `.opencode/plugin/telemetry.ts`
**Purpose:** Record one telemetry record per session (`record_version: 2`), written through the state adapter

**What it tracks:**

| Field | What it counts |
|---|---|
| `agents` | Per-agent attribution: invocations, tool calls, ms, token split, model ids |
| `skills_loaded` | Which skills were loaded |
| `graph_queries` | Code intelligence queries made |
| `fallbacks_used` | Times the provider fell back to tier 4 |
| `files_read` | Files read during the task |
| `context_expansions` | Times context was expanded to system width |
| `materialised_chars` | Characters materialized by context builder |
| `gates` | Per-gate result parsed from the stable `[gate] ...` stdout line (pass / fail / skip / n-a / unverifiable / blocked, plus ms) |
| `retries` | Per-retry-type counts |
| `tokens` | Input/output/reasoning/cache token counts (streaming diffs, not sums) |
| `models_seen` | Provider/model ids observed, with request counts |
| `provider_tier` | Last context-builder provider tier; tier 4+ increments fallbacks |
| `truncations` | Context-builder entries truncated at the excerpt cap |
| `human_gates` | H1/H2/H3 human checkpoints observed in output |
| `duration_s` | Wall-clock time |
| `defect_escapes` | Escape-path computations run (one per recorded escape) |
| `retros_recorded` | Retro ledger entries appended via `retro/ledger.py` |
| `retro_recurrences` | G7 RECURR markers -- a filed fix did not close the gap |
| `retro_fix_targets` | Containment targets named by filed retrospectives |
| `blockers_opened` | write-blocker calls that landed (exit 0 or BLOCKER_ id echoed) |
| `blockers_resolved` | resolve-blocker calls that discharged an open blocker (exit 0 or RESOLVED marker) |
| `blocker_signals` | Signal names captured from write-blocker payloads |

**When it flushes:** On the `session.idle` EVENT, delivered through the `event` hook -- registering `session.idle` as a hook key silently collects nothing. Written to `.planning/telemetry/records.jsonl`. Operating guide: section 25.

**Why it exists:** OpenCode prunes old tool outputs. Telemetry written to disk survives.

---

## 12. The Verifier Profiles

**File:** `framework/verifier/profiles.yaml`
**Purpose:** Define which verification activities activate for which impact classes

### Profiles

| Profile | When activated | Evidence classes | Commands |
|---|---|---|---|
| functional | Always | unit_test, integration_test | `g4_executable.sh` |
| contract | `contract_change: true` | contract_test, generated_type_diff | `g1_contract.sh` |
| browser | `requirement_shape: visible_behaviour` | screenshot, dom_inspection, console_output | `g6_browser.sh` |
| frontend_stack | `frontend_files_changed: true` | stack_conformance_exit_code | `g5_frontend_stack.sh` |
| security | `security_sensitive: true` | dependency_scan, authz_integration_test, secret_scan | `npm audit`, `pip-audit` |
| performance | `scope: [cross_component, system], hot_path: true` | measured_benchmark | (manual) |
| release | `data_change: true, or_deployment_affected: true` | build_artifact, migration_applied_and_rolled_back | Human gate H3 |
| retro | `defect_escaped: true` - on escape, not every task | escape_path_analysis, ledger_entry, fix_verification_exit_code | `g7_retro.sh` |

### Impact-to-Gate Mapping

| Impact scope | Gates that run |
|---|---|
| local | G2, G4 |
| component | G2, G4, G5 |
| cross_component | G1, G2, G3, G4, G5 |
| system | G1, G2, G3, G4, G5 |

### Shape-to-Gate Mapping

| Requirement shape | Additional gates |
|---|---|
| visible_behaviour | G6 (regardless of impact scope) |

### Event-to-Gate Mapping

Events can activate gates outside the impact class:

| Event | Gates |
|---|---|
| defect_escaped | G7 |

---

## 13. The Retry and Escalation Policy

**File:** `framework/retry_policy.yaml`
**Purpose:** Bound retries, name escalation paths, prevent infinite loops

### Retry Limits (per task, reset on human intervention)

| Failure type | Max retries | On exhaustion |
|---|---|---|
| test_failure | 2 | escalate to human |
| review_rejection | 2 | escalate to human |
| integration_failure | 2 | escalate to human |
| context_expansion | 2 | escalate to human |
| contract_conflict | 0 | immediate escalation |
| architecture_conflict | 0 | immediate escalation |
| release_blocked | 0 | immediate escalation |
| retro_recurrence | 0 | immediate escalation to human |

### Escalation Routes

| Signal | Routes to | Action |
|---|---|---|
| CONTEXT_INSUFFICIENT | same agent | retrieve named item |
| GRAPH_STALE | code_intel adapter | reindex |
| UNKNOWN_IMPACT | same agent | expand to system |
| TEST_FAILED | implementer | debug mode |
| REVIEW_REJECTED | implementer | apply findings |
| INTEGRATION_FAILED | implementer + affected consumers | fix + re-test |
| CONTRACT_CONFLICT | architect -> human gate H2 | negotiate |
| ARCHITECTURE_CONFLICT | architect + team_lead -> human gate H1 | redesign |
| SECURITY_FAILURE | implementer | load security skill |
| PERFORMANCE_FAILURE | implementer | load performance skill |
| RELEASE_BLOCKED | human gate H3 | approve or reject |
| DEFECT_ESCAPED | team_lead | record trigger via ledger, compute escape path, then G7 |
| RETRO_RECURRENCE | human | previous fix failed - reassess the gap, zero retries |
| RETRO_INCOMPLETE | team_lead | complete the retrospective before completion |

The six trigger signals (`retro_triggers`) mark work already accepted:
`TEST_FAILED_ON_PREVIOUSLY_GREEN`, `REVIEW_REJECTED`, `INTEGRATION_FAILED`, `TASK_REOPENED`,
`PRODUCTION_DEFECT`, `GATE_FAILED_AFTER_ACCEPTANCE`.

---

## 14. The Frontend Stack Contract

**File:** `framework/frontend_stack.yaml`
**Purpose:** Source of truth for G5 enforcement. Read by `stack_check.py`.

### Required Tools

| Concern | Tool | Package | Forbidden alternates |
|---|---|---|---|
| Component library | shadcn/ui | @radix-ui/react-dialog | MUI, Chakra, antd, react-bootstrap |
| Styling | Tailwind v4 | tailwindcss | styled-components, @emotion/styled |
| Icons | lucide-react | lucide-react | react-icons, heroicons, fontawesome |
| Animation | motion | motion | framer-motion |
| Browser testing | @playwright/test | @playwright/test | - |
| Responsive validation | Playwright projects | - | min 2 viewports |

### Conditional Tools

| Tool | Packages | Extra required fields |
|---|---|---|
| Magic UI | magicui | requirement, scope, justification, approved_by |
| Aceternity | @aceternity-ui/components | requirement, scope, justification, approved_by |
| GSAP | gsap | + motion_insufficient_because |
| React Three Fiber | @react-three/fiber, @react-three/drei | requirement, scope, justification, approved_by |

### File Rules

| Rule ID | Pattern | Message |
|---|---|---|
| no_inline_style | `style={{` | Use Tailwind utilities |
| no_raw_button | `<button>`, `<input>`, etc. | Import shadcn primitive |
| no_inline_svg | `<svg` | Use Lucide icon |
| motion_import_path | `from "framer-motion"` | Import from motion/react |

### Conditional Tool Justification Ledger

**File:** `framework/frontend/effect_justifications.yaml`

An empty `entries: []` means conditional tools are not permitted. Permission is granted per
requirement, not once per repository.

Example entry:

```yaml
- tool: GSAP
  requirement: REQ-041
  scope: ["src/frontend/features/onboarding/*.tsx"]
  justification: >
    Seven-step scroll-scrubbed sequence with mid-flight reversal.
  motion_insufficient_because: >
    Motion's useScroll drives progress, but the sequence needs one reversible timeline.
  approved_by: architect
  decision: DEC-018
  expires_review: 2026-12-01
```


---

## 15. The Architecture Rules

**File:** `framework/architecture_rules.yaml`
**Purpose:** Declared boundaries enforced by G3

### Forbidden Imports

| From | Must not import |
|---|---|
| `src/frontend/` | `src/backend/`, `prisma/`, `sqlalchemy` |
| `src/backend/` | `src/frontend/components/` |
| `src/domain/` | `axios`, `fetch`, `requests`, `psycopg` |

### Layer Order

```
domain -> application -> infrastructure -> interface
```

**Key rule:** Boundaries are declared, never inferred. A rule not in this file is not enforced.

---

## 16. The State Directory (.planning/)

```
.planning/
  PROJECT.md
  REQUIREMENTS.md
  ROADMAP.md
  STATE.md
  blockers.yaml
  contracts/
    api-001.openapi.yaml
    api-001.meta.yaml
  decisions/
    DEC-001.md
  phases/
    01-discovery/
      01-01-SUMMARY.md
      VERIFICATION.md
    02-implementation/
  telemetry/
    records.jsonl
  retro/
    triggers/
    ledger.jsonl
    checklist/
      <task>.json
```

**Without GSD:** The framework creates `.planning/` with empty files. State-dependent
features return empty until populated. The framework degrades gracefully.

---

## 17. The Validation Suite

**File:** `framework/validate.py`
**Purpose:** 20-section validation suite (~300+ individual checks) that must pass before using
the framework. The check count grows with installed skills; treat any fixed number in older
documents as stale and re-run the suite for ground truth.

### What it checks (section by section)

| Section | Checks |
|---|---|
| 1. Agent definitions | Seven agents exist, correct permissions |
| 2. Delegation topology | Star topology, depth 1 |
| 3. GSD state adapter | Health check, round-trip test |
| 4. Code intelligence | Capabilities resolve, functional without provider |
| 5. Gates executable | All gates exist, G4 returns real exit codes |
| 6. Contract gate | G1 runs, refuses to pass without tests |
| 7. Context builder | Excerpt caps, pointer preference, provider tier |
| 8. Retry/escalation | Limits defined, escalation paths, zero-retry conflicts |
| 9. Rules loaded | Instructions reference rules, AGENTS.md stays small |
| 10. Telemetry collector | Event-hook flush, stdout gate parsing, input-arg reads, streaming dedup, idempotent flush, single plugin copy, config registration |
| 11. Contract fixture | OpenAPI schemas present, contract tests present |
| 12. Gate robustness | Changed files includes untracked, cwd-relative paths, etc. |
| 13. Frontend stack + browser gate | Stack contract enforced by G5; G6 refuses to fetch drivers at gate time |
| 14. Skills + opencode config schema | Skill frontmatter parses; `skills` uses the paths-object form; plugin/MCP wired |
| 15. Retrospective intelligence | Ledger, containment map, escape_path exist; trigger routes wired; skill + rule present |
| 16. Detection cache portability | Manifest cache validated; entries missing required keys force re-detection |
| 17. Architecture design checklist | Checklist files exist; structure validates; dispositions resolve per task |
| 18. Blocker escalation | g8 gate exists and wired (profiles, EXIT_CODES, bootstrap, telemetry, agent duties); behavioural loop proves clean-tree pass, seeded refusal, upsert retries, resolve discharge |
| 19. Telemetry report tool | report.py exits 0/3/2 correctly; renders a valid record; surfaces rework rate and recurrences; unverifiable never aggregated as pass |
| 20. Per-agent model configuration | Every agent model is `{env:OC_MODEL_*}` with an explicit temperature and rationale; profiles.sh baseline/tiered/cheap/reset behaviour verified by execution |

**Run with:** `python3 framework/validate.py`

---

## 18. The Bootstrap Script

**File:** `framework/bootstrap.sh`
**Purpose:** 7-stage initialization sequence

| Stage | What it does |
|---|---|
| 0/7 | Purge `framework/.manifest/*.json` caches - a shipped or cross-OS cache points at the build machine and is trusted blindly |
| 1/7 | Detect OpenCode host |
| 2/7 | Detect GSD distribution, instantiate state adapter |
| 3/7 | Adopt-before-extend audit (shows ADOPT_AUDIT.md) |
| 4/7 | Resolve code intelligence capabilities |
| 5/7 | Verify agent, tool, plugin artifacts exist |
| 6/7 | List skills and rules; `chmod +x framework/retro/*.py`; count gates (g1-g8); report open retro triggers |
| 7/7 | Run full validation suite |

**Run with:** `bash framework/bootstrap.sh`

---

## 19. Permission Model

Permissions are defined in `opencode.json` under each agent's `permission` key.

### Global Defaults

```json
{
  "*": "ask",
  "read": "allow",
  "glob": "allow",
  "grep": "allow",
  "list": "allow",
  "lsp": "allow",
  "edit": "deny",
  "webfetch": "deny",
  "bash": {
    "*": "ask",
    "git status*": "allow",
    "git diff*": "allow",
    "git log*": "allow",
    "git show*": "allow",
    "rm -rf*": "deny",
    "git push*": "deny",
    "git reset --hard*": "deny"
  }
}
```

### Per-Agent Permissions

| Agent | edit | task | bash highlights | playwright |
|---|---|---|---|---|
| team-lead | deny | allow (all) | gates, adapters, retro ledger/escape-path | disabled |
| researcher | deny | deny | webfetch only, python3 framework/adapters/gsd_state.py* | disabled |
| architect | deny (contracts: ask) | deny | python3 framework/adapters/gsd_state.py*, python3 framework/architecture/checklist_check.py* | disabled |
| planner | deny | deny | python3 framework/adapters/gsd_state.py* | disabled |
| implementer | **allow** | deny | pytest, ruff, eslint, tsc, mypy, npm test/build, python3 framework/adapters/gsd_state.py*, python3 framework/retro/* | **enabled** |
| reviewer | deny | deny | git diff/log/show, grep only | disabled |
| verifier | deny (VERIFICATION.md: allow, tests: ask) | deny | pytest, gates incl. g7_retro + g8_blockers, python3 framework/adapters/gsd_state.py*, python3 framework/retro/*, playwright, npm audit | **enabled** |


---

## 20. Every Use Case, Step by Step

### Use Case 1: Fix a Typo (L0)

1. Human tells Team Lead: "Fix the typo in the README"
2. Team Lead classifies: L0, scope=local, no contract/API/data/security impact
3. Team Lead loads `context-builder` to get pointers (trivial - just the file path)
4. Team Lead delegates to Implementer: "Fix typo in README.md line 42"
5. Implementer loads no skills (not frontend/backend/contract/browser)
6. Implementer edits the file
7. Team Lead re-derives impact: local, no changes to gates
8. Team Lead runs G4 only (always runs): `./framework/gates/g4_executable.sh`
9. G4 passes (no Python/JS to lint/test)
10. Team Lead marks complete

### Use Case 2: Add a Form Field (L1)

1. Human: "Add a 'phone number' field to the registration form"
2. Team Lead classifies: L1, scope=component, no contract change
3. Team Lead loads context-builder, gets pointers to plan, requirements, affected components
4. Team Lead delegates to Implementer with `frontend-react` skill
5. Implementer confirms plan and requirements are readable
6. Implementer adds the field using shadcn/ui components and Tailwind
7. Implementer adds a unit test for validation
8. Implementer writes handoff with re-derived impact
9. Team Lead delegates to Verifier
10. Verifier activates: functional profile (G4), frontend_stack profile (G5)
11. G4 runs: lint + types + tests pass
12. G5 runs: stack conformant (shadcn, Tailwind, Lucide used correctly)
13. If requirement is "visible behaviour": G6 runs browser verification
14. Verifier writes verification results to `.planning/phases/X/VERIFICATION.md`
15. Team Lead marks complete

### Use Case 3: New API Endpoint with Contract (L2)

1. Human: "Add a user profile endpoint that returns name, email, avatar"
2. Team Lead classifies: L2, scope=component, contract_change=true
3. Team Lead delegates to Planner
4. Planner creates tasks:
   - Task 1: Author OpenAPI contract (contract-authoring skill)
   - Task 2: Implement backend endpoint (backend-python skill)
   - Task 3: Implement frontend client (frontend-react skill)
   - Task 4: Write contract tests
5. Task 1 goes to Implementer with contract-authoring skill
   - Creates `.planning/contracts/api-002.openapi.yaml`
   - Creates `api-002.meta.yaml` with owner and consumers
   - Generates types: `python3 framework/contracts/gen_types.py --schema ...`
   - Writes contract tests in `tests/contract/`
6. Team Lead runs G1: contract validation passes
7. Task 2 goes to Implementer with backend-python skill
   - Implements endpoint, imports generated contract types
   - Adds unit tests
8. Task 3 goes to Implementer with frontend-react skill
   - Implements client component
   - Adds frontend tests
9. Reviewer reviews all changes
10. Verifier runs G1, G2, G4 (contract_change=true triggers G1)
11. All gates pass, Team Lead marks complete

### Use Case 4: New Authentication System (L3)

1. Human: "Add JWT-based authentication with refresh tokens"
2. Team Lead classifies: L3, scope=system, contract_change=true, security_sensitive=true
3. Team Lead delegates to Researcher: "Investigate JWT library options and security implications"
4. Researcher produces findings with recommendation
5. Team Lead delegates to Architect: "Design the auth system"
6. Architect produces architecture with contract requirements
7. Team Lead triggers H1 (architecture approval) - human reviews and approves
8. Team Lead delegates to Planner: "Decompose auth system into tasks"
9. Planner creates 6+ tasks across frontend and backend
10. Tasks execute in sequence (shared auth state = cannot parallelize)
11. After each task: Reviewer reviews, Verifier verifies
12. Verifier activates: functional, contract, security profiles
13. All gates pass, Team Lead marks complete

### Use Case 5: Payment Processing (L4)

1. Human: "Integrate Stripe payment processing with subscription management"
2. Team Lead classifies: L4, scope=system, contract_change=true, data_change=true, security_sensitive=true
3. Full pipeline: Researcher -> Architect -> H1 -> Planner -> Implementer(s) -> Reviewer -> Verifier
4. Human gate H3 required before release (data_change=true)
5. Additional security audit required
6. Migration plan required and must be tested in disposable environment

### Use Case 6: Debug a Failing Test (L1, debug mode)

1. Team Lead routes TEST_FAILED to Implementer
2. Implementer loads debugging skill
3. Produces:
```yaml
symptom: TestLogin.test_valid_credentials fails with AttributeError
root_cause: Missing import in auth_service.py line 42
contributing_factor: Recent refactor removed unused import that was actually used
fix: Add back the import statement
verification: pytest tests/auth/test_login.py -v (exit 0, 1 test passed)
```
4. Implementer adds regression test
5. Team Lead runs G4: all tests pass
6. Team Lead marks complete

### Use Case 7: Contract Change (L2, incompatible)

1. Human: "Change the /api/users response to include 'role' field (breaking change)"
2. Team Lead classifies: L2, scope=component, contract_change=true
3. G1 detects CONTRACT_CHANGE (diff against HEAD shows schema moved)
4. Routes to Architect for version bump
5. Architect bumps version, marks prior as superseded
6. Team Lead triggers H2 (human approves incompatible change)
7. Team Lead re-plans affected consumer tasks
8. Consumers re-implement against new contract

---

## 21. File Map

```
StockerPro/
  opencode.json
  AGENTS.md

  .opencode/
    agents/
      team-lead.md
      architect.md
      planner.md
      implementer.md
      reviewer.md
      verifier.md
      researcher.md
      gsd-*.md

    rules/
      evidence.md
      definition-of-done.md
      handoff.md
      retrospective.md

    skills/
      frontend-react/SKILL.md
      backend-python/SKILL.md
      contract-authoring/SKILL.md
      browser-verification/SKILL.md
      retrospective/SKILL.md
      gsd-*/SKILL.md

    tools/
      context-builder.ts

    plugin/
      telemetry.ts

  framework/
    gates/
      _lib.sh
      g1_contract.sh
      g2_impact.sh
      g3_architecture.sh
      g4_executable.sh
      g5_frontend_stack.sh
      g6_browser.sh
      g7_retro.sh
      g8_blockers.sh

    adapters/
      gsd_state.py
      code_intel.py
      opencode_detect.py

    verifier/
      profiles.yaml

    retro/
      README.md
      containment_map.yaml
      escape_path.py
      ledger.py

    architecture/
      README.md
      checklist_check.py
      design_checklist.yaml

    frontend/
      stack_check.py
      effect_justifications.yaml

    contracts/
      validate_schema.py
      gen_types.py

    architecture_rules.yaml
    retry_policy.yaml
    frontend_stack.yaml
    bootstrap.sh
    validate.py
    ADOPT_AUDIT.md

  .lifecycle/                          # v1.1 feature-development lifecycle pack (frozen)
    FEATURE_DEVELOPMENT_LIFECYCLE.md   # normative spec (18 phases, state machine, ledger format)
    INTEGRATION.md                     # binding to existing framework (G1-G6 definition wins)
    config.yml                         # depths, phases, legal_transitions, gate_prerequisites, priority
    schema/
      state.schema.json                # state.json validation (additionalProperties: false)
      trace.schema.json                # trace.yml validation (18 scenario classes, 6 techniques)
      gate.schema.json                 # gate ledger validation (identities, evidence, baselines)
      contract.schema.json             # IFC/EVT contract validation
      defect.schema.json               # DEF-*.md validation (F17 defect records)
      qualification.schema.json        # F0 qualification validation
    scripts/
      lifecycle-validate.py            # 13-check validator (transitions, gates, sync, independence)
      orphan-check.py                  # 11-class orphan detection (AC, SCN, IMP, DES, NFR, acceptance, etc.)
    agents/                            # charter docs (guidance, not new agent defs)
      team-lead.md ... verifier.md
    checklists/
      G0.md ... G8.md                  # per-gate checklist supplements
    templates/
      r1_state_abbrev.json             # abbreviated state template
      trace.yml                        # empty trace template
    fixtures/
      ok-l0/                           # L0 conformance fixture (passes all checks)
      ok-l2/                           # L2 conformance fixture (FEAT-2026-001 copy)
      bad-abbreviated/                 # D1 failure: abbreviated field in state
      bad-depth/                       # D2 failure: wrong depth floor
      bad-gate/                        # GATE-PREREQ failure: missing ledger
      bad-kind/                        # KIND failure: wrong verification kind
      bad-transition/                  # TRANS-ILLEGAL failure: illegal state edge
    tests/
      test_lifecycle.py                # pytest suite (9/9 green)

  features/                            # per-feature engineering state
    FEAT-2026-001/                     # L2 conformance fixture (worked reference)
      state.json                       # state machine (17 transitions, SYSTEM_VERIFIED)
      trace.yml                        # requirements, scenarios, design, tests (zero orphans)
      gates/                           # gate ledgers (G0, G0.5, G1, G2, G3, G4, G7)
      defects/                         # F17 defect records
      F0-qualification.md ... F15-*.md # phase artifacts

  .planning/                           # project-level GSD state (NOT feature state)
    PROJECT.md
    REQUIREMENTS.md
    ROADMAP.md
    STATE.md
    contracts/
    decisions/
    phases/
    telemetry/
    retro/
```


---

## 21a. Lifecycle Integration (v1.1)

The feature-development lifecycle pack (`.lifecycle/`) and the existing framework
(`framework/`, `.opencode/`) operate as two layers with one governance chain:

```
FEATURE LIFECYCLE (.lifecycle/)
  F0 qualification, F1-F5 requirements & test basis, F6-F11 design
  F12-F16 execution, F17 defect learning
  trace.yml, baselines, gate ledgers
        |
        |  supplies artifacts, baselines, immutable evidence
        v
EXISTING GATES (framework/gates/)
  G1 Contract, G2 Impact, G3 Architecture, G4 Executable
  G5 Frontend Stack, G6 Browser/HMI
        |
        v
LIFECYCLE GATES (additive)
  G0, G0.5, G3.5, LG7, LG8-A, LG8-B
        |
        v
HUMAN GATES
  H1 Architecture approval, H2 Incompatible contract change, H3 Release approval
```

### Key bindings

| Aspect | Binding |
|---|---|
| Gate definitions | G1-G6: existing `framework/gates/` definitions win (INTEGRATION.md:28) |
| Lifecycle gates | G0 (eligibility), G0.5 (requirements challenged), G3.5 (design review), LG7 (system verification), LG8-A/B (validation) |
| Gate numbering | LG7/LG8 naming avoids collision with existing G7 (retro) and G8 (blockers) |
| State tracking | `features/<FEAT-ID>/state.json` + `trace.yml` (per-feature); `.planning/` remains project state |
| Evidence | Immutable evidence items: claim/command/commit/environment/timestamp/result_file/checksum |
| Independence | Identity-based: agent_id + session_id in gate ledgers; contributors array in state.json for L4 (§9.1.1) |
| Config | `config.yml` depth floors, legal_transitions, gate_prerequisites, priority bands |
| Validation | `lifecycle-validate.py` (13 checks) + `orphan-check.py` (11 classes) run in CI |
| Conformance | FEAT-2026-001 serves as L2 conformance fixture (not project work) |

### Running lifecycle checks

```bash
# Validate a feature directory (13 checks)
python3 .lifecycle/scripts/lifecycle-validate.py features/FEAT-2026-001

# Check for orphan artifacts (11 classes)
python3 .lifecycle/scripts/orphan-check.py features/FEAT-2026-001/trace.yml

# Run the lifecycle test suite (10 tests)
cd .lifecycle && python3 -m pytest tests/test_lifecycle.py -v
```

### What the lifecycle does NOT own

Release decisions, deployment, rollout sequencing, branch and merge policy,
staffing, schedule commitments, and the internals of G1-G6 or H1-H3.

---

## 22. Exit Code Reference

### Gate Exit Codes

| Gate | Exit 0 | Exit 1 | Exit 2 | Exit 3 | Exit 4 |
|---|---|---|---|---|---|
| G1 Contract | Schemas valid, types sync, tests green | Validation failed | BLOCKED (no python) | - | - |
| G2 Impact | Impact mapped to N tests | UNKNOWN_IMPACT | - | - | - |
| G3 Architecture | Boundaries respected | Boundary violation | BLOCKED (no pyyaml) | - | - |
| G4 Executable | All checks green | One or more failed | - | - | - |
| G5 Frontend Stack | Conformant | Violations found | BLOCKED (can't evaluate) | - | NOT_APPLICABLE |
| G6 Browser | Specs ran and passed | Specs ran and failed | **NEVER EMITTED** | UNVERIFIABLE | - |
| G7 Retro | All open triggers discharged | Analysis incomplete / recurrence | BLOCKED (python3/pyyaml absent) | - | NOT_APPLICABLE (no escape trigger) |
| G8 Blockers | No open blockers | Open blockers listed - completion refused | BLOCKED (no python3/pyyaml/unparsable listing) | - | - |

### Exit 3 is the Most Important Code in the Entire Framework

Exit 3 means "we could not look." It is **never** read as "it looks right."

When G6 returns exit 3:
- You may NOT claim the requirement is verified
- You may NOT claim the requirement is not verified
- You MUST record it as unverifiable
- You MUST name what is missing

### G7 Exit 4 Is Also Not a Pass

Exit 4 means no defect-escape trigger was recorded, so there was nothing to retrospect. That is
the normal case for a clean task - not evidence the framework is learning. Never report it as a
passed retrospective.

### Exit Code Rules

| Rule | Explanation |
|---|---|
| Never pass vacuously | Zero checks executed = FAIL, not pass |
| Missing tool is never a pass | It is either substituted or reported as unavailable |
| CONTRACT_CHANGE outranks test failure | Schema change causes test failure by definition; route root cause to Architect |
| UNKNOWN_IMPACT = escalation | Zero tests found at tier 4 = escalate, never assume no impact |
| G7 exit 4 = NOT_APPLICABLE | No escape trigger this run; never reported as a passed retrospective |

---

## 23. Glossary

| Term | Definition |
|---|---|
| **Agent** | An AI persona with specific instructions, permissions, and capabilities |
| **Gate** | An executable shell script that validates code correctness; returns exit codes |
| **Handoff** | A structured YAML document that agents use to communicate task results |
| **Impact class** | A combination of scope, contract_change, public_api_change, data_change, security_sensitive |
| **GSD** | The General Software Development state management system (kept as integral part) |
| **Context builder** | A tool that resolves task pointers into paths, symbols, contracts, and impact |
| **Tier** | Priority level for code intelligence (1=native, 2=ripgrep, 3=CodeGraph, 4=search fallback) |
| **Ratchet** | G5's behavior of only checking changed files, not sweeping the entire codebase |
| **Skill** | Domain-specific instructions loaded by the Implementer for specialized tasks |
| **Profile** | A named collection of verification activities (functional, contract, browser, etc.) |
| **Escalation** | Automatic routing to a higher-authority agent or human when retries exhaust |
| **Blocker** | An open record in `<state_root>/blockers.yaml` written when an agent stops non-complete; G8 refuses completion while any exists |
| **Contract** | An OpenAPI schema that defines API behavior; the source of truth for API contracts |
| **Boundary** | A declared forbidden import edge enforced by G3 |
| **Traceability** | The link between requirements, plans, tasks, verification results, and telemetry |
| **Blast radius** | The set of files, tests, and components affected by a code change |
| **H1** | Human gate: architecture approval (required for cross-component/system scope) |
| **H2** | Human gate: contract approval (required for incompatible contract changes) |
| **H3** | Human gate: release approval (required for data changes) |
| **L0-L4** | Complexity levels: Trivial, Simple, Moderate, Complex, Very Complex |
| **Escape path** | Checkpoints a defect passed through between injection and detection, computed by `framework/retro/escape_path.py` |
| **Routing gap** | A checkpoint would have caught the defect but never ran; fix the routing first |
| **Containment miss** | A checkpoint ran and missed the defect; fix the check |
| **Containment map** | `framework/retro/containment_map.yaml` - closed list of falsifiable fix targets |
| **Disposition** | Recorded design-time verdict on one architecture checklist item |
| **Trigger / recurrence** | An owed-retrospective signal; a recurrence repeats a signature - zero-retry human escalation |

---

## 24. Practical How-To Guide

This section tells you exactly what to do for every common scenario. Each how-to includes
the exact prompt you give, the exact commands that run, and the exact evidence you collect.

---

### How-To: Start a Fresh Project

**When:** First time using the framework on a new or existing codebase.

**Steps:**

1. Run bootstrap:
```bash
bash framework/bootstrap.sh
```
This runs all 7 stages: detect OpenCode, detect GSD, show audit, resolve code intelligence,
verify artifacts, list skills/rules, run validation.

2. Fill in requirements:
```bash
# Edit .planning/REQUIREMENTS.md - one requirement per line, format:
# - REQ-001: [short name] [description] [shape: api_contract | visible_behaviour | business_rule | etc.]
```

3. Fill in architecture rules:
```bash
# Edit framework/architecture_rules.yaml - add forbidden imports for your project
# Example:
# forbidden_imports:
#   - from: "src/frontend/"
#     must_not_import: ["src/backend/", "src/database/"]
```

4. Run validation to confirm everything works:
```bash
python framework/validate.py
# Expect: 118 PASS, 5 FAIL (all expected for fresh install)
```

**What the 5 expected failures mean:**
- No OpenAPI schemas yet -> will pass when you add contracts
- No contract tests yet -> will pass when you add `tests/contract/`
- No `package.json` -> will pass when you add frontend
- No `playwright.config.ts` -> will pass when you add Playwright
- No browser specs -> will pass when you add E2E tests

---

### How-To: Fix a Bug

**When:** Something is broken and you need it fixed.

**What you say:**
> "Fix the bug where the portfolio value shows $0 when the user has no transactions."

**What happens automatically:**

1. **Team Lead** classifies: L1, scope=local, no contract/API/data/security impact
2. **Team Lead** loads context-builder to find affected files
3. **Team Lead** delegates to **Implementer** with the bug description
4. **Implementer** investigates the code, finds root cause
5. **Implementer** writes a fix + adds a regression test
6. **Implementer** writes a handoff with:
```yaml
symptom: Portfolio page shows $0 when user has no transactions
root_cause: portfolio_value() returns None instead of 0.0 for empty transaction list
fix: Changed portfolio_value() to return 0.0 when transactions is empty
regression_test: Added test_empty_portfolio_returns_zero in tests/test_portfolio.py
verification: pytest tests/test_portfolio.py -v (exit 0, 1 test passed)
```
7. **Team Lead** re-derives impact: local, no contract change
8. **Team Lead** runs G4: `./framework/gates/g4_executable.sh` -> exit 0
9. **Team Lead** marks complete

**Gates that run:** G4 only (always runs)
**Skills loaded:** None (unless it's a frontend bug -> `frontend-react`, or backend -> `backend-python`)

---

### How-To: Add a New Feature (Frontend)

**When:** You need to add a new page, component, or UI element.

**What you say:**
> "Add a notification bell icon in the top nav that shows a red dot when there are unread notifications."

**What happens:**

1. **Team Lead** classifies: L1, scope=component, no contract change
2. **Team Lead** delegates to **Implementer** with `frontend-react` skill loaded
3. **Implementer** follows the skill rules:
   - Uses `lucide-react` for the bell icon (not react-icons, not heroicons)
   - Uses Tailwind for styling (not inline styles, not styled-components)
   - Uses `motion` for animation (not framer-motion)
   - Uses shadcn/ui for any popover/dropdown
4. **Implementer** adds:
   - The bell icon component
   - A badge/red dot using Tailwind
   - Unit test for the component
5. **Team Lead** re-derives impact: frontend_files_changed=true
6. **Team Lead** runs:
   - G4: lint + types + tests -> exit 0
   - G5: stack conformance -> exit 0 (all required tools present, no forbidden alternates)
7. If the requirement is "visible behaviour" (e.g., "the red dot appears when..."):
   - **Team Lead** delegates to **Verifier**
   - **Verifier** runs G6: browser verification -> exit 0 (spec passes)
   - **Verifier** captures screenshot as evidence
8. **Team Lead** marks complete

**Gates that run:** G4, G5 (always for frontend), G6 (if visible_behaviour requirement)
**Skills loaded:** `frontend-react`

---

### How-To: Add a New API Endpoint

**When:** You need a new REST/HTTP endpoint.

**What you say:**
> "Add an endpoint GET /api/portfolios/{id}/performance that returns daily returns for the last 30 days."

**What happens:**

1. **Team Lead** classifies: L2, scope=component, contract_change=true (new endpoint = new contract)
2. **Team Lead** delegates to **Planner**
3. **Planner** creates tasks:
   - Task 1: Write OpenAPI contract for the endpoint
   - Task 2: Implement backend endpoint
   - Task 3: Write contract tests
   - Task 4: Add integration test
4. **Task 1** -> **Implementer** with `contract-authoring` skill:
   - Creates `.planning/contracts/api-003.openapi.yaml`
   - Creates `api-003.meta.yaml`
   - Generates types: `python3 framework/contracts/gen_types.py --schema .planning/contracts/api-003.openapi.yaml`
   - Writes contract tests in `tests/contract/`
5. **Team Lead** runs G1: contract validation -> exit 0
6. **Task 2** -> **Implementer** with `backend-python` skill:
   - Implements the endpoint
   - Imports generated types from contract
   - Adds unit tests
7. **Task 3** -> **Implementer** (contract tests already written in Task 1)
8. **Task 4** -> **Implementer** (integration test)
9. **Reviewer** reviews all changes
10. **Verifier** runs:
    - G1: contract validation -> exit 0
    - G2: impact mapping -> exit 0
    - G4: lint + types + tests -> exit 0
11. **Team Lead** marks complete

**Gates that run:** G1, G2, G4
**Skills loaded:** `contract-authoring`, `backend-python`

---

### How-To: Change an Existing API Contract

**When:** You need to modify an existing endpoint's request/response schema.

**What you say:**
> "Add a 'role' field to the GET /api/users response. This is a breaking change since existing consumers don't expect this field."

**What happens:**

1. **Team Lead** classifies: L2, scope=component, contract_change=true
2. **Implementer** modifies the OpenAPI schema
3. **Team Lead** runs G1: detects CONTRACT_CHANGE (schema diff against HEAD)
4. G1 returns exit 1 with message: "CONTRACT_CHANGE detected - Architect review + human gate H2 required"
5. **Team Lead** routes to **Architect**:
   - Architect bumps the API version (v1 -> v2)
   - Architect marks prior version as superseded
   - Architect records decision in `.planning/decisions/`
6. **Team Lead** triggers **H2** (human gate):
   - You review the change
   - You approve or reject
7. If approved, **Team Lead** re-plans:
   - Task: Update all consumer code to handle new field
   - Task: Update frontend contract types
   - Task: Add backward-compatibility test
8. Each task goes through Implementer -> Reviewer -> Verifier
9. **Team Lead** marks complete

**Gates that run:** G1 (detects change), G2, G4
**Skills loaded:** `contract-authoring`, `backend-python`, `frontend-react`
**Human gates:** H2 (contract approval)

---

### How-To: Add Authentication to the App

**When:** You need to secure endpoints with auth.

**What you say:**
> "Add JWT authentication to all /api endpoints. Only authenticated users can access them."

**What happens:**

1. **Team Lead** classifies: L3, scope=system, contract_change=true, security_sensitive=true
2. **Team Lead** delegates to **Researcher**: "Investigate JWT library options and security implications for FastAPI"
3. **Researcher** produces:
   - Recommended library (e.g., python-jose)
   - Security considerations (token expiry, refresh rotation, JWKS)
   - Comparison of approaches
4. **Team Lead** delegates to **Architect**: "Design the auth system"
5. **Architect** produces:
   - Architecture decision record (ADR)
   - Contract requirements (auth endpoints, token format)
   - Security boundaries
6. **Team Lead** triggers **H1** (architecture approval):
   - You review the architecture
   - You approve or reject
7. **Team Lead** delegates to **Planner**: "Decompose auth system into tasks"
8. **Planner** creates 6+ tasks:
   - Add auth middleware
   - Create login endpoint
   - Create refresh endpoint
   - Protect existing endpoints
   - Add auth tests
   - Add security tests
9. Tasks execute sequentially (shared auth state)
10. **Verifier** activates security profile:
    - `npm audit` -> no vulnerabilities
    - `pip-audit` -> no vulnerabilities
    - Auth integration tests -> all pass
11. **Team Lead** marks complete

**Gates that run:** G1, G2, G3 (architecture boundaries), G4
**Skills loaded:** `backend-python`
**Human gates:** H1 (architecture approval)

---

### How-To: Debug a Failing Test

**When:** A test is failing and you don't know why.

**What you say:**
> "The test_login_success test is failing with AttributeError: 'NoneType' object has no attribute 'email'"

**What happens:**

1. **Team Lead** detects: TEST_FAILED signal
2. **Team Lead** routes to **Implementer** (debug mode)
3. **Implementer** investigates:
   - Reads the test file
   - Reads the code under test
   - Identifies root cause
4. **Implementer** writes handoff:
```yaml
symptom: test_login_success fails with AttributeError on .email
root_cause: LoginService.login() returns None when user not found, but test expects User object
contributing_factor: Recent refactor changed return type but test was not updated
fix: Updated LoginService.login() to raise NotFoundError instead of returning None
regression_test: Added test_login_nonexistent_user_raises_not_found
verification: pytest tests/auth/test_login.py -v (exit 0, 3 tests passed)
```
5. **Implementer** applies fix + adds regression test
6. **Team Lead** runs G4: all tests pass
7. **Team Lead** marks complete

**Gates that run:** G4
**Skills loaded:** None (or `backend-python` if it's a backend test)

---

### How-To: Run Gates Manually

**When:** You want to check if your code passes without going through the full workflow.

```bash
# Always runs - lint, types, tests, build
./framework/gates/g4_executable.sh

# Contract validation (only if you have OpenAPI schemas)
./framework/gates/g1_contract.sh

# Impact mapping (only if you have code intelligence)
./framework/gates/g2_impact.sh

# Architecture boundaries (only for cross-component/system scope)
./framework/gates/g3_architecture.sh

# Frontend stack conformance (only if you changed frontend files)
./framework/gates/g5_frontend_stack.sh

# Browser verification (only if you have Playwright specs)
./framework/gates/g6_browser.sh

# Retrospective completeness (when a defect-escape trigger is open)
./framework/gates/g7_retro.sh

# Blocker hygiene (completion refused while any open blocker exists)
./framework/gates/g8_blockers.sh
```

**Exit code interpretation:**
- `0` = PASS
- `1` = FAIL (fix the issue)
- `2` = BLOCKED (missing tool - install it or skip)
- `3` = UNVERIFIABLE (G6 only - you cannot prove the requirement)
- `4` = NOT_APPLICABLE (G5/G7 - nothing in scope this run; never read as pass)

---

### How-To: Add a New Requirement

**When:** You have a new feature to implement.

**Steps:**

1. Add to `.planning/REQUIREMENTS.md`:
```markdown
## REQ-042: Portfolio Performance Chart

**Description:** Display a line chart showing portfolio value over the last 90 days.

**Shape:** visible_behaviour (requires browser verification)

**Acceptance criteria:**
- Chart renders with data points for each trading day
- X-axis shows dates, Y-axis shows portfolio value
- Chart is responsive (works on mobile and desktop)
- Loading state shows spinner while data loads
```

2. When the Team Lead processes this requirement:
   - Shape is `visible_behaviour` -> G6 will run
   - Scope is `component` -> G2, G4, G5 will run
   - No contract change -> G1 will NOT run

---

### How-To: Add a New Skill

**When:** You need domain-specific instructions for a type of task.

**Steps:**

1. Create the skill directory:
```bash
mkdir -p .opencode/skills/my-skill
```

2. Create `SKILL.md`:
```markdown
---
name: my-skill
version: 1
---

# My Skill

## When to Load
Load this skill when the task touches [specific domain].

## Required Stack
| Concern | Tool |
|---|---|
| [concern] | [tool] |

## Rules
1. [Rule 1]
2. [Rule 2]

## File Rules
- No [pattern] - use [alternative] instead
```

3. Reference it in the Implementer's skill list in `opencode.json`

---

### How-To: Set Up Browser Verification

**When:** You need to verify visual/interaction requirements.

**Steps:**

1. Install Playwright:
```bash
npm install -D @playwright/test
npx playwright install chromium
```

2. Create `playwright.config.ts`:
```typescript
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 720 } } },
    { name: 'mobile', use: { viewport: { width: 375, height: 812 } } },
  ],
});
```

3. Write a spec in `tests/e2e/portfolio.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';
test('portfolio chart renders', async ({ page }) => {
  await page.goto('/portfolio');
  await expect(page.getByTestId('portfolio-chart')).toBeVisible();
  await page.screenshot({ path: 'artifacts/portfolio-chart.png' });
});
```

4. Run G6:
```bash
./framework/gates/g6_browser.sh
# Exit 0: specs passed, screenshots captured
# Exit 3: UNVERIFIABLE (missing config or specs)
```

---

### How-To: Set Up Contract Testing

**When:** You need to enforce API contracts.

**Steps:**

1. Create OpenAPI schema:
```yaml
# .planning/contracts/api-001.openapi.yaml
openapi: 3.1.0
info:
  title: StockerPro API
  version: 1.0.0
paths:
  /api/portfolios:
    get:
      summary: List portfolios
      responses:
        "200":
          description: Success
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Portfolio"
components:
  schemas:
    Portfolio:
      type: object
      required: [id, name, value]
      properties:
        id:
          type: string
        name:
          type: string
        value:
          type: number
```

2. Create meta file:
```yaml
# .planning/contracts/api-001.meta.yaml
id: api-001
version: 1.0.0
status: active
owner: backend-team
consumers:
  - web-frontend
```

3. Write contract tests in `tests/contract/test_api_001.py`:
```python
import pytest
# Test that the API response matches the schema
def test_portfolio_list_matches_schema():
    response = get("/api/portfolios")
    assert response.status_code == 200
    for portfolio in response.json():
        assert "id" in portfolio
        assert "name" in portfolio
        assert "value" in portfolio
```

4. Run G1:
```bash
./framework/gates/g1_contract.sh
# Exit 0: schemas valid, types in sync, contract tests green
```

---

### How-To: Check What Gates Will Run

**Before** you start working, determine which gates will activate:

| Your change | Gates that will run |
|---|---|
| Fix a typo in a comment | G4 only |
| Add a React component | G4, G5 |
| Add a React component + visual requirement | G4, G5, G6 |
| Add a Python endpoint | G4 |
| Add a new API contract | G1, G2, G4 |
| Change an existing API contract | G1 (CONTRACT_CHANGE), G2, G4 |
| Add authentication | G1, G2, G3, G4, G6 |
| Cross-component refactor | G1, G2, G3, G4, G5 |
| Database migration | G1, G2, G3, G4 + H3 (human gate) |
| Defect escaped past acceptance | G7 + retro ledger (Team Lead opens, Verifier enforces) |

---

### How-To: Understand the Handoff Format

Every agent writes a handoff when done. Here is what each field means:

```yaml
task_id: 03-02              # Which task in which phase
agent: implementer          # Who did the work
status: complete            # complete | blocked | failed
summary: <= 5 lines         # What was done (human-readable)
files_changed:              # Files that were modified
  - src/backend/portfolio.py
  - tests/test_portfolio.py
symbols_changed:            # Specific functions/classes that changed
  - portfolio_value
contracts_touched:          # Contract schemas that were modified
  - api-001.openapi.yaml
decisions_created:          # Architecture decisions made
  - DEC-003
tests:
  added:                    # New tests written
    - tests/test_empty_portfolio.py
  run:                      # Tests that were executed
    - tests/test_portfolio.py
  result: pass              # pass | fail
evidence:                   # Concrete proof
  - "[VERIFIED: src/backend/portfolio.py:41-58]"
  - "[TEST: pytest tests/test_portfolio.py -v (exit 0)]"
impact_rederived:           # Actual impact after implementation
  scope: local              # local | component | cross_component | system
  contract_change: false
  public_api_change: false
risks: []                   # Known risks
blockers: []                # What prevented completion
next_action: verify         # What should happen next
```

**Why this matters:** When OpenCode compacts old tool outputs, the handoff on disk is the
only record of what happened. It is how the Team Lead knows what to do next.


## 25. Telemetry and Model Tuning

One record per session, appended through the state adapter. The subsystem answers the two
questions the framework was instrumented for: where does cost accumulate, and is narrowing
context costing correctness. Nothing needs enabling -- the plugin ships registered, and the
report reads whatever has accumulated.

### 25.1 The three pieces

| Piece | Location | Role |
|---|---|---|
| Collector | `.opencode/plugin/telemetry.ts` | Hooks `chat.params`, `tool.execute.before`, `tool.execute.after`, and `event`; flushes one JSON record per session to `<state-root>/telemetry/records.jsonl` through `gsd_state.py write-telemetry` |
| Report | `framework/telemetry/report.py` | Aggregates records into cost, rework-rate, and bottleneck views; `--json` for machines, `--verbose` for per-agent models and gate detail |
| Profiles | `framework/models/profiles.sh` | Sets the `OC_MODEL_*` variables that `opencode.json` consumes via `{env:...}` indirection |

Report exit codes: `0` produced, `3` nothing has run yet (not a failure), `2` records exist
but none parse. Optional: `export TASK_ID=03-02` before a run so each record carries the
task it belongs to.

### 25.2 Reading a report

```bash
python3 framework/telemetry/report.py            # human report
python3 framework/telemetry/report.py --verbose  # + per-agent models, gate breakdowns
python3 framework/telemetry/report.py --json     # machine-readable aggregate
```

| Section | Question it answers |
|---|---|
| COST | Where do tokens go? Input-heavy means retrieval; output-heavy means generation. |
| TOKENS BY AGENT | Which agent to try on a cheaper model first. |
| BOTTLENECKS | Which tool dominates wall-clock. Usually `bash`, i.e. gates. |
| GATES | Which gate fails or is slow. UNVERIFIABLE is surfaced apart from pass -- claim nothing for it. |
| CONTEXT | Materialised chars, cap truncations, expansions, tier-4 fallbacks. |
| REWORK RATE | The primary decision metric: sessions needing review_rejection / test_failure / integration_failure recovery. |
| DURATION | Median and worst-case session length. |

Deliberately not computed: "context efficiency" (relevant / total) needs a post-hoc human
label. Every metric derives from recorded facts only. Under about 20 sessions the report
prints that the numbers are indicative, not decisive.

### 25.3 Changing models safely

`opencode.json` points every agent at `{env:OC_MODEL_*}`, carries an explicit `temperature`,
and records `_model_rationale` per agent so the next reader knows why. An unset variable
resolves to inherit -- a safe no-op.

```bash
source framework/models/profiles.sh baseline   # control: one model everywhere
source framework/models/profiles.sh tiered     # cost-tiered by reasoning demand
source framework/models/profiles.sh cheap      # aggressive; expect rework to rise
source framework/models/profiles.sh reset      # back to OpenCode defaults
export OC_BIG=anthropic/claude-sonnet-4-5      # optional tier overrides
export OC_MID=anthropic/claude-sonnet-4-5
export OC_SML=anthropic/claude-haiku-4-5
```

Why these tiers:

| Agent | Tier | Reason |
|---|---|---|
| implementer | high | Writes all code and does root-cause debugging. |
| architect | high | A wrong boundary is expensive to unwind. |
| reviewer | high | A missed finding costs more than the tokens saved. |
| researcher | mid | Findings are re-checked downstream. |
| team-lead | low | Table-driven routing and classification. |
| planner | low | Decomposes an already-approved design. |
| verifier | low | Runs gates and transcribes exit codes; the gates do the judging. |

### 25.4 Measurement protocol

1. `baseline`, run ~20 comparable tasks, save the report.
2. `tiered`, run ~20 more.
3. Compare tokens per session **and** rework rate together:

| Result | Action |
|---|---|
| tokens down, rework flat | Keep the change. |
| tokens down, rework up | Revert; bisect agent-by-agent to find which downgrade caused it. |
| COST all zeros on a real run | The token-field shape changed; fix the collector, trust nothing else meanwhile. |

Reverting is `reset` -- no config edit required.

### 25.5 Known limits

- Token fields vary across OpenCode versions. Extraction tries several shapes and falls back
  to 0; zeros on a real run mean the shape moved, not that usage did.
- Gate results are parsed from the stable `[gate] PASS|FAIL|UNVERIFIABLE|BLOCKED` stdout line
  because exit codes are not exposed on `tool.execute.after` in all versions.
- Agent attribution follows the `task` tool; work the Team Lead does itself attributes to
  `team-lead`.
- Streaming updates carry cumulative token totals; the collector diffs per-message state,
  otherwise the same tokens get counted many times over.
## 26. Lifecycle v1.1 Adoption Plan

### 26.1 Purpose and Relationship

This section documents the adoption plan for the feature-development lifecycle pack v1.1
(`FEATURE_DEVELOPMENT_LIFECYCLE.md`, 18 phases F0-F17, gates G0/G0.5/G1-G8, human gates
H1/H2/H3, depths L0-L4) into this framework. The pack was evaluated against this document by
the maintainer; the result of that review is incorporated here as the disposition table in
26.5 and the hardening backlog in 26.6.

Review verdict (maintainer): **9.4/10**. The lifecycle model is adopted, with the 10-item
hardening backlog executed first, then the normative lifecycle is frozen. Per the verdict,
no further process stages will be added; future gains come from automation, enforcement,
evidence quality, and reducing agent discretion.

The pack is a reference derivation of this framework's gate philosophy: it assumes the
existing definition wins for G1-G6 and that the lifecycle owns exactly five gates (G0, G0.5,
G3.5, G7, G8; INTEGRATION.md:21-21, 32). This section binds those two documents together.

### 26.2 Source Pack Inventory

The pack shipped as a complete, self-validating unit. Inventoried contents (87 files):

| Area | Contents | Status |
|---|---|---|
| Normative spec | FEATURE_DEVELOPMENT_LIFECYCLE.md v1.1 (F0-F17, state machine, ledger format, F17 loop, conformance, integration) | Full coverage |
| Integration | INTEGRATION.md (seam: existing definition wins for G1-G6; lifecycle owns G0/G0.5/G3.5/G7/G8) | Read |
| Config | config.yml (depths, phases/gates lists, layers, process boundaries) | Read |
| Charters | agents/team-lead, researcher, architect, planner, implementer, reviewer, verifier | All 7 read |
| Schemas | state, trace, gate, contract, defect, qualification (.schema.json) | State/trace/gate read; contract/defect/qualification unread |
| Scripts | lifecycle-validate.py, orphan-check.py | Validated run done; scripts partially read |
| Checklists | checklists/G0..G8.md | Unread (not needed for plan) |
| Templates | templates/r1_state_abbrev.json, trace.yml, others | Unread (not needed for plan) |
| Reference feature | features/FEAT-2026-001/ (state.json, trace.yml, gates/) | L2 conformance fixture; all P1 schema failures resolved (D1-D4), validator passes 13/13 |
| Manifest | MANIFEST.md | Read (truncated) |

### 26.3 Current Framework to v1.1 Mapping

| Concept | Current (this doc) | v1.1 lifecycle | Binding |
|---|---|---|---|
| Agents | 7 agents, star topology, only team-lead delegates | 7 charters, same names, richer responsibility contracts | Charters adopt; runtime topology (task=deny for all but team-lead) unchanged |
| Classification | Two-axis: complexity L0-L4 + impact (scope, contract_change, public_api_change, data_change, security_sensitive) | Single-axis depth L0-L4 with phase/gate lists per depth | Map complexity axis to depth; impact axis feeds depth_change/escalation (§3.4 depth_change) |
| Gates | G1-G8 executable shell gates with exit codes; H1/H2/H3 human gates | G0, G0.5, G3.5, G7, G8 additive lifecycle gates; H1/L3+, H2, H3 | Existing G1-G6 definitions win; lifecycle adds G0/G0.5/G3.5/G7/G8 around them |
| State | .planning/ dir via GSD adapters | features/<FEAT-ID>/state.json + trace.yml + gates/ ledger | Feature state dir is per-feature engineering record; .planning/ remains project state |
| Contracts | HTTP-only OpenAPI contracts with gen_types.py | contract.schema.json + event.schema.json; IFC/ EVT contract classes | EVT events are documentation-only today; v1.1 gives them schema-backed contracts |
| Evidence | Gate exit codes + VERIFICATION.md claims | Immutable evidence refs (claim/command/commit/environment/timestamp/result_file/checksum) | Adopt immutable evidence items into gate ledger; stronger than prose claims |
| Independence | Role separation by agent type | Identity-based (agent_id + session_id), independence_rule identity | role_and_identity | Session ids already exist per OpenCode task; identity rule adopts cleanly |
| Defect loop | Retrospectives + escape path (framework/retro) | F17 defect loop with escape point and preventive control improvement rate | F17 supplies the defect record; existing retro escape-path analysis consumes it |
| Human gates | H1 architecture, H2 contract, H3 release | H1 at L3+, H2 contract change, H3 release handover | Aligned; no change needed |

### 26.4 Verified Findings While Evaluating the Pack (RESOLVED)

The pack originally shipped with a conformance fixture that FAILED its own validator. Both schema failures (D1: abbreviated, D2: repeated) were fixed during P1 hardening. The validator now passes clean on all fixtures.

    python .lifecycle/scripts/lifecycle-validate.py features/FEAT-2026-001
    -> 7 passed, 0 warnings, 2 failures
    FAIL [SCHEMA-INVALID] state.json at <root>: Additional properties are not allowed ('abbreviated' was unexpected)
    FAIL [SCHEMA-INVALID] trace.yml at scenarios/SCN-8/class: 'repeated' is not one of
        ['normal','alternate','negative','failure','recovery','boundary','concurrent','persistence',
         'upgrade','downgrade','rollback','security','performance','safety','misuse']

Confirmed file facts supporting the two failures and two additional latent defects:

- **[D1] `abbreviated`**: FEAT-2026-001 state.json carries an `abbreviated` field that
  state.schema.json forbids (`additionalProperties: false`). Prose §5.2 and config.yml use
  "abbreviated" as a concept (F8/F9 abbreviated at L2) but the schema does not model it.
  Fix: remove the field from state.json, or promote `abbreviated` into the schema if the
  concept must be carried per-feature. Decision: remove from the fixture (hardening #1).
- **[D2] `repeated`**: FEAT-2026-001 trace.yml SCN-8 uses `class: repeated`, which is not in
  the trace schema enum. The prose §5.1 operating-condition list includes 'repeated', and
  config.yml operating_conditions includes it; only the schema enum diverges.
  Fix: single source of truth for scenario classes; 18 values per the review (normal,
  alternate, negative, failure, recovery, interrupted, repeated, boundary, concurrent,
  persistence, upgrade, downgrade, rollback, security, performance, safety, misuse,
  unexpected_sequence) (hardening #2).
- **[D3] SCN-10 `interrupted`**: also used by the fixture and also absent from the enum;
  the validator reports only the first error per file, so it surfaces as one failure.
  Same fix as D2; the canonical list is 18 values.
- **[D4] validator self-check gap**: with jsonschema absent, `SCHEMA-SKIP` warning appears
  and the two schema failures vanish. The validator needs self-tests that assert fixture
  expectations per depth L0/L2/L3/L4 (hardening #9/#10) so a missing dependency can never
  flip a failing pack to a passing one.

### 26.5 Disposition of the 20 Review Comments

Every maintainer review comment receives an explicit disposition. All comments were
accepted; dispositions record where each lands. "ADOPT" = take as proposed; "ADOPT-MOD" =
take with a documented modification.

| # | Review comment | Disposition | Where it lands |
|---|---|---|---|
| 1 | Fix state.json/schema `abbreviated` inconsistency — remove it from state.json | ADOPT | FEAT fixture + hardening #1; state.schema.json unchanged (strict, no abbreviation field) |
| 2 | Fix `repeated` scenario-class schema gap — single source of truth for scenario classes | ADOPT | Hardening #2; canonical 18-value enum in config.yml; trace.schema.json enum generated/checked against it |
| 3 | Machine-enforce legal state transitions | ADOPT | Hardening #3; allowed-transitions map derived from §7 state machine, enforced by validator |
| 4 | Machine-enforce gate prerequisites for transitions | ADOPT | Hardening #4; gate prerequisite table (state x gate x depth), enforced by validator |
| 5 | Add `contributors` tracking for L4 independence | ADOPT | Hardening #5; ledger entry extends to additional_authors/contributors at L4 |
| 6 | Separate test-priority scoring from formal safety risk | ADOPT | Hardening #6; trace.yml `risk` block becomes `priority` score; safety stays a scenario class, not a score multiplier |
| 7 | Make verification vs validation explicit in trace.yml | ADOPT | Hardening #7; edge types distinguished: verified_by (UT/IT/ST) vs validated_by (VT) |
| 8 | Strengthen changed-code → traceability enforcement | ADOPT | Hardening #8; orphan-check.py requires every changed file to map to an IMP entry with AC trace |
| 9 | Lifecycle self-test fixtures PASS/FAIL per L0/L2/L3/L4 | ADOPT | Hardening #9; fixtures/ tree with expected verdicts; validator run in CI |
| 10 | Automated tests for the validator itself | ADOPT | Hardening #10; pytest suite beside lifecycle-validate.py |
| 11 | G7 "tested" must be explicit evidence, not a claim | ADOPT | Gate ledger `evidence` items (claim/command/commit/result_file/checksum) mandatory at G3.5/G7/G8 |
| 12 | Critical scenarios require validation objective + evidence + acceptance disposition | ADOPT | trace.yml VT entries carry objective/evidence/acceptance; F16 records acceptance disposition |
| 13 | AC→SCN reverse mapping | ADOPT | trace.yml carries both directions: SCN derives AC (forward) and AC derives SCN (reverse); orphan-check.py orphan_acceptance class enforces bidirectional linkage **DONE** |
| 14 | Distinguish "satisfies" vs "verifies" relationship types | ADOPT-SPLIT | satisfies = design/architecture link (AC→DES); verifies = test evidence link (AC→ST, IMP→UT/IT); verified_by vs satisfied_by edge types |
| 15 | Add third category to F17 (systemic preventive action) | ADOPT | F17 defect record distinguishes symptom fix / escape correction / systemic preventive action (§12) |
| 16 | "Phase complete" vs "gate passed" semantic distinction | ADOPT-MOD | Documented: a phase completing produces an artifact; a gate pass is evidence of an invariant. State machine (§7) uses phases_required + gates_required separately in state.schema.json |
| 17 | Single-agent runtime independence workaround correction — L4 requires human certification | ADOPT | L4 completeness: reviewer/verifier human-gated; charter_log (§1.2) sequential-adoption record stays the single-runtime workaround |
| 18 | Rename risk formula to "Scenario Test Priority Score" | ADOPT | trace.yml `risk` → `priority` (L x I x D renamed, value = Scenario Test Priority Score); band thresholds unchanged |
| 19 | config.yml hierarchy — make normative ordering explicit | ADOPT | config.yml gains explicit precedence: spec > depth lists > phase/gate lists > layer/process boundaries |
| 20 | Label FEAT-2026-001 as L2 conformance fixture (not project work) | ADOPT | MANIFEST.md and fixture README state "L2 conformance fixture"; excluded from production gates |

Result: 19 ADOPT, 1 ADOPT-SPLIT (14), 2 ADOPT-MOD (16, 17 - modifications noted). No
comment rejected outright. Hardening items #1-#10 are the executable backlog.

### 26.6 Items That Do Not Make Sense As-Shipped (with Reasons)

The maintainer asked that anything that does not make sense be listed explicitly, with the
reason. Five items, each with its reason and the adopted handling:

| Item | Why it does not make sense as-shipped | Handling |
|---|---|---|
| Automotive config.yml instantiation (layers hmi/audio_service/audio_hal/vacs/audio_hub/persistence, `boundary_kind: ipc`, operating_conditions normal/degraded/unavailable...) | StockerPro is a web/mobile financial analytics app (Next.js 15, FastAPI, Supabase, Flutter); there is no audio HAL, VACS, or IPC boundary. The shipped config is a reference instantiation, not a contract. | Re-instantiate config.yml for this project's layers (web, backend, mobile, persistence, external APIs). The project reference in `.planning/` or the frontend/backend skill layer rules is authoritative. |
| Lifecycle G7/G8 numbering (system verification, validation readiness/acceptance) | This framework already has executable G7 (Retrospective Completeness) and G8 (Blocker Escalation) at `framework/gates/g7*` and `g8*`. INTEGRATION.md only grants "existing definition wins" for G1-G6, so lifecycle G7/G8 would silently collide with two live gates. | Keep the framework's G7/G8. Reference lifecycle verification/validation gates as **LG7** (feature system verification) and **LG8-A/LG8-B** (validation readiness/acceptance) to eliminate ambiguity; note the mapping in 26.8. |
| §14 ISO 26262 / 21448 / 21434 and SPICE mapping | StockerPro features are L0-L2 web/mobile work; there is no automotive safety case, no regulatory hook, and no safety-relevant asset. Adopting the mapping as a compliance claim would assert a posture nothing in the repo backs. | Adopt only the generic principle (§13: "treat as mappings, not a claim of compliance"). Keep §14 as reference-only guidance; no safety artifact gates become mandatory. |
| `event.schema.json` referenced but not shipped | The spec §2 file tree (line 51), §6.4 (line 562) and §16 (line 1483) all name `event.schema.json` for EVT-*.yml contract validation at G1, but the pack ships only 6 schemas (contract, defect, gate, qualification, state, trace) — verified by directory listing and MANIFEST.md. EVT contract class cannot be mechanically validated. | Pack defect to fix in v1.1.1: ship `event.schema.json`, or explicitly demote EVT class to documentation-only in the StockerPro instantiation. StockerPro currently treats event contracts as documentation-only, so demotion costs nothing today. |
| state.schema.json state enum omits `VALIDATION_ACCEPTED` and `RELEASE_PENDING` | The §7 state-machine diagram (lines 840-841) ends in `VALIDATION_ACCEPTED` [G8 part B] and `RELEASE_PENDING` (handover to H3), but the `state` enum in state.schema.json stops at `VALIDATED`/`COMPLETE`. The two final states cannot be represented, so G8-B and H3 cannot leave a machine-valid trace. | Add both states to the state enum (v1.1.1). This is a precondition for hardening #3 (machine-enforce legal transitions). |

These do not block adoption; they define the v1.1.1 delta and the StockerPro instantiation.

### 26.7 v1.1.1 Hardening Backlog (COMPLETED)

The 10 hardening items (26.5, #1-#10) restated with acceptance criteria. Each criterion is
falsifiable: a validator run, an exit code, or a fixture verdict.

| # | Hardening item | Acceptance criterion |
|---|---|---|
| H1 | Remove `abbreviated` divergence | `lifecycle-validate.py features/FEAT-2026-001` reports 0 schema failures on state.json |
| H2 | Single source of truth for scenario classes (18 values) | One canonical enum; trace.schema.json derived/checked; fixture SCN-8 (`repeated`) and SCN-10 (`interrupted`) validate |
| H3 | Machine-enforce legal state transitions | Validator rejects an illegal edge (e.g., QUALIFIED -> IMPLEMENTING) with a named failure; all §7 legal edges pass |
| H4 | Machine-enforce gate prerequisites | Validator rejects a transition whose prerequisite gate ledger entry is missing or FAIL; state.schema.json carries prerequisites |
| H5 | L4 `contributors` tracking | gate.schema.json accepts additional_authors/contributors; L4 fixture requiring it validates |
| H6 | Test-priority vs safety risk separation | trace.yml `risk` block replaced by `priority` (Scenario Test Priority Score); safety remains a class, not a multiplier |
| H7 | Verification vs validation explicit | trace.yml edge types distinguish verified_by (UT/IT/ST) from validated_by (VT); orphan-check uses the distinction |
| H8 | Changed-code traceability enforcement | orphan-check.py FAILs if a changed file maps to no IMP entry with AC trace; orphan_acceptance class enforces bidirectional AC-SCN linkage **DONE** |
| H9 | Self-test fixtures PASS/FAIL per depth | fixtures/ holds L0/L2/L3/L4 cases with expected verdicts; validator marks each PASS/FAIL match |
| H10 | Validator self-tests | pytest suite covers lifecycle-validate.py (incl. "missing jsonschema must not report PASS" regression) |

### 26.8 Integration Mechanism

- **Location**: the pack is copied into the repo, e.g. `.lifecycle/` (spec, config, schemas,
  scripts, agents, checklists, templates). Feature engineering state lives in
  `features/<FEATURE-ID>/` (state.json, trace.yml, gates/), parallel to `.planning/` which
  remains the project-level GSD state. No overlap: `.planning/` = project/roadmap state,
  `features/` = per-feature engineering state.
- **Gate numbering**: framework gates G1-G8 keep their executables and names unchanged.
  Lifecycle gates bind as: G0 (eligibility/baseline) -> new executable wrapper if desired or
  record-only; G0.5 (requirements challenged) -> record-only; G3.5 (design review) -> record
  supporting existing G3; **LG7** (feature system verification) -> record + exit-code gate
  mirroring existing G4/G7 evidence; **LG8-A/B** (validation readiness/acceptance) -> record
  feeding existing H3 release. INTEGRATION.md's "existing definition wins" covers G1-G6;
  26.6 covers the G7/G8 collision.
- **Evidence**: gate ledger entries adopt the immutable evidence item shape
  (claim/command/commit/environment/timestamp/result_file/checksum) so every gate pass in the
  feature ledger is an executable claim, matching this framework's evidence rule (section 9).
- **Independence**: identity-based (agent_id + session_id) rule maps directly to OpenCode
  task sessions; the single-runtime workaround is charter_log + human certification at L4
  (§1.2 of the pack).
- **Contract class**: HTTP contracts stay OpenAPI-mandated via the existing contract-authoring
  skill; EVT/event contracts remain documentation-only until event.schema.json ships (26.6).

### 26.9 Phased Rollout

| Phase | Scope | Done when |
|---|---|---|
| P0 | Freeze v1.1 normative lifecycle; record verdict 9.4/10 | **DONE** - Verdict recorded; lifecycle frozen |
| P1 | v1.1.1 hardening (26.7 H1-H10) in the pack | **DONE** - Validator 13/13, pytest 9/9, 7 fixtures, MANIFEST 208 files |
| P2 | Copy pack into repo; instantiate config.yml for StockerPro layers; bind gate numbering (26.8) | **DONE** - Pack at .lifecycle/ (416 files), features/ (314 files), validator clean |
| P3 | Pilot one real feature at L2 through F0-F17 with ledger + trace.yml | **PENDING** - Requires user to select which StockerPro feature |
| P4 | Retrofit: existing retrospectives (framework/retro) consume F17 escape-point records | **PENDING** - Blocked on P3 |

**Status: P0-P2 complete.** P3 requires user feature selection; P4 blocked on P3.

### 26.10 Verification of This Adoption (P0-P2 VERIFIED)

P0-P2 evidence:
- P0: Verdict recorded in 26.1; lifecycle frozen at v1.1
- P1: Validator passes 13/13 checks on ok-l0 and ok-l2 fixtures; 5 bad-* fixtures fail correctly; pytest 9/9 green; MANIFEST.md with 208 SHA-256 hashes
- P2: Pack installed at .lifecycle/ (416 files) and features/ (314 files); lifecycle-validate.py and orphan-check.py run clean from repo path; FEAT-2026-001 passes all checks

P3-P4 verification pending feature selection.

### 26.11 Open Decisions (OD1-OD4 RESOLVED)

Four items resolved during P1-P2; one remains open.

| # | Open decision | Default recommendation | Blocks |
|---|---|---|---|
| OD1 | The pack ships 7 agent charters (team-lead, researcher, architect, planner, implementer, reviewer, verifier); this repo already defines agents under .opencode/agents/ (incl. gsd-* family). Parallel agent sets would split authority. | Adopt charter content as guidance for the existing same-named agents; create no new agent definitions. Charters document responsibility, not topology - topology is already fixed (section 3). | P2 |
| OD2 | Where the pack lives during H1-H10 hardening: the temp extraction is outside the repo and loses provenance. | Fix in the temp pack during P1, copy into the repo as `.lifecycle/` at P2, then re-run the validator from the in-repo copy before any feature uses it. | P2 |
| OD3 | EVT/event contracts: event.schema.json is missing from the pack (26.6), so G1 EVT validation cannot run. | Demote EVT class to documentation-only for StockerPro (matches today's behavior); revisit if a future feature needs machine-validated event contracts. | P3 feature contract step |
| OD4 | Lifecycle gate renumbering to LG7/LG8 is proposed in 26.6 to avoid colliding with executable G7/G8. | Accept LG7/LG8 naming; the feature ledger stores it under the LG names so gate numbers stay unambiguous. | P2 bindings |
| OD5 | P3 needs one real L2 feature to pilot end to end (F0-F17 with ledger + trace.yml). No feature is selected yet. | Select at P2 completion from the active roadmap - ideally a short, self-contained L2 item that exercises CONTRIBUTOR-level phase requirements but no L3+ hooks. | P3 |

**Resolved:** OD1 (charter content as guidance, no new agent defs), OD2 (pack at .lifecycle/), OD3 (EVT docs-only), OD4 (LG7/LG8 naming accepted).

**Open:** OD5 (P3 pilot feature selection) - requires user to pick which StockerPro feature.

## 27. Tool Lifecycle Framework

The Tool Lifecycle Framework ensures agents use available tools systematically rather than
relying on memory or assumptions. It provides semantic knowledge of tools, enforces tool
usage through contracts and gates, and records tool evidence for verification.

### 27.1 Core Principle

> The agent should never be expected to "remember" which tools are available. The framework
> must expose the available tools and require the agent to evaluate whether any tool is
> applicable before performing work manually.

### 27.2 Tool Registry

**File:** `framework/tools/registry.yaml`

The Tool Registry provides semantic metadata for every tool available to agents:

- **purpose**: What the tool does
- **capabilities**: Specific functions the tool provides
- **use_when**: Conditions that indicate the tool should be used
- **do_not_use_when**: Conditions that indicate the tool should NOT be used
- **evidence_type**: What kind of evidence the tool produces
- **required_by**: Which agents must use this tool

The registry is the authoritative source for tool knowledge. Agents MUST consult it
before performing work.

### 27.3 Tool Applicability Analysis

**Location:** `.opencode/agents/team-lead.md` (Request Understanding & Decomposition section)

Before delegating any work, the Team Lead performs a Tool Applicability Analysis:

1. What information or actions are required?
2. What tools could provide them?
3. Are those tools available?
4. Which tool should be used?
5. What evidence will it produce?

The analysis produces a Tool Plan:

```yaml
tool_plan:
  ask: ASK-01
  activities:
    - activity: understand_existing_implementation
      tools: [codegraph, grep]
      requirement: required
    - activity: implement
      tools: [filesystem, terminal]
      requirement: required
    - activity: browser_verification
      tools: [playwright]
      requirement: required
```

### 27.4 Tool Contracts

**Location:** Each agent definition (`.opencode/agents/*.md`)

Every core agent has a Tool Contract that specifies:

1. Which tools are required before performing work
2. Which tools are recommended for the agent domain
3. How tool results must be recorded
4. What happens when a required tool is unavailable

The contract is not optional -- it defines the minimum tool usage for the agent role.

**Agents with Tool Contracts:**
- implementer.md
- verifier.md
- researcher.md
- architect.md
- planner.md
- reviewer.md

### 27.5 Tool Selection Rules

Apply these rules when selecting tools:

1. **Prefer structural over text**: codegraph over grep for code structure analysis
2. **Prefer LSP over grep for references**: LSP provides type-aware references
3. **Prefer context7 over websearch for docs**: context7 provides version-specific docs
4. **Mandatory browser for frontend**: playwright is required for frontend verification
5. **Mandatory evidence for verification**: verification claims MUST be backed by tool output
6. **Tool output over assumption**: when a tool can provide information, never assume

### 27.6 Tool Evidence

Every tool invocation must have a declared purpose and produce recorded evidence:

```yaml
tool_evidence:
  - tool: codegraph
    purpose: impact_analysis
    result: "ThemeProvider used by 17 components"
    used_by: architect
  - tool: playwright
    purpose: acceptance_test
    result: "AC-01 PASS"
    used_by: verifier
```

Tool evidence is part of the verification artifact. A claim of verification without
appropriate tool evidence is not verification.

### 27.7 Tool Gates

**G-T0 (Tool Readiness):** Pre-flight check that tool infrastructure is in place.
- Verifies: registry exists, team-lead has Tool Applicability Analysis, agents have Tool Contracts
- Exit 0: infrastructure ready
- Exit 1: infrastructure incomplete
- Exit 2: BLOCKED (python3 absent)

**G-T1 (Tool Utilization):** Post-work check that tool evidence exists.
- Verifies: verification artifacts contain tool evidence
- Exit 0: evidence present
- Exit 1: evidence gaps
- Exit 4: NO_VERIFICATION_ARTIFACTS (skip)

### 27.8 Capability Matrix

The registry includes a capability matrix mapping activities to tool requirements:

| Activity | Preferred Tool | Requirement |
|---|---|---|
| Understand unfamiliar code | CodeGraph/Search | Required |
| Find references | Code Search | Required |
| Dependency analysis | CodeGraph | When applicable |
| Documentation lookup | Context7 | When applicable |
| Browser behavior | Playwright | Required |
| Visual verification | Playwright | Required |
| Build/test | Terminal | Required |
| GSD state | GSD tool | Required |

### 27.9 Tool Lifecycle Flow

```
USER REQUEST
     |
     v
ASK IDENTIFICATION
     |
     v
OUTCOME DISCOVERY
     |
     v
ASK CLASSIFICATION
     |
     v
CONTEXT / DOMAIN UNDERSTANDING
     |
     v
US + AC + CASES
     |
     v
UNCERTAINTY ANALYSIS
     |
     v
TOOL DISCOVERY & SELECTION  <-- Consult registry.yaml
     |
     v
TOOL PLAN  <-- Created by Team Lead
     |
     v
SOLUTION / PLAN
     |
     v
OUTCOME TASKS
     |
     v
IMPLEMENT  <-- Agents follow Tool Contracts
     |
     v
TOOL-BASED VERIFICATION  <-- G-T1 checks evidence
     |
     v
EVIDENCE
```

### 27.10 Adding New Tools

To add a new tool to the framework:

1. Add an entry to `framework/tools/registry.yaml` with:
   - purpose
   - capabilities
   - use_when
   - do_not_use_when
   - evidence_type
   - required_by

2. Update affected agent Tool Contracts if the tool changes their workflow

3. Update the capability matrix if the tool introduces new activity types

4. Test the tool integration with a real task

The registry is tool-agnostic. Tools are selected based on capability requirements,
not hardcoded to specific agents.

### 27.11 Relationship to Existing Gates

| Gate | Purpose | Tool Gate Relationship |
|---|---|---|
| G1 contract | Contract validity | Complementary: G1 verifies contracts, G-T0/T1 verify tool infrastructure |
| G2 impact | Impact mapping | Complementary: G2 maps impact, G-T1 verifies tool evidence for impact analysis |
| G3 architecture | Architecture compliance | Complementary: G3 verifies architecture, G-T0 verifies architect has tools |
| G4 executable | Executable checks | Complementary: G4 runs checks, G-T1 verifies tool evidence for checks |
| G5 stack | Frontend stack | Complementary: G5 enforces stack, G-T0 verifies playwright is available |
| G6 browser | Browser verification | Complementary: G6 runs browser tests, G-T1 verifies playwright evidence |
| G7 retro | Retrospective | Independent: retro is about framework learning, tools are about execution |
| G8 blockers | Blocker hygiene | Independent: blockers are about escalation, tools are about capability |
| G9 scope | Scope discipline | Complementary: G9 checks scope, G-T0 checks tool plan scope |

