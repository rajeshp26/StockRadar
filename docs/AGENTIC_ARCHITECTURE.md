# Agentic Architecture — the whole framework explained

> This document explains **everything** in this repository that makes agents work — the
> agents, the rules they follow, the gates that check them, and the flow a task travels
> through from "you asked for something" to "it is done and proven".
>
> It is written so that anyone — even someone seeing the code for the first time — can
> read it top to bottom and understand what exists and why.
>
> **Ground truth rule:** every fact below was checked against the current code and
> configuration in this repository. If a statement here ever disagrees with a gate's
> own exit-code table (`framework/gates/EXIT_CODES.md` says it is authoritative), the
> gate table wins — "if a document disagrees with this table, the document is wrong"

---

## Table of contents

1. [What this is](#1-what-this-is)
2. [The big picture](#2-the-big-picture)
3. [The two governing rules](#3-the-two-governing-rules)
4. [Two axes, not one: complexity and impact](#4-two-axes-not-one-complexity-and-impact)
5. [The forty agents](#5-the-forty-agents)
   - 5.1 [The seven core agents](#51-the-seven-core-agents)
   - 5.2 [The GSD distribution agents](#52-the-gsd-distribution-agents)
6. [How agents talk to each other](#6-how-agents-talk-to-each-other)
7. [The nine agent rules](#7-the-nine-agent-rules)
8. [The eighty-five skills](#8-the-eighty-five-skills)
9. [The enforcement plane](#9-the-enforcement-plane)
10. [The permission model](#10-the-permission-model)
11. [The gates](#11-the-gates)
12. [The verifier profiles](#12-the-verifier-profiles)
13. [The retry and escalation policy](#13-the-retry-and-escalation-policy)
14. [The adapters](#14-the-adapters)
15. [The claim ledger and evidence provenance](#15-the-claim-ledger-and-evidence-provenance)
16. [The retrospective subsystem](#16-the-retrospective-subsystem)
17. [The telemetry plugin and model tuning](#17-the-telemetry-plugin-and-model-tuning)
18. [The execution context](#18-the-execution-context)
19. [The architecture rules](#19-the-architecture-rules)
20. [The state directory (.planning/)](#20-the-state-directory-planning)
21. [The lifecycle integration (.lifecycle/)](#21-the-lifecycle-integration-lifecycle)
22. [The bootstrap script and validation suite](#22-the-bootstrap-script-and-validation-suite)
23. [The frontend stack contract](#23-the-frontend-stack-contract)
24. [The context builder tool](#24-the-context-builder-tool)
25. [Delegated task supervision](#25-delegated-task-supervision)
26. [Every use case, step by step](#26-every-use-case-step-by-step)
27. [File map](#27-file-map)
28. [How to add a skill](#28-how-to-add-a-skill)
29. [How to modify the flow](#29-how-to-modify-the-flow)
30. [Exit code reference](#30-exit-code-reference)
31. [Glossary](#31-glossary)

---

## 1. What this is

This repository is an **agentic engineering framework**: a set of instructions and
executable checks that make AI agents work like a disciplined engineering team.

The framework is split into two cooperating halves:

- **The runtime and the rules** — who the agents are, what they may do, which rules
  they obey. These live in the OpenCode configuration (`opencode.json`) and the
  `.opencode/` directory.
- **The framework machinery** — the gates, adapters, profiles, and tools that check
  the work. These live in `framework/`.

Everything an agent can do is bounded by a **permission model** in `opencode.json`.
Everything an agent claims is checked by an **executable gate** in `framework/gates/`.
A claim that was not proven by executing something is not a done task — this is the
single most important idea in the framework (see the rules in `.opencode/rules/`).

The framework deliberately does **not** rebuild things that already exist. It builds on:

- **OpenCode** — the agent runtime (models, tools, permissions).
- **GSD** — the planning/workflow system (phases, plans, requirements, state under
  `.planning/`).
- **Code intelligence providers** — for understanding the codebase.
- **Git** — for history and diff.
- **The host** — for running commands.

The framework wraps and extends those, never duplicates them ("rule zero", below).

---

## 2. The big picture

Here is the whole flow in one picture, then explained in words.

```
 you (a person)
    │  you ask for something ("add a login screen")
    ▼
 team-lead  ──── classifies the ask
    │             complexity (L0-L4) + impact (scope/contract/API/data/security)
    ▼
 researcher ──► architect ──► planner
    │              │             │
    │              │             └──► produces a plan (approved, files, acceptance criteria)
    │              ▼
    │        G-ENTRY checks the plan before any agent is dispatched
    ▼
 implementer ── writes code (loads the skills the plan says to use)
    │
    ├──► G1 contract   (if the HTTP API changed)
    ├──► G2 impact     (each impact mapped to tests)
    ├──► G3 architecture (boundaries respected)
    ├──► G4 executable (checks actually ran)
    ├──► G5 stack      (frontend uses the mandated stack)
    ├──► G6 browser    (visible behaviour proven in a real browser)
    │
    ▼
 reviewer ── independent judgement over the diff
    ▼
 verifier ── proves the requirements are satisfied (runs tests, builds, gates,
    │          browser checks) and records evidence
    ├──► G9 scope      (only files the plan declared)
    ├──► G10 permission (permission policy is conformant)
    ├──► G11 evidence  (claims recorded with provenance)
    ├──► G13 worker    (no worker left unhealthy)
    ├──► G14 evidence-integrity (evidence is not borrowed or stale)
    └──► G8 blockers   (no open blocker records)
    ▼
 done — telemetry recorded, retrospective if a defect escaped (G7)
```

Key terms to understand before reading on:

| Term | Meaning |
|---|---|
| Agent | A persona definition with its own permissions and model. Many are "subagents" the team-lead delegates work to. |
| Gate | An executable script that returns a real exit code. It either proves something or it does not. |
| Rule | A standing instruction agents must obey (in `.opencode/rules/`). |
| Skill | A packaged body of specialist knowledge agents load when a task needs it. |
| Plan | The GSD document that says what will be built, which files, and how we will know it works. |
| Evidence | The recorded result of an executed check. Reasoning alone is never evidence. |

---

## 3. The two governing rules

Two rules govern every agent decision (`AGENTS.md`, `README.md`):

1. **Non-duplication ("rule zero").** Do not rebuild what OpenCode, GSD, the code
   intelligence provider, Git, or the host already provide. Wrap them. If a capability
   already exists somewhere, an agent must extend it through adapters and gates — not
   build a second copy.

2. **Do not invoke agents gratuitously.** An agent must not be invoked merely because
   it exists. Someone must name the specific information or execution need that cannot
   be satisfied by the active agent, an existing skill, GSD, the code intelligence
   provider, or a gate. No need, no delegation.

Two further rules complete the picture:

3. **Evidence beats reasoning.** Use the strongest *applicable executable* evidence for
   the requirement. Reasoning cannot substitute for an executable check that was
   available. If the applicable evidence class existed and was skipped, that is a
   verification failure, not a pass with a caveat.

4. **The enforcement plane is agent-immutable.** The security plane — the gates, the
   rules, the permission model — cannot be edited by an agent (see §9).

---

## 4. Two axes, not one: complexity and impact

The team-lead classifies every ask on **two independent axes** (`README.md`):

- **Complexity** governs *how much planning* a task deserves.
- **Impact** governs *how much verification* a task requires.

```yaml
complexity: L0 | L1 | L2 | L3 | L4
impact:
  scope: local | component | cross_component | system
  contract_change: false
  public_api_change: false     # forces at least cross_component
  data_change: false
  security_sensitive: false
```

- `public_api_change: true` automatically forces at least `cross_component` scope.
- Impact is **re-derived from the actual diff after implementation** — the plan may
  say "local", but if the changed code touches other components, the wider class
  triggers expansion and the gates that wider class requires.
- **Unknown impact is never "no impact"** — an impact that cannot be determined is an
  escalation (G2 returns `UNKNOWN_IMPACT`, see §11).

The `impact_to_gates` mapping in `framework/verifier/profiles.yaml` decides which
gates a task must pass based on its impact and its change shape.

---

## 5. The forty agents

There are **40 agent definitions** in `.opencode/agents/`:

- **7 core agents** — the hand-written orchestration crew.
- **33 `gsd-*` agents** — distribution agents owned by the GSD workflow system
  (planning, execution, review, docs, debugging, etc.).

Every agent definition sets: a `description`, a `mode` (`primary` = can start
conversations, `subagent` = only works when delegated to), a `permission` block, a
model, a temperature, and an optional `_model_rationale` explaining the choice.

### 5.1 The seven core agents

| Agent | Mode | Role | Tempera-ture | Playswright |
|---|---|---|---|---|
| `team-lead` | primary | Orchestrator. Classifies complexity and impact, delegates, enforces gates and completion. | 0.1 | off |
| `researcher` | subagent | Investigates unknowns before design. Produces structured findings with evidence. | 0.3 | off |
| `architect` | subagent | Owns system design, component boundaries, and contract versions. | 0.2 | off |
| `planner` | subagent | Decomposes approved architecture into atomic tasks with acceptance criteria. | 0.1 | off |
| `implementer` | subagent | Writes and modifies code. Loads domain skills per task. Also runs debug mode. | 0.1 | on |
| `reviewer` | subagent | Independent design and correctness judgement over the diff. Never edits. | 0.1 | off |
| `verifier` | subagent | Proves requirements are satisfied by executing tests, builds, gates and browser checks. | 0.0 | on |

Their configured permissions (in `opencode.json`) are:

| Agent | edit | task (delegate) | bash | key allow/deny notes |
|---|---|---|---|---|
| team-lead | ask (framework/.opencode/opencode.json/AGENTS.md denied) | `*` allow | ask; git read + framework scripts allowed; push/reset/clean/checkout/restore/rebase/merge/cherry-pick denied | may delegate to anyone; may not touch the plane |
| researcher | deny | `*` deny | `*` deny; git read + gsd_state + ledger + framework scripts allowed | may append claims to the ledger |
| architect | deny except `.planning/contracts/**` ask | `*` deny | `*` deny; git read + gsd_state + checklist_check allowed | may write contract files |
| planner | deny | `*` deny | git read + gsd_state allowed | read/write planning state only |
| implementer | deny except `src/**`, `tests/**`, `docs/**`, `package.json`, lockfiles, configs allow | `*` deny | test/build/lint/typecheck + gsd_state + framework scripts; `npx shadcn@latest add*` denied | edits application code, never the plane |
| reviewer | deny | `*` deny | git diff/log/show + grep only | reads, never writes |
| verifier | deny except `.planning/**/VERIFICATION.md` allow; `tests/**` ask | `*` deny | test/build/audit/playwright/gates allowed; destructive + history-mutating denied | runs gates, records exit codes |

The core-agent *charters* (`.opencode/agents/*.md`) add standing instructions on top of
the JSON permissions:

- **team-lead**: classifies (Phase 1 ask discovery, Phase 2 outcome discovery, Phase 3
  ask classification into NEW FEATURE / BUG FIX / ENHANCEMENT / REFACTOR / PERFORMANCE),
  and has a **trivial-request gate**: a single ask, single file, unambiguous, no
  behavioural scope → classify it and, if it is truly trivial, it may skip heavy
  planning (`ENTRY_EXEMPT=TRIVIAL`, §27-28). It runs **G-ENTRY before every
  `task(...)` dispatch** and **G12 before dispatch** (provider health).
- **researcher**: produces YAML findings (`research_id`, `question`, ≤10 findings,
  evidence, recommendation, alternatives, risks, confidence, classification
  FACT|HYPOTHESIS|ASSUMPTION|UNKNOWN). Uses the technical-validation evidence
  hierarchy: repo inspection → documentation → experiment → POC → explicit assumption.
  Never skips a level.
- **architect**: evidence-first; evidence taxonomy DIRECT / DERIVED / INFERRED /
  ASSERTED / UNOBSERVED / CONTRADICTED; architecture pass modes **Scan / Focus / Full**
  with "Rule 0: default to Scan".
- **planner**: consumes the approved architecture. Produces GSD tasks with
  `task_id/phase/objective/requirements/dependencies/files_or_components/contracts/
  acceptance_criteria/evidence_classes/complexity/impact/required_skills/assigned_agent`.
  MUST NOT redesign the architecture. Every task MUST name `required_skills`.
- **implementer**: confirms the plan, requirements, contracts and tests are readable
  before acting; if something critical is missing it returns `CONTEXT_INSUFFICIENT`
  through the blocker system, never guessing. MUST load every skill named in
  `required_skills` — not loading one makes the task incomplete regardless of code.
  Never merges its own changes.
- **reviewer**: independent judgement over Requirement → Architecture → Plan →
  Implementation → Tests. Eight review questions include "Do conclusions trace to
  VERIFIED claims?".
- **verifier**: three modes — V1 Evidence Review, V2 Direct Inspection, V3 Independent
  Reproduction. The implementer's report is *not* evidence; the verifier executes.
  Chooses a `verification_profile` from `framework/verifier/profiles.yaml`.

### 5.2 The GSD distribution agents

The 33 `gsd-*` agents implement the GSD workflow system. Each is an OpenCode agent
definition that GSD commands and skills delegate to. They fall into families:

| Family | Agents |
|---|---|
| Planning | `gsd-plan-checker`, `gsd-phase-researcher`, `gsd-pattern-mapper`, `gsd-planner`, `gsd-roadmapper`, `gsd-project-researcher`, `gsd-research-synthesizer` |
| Execution | `gsd-executor`, `gsd-code-fixer`, `gsd-integration-checker`, `gsd-verifier`, `gsd-nyquist-auditor` |
| Review & quality | `gsd-code-reviewer`, `gsd-security-auditor`, `gsd-eval-auditor`, `gsd-ui-auditor`, `gsd-ui-checker`, `gsd-eval-planner` |
| Docs & codebase | `gsd-codebase-mapper`, `gsd-doc-classifier`, `gsd-doc-synthesizer`, `gsd-doc-verifier`, `gsd-doc-writer`, `gsd-intel-updater` |
| Debugging | `gsd-debugger`, `gsd-debug-session-manager` |
| AI phases | `gsd-ai-researcher`, `gsd-domain-researcher`, `gsd-framework-selector` |
| UI | `gsd-ui-researcher` |
| Users & memory | `gsd-user-profiler`, `gsd-mempalace-curator` |
| Ingest | `gsd-assumptions-analyzer` |

These agents exist so GSD skills can hand specialized work to a dedicated persona
instead of doing it inline. They are invoked by GSD orchestrator skills (for example
`gsd-code-review` spawns `gsd-code-reviewer` and `gsd-code-fixer`).

---

## 6. How agents talk to each other

**Star topology.** Only `team-lead` delegates. All subagents have the `task` tool
denied — a subagent can never spawn another subagent. Delegation happens through
`task(...)` invocations with an explicit prompt, and handoffs are written as
structured records to GSD state (`.opencode/rules/handoff.md`) — never by passing raw
reasoning transcripts between agents.

**Delegation protocol** (`.opencode/rules/delegation-protocol.md`):

1. **Register before you delegate.** Every supervised task is registered with
   `task-register` into `<state_root>/tasks/` as an immutable contract (agent,
   objective, expected artifact) plus an append-only lifecycle event stream
   (`<state_root>/tasks/T-01.events.jsonl`).
2. The **supervisor (team-lead) owns the contract**; only it may cancel.
3. The worker appends lifecycle events (see §25).
4. **Accept nothing without** `task-status` health `COMPLETE` **and your own check of
   the deliverable** — read the diff or output, run the gate, record the exit code.
5. A silent worker is a **blocker with signal `WORKER_STALLED`** — a stall that lives
   only in conversation repeats.

**Headless-interaction firewall.** A contract flagged `headless: true` — and every
background/supervised task — must not issue interactive asks (permission prompts,
clarifying questions, human gates). If a headless task needs a decision, it emits
`BLOCKED` with a detail naming the decision.

**Background tasks use a pub/sub contract, not polling.** Launch → get a `bg_xxx` id →
end your response → the system sends a completion notification → collect output. Polling
`background_output` before the notification is a framework violation (tracked in
telemetry as `bg_poll_total`).

**Handoff shape** (written via `gsd_state.py write-summary`):

```yaml
task_id: 03-02
agent: implementer
status: complete | blocked | failed
summary: <= 5 lines
files_changed: []
contracts_touched: []
tests: {added: [], run: [], result: pass|fail}
evidence: ["[VERIFIED: src/auth/service.py:41-58]"]
impact_rederived: {scope: local, contract_change: false, public_api_change: false}
risks: []
blockers: []
next_action: review | verify | escalate
actions_to_avoid_until_clarified: []
```

---

## 7. The nine agent rules

`.opencode/rules/` contains nine standing rules. They are loaded into every agent
session via `opencode.json` `instructions`.

| Rule file | What it says |
|---|---|
| `evidence.md` | Which evidence class proves which requirement shape (contract test for API status, unit test for business rule, type check for types, browser screenshot for visuals, etc.). **Unverifiable is not pass.** |
| `evidence-provenance.md` | Claims are the unit of truth. Classes: environment / behavioral / data / causal. Vocabulary: FACT / HYPOTHESIS / ASSUMPTION / UNKNOWN. `VERIFIED` only under the canonical runtime with reproducible provenance. Logs are not evidence of behaviour. |
| `handoff.md` | The handoff shape (§6) — a handoff is a structured record, never a transcript. |
| `background-tasks.md` | The pub/sub contract — launch, end response, wait for notification, collect. Polling is a violation. |
| `delegation-protocol.md` | Register before delegate; supervisor owns the contract; lifecycle events; health rules; failure classification; headless firewall; supervisor survival. |
| `definition-of-done.md` | DoD is a set of *claims*; verification is *evidence* each claim is true this run. A test that exists but never ran is not evidence. |
| `blockers.md` | A non-complete stop lands as a visible blocker record (`write-blocker`), not a quiet context note. G8 refuses completion while any open blocker exists. |
| `bash-hygiene.md` | Bash is for git state, test/build/lint runners, and trusted framework scripts — not for inspection or file management. One command per invocation. Never rephrase to dodge a permission prompt. |
| `retrospective.md` | A defect that reaches production is two failures: the defect and the framework that passed it. Retrospectives are computed, not argued (see §16). |

---

## 8. The eighty-five skills

There are **85 skills** in `.opencode/skills/`:

- **14 framework-authored skills** — specialist knowledge for engineering domains:
  `api-design`, `apple-ui`, `architecture-right-sizing`, `backend-python`,
  `browser-verification`, `contract-authoring`, `database-schema-design`,
  `frontend-react`, `performance-testing`, `requirements-authoring`, `retrospective`,
  `software-architecture-design`, `technical-validation`, `unit-test-authoring`.
- **71 `gsd-*` distribution skills** — the GSD workflow system (planning, execution,
  review, docs, security, UI, debugging, etc.).

A skill is a directory with a `SKILL.md` plus supporting files. Skills are loaded by an
agent when a task matches the skill's description (the `skill` tool) or via the
`task(..., load_skills=[...])` parameter.

**Skill routing** (`.opencode/skill-routing.md`) is the central registry mapping a
*condition* to a *skill* and an *agent*:

| Condition | Skill(s) | Agent |
|---|---|---|
| New feature / enhancement | `requirements-authoring` | team-lead / architect |
| Architecture change | `software-architecture-design` | architect |
| Unknown technical behaviour | `technical-validation` | researcher / architect |
| API endpoint change | `api-design` | architect |
| API contract change | `contract-authoring` | architect / implementer |
| Database / schema change | `database-schema-design` | architect |
| Unit tests required | `unit-test-authoring` | implementer |
| Performance impact | `performance-testing` | verifier |
| Security concern | `security-research` | researcher |
| UI change | `apple-ui` + `frontend-react` | implementer |
| Backend logic change | `backend-python` | implementer |
| Visible behaviour change | `browser-verification` | verifier |
| Code review | `gsd-code-review` | reviewer |
| Defect escape | `retrospective` | implementer |

**Skill integration matrix** (`.opencode/skill-integration-matrix.md`, ratified v1.0)
is the single binding contract: *which role loads which skill, produces which
artifact, and is judged by which gate*. It is verified by gate reviewers and by
**G-T1** (tool utilization). It encodes critic findings #3 (skills as verifiable
artifacts of the control plane), #5 (functional consolidated integration matrix), and
#9 (the G-EXEC execution-integrity gate).

Matrix highlights (role → loads → produces):

- **team-lead** → `requirements-authoring` for every feature request → the Tool Plan
  (which records the required skills).
- **architect** → `software-architecture-design` (L3/L4), `technical-validation`,
  `api-design` before `contract-authoring`, `database-schema-design` → design docs.
- **planner** → verifies required skills per task → GSD task list (never redesigns).
- **implementer** → ALL skills the plan names; `apple-ui`/`frontend-react` for UI,
  `unit-test-authoring` for business logic → code + tests.
- **reviewer** → verifies implementation against architecture / contract /
  required-skills-used / unit tests / performance evidence / VERIFIED claims.
- **verifier** → `browser-verification`, `performance-testing` → verification
  artifacts with tool evidence (G-T1).

> Note: the routing table above lists `security-research` for security concerns. In
> this repository the actual skill directories are the 85 under `.opencode/skills/`;
> a security-scoped agent should confirm the exact skill name before loading.

---

## 9. The enforcement plane

The framework has a small set of files that are **agent-immutable**: no agent may
modify them, because they define the boundaries that *check* the agents. Canonical
source: `framework/security/enforcement_plane.yaml`.

```
framework/**        gates, claims, retro, security, adapters, policy
.opencode/**        agents, rules, skills, plugin, config
opencode.json       permission model
AGENTS.md           stable global rules
```

This fence is enforced by:

1. **Edit permissions** in `opencode.json` — narrow allowlists with deny fallback and
   an explicit plane deny after any path-scoped allow (`*` in a permission pattern
   spans path segments).
2. `framework/security/sync_enforcement_plane.py` — human-run; propagates the YAML
   list into the `permission.edit` deny blocks in `opencode.json` and the fence in
   `AGENTS.md`. It only mirrors the YAML.
3. `framework/security/check_enforcement_plane.py` — must exit 0 after any plane
   change; asserts all three (YAML, opencode.json, AGENTS.md) agree.

Agents may **execute** the sync and check scripts, but every input, implementation,
and configuration that determines the enforcement-plane result is a plane file —
immutable to agents, the checker included. Nothing that could change the check's
verdict can be changed by an agent. That is what makes the check trustworthy.

**Adding a rule that crosses a plane boundary requires a trailing deny for the plane.**

---

## 10. The permission model

`opencode.json` is the permission model. Its defaults:

| Tool | Default | Notes |
|---|---|---|
| read / glob / grep / list / lsp / todowrite / question / websearch / skill | allow | safe read & meta tools |
| task | `*` allow (root) | delegation; subagents get `*` deny |
| edit | `*` ask, then plane denies | framework/**, .opencode/**, opencode.json, AGENTS.md denied everywhere |
| webfetch | deny | |
| bash | `*` ask, then allow/deny families | |

**Bash allow families** (root): git read (`git status/diff/log/show`), test/build/lint
(`npm test`, `npm run build`, `npm run lint`, `pytest`, `tsc`, `eslint`, `ruff`,
`mypy`), trusted framework scripts (`python3 framework/*`, `./framework/*`, `python
framework/*`, `bash framework/*`), and PowerShell read cmdlets (`Select-String`,
`Get-ChildItem`, `Get-Content`, `Get-Item`, `Test-Path`).

**Bash deny families** (root and every agent): destructive filesystem (`Remove-Item`,
`rm`, `del`, `rmdir`, `rd`) and git history mutation (`git push`, `git reset`, `git
clean`, `git checkout`, `git restore`, `git rebase`, `git merge`, `git cherry-pick`).

Per-agent permission blocks narrow these further (§5.1 table). The enforcement-plane
denies (`framework/**`, `.opencode/**`, `opencode.json`, `AGENTS.md`) appear in every
agent's edit block.

**G10** asserts this policy structure (filter at the top with "ask", allow families,
deny families, negative invariants: no `backend/scripts/` path trust, no arbitrary
python allow, no `New-Item`). A gate cannot drive opencode's interactive ask/allow
engine, so the behavioural smoke test is manual: `git status` should not prompt,
`python -c "print(1)"` should prompt, `Remove-Item` and `git push` should be denied.

---

## 11. The gates

Gates are executable scripts in `framework/gates/` that return real exit codes.
There are **18 gates** plus the shared library `_lib.sh` and the authoritative exit
code table `EXIT_CODES.md` — 20 files in the directory.

**The universal exit code contract** (from `EXIT_CODES.md`, the authoritative table —
if any document disagrees with it, that document is wrong):

| Code | Meaning |
|---|---|
| 0 | pass |
| 1 | fail (a verdict about the code) |
| 2 | BLOCKED — the gate could not evaluate (toolchain problem: python3 missing, state unreadable). Never read as pass. |
| 3 | UNVERIFIABLE — the gate evaluated preconditions and found no way to produce evidence (capability problem). **Never read as "it looks right."** |
| 4 | NOT_APPLICABLE — there is nothing of this class to judge. A skip, never a pass. |

**Non-zero codes are not interchangeable.** 2 = we could not evaluate (toolchain). 3 =
we could not produce evidence (capability). 4 = nothing to judge. Only 1 is a verdict
about the code. "Exit 3 is the most important code in the framework": on exit 3 you may
NOT claim verified and may NOT claim violated — record `unverifiable` and name what is
missing.

### The gate table

| Gate | File | 0 = | 1 = | 2 = | 3 = | 4 = |
|---|---|---|---|---|---|---|
| G1 contract | `g1_contract.sh` | valid, types in sync, tests green | validation failed / CONTRACT_CHANGE | BLOCKED (python3 absent) | — | — |
| G2 impact | `g2_impact.sh` | impact mapped to N tests | UNKNOWN_IMPACT | — | — | — |
| G3 architecture | `g3_architecture.sh` | boundaries respected | boundary violation | BLOCKED (pyyaml absent) | — | — |
| G4 executable | `g4_executable.sh` | N checks green | ≥1 check failed | — | — | — |
| G5 stack | `g5_frontend_stack.sh` | conformant | violations found | BLOCKED (cannot evaluate) | — | NOT_APPLICABLE (no frontend) |
| G6 browser | `g6_browser.sh` | specs ran and passed | specs ran and failed | **NEVER EMITTED** | UNVERIFIABLE | — |
| G7 retro | `g7_retro.sh` | retros complete, no recurrence | incomplete or recurrence | BLOCKED (python3/pyyaml absent) | — | NOT_APPLICABLE (no escape trigger) |
| G8 blockers | `g8_blockers.sh` | no open blockers | open blockers listed | BLOCKED (python3/pyyaml absent) | — | — |
| G9 scope | `g9_scope.sh` | within declared scope (or SKIP: no plan/no changes) | undeclared files listed | — | — | — |
| G10 permission | `g10_permission.sh` | policy conformant | violations found | BLOCKED (python3 absent) | — | NOT_APPLICABLE (opencode.json absent) |
| G-T0 tool_readiness | `g_tool_readiness.sh` | tool plan exists, registry present, contracts in place | tool plan missing or tools unavailable | BLOCKED (python3 absent) | — | — |
| G-T1 tool_utilization | `g_tool_utilization.sh` | tool evidence present in verification artifacts | tool evidence gaps found | BLOCKED (python3 absent) | — | NO_VERIFICATION_ARTIFACTS |
| G11 evidence | `g11_evidence.sh` | claims valid, provenance present | invalid claims listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G12 provider | `g12_provider.sh` | healthy — dispatch allowed | unhealthy — NO TASK DISPATCH | BLOCKED (cannot verify provider health) | — | NOT_APPLICABLE (no model resolved) |
| G13 worker | `g13_worker.sh` | all workers healthy or terminal | unhealthy worker(s) listed | BLOCKED (cannot read task state) | — | NOT_APPLICABLE (no tasks registered) |
| G14 evidence-integrity | `g14_integrity.sh` | all claims pass E1-E8 | integrity violation(s) listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no claims recorded) |
| G-ENTRY entry | `g_entry.sh` | approved plan + declared scope + acceptance criteria, no open questions — dispatch allowed | named missing prerequisite — NO TASK DISPATCH | BLOCKED (python3 absent / unreadable) | — | NOT_APPLICABLE (ENTRY_EXEMPT=TRIVIAL) |
| G-EXEC exec-integrity | `g_exec.sh` | matrix 38/38 checks pass | deviations listed | BLOCKED (python3 absent) | — | NOT_APPLICABLE (no matrix module) |

### The semantics that matter

- **G6 emits ONLY 0, 1, 3.** It has no exit 2. Missing driver, missing config, and
  missing specs all return **3** (UNVERIFIABLE). A "2 = BLOCKED" for G6 would be a bug:
  it would create a second code for the condition exit 3 exists to name.
- **G7 exit 4 is not a pass.** It means no defect-escape trigger was recorded — the
  normal case for a clean task. It is not evidence the framework is learning.
- **G8 blocks completion on open blockers.** While any open blocker record exists, G8
  returns exit 1 and completion is refused. Exit 2 (unreadable store) is never read as
  zero.
- **G9 skips are not silent passes.** "No plan / no changes" logs SKIP and exits 0 —
  that is "nothing was judged", not "scope respected". A skip must be reported as
  skipped, never counted as a passed check.
- **G11 validates claims, not prose.** It does not judge whether a conclusion is true;
  it judges whether conclusions were recorded as ledger claims with sufficient,
  reproducible provenance.
- **G12 is a pre-flight gate — it refuses dispatch, it does not report it.** It runs
  BEFORE every `task()` dispatch. The first dispatch in a window is the probe; its
  outcome is recorded; a blocking outcome (QUOTA_FAILURE, AUTH_FAILURE,
  MODEL_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_NETWORK_FAILURE) refuses the NEXT
  dispatch with exit 1. G12 has no exit 3.
- **G13 is an observability gate — it refuses completion on an unhealthy worker.** It
  judges the task event stream, not the contract file. STALLED, OVERDUE, unresolved
  FAILED, supervisor-declared LOST, or an unreadable stream → exit 1 naming each task
  WITH its recovery route. WARNING (silent past the progress timeout,
  probe-and-continue) is healthy; only recovery_level ≥ 2 escalates.
- **G14 is an evidence-integrity gate — it refuses completion on borrowed or stale
  evidence.** E1-E5 share the ledger's own validate-record checks; E2 requires a
  repo-relative entry_point to exist on disk; E6 requires a gate named in evidence to
  have a receipt in VERIFICATION.md; E7 forbids open reviewer suspicion on a VERIFIED
  claim; E8 forbids reusing an identical evidence payload across tasks.
- **G-ENTRY is a pre-flight gate.** It runs BEFORE every dispatch, mirroring G12: an
  approved plan (status: approved / approved: true / accepted: true), declared
  `files_or_components`, `acceptance_criteria`, and no unresolved `open_questions`.
  A task with no plan context and no exemption is a routing defect — exit 1, never a
  skip. `ENTRY_EXEMPT=TRIVIAL` is the only documented bypass (team-lead's
  trivial-request gate) and returns 4 — a recorded exemption, not a verdict. G9 remains
  the post-hoc scope check; G-ENTRY is its pre-flight half.
- **G-EXEC asserts execution integrity against the failure-injection matrix.** It
  wraps `framework/adapters/failure_injection.py`, the adversarial E/G matrix that
  drives a delegated-task lifecycle through injected deviations (wrong budgets,
  out-of-order lifecycle events, THINKING while paused, leaked supervision state).
  All 38 checks must behave as the framework declares; the matrix is self-cleaning.

**Universal rules** (verbatim from `EXIT_CODES.md`):

| Rule | Meaning |
|---|---|
| Never pass vacuously | zero checks executed is FAIL, never pass (G4) |
| Missing tool is never a pass | substitute it, or report BLOCKED / UNVERIFIABLE |
| SKIP ≠ PASS | skip means no artefact of that class exists to judge |
| CONTRACT_CHANGE outranks test failure | a schema change causes test failure by definition; route the cause to Architect, not the symptom to Implementer |
| UNKNOWN_IMPACT is not "no impact" | zero tests found at tier 4 escalates |

---

## 12. The verifier profiles

`framework/verifier/profiles.yaml` maps *when a profile applies* → *evidence classes* → *commands/gates*.

| Profile | Applies when | Evidence | Commands / gates |
|---|---|---|---|
| functional | always | unit_test, integration_test | g4, g8, g9, g11, g14 |
| contract | contract_change | contract tests | g1 |
| browser | requirement_shape = visible_behaviour | screenshot, dom_inspection, console_output | g6 (sequence: build → start → navigate → interact → read console → capture → assert) |
| frontend_stack | frontend_files_changed | stack_conformance_exit_code | g5 |
| security | security_sensitive | dependency_scan, authz_integration_test, secret_scan, permission_policy_invariants | npm audit --audit-level=high, pip-audit, g10 |
| performance | scope ∈ {cross_component, system} AND hot_path | measured_benchmark | (benchmark harness) |
| retro | defect_escaped | escape_path_analysis, ledger_entry, fix_verification | g7 |

Two structural rules in the profiles:

- **Browser missing driver → `report_unverifiable`.** When the browser profile applies
  but no browser driver can be produced, the result is UNVERIFIABLE — "never report
  pass". G6's mandatory use cases are visual_alignment, interaction_flow,
  responsive_behaviour.
- **Frontend stack enforcement is a ratchet.** G5 judges only files the current task
  changed; pre-existing violations elsewhere are baseline debt — reported, never
  blocking, and never fixed opportunistically inside an unrelated task.

---

## 13. The retry and escalation policy

`framework/retry_policy.yaml` bounds retries and names escalation routes.

**Retry counts** (max retries per signal, then `on_exhaustion: escalate_to_human`):

| Signal | Retries |
|---|---|
| test_failure | 2 |
| review_rejection | 2 |
| integration_failure | 2 |
| context_expansion | 2 |
| contract_conflict | 0 (immediate escalation) |
| architecture_conflict | 0 (immediate escalation) |
| release_blocked | 0 |
| retro_recurrence | 0 (second occurrence escalates to a human) |
| worker_stalled | 1 (retry once narrower, then take over) |

**Retro triggers** — signals that open a retrospective: `TEST_FAILED_ON_PREVIOUSLY_GREEN`,
`REVIEW_REJECTED`, `INTEGRATION_FAILED`, `TASK_REOPENED`, `PRODUCTION_DEFECT`,
`GATE_FAILED_AFTER_ACCEPTANCE`. These are the cases where a defect was found after the
change that introduced it was accepted.

**Escalation routes** (signal → route): CONTEXT_INSUFFICIENT → same agent retrieves the
named item; GRAPH_STALE → code-intel adapter reindexes; UNKNOWN_IMPACT → same agent
expands to system; TEST_FAILED → implementer debugs; REVIEW_REJECTED → implementer
applies findings; INTEGRATION_FAILED → implementer plus affected consumers;
CONTRACT_CONFLICT → architect then human gate H2; ARCHITECTURE_CONFLICT → architect and
team-lead then human gate H1; SECURITY_FAILURE → implementer with security skill;
PERFORMANCE_FAILURE → implementer with performance skill; RELEASE_BLOCKED → human gate
H3; DEFECT_ESCAPED → team-lead opens a retro trigger, then gate G7; RETRO_RECURRENCE →
human re-assessment.

**Failure classification** (from `framework/providers/healthcheck.py`) decides where
recovery goes:

| Class | Type | Route |
|---|---|---|
| AUTH_FAILURE, QUOTA_FAILURE, MODEL_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_NETWORK_FAILURE | provider (blocking) | provider route: g12 pre-flight, record provider health, dispatch via a fallback provider — no dispatch to this provider (BLOCKED - ENVIRONMENT) |
| AGENT_FAILURE, SUSPECTED_STALL | worker | worker route: record_blocker WORKER_STALLED, retry once narrower, then take over |

Worker-level classes are never provider failures and provider classes are never worker
stalls — misclassifying one as the other is the defect this protocol exists to prevent.
`SUSPECTED_STALL` = "process exists, no output".

---

## 14. The adapters

`framework/adapters/` contains the integration layer — the only place that knows about
specific external systems:

| Adapter | Purpose |
|---|---|
| `gsd_state.py` | GSD state adapter: `task-register`, `task-event`, `task-status`, `task-list`, `task-cancel`, `write-blocker`, `resolve-blocker`, `write-summary`, `detect`, `manifest`, `state-root`, `plan-path`, etc. The supervision commands behind §25. |
| `host.py` | Runtime-neutral host interface — THE only host-aware component. `describe`, `downgrade` (reports whether the active host can enforce permissions). |
| `hosts/opencode.py` | OpenCode backend — fully implemented. |
| `hosts/dsh.py` | DeepSeek Harness — DECLARED, NOT SUPPORTED (runtime peer). |
| `code_intel.py` | Capability interface with the 4-tier priority ladder for code intelligence providers; `resolve`. |
| `failure_injection.py` | The adversarial E/G matrix for G-EXEC (§11): drives a delegated-task lifecycle through injected deviations and reports the 38 checks. |
| `opencode_detect.py` | DEPRECATED shim → host.py. |

Supporting scripts:

- `framework/security/sync_enforcement_plane.py`, `check_enforcement_plane.py` — plane
  mirroring and verification (§9).
- `framework/architecture/checklist_check.py` — design-checklist disposition check.
- `framework/claims/ledger.py` — the claim ledger (§15); commands `path`, `append`,
  `analyse`, `integrity` (E1-E8).
- `framework/verification/suspicion_log.py`, `recovery.py` — reviewer suspicion and
  recovery support (E7/E8 in G14).
- `framework/audit_check.py` — adopt-before-extend audit (exit 3 = undecided overlaps),
  stage 3 of bootstrap.

---

## 15. The claim ledger and evidence provenance

**The claim ledger** (`framework/claims/ledger.py`, append-only JSONL under the state
root) is where conclusions live. A conclusion that is not recorded as a claim with
reproducible provenance is not a conclusion — it is an unverified observation
(`.opencode/rules/evidence-provenance.md`).

- **Claim classes**: environment / behavioral / data / causal.
- **Classification vocabulary**: FACT | HYPOTHESIS | ASSUMPTION | UNKNOWN. The default
  for anything not reproduced is UNKNOWN. An agent may not silently promote a claim to
  a higher certainty without the evidence the class requires.
- **VERIFIED** requires: confirmed under the canonical runtime, reproducible, names the
  exact command, has provenance (runtime + entry_point + reproduced: true), records
  expected vs actual, and an independent check for high-impact claims. Provider-chain
  bugs are verified end-to-end (L3), not in a unit harness.
- **Ledger commands**: `append --json '{...}'` auto-assigns `CLM-NNN`; validation
  failure exits 1 (never 2); `integrity` runs E1-E8.

**G11** validates ledger validity on every functional run; **G14** judges evidence
integrity (E1-E8: bound to task, entry_point exists on disk, git_sha-consistent,
timestamp-sane, gate receipt in VERIFICATION.md, no open suspicion, no cross-task
evidence reuse).

**verify/G-VERIFY rule**: the team-lead gate on findings; insufficient provenance is
blocker signal `EVIDENCE_INSUFFICIENT` (retry action: gather_provenance_or_downgrade_claim).

---

## 16. The retrospective subsystem

`framework/retro/` implements the rule: *a defect that reaches production is two
failures — the defect, and the framework that passed it.*

- **When owed**: a defect found after the change that introduced it was accepted
  (TEST_FAILED_ON_PREVIOUSLY_GREEN, REVIEW_REJECTED, INTEGRATION_FAILED, TASK_REOPENED,
  PRODUCTION_DEFECT, GATE_FAILED_AFTER_ACCEPTANCE). NOT owed when a checkpoint catches a
  defect at the first place it could have been caught — that is the framework working.
- **Escape path is computed, not argued**: `framework/retro/escape_path.py` takes where
  the defect was injected, where it was caught, and the task's original classification,
  and returns the checkpoints it passed through. An agent cannot reason its way out of
  it, and cannot inflate it.
- **Routing gap vs containment miss**: a routing gap means the checkpoint would have
  caught the defect but never ran — fix the routing (cheaper, closes a whole class). A
  containment miss means the checkpoint ran and missed it — fix the check. Routing gaps
  take precedence.
- **Recommendations must be falsifiable**: one target from the closed list in
  `framework/retro/containment_map.yaml` (a file plus a check that proves the change
  landed). Unfalsifiable recommendations ("be more careful", "add more tests") are
  rejected.
- **A claimed fix needs an exit code**: `fix_verified_by` is a command and its result.
- **Recurrence outranks any individual retrospective**: the ledger matches structural
  signatures (injection phase + defect class + primary gap + escaped checkpoints —
  never task id/description). Second occurrence escalates to a human with zero retries.
- **Where a lesson goes**: `destination.tier` decides — executable_check (gate exit
  code) / declared_rule (architecture_rules.yaml or a skill rule) / design_checklist
  (architecture only) / agent_instruction / unmapped_combination (adding the map row is
  the fix) / accepted (prevention costs more than recurrence).

**G7** gates completion on this: retros complete and no recurrence (0), incomplete or
recurrence (1).

---

## 17. The telemetry plugin and model tuning

**Telemetry plugin** (`.opencode/plugin/telemetry.ts`, registered in `opencode.json`):
a v2 collector that writes one lifecycle record per session to
`<state_root>/telemetry/records.jsonl` in a series: `started` → `heartbeat` (every 60s
and at compaction) → `final`. Optional `TASK_ID` environment variable tags a session to
a task.

**Aggregation** (`framework/telemetry/report.py`):

| Exit | Meaning |
|---|---|
| 0 | report produced |
| 1 | produced, but sessions were never finalized or telemetry anomalies exist |
| 2 | records exist but none parse |
| 3 | nothing has run — not a failure |

Report sections: COST, TOKENS BY AGENT, BOTTLENECKS, GATES, CONTEXT, REWORK RATE,
DURATION. `validate.py` verifies the telemetry record after a session
(`bg_poll_total > 0` flags a session as violating the background-task contract).

**Model tuning** (`framework/models/profiles.sh`): switches per-agent models by
profile — `baseline | tiered | cheap | reset` — using `OC_BIG`, `OC_MID`, `OC_SML`
environment variables. This repository's current single model is `opencode/big-pickle`
for both the main and small model.

---

## 18. The execution context

`framework/execution_context.yaml` declares the **canonical runtime** per scope. This
is what "under the canonical runtime" means in the evidence rules: recorded `ENV-`
rows are compared against the declaration.

- `check-env` compares a recorded `ENV-` row against the declaration for its scope and
  exits 0 (match) / 1 (mismatch) / 3 (no canonical declaration or no recorded row).
- Only declared fields are compared; a declared field missing from the recorded row is
  a mismatch.
- Fields: `interpreter` (bare name or repo-root-resolved path), `cwd` (repo-root
  resolved), `os`, optional `git_dirty`.

Current declarations:

```yaml
scopes:
  backend:
    interpreter: .venv/Scripts/python.exe
    cwd: .
    os: win32
  framework:
    interpreter: python
    cwd: .
    os: win32
```

---

## 19. The architecture rules

`framework/architecture_rules.yaml` declares the boundaries **G3 enforces**. Everything
here is explicit; a boundary not written here is not enforced ("Boundaries are
declared, never inferred").

```yaml
forbidden_imports:
  - from: src/frontend/
    must_not_import: ["src/backend/", "prisma/", "sqlalchemy"]
  - from: src/backend/
    must_not_import: ["src/frontend/components/"]
  - from: src/domain/
    must_not_import: ["axios", "fetch", "requests", "psycopg"]

layer_order: [domain, application, infrastructure, interface]
```

- `src/domain/` is the pure layer: no web clients, no database drivers.
- `src/frontend/` must not reach into the backend, prisma, or sqlalchemy.
- `src/backend/` must not reach into frontend components.

---

## 20. The state directory (.planning/)

GSD keeps its state under `.planning/` in the repository (the *state root*; the
bootstrap creates `contracts/`, `decisions/`, `telemetry/` there):

| Path | Contents |
|---|---|
| `.planning/` | project state: phases, plans, requirements, decisions, tasks |
| `.planning/contracts/` | contracts (owned by the architect; `.planning/contracts/**` is the one edit path the architect may ask for) |
| `.planning/decisions/` | recorded decisions |
| `.planning/telemetry/` | telemetry records |
| `<state_root>/tasks/` | supervised-task contracts (T-01.json) and event streams (T-01.events.jsonl) |
| `<state_root>/blockers.yaml` | open blocker records (G8 reads this) |
| `<state_root>/retro/triggers/` | open defect-escape triggers (G7 reads this) |
| `<state_root>/providers/health.jsonl` | provider health records (G12 reads this) |
| `<state_root>/claims/` | the claim ledger |

The GSD adapter (`framework/adapters/gsd_state.py`) is the *only* interface to this
state — never hand-edit these files. It detects the installed GSD distribution
(`detect`), builds a manifest, and exposes `state-root` for all consumers.

---

## 21. The lifecycle integration (.lifecycle/)

The feature-development lifecycle (`FEATURE_DEVELOPMENT_LIFECYCLE.md`, spec v1.1)
integrates with the gate framework in **two layers, one governance chain**
(`.lifecycle/INTEGRATION.md`):

```
feature lifecycle F0 qualification
  → F1-F5 requirements & test basis
  → F6-F11 design
  → F12-F16 execution
  → F17 defect learning (trace.yml, baselines)
        │
        ▼
existing gates G1-G6 (unchanged)
  + additive lifecycle gates G0, G0.5, G3.5, G7, G8
  + human gates H1, H2, H3
```

- **The lifecycle owns exactly five gates: G0, G0.5, G3.5, G7, G8.** G0/G0.5 gate
  entry into the lifecycle; G3.5 gates the design handoff; G7 (retro) and G8
  (blockers) are shared with the core framework.
- **H1** inbound: F8-architecture.md, F9-detailed-design.md, the alternatives record
  (L3+), and the F8 architecture F9 detailed design deliverables.
- **Rule of precedence**: the existing authoritative definition wins (e.g.,
  `EXIT_CODES.md` outranks any checklist). `external_gates.definitions_location` binds
  in `config.yml`; until bound, G1-G6 checklists are supplements.
- Configuration lives in `.lifecycle/config.yml`.

---

## 22. The bootstrap script and validation suite

**Bootstrap** (`framework/bootstrap.sh`) is sequential and stops on the first failed
stage. Seven stages:

1. **Detect agent runtime host** — `host.py describe`; prints host, version,
   permission-enforcement capability, agent-format kind, host-neutral portability
   percentage; warns if the host cannot enforce permissions ("star topology is
   advisory").
2. **Detect GSD distribution and instantiate the state adapter** — `gsd_state.py
   detect`, `manifest`, `state-root`; creates contracts/decisions/telemetry dirs.
3. **Adopt-before-extend audit** — `audit_check.py`: every overlap between GSD and
   framework capabilities needs a recorded decision (adopt | wrap | replace).
   "Unexamined overlap is how a 7-agent framework silently becomes a 13-agent one."
   Exit 3 = required step, not a defect.
4. **Resolve code intelligence capabilities** — `code_intel.py resolve`; prints the
   provider and capability tiers.
5. **Agent, tool, plugin and permission artifacts** — verifies `opencode.json`,
   `AGENTS.md`, `.opencode/tools/context-builder.ts`, `.opencode/plugins/telemetry.ts`
   exist; counts agent definitions; marks scripts executable.
6. **Skills and rules** — lists skills and rules; chmods retro scripts; reports open
   retro triggers ("an install inherits nothing silently") and open blockers (an
   unreadable blocker store is reported as unreadable, never as zero).
7. **Validate** — runs `framework/validate.py`; on failure, stops.

**Validation suite** (`framework/validate.py`, ~2360 lines, machine-checks the whole
framework): every check prints PASS/FAIL/WARN. What it checks includes:

- **Agents & permissions**: the seven core agents are defined; implementer can edit;
  architect edits contracts only; verifier cannot edit source; team-lead may delegate;
  per-agent permission invariants.
- **Adapters**: adapter health runs, state round-trips, capabilities resolve.
- **Gates**: g4 returns a real exit code and does not pass vacuously; g1 runs and
  reports; g1 refuses to pass without contract tests.
- **Context builder**: excerpt caps present; prefers pointers; returns provider tier.
- **Retry policy & profiles**: `test_failure: 2`, `on_exhaustion: escalate_to_human`,
  zero-retry conflicts, `impact_to_gates` present, `report_unverifiable` for missing
  browser driver.
- **Config**: instructions reference AGENTS.md and the rules; AGENTS.md stays small
  (< 6000 chars); no requirements inlined; the do-not-invoke rule is present.
- **Telemetry plugin**: exists; collector targets g8; session.idle not used as a hook
  key; flush routed through the event hook; bash args read from the input parameter;
  gate result parsed from stdout not exit code; per-agent token attribution; streaming
  tokens de-duplicated; flush idempotent; no duplicate plugin copy; plugin registered.
- **Contracts**: openapi schema present; contract tests present.
- **Frontend**: stack contract exists; G5 gate wired; G6 browser gate exists.

---

## 23. The frontend stack contract

The frontend stack is a **contract**, not a preference (`AGENTS.md`,
`framework/frontend/`):

- **Mandated**: shadcn/ui, Tailwind, Lucide, Motion, Playwright. G5 enforces this on
  files the current task changes (ratchet — baseline debt elsewhere is reported, never
  blocking, never fixed opportunistically).
- **Conditional** (require an entry in
  `framework/frontend/effect_justifications.yaml` naming a requirement ID, a file
  scope, and an approver): Magic UI, Aceternity, GSAP (which additionally requires a
  measured reason Motion is insufficient), and React Three Fiber.
- **An empty ledger means conditional tools are not permitted** — permission is granted
  per requirement, not once per repository.
- **Visible behaviour needs browser evidence**: G6. Exit 3 (unverifiable) is never a
  pass.

---

## 24. The context builder tool

`.opencode/tools/context-builder.ts` resolves a task pointer set (requirements,
contracts, decisions, symbols, GSD task id) into paths, symbol locations, contract
files, and impact sets — returning pointers plus capped excerpts. It:

- enforces excerpt caps (`EXCERPT_CAP_CHARS`, `TOTAL_MATERIALISE_CAP`),
- prefers pointers over copied content ("Prefer pointers over copied content" is a
  requirement validated by `validate.py`),
- returns the provider tier (integration with the code-intel adapter),
- is integration-tested by the validation suite.

---

## 25. Delegated task supervision

Supervision is executable state, not conversation (`.opencode/rules/delegation-protocol.md`).
Every supervised `task(...)` is registered in `<state_root>/tasks/` as an immutable
contract plus an append-only lifecycle event stream. `session_info` is not progress.

**Contract fields** (`task-register`): `agent`, `objective`, `expected_artifact`
(required); recommended `type`, `session_id`, `background_task_id`, `checkpoints`,
`allowed_tools`, `completion_criteria`, `failure_criteria`, `progress_timeout_s`,
`max_duration_s`, `retry_of`, `headless`. Contracts are immutable — a re-register for
the same id fails with EXISTS; the suggested fix is a fresh id carrying
`retry_of: <old-id>`. Time budgets come from `framework/tasks/task_types.yaml`; a type
declaring `null` (verify) requires the contract to name the budget.

**Lifecycle** (`task-event`): SPAWNED → ACK → STARTED → PROGRESS → BLOCKED → COMPLETED |
FAILED | LOST; supervisor CANCELLED. Terminal states are final. `FAILED` REQUIRES
`failure_class` (closed taxonomy, §13) — without it the event is refused
(TASK_INVALID_FAILURE_CLASS). `LOST` is supervisor-declared only, with a non-empty
detail, and never routes through the failure ladder.

**Shared checkpoint vocabulary** (declared in `framework/tasks/task_types.yaml`):

| Checkpoint | Meaning |
|---|---|
| C0-TASK_ACCEPTED | worker accepted the contract and objective |
| C1-CONTEXT_READ | plan, requirements, contracts and tests read |
| C2-PLAN_CONFIRMED | plan confirmed against the contract before work |
| C3-IMPLEMENTATION_STARTED | first change landed |
| C4-IMPLEMENTATION_COMPLETE | implementation done, tests not yet green |
| C5-TESTS_GREEN | applicable tests pass |
| C6-REVIEW_READY | work ready for review |
| C7-VERIFICATION_DONE | verification evidence recorded |
| C8-HANDOFF_READY | handoff written, task complete |

**Health** (`task-status`), derived from the last event against contract deadlines:

| Health | Level | Condition | Recovery action |
|---|---|---|---|
| HEALTHY | 0 | silent_s < progress_timeout_s | continue |
| WARNING | 1 | silent_s ≥ progress_timeout_s | query_worker: ask for current checkpoint and blockers |
| STALLED | 2 | silent_s ≥ 2 * progress_timeout_s | inspect_session: read session state; cancel only if frozen |
| OVERDUE | 3 | elapsed_s ≥ max_duration_s | cancel_and_retry: cancel, retry with narrowed prompt |
| FAILED | 4 | worker event FAILED (failure_class REQUIRED) | blocking class → g12 pre-flight, fallback provider; worker class → record_blocker WORKER_STALLED, retry once narrower, then take over |
| LOST | 4 | supervisor-declared, no failure recorded | re-dispatch a fresh attempt on a narrowed contract |
| COMPLETE | 0 | state COMPLETED | accept only after checking the deliverable |
| CANCELLED | 0 | supervisor cancel | never quietly forgotten |

A stale-looking task is **inspected with `task-status`, never re-invoked blindly** —
probing is the WARNING action, not the STALLED one. Per-type recovery routes are
declared in `task_types.yaml` and surfaced as `recovery_policy` — the supervisor acts
on the declared policy, never an invented one.

---

## 26. Every use case, step by step

### 26.1 The golden path — a new feature

1. **Ask.** You tell the team-lead: "add a login screen."
2. **Discovery & classification (team-lead).** It discovers the outcome, classifies
   the ask (NEW FEATURE), and assigns complexity and impact. `public_api_change` or
   `security_sensitive` widens the impact automatically.
3. **Requirements.** `requirements-authoring` produces user stories with
   Given/When/Then acceptance criteria.
4. **Research (if unknowns exist).** `researcher` investigates, using the evidence
   hierarchy, and returns YAML findings with classifications.
5. **Architecture.** `architect` runs a Scan/Focus/Full pass, produces the design, and
   — if the HTTP API changes — `api-design` then `contract-authoring` update the
   OpenAPI contract and regenerate types (this triggers G1's CONTRACT_CHANGE path).
6. **Planning.** `planner` decomposes the approved design into GSD tasks, each with
   `files_or_components`, `acceptance_criteria`, `evidence_classes`, `complexity`,
   `impact`, and `required_skills`. A tool plan records the skills.
7. **Pre-flight.** For each dispatch: **G-ENTRY** confirms the plan is approved,
   declares files and acceptance criteria, and has no open questions. **G12** confirms
   the provider is healthy.
8. **Registration.** The task is registered (`task-register`) with budgets matching its
   type; the worker ACKs and starts the C0 → C8 checkpoint progression.
9. **Implementation.** `implementer` loads every required skill, writes code and tests,
   watches gates from §2's list (G1-G6 as applicable).
10. **Review.** `reviewer` judges the diff independently — ever edits.
11. **Verification.** `verifier` executes tests, builds, gates, and (for visible
    behaviour) browser specs, then writes `.planning/**/VERIFICATION.md` with gate
    receipts. **G9** confirms only declared files changed. **G11/G14** confirm claims
    are valid and evidence is not borrowed or stale. **G13** confirms every worker is
    healthy or terminal. **G8** confirms no open blockers.
12. **Close.** The handoff is written; telemetry records the session; if a defect
    escaped at any earlier accepted change, **G7** blocks until the retrospective is
    complete and the recomputed escape path is closed.

### 26.2 A trivial bug fix

1. **Classification.** team-lead applies the trivial-request gate: single ask, single
   file, unambiguous, no behavioural scope. It records `ENTRY_EXEMPT=TRIVIAL`.
2. **Dispatch.** G-ENTRY returns 4 (NOT_APPLICABLE by exemption — a recorded exemption,
   not a verdict); G12 still checks provider health.
3. **Execute.** The fix lands; G2/G9/G8/G11 confirm impact mapping, scope, blockers,
   and claims.

### 26.3 A task whose worker goes silent

1. `task-status` shows the worker past `progress_timeout_s` → WARNING → the supervisor
   queries it.
2. Past `2 * progress_timeout_s` with no progress → STALLED → the supervisor inspects;
   cancels only if frozen.
3. Past `max_duration_s` → OVERDUE → cancel_and_retry with a narrowed prompt.
4. If the worker emitted FAILED, the `failure_class` decides the route: a blocking
   provider class → g12 pre-flight and a fallback provider, NO dispatch to this
   provider; a worker class → `record_blocker WORKER_STALLED`, retry once narrower,
   then the supervisor takes over.

### 26.4 A gate that cannot run

- Missing python3 → the gate exits 2 (BLOCKED): "never read as pass".
- Browser profile applies but no driver → `report_unverifiable`: exit 3, record the
  requirement as unverifiable and name what is missing. You may not claim verified, you
  may not claim violated.
- Nothing of that class exists (no frontend, no claims, no tasks) → exit 4 (a skip,
  reported as skipped, never counted as pass).

### 26.5 A defect that escapes to the next check level

1. The trigger is recorded (e.g., REVIEW_REJECTED — review caught what earlier
   checkpoints did not).
2. `escape_path.py` computes which checkpoints it passed through — arithmetic, not
   argument.
3. The gap is classified as a routing gap (check never ran → fix the routing) or a
   containment miss (check ran and missed → fix the check).
4. A falsifiable recommendation from the closed containment map lands at its
   destination tier; the fix is proven by an exit code (`fix_verified_by`).
5. G7 blocks completion until the retro ledger shows no recurrence.

---

## 27. File map

```
opencode.json                     runtime config: model, instructions, permissions,
                                  agents, MCP servers, references, skills paths,
                                  plugin, compaction (auto + prune)
AGENTS.md                         stable global rules + enforcement-plane fence
README.md                         install + two-axis summary
framework/
  gates/
    EXIT_CODES.md                 AUTHORITATIVE exit-code contract (the table in §11)
    g1_contract.sh  g2_impact.sh  g3_architecture.sh  g4_executable.sh
    g5_frontend_stack.sh          g6_browser.sh  g7_retro.sh  g8_blockers.sh
    g9_scope.sh  g10_permission.sh  g_tool_readiness.sh  g_tool_utilization.sh
    g11_evidence.sh  g12_provider.sh  g13_worker.sh  g14_integrity.sh
    g_entry.sh  g_exec.sh  _lib.sh (shared gate library)
  adapters/
    gsd_state.py                  GSD state adapter (supervision + state commands)
    host.py                       host detection/describe/downgrade
    hosts/opencode.py, dsh.py     host backends
    code_intel.py                 code-intelligence capability ladder
    failure_injection.py          G-EXEC adversarial E/G matrix
    opencode_detect.py            DEPRECATED shim
  security/
    enforcement_plane.yaml        canonical plane
    sync_enforcement_plane.py     mirrors the plane into opencode.json + AGENTS.md
    check_enforcement_plane.py    asserts all three agree (must exit 0)
  claims/ledger.py                claim ledger (append/analyse/integrity E1-E8)
  retro/                          escape_path.py, containment_map.yaml, README
  telemetry/                      report.py, records
  verifier/profiles.yaml          profile → evidence → gates mapping
  tasks/task_types.yaml           task types, budgets, checkpoints, recovery routes
  retry_policy.yaml               retry counts, routes, retro triggers
  providers/healthcheck.py        provider health: classify/record/check
  architecture_rules.yaml         G3 boundaries
  architecture/checklist_check.py design-checklist disposition
  execution_context.yaml          canonical runtime declarations
  models/profiles.sh              model profile switching (baseline|tiered|cheap|reset)
  audit_check.py                  adopt-before-extend audit
  ADOPT_AUDIT.md                  required install step
  bootstrap.sh                    seven-stage install
  validate.py                     validation suite (machine-checks the framework)
.opencode/
  agents/                         40 agent definitions (7 core + 33 gsd-*)
  rules/                          9 standing rules
  skills/                         85 skills (14 framework + 71 gsd-*)
  skill-routing.md                central registry: condition → skill → agent
  skill-integration-matrix.md     binding contract: role → skill → artifact → gate
  tools/context-builder.ts        pointer resolver, capped excerpts
  plugin/telemetry.ts             v2 telemetry collector
.lifecycle/
  INTEGRATION.md                  lifecycle-gate integration (spec v1.1)
  config.yml                      lifecycle configuration
  FEATURE_DEVELOPMENT_LIFECYCLE.md normative source
.planning/                        GSD state root (phases, plans, decisions, contracts,
                                  telemetry, tasks, blockers, retro triggers, claims)
docs/                             project documentation (this file lives here)
src/                              application source (frontend/, backend/, domain/)
tests/                            tests
```

---

## 28. How to add a skill

A skill is a directory under `.opencode/skills/<name>/` with a `SKILL.md` (plus
supporting files). To add one:

1. **Write the skill** in `.opencode/skills/<name>/SKILL.md`:
   - a one-paragraph description that states **when to use it** (the `skill` tool and
     agent delegation match on this),
   - the workflow or rules the agent should follow,
   - any supporting files (templates, scripts, reference docs) in the same directory.
2. **Register it in the routing table** (`.opencode/skill-routing.md`): add a row
   mapping the triggering *condition* → your skill → the *agent* that should load it.
   This is the file agents consult to know which skill matches which task.
3. **Update the integration matrix** (`.opencode/skill-integration-matrix.md`): add the
   role → skill → artifact → gate row. The matrix is the binding contract; a skill that
   is not in the matrix is not verifiable by G-T1.
4. **Reference it where needed**:
   - plans name it in `required_skills` (planner → implementer),
   - team-lead's tool plan records it,
   - if the skill produces an artifact a gate judges, wire the gate check.
5. **Verify with the tool gates**: G-T0 (tool readiness — registry present) and G-T1
   (tool utilization — evidence in verification artifacts) plus
   `python3 framework/validate.py` and the plane checker
   (`framework/security/check_enforcement_plane.py`, exit 0) after any change.

> **Plane constraint**: `.opencode/` is part of the enforcement plane — agents cannot
> edit it. Adding or changing a skill is therefore a human/owner action (or a change
> approved outside the plane): propose the skill content + routing rows in a reviewable
> change, have a human apply it, then re-run the plane checker and validation.

---

## 29. How to modify the flow

The flow (§2) is produced by the interaction of: the permission model (`opencode.json`),
the team-lead charter (`.opencode/agents/team-lead.md`), the routing and integration
matrices, the gate wiring, and the verifier profiles. Changing the flow means changing
one of those, and each has a check:

| You want to change… | You edit… | You must then verify… |
|---|---|---|
| Who may do what (permissions) | `opencode.json` (permission blocks) | G10 + the manual smoke test (§10) + `check_enforcement_plane.py` (exit 0) if the plane fence is touched |
| How asks are classified | `.opencode/agents/team-lead.md` | agents reload instructions on next session; validate.py checks instructions reference the rules |
| Which skill a task uses | `.opencode/skill-routing.md` + `.opencode/skill-integration-matrix.md` | G-T0 / G-T1 |
| Which gate proves a requirement | `framework/verifier/profiles.yaml` (profile → commands/gates) + `framework/gates/*.sh` | run the gate, record its exit code; `framework/validate.py`; `EXIT_CODES.md` stays authoritative |
| Declared boundaries | `framework/architecture_rules.yaml` | G3 on affected tasks |
| Retry behaviour / escalation | `framework/retry_policy.yaml` | validate.py checks retry counts and escalation exist |
| Task budgets / checkpoints | `framework/tasks/task_types.yaml` | task-status surfaces them; G13 enforces |
| Canonical runtime | `framework/execution_context.yaml` | check-env compare |
| The security plane itself | `framework/security/enforcement_plane.yaml` (human-only) | `sync_enforcement_plane.py` then `check_enforcement_plane.py` (exit 0); validate.py |

**The universal rule**: any flow change must land with (a) the changed file, (b) the
executable check that proves the change behaves as declared — an exit code, not a
description — and (c) a note in the relevant handoff/decision record. A flow change
with no verification is a claim, not a change.

---

## 30. Exit code reference

Reserved codes across the framework (each tool may use a subset):

| Code | Meaning |
|---|---|
| 0 | pass / produced / healthy / dispatch allowed |
| 1 | fail / violations / unhealthy / NO TASK DISPATCH / report produced with anomalies |
| 2 | BLOCKED (cannot evaluate; toolchain problem) — never read as pass |
| 3 | UNVERIFIABLE (capability problem; used by G6, check-env, telemetry "nothing has run") |
| 4 | NOT_APPLICABLE (nothing to judge; recorded exemption; a skip, never a pass) |
| 124 | timeout (mirrors POSIX `timeout(1)`; a slow gate is "blocked", never a crashed suite — validate.py sh()) |

Specific tools:

- `check-env` (execution_context): 0 match / 1 mismatch / 3 no canonical declaration or
  no recorded ENV- row.
- `ledger.py append`: 0 appended / 1 validation failure (never 2).
- `ledger.py integrity`: 0 clean / 1 violations / 2 blocked / 3 empty ledger (G14 maps
  this to NOT_APPLICABLE).
- `report.py` (telemetry): 0 produced / 1 produced with finalized-session anomalies /
  2 unparsable records / 3 nothing has run.
- `audit_check.py`: 0 complete / 3 undecided overlaps (required step) / other = failure.
- `failure_injection.py` (G-EXEC): 0 = matrix 38/38 green; non-zero = deviations listed.
- `provider check` (healthcheck): 0 pass / 1 blocking class named / 2 cannot determine /
  3 usage / 4 nothing resolved. Blocked is never a pass.

---

## 31. Glossary

| Term | Definition |
|---|---|
| Agent | A persona definition with its own permissions, model, and temperature. |
| Ask | A request to team-lead; classified before work starts. |
| Blocker | A recorded non-complete stop (signal + missing item + what was tried). |
| Claim | The unit of truth: a recorded conclusion with provenance and classification. |
| Complexity | L0-L4; governs how much planning a task deserves. |
| Contract | An HTTP API specification (OpenAPI) plus generated types and tests. |
| CONTRACT_CHANGE | A schema change that makes old tests fail by definition; routed to Architect. |
| Defect escape | A defect found after the change that introduced it was accepted. |
| Enforcement plane | The agent-immutable files that define what checks the agents. |
| Evidence | Recorded output of an executed check, with runtime and entry point. |
| Gate | An executable script returning a real exit code; proves or fails to prove. |
| GSD | The planning/workflow system: phases, plans, requirements, state under .planning/. |
| Impact | Scope/contract/API/data/security; governs how much verification is required. |
| Ledger | The append-only claim store; claims live here or they do not exist. |
| Plan | GSD task plan: approved, declares files and acceptance criteria. |
| Retrospective | The computed analysis of a defect escape; fixes the framework, not just the code. |
| Routing gap | A checkpoint that would have caught a defect but never ran. |
| Containment miss | A checkpoint that ran but missed the defect. |
| Rule | A standing instruction agents must obey. |
| Skill | Packaged specialist knowledge, loaded by agents when needed. |
| Subagent | An agent that only works when delegated to (all except team-lead). |
| Tool plan | team-lead's record of which skills/tools a task requires (G-T0 checks it). |
| Verification | Evidence that a DoD claim is true in this run. |
| VERIFIED | A claim confirmed under the canonical runtime with reproducible provenance. |