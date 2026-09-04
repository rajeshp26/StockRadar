# FEATURE_DEVELOPMENT_LIFECYCLE.md

Version: 1.1
Status: Normative
Supersedes: 1.0 (see `.lifecycle/CHANGELOG.md` for the v1.0 → v1.1 delta)
Applies to: any repository, any host agent runtime (OpenCode, Codex, Antigravity, Claude Code, Cursor, Copilot Workspace)
Owner agent: Team Lead
Integrates with: the project's existing G1–G6 executable gates and H1/H2/H3 human gates (§15)

## 0. What this document is

This is the normative feature-engineering front end for an agentic development framework. It defines a feature-level lifecycle with two synchronized paths — Development and Verification — joined by bidirectional traceability and a defect learning loop.

It is deliberately tool-agnostic. It lives in the repository as plain Markdown plus machine-readable configuration and schemas. The host agent runtime is only an execution surface; the lifecycle, the artifacts, the gates and the traceability graph belong to the repo.

This document is the front end. It does not own release governance. Existing G1–G6 remain the executable enforcement layer, and existing H1/H2/H3 remain the human decision layer. §15 defines the seam.

Four rules govern everything below.

1. Verification analysis begins when a requirement is created, not after code exists.
2. **The lifecycle must be rigorous in reasoning but proportional in execution.** Depth is a function of classified complexity, impact and risk. Small changes must not be forced through the full lifecycle.
3. No agent identity may certify a gate on an artifact that same identity authored.
4. A defect requires symptom correction always, and escape correction whenever an engineering artifact or process was inadequate.

## 1. Installation

### 1.1 Repository layout

```
<repo-root>/
├── AGENTS.md                          # host-tool entry contract; points here
├── .lifecycle/
│   ├── FEATURE_DEVELOPMENT_LIFECYCLE.md   # this file (source of truth)
│   ├── CHANGELOG.md                   # version delta record
│   ├── INTEGRATION.md                 # G1–G6 and H1/H2/H3 binding (§15)
│   ├── config.yml                     # depth tailoring + project bindings
│   ├── agents/                        # per-agent charters (§4)
│   │   ├── team-lead.md
│   │   ├── researcher.md
│   │   ├── architect.md
│   │   ├── planner.md
│   │   ├── implementer.md
│   │   ├── reviewer.md
│   │   └── verifier.md
│   ├── templates/                     # artifact templates
│   ├── checklists/                    # gate checklists (§9)
│   ├── schema/                        # machine-readable validation (§16)
│   │   ├── state.schema.json
│   │   ├── trace.schema.json
│   │   ├── contract.schema.json
│   │   ├── event.schema.json
│   │   ├── gate.schema.json
│   │   └── defect.schema.json
│   └── scripts/
│       ├── orphan-check.py            # §8.4 mechanical check
│       └── lifecycle-validate.py      # §16 schema + depth-rule validator
└── features/
    └── <FEATURE-ID>/
        ├── state.json                 # lifecycle state machine (§7)
        ├── trace.yml                  # traceability graph + baselines (§8)
        ├── F0-qualification.md
        ├── F1-context.md
        ├── F2-scenarios.md
        ├── F3-requirements.md
        ├── F4-requirements-challenge.md
        ├── F5-test-analysis.md
        ├── F6-decomposition.md        # includes the state-ownership register (§6.5)
        ├── F7-contracts/
        │   ├── IFC-*.yml
        │   └── EVT-*.yml
        ├── F8-architecture.md
        ├── F9-detailed-design.md
        ├── F10-impact-analysis.md
        ├── F11-design-review.md
        ├── evidence/
        │   ├── F13-unit/
        │   ├── F14-integration/
        │   ├── F15-system/
        │   └── F16-validation/
        ├── gates/
        │   └── <GATE-ID>.md           # gate ledger entries (§9.1)
        └── defects/
            └── DEF-*.md
```

### 1.2 Host-tool binding

The only integration point is the host tool's always-on entry file. Add this block to it verbatim.

```markdown
## Feature lifecycle (mandatory)

Before any non-trivial change, read `.lifecycle/FEATURE_DEVELOPMENT_LIFECYCLE.md`
and `.lifecycle/config.yml`.

1. Classify the task per §3 (Feature Qualification) and write `features/<ID>/F0-qualification.md`.
2. Execute only the phases required by the resulting depth level (§3.4).
3. Do not write production code until the gates required for that depth have PASS
   entries in `features/<ID>/gates/`.
4. Update `features/<ID>/trace.yml` in the same change that creates or modifies any
   requirement, contract, design element, code unit or test.
5. Record your agent identity (`agent_id`, `role`, `session_id`) in every artifact
   header and every gate ledger entry (§9.1). Independence is checked on identity,
   not on role name.
```

Binding per runtime:

| Runtime | Entry file to contain the block above | Agent definitions |
|---|---|---|
| OpenCode | `AGENTS.md` | `.opencode/agent/*.md`, each a thin file whose body is `Read .lifecycle/agents/<role>.md and act only within that charter.` |
| Codex | `AGENTS.md` | reusable prompts referencing `.lifecycle/agents/<role>.md` |
| Antigravity | its project rules/entry file | same pointer pattern |
| Claude Code | `CLAUDE.md` (or a pointer to `AGENTS.md`) | subagent files pointing at `.lifecycle/agents/*` |
| Cursor / Copilot | project rules file | same pointer pattern |

Verify the current config path for your runtime version. The pointer pattern is what makes the spec portable: charters are never duplicated per tool, only referenced.

Single-agent runtimes: where no subagents exist, one agent adopts each charter sequentially. It records the charter in every artifact header, and it must open a **new session** before certifying a gate on an artifact it authored under a different charter. A new session yields a new `session_id`, which is what §9.1 checks. If the runtime cannot produce a distinct session, the gate is certified by a human reviewer and the ledger records that.

### 1.3 config.yml

See `.lifecycle/config.yml` for the project instantiation. Its normative shape is:

```yaml
project: { id, name, domains, safety_relevant, regulatory_scope }
layers: {}                  # the seams this project's features cross
id_prefixes: {}             # CUS, JRN, UC, SCN, US, AC, NFR, CMP, IFC, EVT, DES, IMP, UT, IT, ST, VT, DEF, ESC, TC, RSK, BL
depths:                     # phases and gates are SEPARATE lists (§3.4)
  L0: { phases: [...], gates: [...] }
  L1: { phases: [...], gates: [...] }
  L2: { phases: [...], gates: [...] }
  L3: { phases: [...], gates: [...] }
  L4: { phases: [...], gates: [...], risk_controls: true }
rules:
  gates_must_be_subset_of_phase_requirements: true
  required_gate_missing: BLOCK
  g0_5_mandatory_when_f5_performed: true
  independence: identity          # identity | role_and_identity  (L4 forces the latter)
depth_floors: []            # project-specific tightening only
gates: { self_certification: forbidden, ledger_required: true, conditional_forbidden_at: [...] }
risk: {}                    # §5.2 scoring bands and the depth each band earns
authorship: {}              # §9.1 identity fields
evidence: {}                # §9.1 immutable reference fields
coverage_menu: []           # §8.5
commands: {}                # bound to real targets; used by G4 evidence
external_gates: {}          # §15 binding to existing G1–G6 and H1/H2/H3
```

## 2. Lifecycle shape

```
                        FEATURE / ENHANCEMENT
                                 │
                                 ▼
                    F0  FEATURE QUALIFICATION
                        classify · complexity · impact · risk · depth
                                 │
                                 ▼
                    F1  FEATURE UNDERSTANDING
                        customer · environment · constraints
                                 │
                                 ▼
                    F2  SCENARIO MODEL
                        journeys · use cases · risk-ranked scenario selection
                                 │
                                 ▼
                    F3  REQUIREMENTS
                        stories · acceptance criteria · NFRs
                                 │
                    F4  INDEPENDENT REQUIREMENTS CHALLENGE
                                 │
                        ═══ G0 + G0.5 (baseline) ═══
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
       DEVELOPMENT PATH                      VERIFICATION PATH
              │                                     │
       F6 Decomposition                      F5 Test Analysis
          + state ownership                         │
              │                                     │
       F7 Contracts ── G1                     test conditions
              │                                     │
       F8 Architecture ── G3 ── H1            test cases
          + concurrency model                       │
              │                                     │
       F9 Detailed Design                     environment matrix
          + state machines                          │
              │                                     │
       F10 Impact Analysis ── G2 ──────────►  impacted-path tests
              │                                     │
       F11 Design Review ── G3.5 ◄──────────  missing-scenario feedback
              │                                     │
       F12 Implementation                           │
              │                                     │
       F13 Unit Verification ── G4                  │
              │                                     │
       F14 Integration Verification ─────────►      │
              │                                     │
       F15 Software/System Verification ── G7       │
              │                                     │
              └──────────────┬──────────────────────┘
                             ▼
                 ═══ G8 §9.3 part A: readiness ═══
                             ▼
                    F16 VALIDATION
                             ▼
                 ═══ G8 §9.3 part B: acceptance ═══
                             ▼
                     H3  RELEASE APPROVAL          ◄── existing governance, not ours
                             │
                       DEFECT / GAP?
                       ┌─────┴─────┐
                      YES          NO
                       │            │
                       ▼            ▼
             F17 DEFECT LEARNING   COMPLETE
             escape point · root cause ·
             symptom + escape correction
```

The two paths are not sequential and not independent. They share one requirements baseline, exchange two mandatory feedback messages (F5→F3 missing scenarios; F10→F5 impacted paths), and converge at G8.

## 3. F0 — Feature Qualification

Owner: Team Lead. First activity for every task without exception. Output: `F0-qualification.md`.

### 3.1 Feature type

Exactly one primary type: `new_feature`, `enhancement`, `bug_fix`, `refactoring`, `performance`, `security`, `safety_related`, `regulatory`, `configuration`.

### 3.2 Complexity

| Level | Meaning | Typical shape |
|---|---|---|
| L0 | Local, behaviour-preserving or trivially scoped | rename, comment, log string, dead-code removal |
| L1 | Single component, no contract change | field added to an internal struct, bounded bug fix |
| L2 | Multiple components inside one domain, or one contract change | new HMI setting backed by an existing service |
| L3 | Cross-domain feature: HMI + service + platform + persistence, or backend + vehicle | personalized audio profiles restored per user |
| L4 | L3 plus safety relevance, regulatory obligation, security-sensitive data, or irreversible data migration | anything with an ISO 26262 / 21448 / 21434 or regulatory hook |

### 3.3 Impact flags

Boolean, all must be answered explicitly. Any `true` raises the floor as noted.

| Flag | Effect when true |
|---|---|
| `contract_change` | G1 mandatory |
| `public_api_change` | G1 mandatory, versioning section required in F7; incompatible change routes to H2 (§15.3) |
| `data_change` | G2 mandatory |
| `persistent_data_change` | migration + rollback scenarios mandatory in F2 |
| `security_sensitive` | floor L3, security scenarios and NFRs mandatory |
| `safety_relevant` | floor L4 |
| `customer_visible` | F1/F2/F3 mandatory regardless of complexity |
| `backend_change` | F14 mandatory |
| `regulatory` | floor L4, traceability to the obligation required |
| `concurrency_change` | concurrency scenarios mandatory in F2; concurrency model mandatory in F8 (§6.6) |
| `shared_mutable_state_change` | state-ownership register mandatory in F6 (§6.5) |

### 3.4 Depth tailoring — the explicit matrix

Depth determines which phases and which gates apply. Phases and gates are separate lists, both in this table and in `config.yml`. This is the mechanism that keeps the lifecycle proportional.

| Depth | Requirements | Verification | Design | Implementation | System |
|---|---|---|---|---|---|
| **L0** | bypass | focused | bypass | F12 | F13 |
| **L1** | F0, F3 | F5 | impact only (F10) | F12 | F13, F14 |
| **L2** | F0–F5 | independent | F6–F9, F8/F9 abbreviated to one page each | F12 | F13–F15 |
| **L3** | F0–F5 | full | F6–F11 full | F12 | F13–F16 |
| **L4** | F0–F5 + §11 hazard/misuse/insufficiency | full + independent risk analysis | F6–F11 full + independent review of F8/F9 | F12 | F13–F16 |

Resulting phase and gate sets:

| Depth | Phases | Gates |
|---|---|---|
| L0 | F12, F13 | G4 |
| L1 | F0, F3, F5, F10, F12, F13, F14 | G0, **G0.5**, G2, G4, G7 |
| L2 | F0–F7, F10, F12–F15 (F8, F9 abbreviated) | G0, G0.5, G1, G2, G3, G4, G7 |
| L3 | F0–F17 | G0, G0.5, G1, G2, G3, G3.5, G4, G5\*, G6\*, G7, G8 |
| L4 | F0–F17 plus §11 risk controls | all of L3 plus the L4 controls |

`*` G5/G6 apply only when the feature has a frontend/UI surface.

Three rules remove the v1.0 ambiguities.

**Rule D1 — G0.5 is mandatory whenever F5 is performed.** F5 is the verification path's entry, and G0.5 is its exit. Performing F5 without G0.5 would leave the F5→F3 loop unenforced, which defeats §0 rule 1. This is why L1 now carries G0.5. At L1 the gate is proportionally scoped: the checklist marks the technique block "as applicable" rather than requiring all nineteen.

**Rule D2 — L2 includes F8 and F9, abbreviated.** One page each. The v1.0 phase list omitted them while the note required them. F8 at L2 states component structure, dependency direction, failure boundaries and the concurrency model. F9 at L2 states the state machines and error propagation. Neither requires the alternatives record, which stays L3+.

**Rule D3 — gates are a subset of what the phases produce.** A gate may not be required at a depth whose phase set cannot produce its evidence. `lifecycle-validate.py` enforces this against `config.yml`, and `rules.gates_must_be_subset_of_phase_requirements: true` makes it a hard check rather than a convention.

Escalation is always allowed mid-flight and is recorded as a `depth_change` entry in `state.json` with a reason. De-escalation requires Reviewer concurrence recorded in the gate ledger. An agent may never de-escalate to avoid a failing gate.

### 3.5 F0 exit criteria

Type, complexity, all impact flags, the initial risk profile (§5.2), the resulting depth, and the phase and gate sets are written down. Ambiguity about depth resolves upward.

## 4. Agent charters

Each charter states scope, mandatory outputs, and explicit prohibitions. Prohibitions are as normative as responsibilities. Full text lives in `.lifecycle/agents/`.

### 4.1 Team Lead

Owns: F0, lifecycle orchestration, gate scheduling, delegation, `state.json`, depth changes, F17 convening, and the §15 handover packages to H1/H2/H3.

May: classify, sequence, delegate, hold or release gates on the basis of ledger entries, escalate depth, declare a feature complete once H3 has approved release.

May not: author requirements, architecture, code or tests; certify any gate whose artifact its identity authored; skip a gate required by the declared depth; declare completion while any required gate lacks a PASS entry, any orphan (§8.4) exists, or H3 has not approved.

### 4.2 Researcher

Owns: F1, external standards and domain research, prior-art and existing-behaviour discovery feeding F10 reverse impact, and the existing-mechanism search record (§6.7).

May: read code and docs, query internal and external sources, record assumptions with confidence and a verification route.

May not: write requirements or design; state an unsourced fact as fact — every claim is `[verified: source]`, `[inferred]`, or `[assumption: how to verify]`.

### 4.3 Architect

Owns: F6 decomposition and the state-ownership register, F7 contracts, F8 architecture with alternatives and the concurrency model, F9 detailed design with state machines, F10 impact analysis in both directions, and chairing F11.

May: define components, interfaces, events, data models, error contracts, reliability semantics, ownership, versioning, state machines, and pattern selections with justification.

May not: change requirements or acceptance criteria — it raises a challenge back to F3 instead; introduce a design pattern without a filled §6.8 justification block; introduce a new mechanism without the §6.7 search record; leave any use case unallocated; leave any inter-component interaction without a contract; leave any mutable state without exactly one authoritative owner; certify G1/G2/G3/G3.5 itself.

### 4.4 Planner

Owns: converting the approved requirements and design into an implementation sequence with dependency order, work units mapped to `IMP-*` ids, and the unit-test obligation per work unit.

May: sequence, batch, define merge and integration order, identify parallelizable work.

May not: begin before G0/G0.5 and, at L3+, G3/G3.5 have passed; invent scope not traceable to an `AC-*` or `NFR-*`; alter contracts.

### 4.5 Implementer

Owns: F12 implementation and the unit tests that accompany it.

May: write the minimal implementation satisfying the assigned `AC-*` set, refactor within the assigned units, add observability required by the design.

May not: change a contract in `F7-contracts/` (raise to Architect); implement behaviour with no `AC-*` id; weaken, skip or delete a test to make a build pass; mark a work unit done without unit tests covering its negative and boundary criteria; self-certify G4.

### 4.6 Reviewer

Owns: requirements review support at F4, design review at F11, code review at F12, traceability and baseline audit, root-cause review at F17, and approval of RED→GREEN exceptions (§12.4).

May: reject any artifact; require additional scenarios, tests or design detail; record gate PASS/FAIL for artifacts its identity did not author; approve a regression-evidence exception with recorded alternative evidence.

May not: author the artifact it reviews; approve on the basis of intent — every approval cites the evidence inspected; pass a gate with an open orphan or an unresolved ambiguity; approve a RED→GREEN exception without alternative evidence.

### 4.7 Verifier

Owns: F4 independent requirements challenge, F5 test analysis, F14 integration verification, F15 system verification, F16 validation, evidence packaging, and G0.5/G4/G6/G7/G8 certification.

Participates from F3. This is the single most important change relative to a conventional flow.

May: derive test conditions the requirements do not mention; declare a requirement unverifiable; feed missing scenarios back to F3 as blocking findings; refuse G8 on insufficient evidence.

May not: mechanically transcribe acceptance criteria into test cases and stop there; author implementation code; certify a gate under the same identity that authored the requirements or design under test; relax a test to accommodate observed behaviour.

## 5. Phases F1–F5 (front end)

### 5.1 F1 — Feature understanding

Answer, explicitly, in `F1-context.md`.

Customer: who is it? Driver, front passenger, rear passenger, owner vs. non-owner user, guest, fleet operator, dealer, service technician, administrator, backend operator, or another software system. Multiple customers get separate `CUS-*` ids.

Environment: enumerate every state dimension the feature can be exposed to, from the `environment_baseline` in `config.yml`. No dimension may be left "unknown" at exit.

Operating conditions: classify each as `normal`, `degraded`, `unavailable`, `failure`, `recovery`, `interrupted`, `concurrent`, `repeated`, `boundary`, `misuse`, `unexpected_sequence`.

Constraints, dependencies, assumptions: each with owner and verification route.

### 5.2 F2 — Scenario model, risk-ranked

Journeys first (`JRN-*`): how each customer discovers, learns, invokes, recovers from and abandons the feature, per environment. Then use cases (`UC-*`). Then scenarios (`SCN-*`), generated from the dimension matrix rather than from imagination.

Matrix dimensions, all swept at L3+:

| Dimension | Values to sweep |
|---|---|
| Customer | every `CUS-*` |
| Surface / environment | vehicle HMI, companion app, backend, voice, physical control, service tool |
| Primary state | e.g. parked / driving / ignition off / accessory |
| Connectivity | online / offline / intermittent / high-latency |
| User state | signed in / guest / multi-user / switched mid-operation |
| Device | supported / unsupported / degraded |
| Configuration | variant A / variant B / unsupported variant |
| Trigger | user-initiated / automatic / scheduled / external event |
| Class | normal / alternate / negative / failure / recovery / boundary / concurrent / persistence / upgrade / downgrade / rollback / security / performance / safety / misuse |

#### 5.2.1 Selection rule — not a Cartesian product

The matrix is never exhaustively expanded. Combinations are **selected**, and the selection technique is recorded per scenario.

Permitted selection techniques, and the only permitted justifications for not testing a combination:

| Technique | Use |
|---|---|
| Equivalence partitioning | collapse values that the system treats identically; state the partition |
| Boundary value analysis | pick the edges of each partition |
| Pairwise / combinatorial | cover all pairs of dimension values where interaction is plausible |
| State-transition coverage | cover transitions, including error transitions, not just states |
| Risk-based selection | depth follows the risk score in §5.2.2 |
| Domain-mandatory combinations | project-declared combinations that must always appear, listed in `config.yml` |

"These are equivalent" is a claim, not a technique. It requires the partition to be named and the reason the system cannot distinguish the values. Unreachable combinations are listed once with the reason they are unreachable.

#### 5.2.2 Risk dimension

Every `SCN-*` carries a risk score. This is what turns the lifecycle from checklist-driven into risk-driven, and it is what prevents a trivial scenario from discharging an important dimension.

```yaml
SCN-17:
  title: "profile restore while offline, user switched mid-restore"
  class: persistence
  technique: risk_based
  priority:
    likelihood: 3        # 1-5, how often the combination occurs in the field
    impact: 4            # 1-5, consequence to the customer if it misbehaves
    detectability: 2     # 1-5, how likely we catch it WITHOUT a targeted test
                         # low detectability = high risk; it hides
    priority: 48         # derived = 3 x 4 x (6 - 2); see the band table
    band: high           # derived; see the band table
```

Priority is derived, not asserted. `config.yml` holds the bands; the default is `likelihood × impact × (6 − detectability)`:

| Score | Priority | Test depth earned |
|---|---|---|
| 1–20 | low | one nominal case may discharge the dimension |
| 21–45 | medium | positive plus at least one negative case |
| 46–80 | high | positive, negative, boundary, and a failure-injection case; must appear at F15 |
| 81–125 | critical | as high, plus an F16 validation case and explicit `NFR-*` measurement |

Rules:

* Every dimension appears in at least one scenario, and every applicable `class` value has at least one scenario. That floor from v1.0 is retained.
* A dimension whose only scenario is `low` priority must be justified. A `high` or `critical` risk hiding behind one nominal case is a G0 finding.
* Risk scores are reviewed at F4 by Verifier and Reviewer. The author does not get the last word on the risk of their own feature.
* Scenarios at `critical` cannot be deferred. Deferral is available to `low` and `medium` only, with a recorded reason.

Exit: every `UC-*` traces to at least one `JRN-*`; every applicable class has at least one `SCN-*`; every `SCN-*` has a risk score and a recorded selection technique; the question "what happens when the customer does something unexpected, the environment changes, or a dependency fails" is answered for every use case.

### 5.3 F3 — Requirements

Four mandatory categories. A feature with only functional requirements fails G0.

Functional:

```
US-014  As a driver
        I want to select my preferred audio profile
        so that my preferred audio settings are restored automatically.

AC-014-1  Given a stored profile exists for the signed-in driver
          When the driver selects that profile
          Then all settings contained in the profile are applied
          And the applied profile is reported as active.
```

Negative:

```
AC-014-4  Given no profile is available for the signed-in driver
          When profile restoration is requested
          Then the system shall retain the current audio configuration
          And shall report that no profile is available.
```

Boundary:

```
AC-014-7  Given a profile containing the maximum supported number of settings
          When the profile is saved
          Then every supported setting shall be persisted
          And no setting shall be silently dropped.
```

Non-functional (`NFR-*`): latency, throughput, availability, memory, CPU, power, startup impact, reliability, security, privacy, accessibility, localization, logging, observability, diagnosability. Each NFR states a measurable threshold and a measurement method. "Fast" is a G0 failure; "profile applied within 300 ms of selection, measured at the HMI event boundary" is not.

Rules: every `AC-*` is independently verifiable; no `AC-*` describes implementation; every `SCN-*` maps to at least one `AC-*` or is explicitly deferred with a reason and a priority no higher than `medium`; every `AC-*` maps back to a `UC-*`.

Requirements are baselined at G0. After that, changes go through §8.6 baseline versioning.

### 5.4 F4 — Independent requirements challenge

Verifier and Reviewer, adversarially, before architecture. The purpose is to break the requirements while they are cheap to fix. Every question below is answered or recorded as a finding.

What is ambiguous? What is unspecified? What assumptions are load-bearing? What happens if a dependency fails, or is unavailable, or responds late? After reboot? During upgrade? After downgrade? After rollback? Offline? Under concurrency, including two customers acting at once? With invalid input? At the minimum and maximum? On timeout? After retry? When the operation partially succeeds? When the user changes state midway? On unsupported configurations? On older software versions? When the same operation repeats? When permissions are revoked mid-operation?

F4 also reviews the §5.2.2 risk scores. Any score the challengers disagree with is a finding.

Each finding is `blocking` or `non-blocking`, with an owner. Blocking findings must be resolved by amending F2/F3 before G0 can pass.

### 5.5 F5 — Test analysis (verification path, starts here)

Verifier derives test conditions from the requirements, the scenario model and independent analysis — explicitly not by one-to-one transcription of acceptance criteria.

Techniques to apply and record: equivalence partitioning, boundary value analysis, state-transition coverage, decision tables, error guessing, interruption and resumption, timeout and retry, concurrency, persistence across restart, reboot, upgrade, downgrade, configuration and platform variants, connectivity variants, performance, security, usability, accessibility, observability. At L0/L1 the applicable subset is recorded with reasons for the rest; at L2+ all are applied or marked not applicable with a reason.

Test depth per condition follows the risk priority of the scenario it derives from (§5.2.2).

Output: `TC-*` test conditions, then `UT/IT/ST/VT-*` test cases, plus an environment matrix stating where each case runs.

Mandatory feedback: any condition with no corresponding requirement is raised as a missing-scenario finding to F3. F3 is amended, F5 re-derived, and only then may G0.5 pass. This loop is not optional and not advisory.

## 6. Development path F6–F11

### 6.1 F6 — Decomposition

Chain, per use case: `UC → capability → software responsibility → component → interface → contract → implementation unit`.

```
UC-014  Driver selects audio profile
  ├── CMP-01  HMI — Audio Settings screen
  ├── CMP-02  ProfileManager (business logic)
  ├── CMP-03  AudioConfigurationService (platform)
  ├── CMP-04  AudioHAL
  ├── CMP-05  ProfileRepository (persistence)
  ├── CMP-06  Backend profile sync
  └── CMP-07  VehicleConfiguration (read-only input)
```

### 6.2 Component cohesion rule

Every component states one cohesive responsibility boundary, in one sentence. Multiple operations are allowed when they belong to that boundary.

```
CMP-02  ProfileManager
Responsibility boundary: the lifecycle and activation of audio profiles.
Operations: create, validate, activate, deactivate, list.
Cohesion: all operations act on the same state (the profile set and the active profile)
          and share the same invariants.
```

The test is cohesion, not operation count. Split when the component's operations act on unrelated state, change for unrelated reasons, or serve different customers of the interface. Retain when they share state and invariants. A three-operation component with one state boundary is correct; a two-operation component spanning profile activation and network transport is not.

Low cohesion → split. High cohesion → retain. Record the judgment when it is not obvious; G3 checks the reasoning, not an operation count.

### 6.3 Interaction modelling

For each interaction, name the mechanism. "Boxes and arrows" without a mechanism is a G3 failure.

Allowed mechanisms: synchronous request/response, asynchronous command, query, event/notification (publish–subscribe), state exposure, callback, subscription, persistence operation, external API call.

```
Request/response:
  HMI → ProfileManager.getProfile(userId)
      → ProfileRepository.read(userId)
      → Database
      ← Profile | PROFILE_NOT_FOUND | STORAGE_UNAVAILABLE

Event:
  ProfileManager  ──publishes EVT-ProfileChanged──▶  Event bus
                                                     ├──▶ AudioConfigurationService
                                                     └──▶ Analytics
```

Sequence, ordering constraints, and what happens when a step fails mid-sequence are stated for every use case.

### 6.4 F7 — Contract-first design

No inter-component interaction may be implemented before its contract file exists. One file per interface and per event. Schemas: `.lifecycle/schema/contract.schema.json` and `event.schema.json`.

#### 6.4.1 Reliability semantics are declared, not universal

Every contract states, for each reliability semantic, whether it applies — and if not, why. This replaces the v1.0 rule that every contract must carry a timeout and a retry policy, which was correct for distributed calls and meaningless for in-process ones.

The rule: **every contract must explicitly state whether each reliability semantic applies.** Not: every contract must implement every semantic. A missing `applicable` field fails G1. An `applicable: false` without a `reason` fails G1.

```yaml
# F7-contracts/IFC-03-profile-service.yml
id: IFC-03
interface: ProfileService
owner: CMP-02                    # exactly one owner
consumers: [CMP-01, CMP-03]
version: 1.0.0
boundary: ipc                    # in_process | ipc | network — drives which semantics apply
operations:
  - name: getProfile
    kind: query
    input:  { userId: string }
    output: { profile: Profile }
    errors: [PROFILE_NOT_FOUND, STORAGE_UNAVAILABLE, INVALID_USER]
    reliability:
      timeout:     { applicable: true,  value_ms: 500 }
      retry:       { applicable: true,  attempts: 2, backoff: exponential }
      idempotency: { applicable: true,  note: "read-only; safe to repeat" }
      cancellation:{ applicable: true,  note: "caller may cancel on screen exit" }
    preconditions:  ["user session established"]
    postconditions: ["no state mutated"]
traces: [UC-014, AC-014-1, AC-014-4]
```

```yaml
# F7-contracts/IFC-08-profile-validator.yml
id: IFC-08
interface: ProfileValidator
owner: CMP-02
consumers: [CMP-02]
version: 1.0.0
boundary: in_process
operations:
  - name: validate
    kind: query
    input:  { profile: Profile }
    output: { result: ValidationResult }
    errors: [INVALID_SCHEMA, UNSUPPORTED_SETTING]
    reliability:
      timeout:     { applicable: false, reason: "in-process synchronous call; no transport" }
      retry:       { applicable: false, reason: "deterministic; caller does not retry validation" }
      idempotency: { applicable: true,  note: "pure function of its input" }
      cancellation:{ applicable: false, reason: "bounded, sub-millisecond" }
traces: [UC-014, AC-014-7]
```

`boundary` sets the expectation. `in_process` may reasonably mark timeout and retry not applicable. `ipc` and `network` may not: a contract crossing a process or network boundary with `timeout.applicable: false` fails G1 unless the reason survives review.

#### 6.4.2 Event semantics

`at_least_once` delivery without consumer idempotency is an incomplete contract. Events therefore declare the full set.

```yaml
# F7-contracts/EVT-07-profile-changed.yml
id: EVT-07
event: ProfileChanged
publisher: CMP-02                # exactly one publisher
subscribers: [CMP-03, CMP-08]
delivery: at_least_once          # at_most_once | at_least_once | exactly_once
ordering: per_user               # none | per_key | per_user | global
duplication:
  possible: true                 # implied by at_least_once
  detection: "profileId + schemaVersion + timestamp"
consumer_idempotency:
  required: true                 # must be true whenever duplication.possible is true
  mechanism: "apply is idempotent; last-write-wins on profileId"
replay:
  supported: false
  reason: "consumers hold no derived state that needs rebuilding"
retention:
  duration: "none — transient bus, no store"
dead_letter:
  applicable: true
  destination: "audio-settings-dlq"
  on_exhaustion: "log, raise diagnostic, retain last-known-good configuration"
payload:
  profileId: string
  userId: string
  timestamp: iso8601
  schemaVersion: integer
compatibility: backward
traces: [UC-014, AC-014-1]
```

G1 checks the coupling rules: `duplication.possible: true` requires `consumer_idempotency.required: true` with a named mechanism; `delivery: exactly_once` requires the mechanism that achieves it; `ordering` other than `none` requires the key; `dead_letter.applicable: true` requires a destination and an exhaustion behaviour.

### 6.5 State and data ownership register

Mandatory F6 artifact whenever the feature reads or writes state shared across components. Mandatory at L2+ unconditionally.

Every mutable piece of state gets exactly one authoritative owner. This is the single highest-value structural check in a settings domain, where per-vehicle, per-seat and per-user values coexist with focus, ducking, mute, zones, concurrent streams and backend synchronization.

```yaml
state:
  - name: activeAudioProfile
    owner: CMP-02                # exactly one authoritative owner
    writers: [CMP-02]            # only the owner, or the exception is justified
    readers: [CMP-01, CMP-03]
    persistence: CMP-05          # ProfileRepository
    scope: user                  # vehicle | seat | user  (control scope, from config.yml)
    synchronization: EVT-07      # how readers learn it changed
    consistency: eventual        # strong | eventual, and the window if eventual
    conflict_resolution: "backend timestamp wins; device change re-published on reconnect"
    invariants:
      - "exactly one profile is active per signed-in user"
      - "no active profile implies the vehicle default configuration"
```

Enforced rules:

* **Every mutable piece of state has exactly one authoritative owner.** Two owners is a G3 failure.
* Any writer other than the owner requires a recorded justification and a serialization mechanism.
* Every reader learns of change through a declared mechanism. Polling is a declared mechanism; implicit assumption is not.
* State whose `scope` differs from the control scope of the `AC-*` that governs it is a G0/G3 inconsistency.

### 6.6 Concurrency as a first-class architecture concern

F8 states the concurrency model. For every concurrently mutable piece of state, F8 records all nine of the following, or marks the item not applicable with a reason. G3 checks it.

| Item | What is recorded |
|---|---|
| Ownership | the authoritative owner from §6.5 |
| Consistency model | strong or eventual, and the convergence window |
| Serialization mechanism | lock, actor, single-threaded executor, queue, transaction |
| Conflict resolution | the deterministic winner, and how it is decided |
| Ordering | guarantees offered to readers and subscribers |
| Atomicity | what is atomic, and what a partial application looks like |
| Race prevention | the specific interleavings prevented, and how |
| Reentrancy | which entry points are reentrant |
| Thread safety | per component, stated rather than assumed |

```
Cloud profile
       │
       ├── device modification  (t1, offline)
       │
       └── backend modification (t2, another device)
               ↓
        conflict resolution: higher backend timestamp wins
               ↓
        deterministic winner, device change re-published on reconnect
               ↓
        readers notified via EVT-07, ordering per_user
```

A concurrency model that names no serialization mechanism, or leaves the conflict winner non-deterministic, fails G3.

### 6.7 Existing-mechanism reuse — a hard check

Before introducing any new service, event bus, repository, abstraction, utility, state manager, serialization format, retry mechanism, logging mechanism, configuration store or test harness, the Architect searches the repository for an existing mechanism and records the search.

```yaml
existing_mechanism:
  seeking: "retry with backoff for backend settings sync"
  searched: true
  search_scope: ["src/net/**", "src/common/**", "platform/**"]
  candidates:
    - { name: "net::RetryPolicy", fit: "full", notes: "backoff configurable, used by 4 callers" }
    - { name: "sync::Retrier", fit: "partial", notes: "no jitter, backend-specific" }
  selected: "net::RetryPolicy"
  reason: "full fit; adding a second retry mechanism would fragment observability"
```

`searched: false` fails G3. A new mechanism selected while a `full` fit candidate exists fails G3 unless the reason explains why the existing one is unusable. This is the mechanized form of "avoid snowflakes", and it is automatable against a code-graph or repository search index.

### 6.8 F8 — Architecture, and F9 — Detailed design

F8 (architectural): component structure and responsibility boundaries, dependencies and their direction, data flow, control flow, the §6.6 concurrency model, persistence model, external dependencies, failure boundaries and degradation behaviour, the §6.7 reuse records, and the architecture alternatives record.

F9 (detailed): classes and responsibilities where they answer a design question, method signatures at interface boundaries, state machines per §6.9, algorithms, data structures, error handling and propagation, threading and reentrancy, object lifecycle and ownership.

Required design principles, evaluated explicitly at G3: single responsibility as a cohesion boundary (§6.2), high cohesion, low coupling, explicit dependencies, dependency inversion where it buys testability, interface segregation, separation of concerns, information hiding, single clear ownership per piece of state (§6.5), determinism where required, testability, observability.

Patterns are permitted but never free. Allowed set: Strategy, State, Observer/Pub-Sub, Factory, Adapter, Facade, Command, Repository, Dependency Injection. Each use requires a justification block; without one the pattern is removed.

```
Pattern: Strategy
Applied to: audio routing algorithm selection (DES-11)
Why: three interchangeable routing algorithms exist and are selected at runtime by variant.
Alternative considered: conditional logic in AudioConfigurationService.
Decision: Strategy — algorithms become independently replaceable and independently testable.
Complexity cost: low (one interface, three implementations, one selector).
```

Architecture alternatives are mandatory at L3+ for any meaningful structural decision:

| Criterion | Option A | Option B | Option C |
|---|---|---|---|
| Complexity | | | |
| Performance | | | |
| Maintainability | | | |
| Testability | | | |
| Scalability | | | |
| Reliability | | | |
| Security / privacy | | | |
| Reuse of existing mechanisms | | | |
| Migration / rollout risk | | | |
| Selected | | | |

At L3+, the selected architecture is handed to **H1** for approval (§15.2). G3 is the evidence check; H1 is the decision.

### 6.9 Temporal behaviour — state machines where they matter

State-machine modelling is mandatory in F9 whenever behaviour depends on any of: object or feature lifecycle, asynchronous operations, transient state, retries, audio focus, connection state, user switching, or power transitions. In a settings and audio domain that is most non-trivial features.

Each state machine records states, events, transitions including error transitions, guards, entry and exit actions, and the states from which the machine cannot recover without external input.

```
Profile application state machine (DES-11)

  IDLE ──select──▶ LOADING ──loaded──▶ APPLYING ──applied──▶ ACTIVE
   ▲                  │                    │                    │
   │            load_failed          apply_failed         user_switch
   │                  ▼                    ▼                    ▼
   └──────────── NO_PROFILE ◄──── PARTIAL_APPLIED ──rollback──▶ IDLE
                                        │
                                  power_off (transient state lost;
                                  on next boot re-enter LOADING)
```

Sequences of interest are modelled explicitly, not left to prose: `A → B → C → A` cycles, and interleavings such as profile loading, then a user profile change, then a late backend response, then a vehicle state change, then ignition off.

### 6.10 Design models — minimum necessary

**No diagram without a design question it answers.** Record the question next to the model.

Available models: component diagram, sequence diagram, class diagram, state machine, data model, deployment diagram, activity diagram. Only the applicable ones are required. Class diagrams are not mandatory. A class diagram that restates the file layout answers no question and is removed at G3.

```
Model: sequence diagram (DES-11)
Question answered: "in what order do HMI, ProfileManager and the arbitrator act,
                    and what happens if the arbitrator does not respond in time?"
```

### 6.11 F10 — Impact analysis

Hard gate before implementation. Two directions, both mandatory.

Forward impact — what does this change touch? Requirements, architecture, components, classes, interfaces, public APIs, events, database and schema, configuration, HMI, apps, backend, vehicle services, platform, HAL, build, deployment and rollout, security posture, logging, telemetry, diagnostics, documentation.

Reverse impact — what existing behaviour depends on what I am changing? For every symbol, contract, event, table, column, config key and file being modified, enumerate existing consumers, existing features relying on current behaviour, existing tests including regression suites, and existing documented behaviour. This is where regression defects hide; a forward-only impact analysis fails G2.

Mandatory output to the verification path: the impacted-path list, which the Verifier converts into the regression test selection at F5.

### 6.12 F11 — Design review

Reviewer chairs, Architect presents, Verifier attends. Checked: requirements ↔ design completeness, use cases ↔ design allocation, contracts ↔ design consistency, failure scenarios ↔ design handling, NFRs ↔ design provisions, design principles conformance, cohesion judgments, pattern justifications, reuse records, state-ownership register, concurrency model, state machines, alternatives record, impact analysis in both directions, and full traceability.

At L4, F8 and F9 additionally receive independent review by a reviewer identity not involved in the feature (§11).

## 7. State machine

`state.json` per feature. Schema: `.lifecycle/schema/state.schema.json`. Transitions record timestamp, acting agent identity, acting charter, and the gate entry that authorized them.

```
QUALIFIED
  → UNDERSTANDING            (F1)
  → SCENARIOS_MODELLED       (F2)
  → REQUIREMENTS_DRAFTED     (F3)
  → REQUIREMENTS_CHALLENGED  (F4 + F5 first pass)
  → REQUIREMENTS_BASELINED   [G0 PASS + G0.5 PASS]      ◄── fork point
      ├── DEV:  DECOMPOSED (F6) → CONTRACTED [G1] (F7) → ARCHITECTED [G3, H1 at L3+] (F8)
      │         → DESIGNED (F9) → IMPACT_ASSESSED [G2] (F10)
      │         → DESIGN_REVIEWED [G3.5] (F11) → IMPLEMENTING (F12)
      │         → UNIT_VERIFIED [G4] (F13) → INTEGRATION_VERIFIED (F14)
      │         → SYSTEM_VERIFIED [G7] (F15)
      └── VER:  TEST_ANALYSED (F5) → TEST_DESIGNED → REGRESSION_SELECTED (from F10)
                → EXECUTION_READY
  → VALIDATION_READY         [G8 part A PASS]   ◄── join
  → VALIDATED                (F16)
  → VALIDATION_ACCEPTED      [G8 part B PASS]
  → RELEASE_PENDING          → handover package to H3 (§15.4)
  → COMPLETE                 [H3 approved]
```

Any state may transition to `DEFECT_LOOP` (F17). Exit from `DEFECT_LOOP` re-enters at the escape phase for escape correction, and at F12 for symptom correction (§12.2). Both re-traverse the affected downstream gates.

Reverse transitions are legal and expected. A missing-scenario finding at F5 moves the feature back to `REQUIREMENTS_DRAFTED`. A contract change during F12 moves it back to `CONTRACTED` and re-runs G1 and G2 for the affected paths.

`COMPLETE` is reachable only after H3 approval. The lifecycle does not self-authorize release.

## 8. Traceability

### 8.1 Graph

```
CUSTOMER (CUS)
   ▼
CUSTOMER JOURNEY (JRN)
   ▼
USE CASE (UC) ◄──── SCENARIO (SCN) ──── RISK (RSK)
   ▼
USER STORY (US)
   ▼
ACCEPTANCE CRITERION (AC) ──────────────┐
   ▼                                     ▼
DESIGN (DES)                      TEST CONDITION (TC)
   ▼                                     ▼
COMPONENT (CMP)                   TEST CASE (UT/IT/ST/VT)
   ▼                                     ▼
INTERFACE / EVENT (IFC/EVT)       TEST RESULT (immutable ref, §9.1)
   ▼                                     ▼
CLASS / UNIT (IMP)                VALIDATION (VT)
   ▼
CODE
   ▼
UNIT TEST (UT) → INTEGRATION TEST (IT) → SYSTEM TEST (ST)
```

Also traced: `NFR → DES`, `NFR → TC`, `IFC/EVT → IT`, `STATE → CMP` (owner), `SCN → RSK`, `DEF → ESC → phase`, every impacted-path entry from F10 → the regression cases selected at F5, and every element → the baseline it belongs to (§8.6).

### 8.2 Bidirectional requirement

Every edge is navigable in both directions, so the framework can answer:

- If I change `AC-014-4`, which design elements, contracts, code units and tests are affected?
- `ST-207` failed — which acceptance criterion, use case, journey and customer does that violate?
- `IFC-03` is changing — which consumers, features and regression suites depend on the current behaviour?
- `activeAudioProfile` is being written by a new component — who owns it, and does that violate §6.5?
- G7 passed on 12 March — against which requirements baseline, and has any `AC-*` changed since?

### 8.3 trace.yml

Schema: `.lifecycle/schema/trace.schema.json`.

```yaml
feature: FEAT-2026-014
schema_version: 1.1

baselines:                                  # §8.6
  - id: REQ-BL-003
    scope: requirements
    created: 2026-08-20T09:14:00-04:00
    approved_by: { agent_id: rev-7f2a, role: reviewer, session_id: s-2026-08-20-a }
    git_commit: 9f1c2ab
    gate: G0
    status: superseded
  - id: REQ-BL-004
    scope: requirements
    created: 2026-09-02T11:40:00-04:00
    approved_by: { agent_id: rev-7f2a, role: reviewer, session_id: s-2026-09-02-c }
    git_commit: 4d77e10
    gate: G0
    status: current

changes:                                    # every post-baseline requirement change
  - baseline_from: REQ-BL-003
    baseline_to: REQ-BL-004
    changed: AC-014-4
    from_text: "shall retain the current audio configuration"
    to_text: "shall restore the previously active configuration"
    reason: DEF-031
    impact: [DES-11, IMP-19, UT-89, IT-35, ST-214]
    gates_reopened: [G2, G3.5, G7]

customers:
  CUS-1: { name: driver }
  CUS-2: { name: front passenger }
journeys:
  JRN-1: { customer: CUS-1, title: "discover and apply an audio profile" }
use_cases:
  UC-014: { journeys: [JRN-1], scenarios: [SCN-3, SCN-9, SCN-17, SCN-24] }
scenarios:
  SCN-17:
    use_case: UC-014
    class: concurrent
    technique: risk_based
    priority: { likelihood: 3, impact: 4, detectability: 2, priority: 48, band: high }
    criteria: [AC-014-4, AC-014-9]
    conditions: [TC-42, TC-58]
stories:
  US-014: { use_case: UC-014, criteria: [AC-014-1, AC-014-4, AC-014-7], baseline: REQ-BL-004 }
nfrs:
  NFR-6:
    statement: "profile applied within 300 ms, measured at the HMI event boundary"
    design: [DES-11]
    conditions: [TC-42]
    baseline: REQ-BL-004
state_ownership:                            # §6.5
  activeAudioProfile:
    owner: CMP-02
    writers: [CMP-02]
    readers: [CMP-01, CMP-03]
    persistence: CMP-05
    scope: user
    synchronization: EVT-07
design:
  DES-11: { component: CMP-03, satisfies: [AC-014-1], contracts: [IFC-03], units: [IMP-19] }
contracts:
  IFC-03: { owner: CMP-02, consumers: [CMP-01, CMP-03], boundary: ipc, tests: [IT-31, IT-32] }
  EVT-07: { publisher: CMP-02, subscribers: [CMP-03, CMP-08], tests: [IT-33] }
units:
  IMP-19: { path: "src/audio/profile_applier.cpp", tests: [UT-88, UT-89, UT-90] }
tests:
  UT-88: { covers: [AC-014-1], type: positive }
  UT-89: { covers: [AC-014-4], type: negative }
  UT-90: { covers: [AC-014-7], type: boundary }
  IT-31: { covers: [IFC-03], type: contract }
  ST-207: { covers: [AC-014-1, NFR-6], type: end_to_end }
  VT-9:  { covers: [JRN-1], type: customer_journey }
impacted_paths:
  - { changed: IFC-03, dependents: [CMP-09], regression: [ST-101, ST-102] }
```

### 8.4 Orphan rules

Checked mechanically at G3.5, G7 and G8 by `.lifecycle/scripts/orphan-check.py`. Any orphan blocks the gate.

| Orphan | Definition |
|---|---|
| Orphan requirement | `AC-*` or `NFR-*` with no design element and no test case |
| Orphan scenario | `SCN-*` with no `AC-*` and no recorded deferral |
| Orphan test | test case covering no `AC-*`, `NFR-*` or contract |
| Orphan component | `CMP-*` allocated to no `UC-*` |
| Orphan contract | `IFC-*`/`EVT-*` with no consumer or no owner |
| Orphan code | changed file with no `IMP-*` and no `AC-*` |
| Orphan impact | F10 impacted path with no selected regression test |
| Orphan state | mutable state with no owner, or with more than one owner (§6.5) |
| Orphan risk | `SCN-*` with no risk score, or a `high`/`critical` scenario with no F15 case |
| Stale baseline | an `AC-*` or `NFR-*` whose baseline is `superseded` and whose gates were not reopened |

### 8.5 Coverage, stated correctly

The requirement is 100% bidirectional requirements-to-verification traceability. Do not claim or demand "100% test coverage" — it is a misleading metric that invites gaming.

Coverage metrics are chosen per feature and per depth from: requirement coverage, acceptance-criteria coverage, scenario coverage, branch coverage, decision coverage, state-transition coverage, interface/contract coverage, error-path coverage, risk coverage, regression coverage. The selected set and its thresholds are recorded in `F5-test-analysis.md` and evidenced at G7.

At L3+, `risk_coverage` is mandatory in the selected set, measured as the fraction of `high` and `critical` scenarios with a case at the depth §5.2.2 requires.

### 8.6 Baseline versioning

Gate evidence is meaningless without knowing what it was evidence *against*. A G7 PASS citing `AC-014-4` is ambiguous if that criterion has since changed meaning.

Rules:

1. A baseline is created at G0 for requirements, at G1 for contracts, and at G3.5 for design. Each has an id, a creation timestamp, an approving identity, and the git commit that contains it.
2. Every `AC-*`, `NFR-*`, `IFC-*`, `EVT-*` and `DES-*` records the baseline it belongs to.
3. Changing a baselined element creates a new baseline, marks the old one `superseded`, and writes a `changes` entry recording the element, the before and after text, the reason, the impact set, and which gates are reopened.
4. Every gate ledger entry names the baseline it certified against.
5. A gate PASS certified against a `superseded` baseline is not valid evidence for the current state. It must be re-certified, or the `changes` entry must show the change does not touch that gate's scope.
6. `stale baseline` is an orphan class (§8.4). This is what makes rule 5 mechanical.

## 9. Gates

Gates are evidence checks, not opinions. Each produces a ledger entry conforming to `.lifecycle/schema/gate.schema.json`.

### 9.1 Ledger entry format

Two v1.1 changes: authorship is identity-based, and evidence references are immutable.

```markdown
# G3.5 — Design Traceability
Feature: FEAT-2026-014
Depth: L3
Verdict: PASS | FAIL | CONDITIONAL
Baseline certified against: DES-BL-002 (requirements REQ-BL-004, contracts IFC-BL-001)

## Authorship and independence
author:
  agent_id: arch-4c19
  role: architect
  session_id: s-2026-08-27-b
  timestamp: 2026-08-27T16:20:00-04:00
certifier:
  agent_id: rev-7f2a           # MUST differ from author.agent_id
  role: reviewer
  session_id: s-2026-08-29-a   # MUST differ from author.session_id
  timestamp: 2026-08-29T14:02:00-04:00
independence_rule: identity     # identity | role_and_identity (L4)
independence_check: PASS

## Artifacts inspected
F8-architecture.md, F9-detailed-design.md, trace.yml

## Checklist
.lifecycle/checklists/G3.5.md  (all items marked)

## Evidence
- id: EV-1
  claim: "every UC-* allocated to >=1 CMP-* (14/14)"
  command: "python3 .lifecycle/scripts/orphan-check.py features/FEAT-2026-014/trace.yml"
  commit: 4d77e10
  environment: "host, python 3.11.6"
  timestamp: 2026-08-29T14:01:12-04:00
  result_file: "features/FEAT-2026-014/evidence/F11-review/orphan-check-4d77e10.txt"
  checksum: "sha256:3b1f...c9a2"
- id: EV-2
  claim: "orphan check: 0 orphans across all 10 classes"
  command: "python3 .lifecycle/scripts/orphan-check.py --strict features/FEAT-2026-014/trace.yml"
  commit: 4d77e10
  environment: "host, python 3.11.6"
  timestamp: 2026-08-29T14:01:12-04:00
  result_file: "features/FEAT-2026-014/evidence/F11-review/orphan-strict-4d77e10.txt"
  checksum: "sha256:8e04...11bd"

Conditions (if CONDITIONAL): <specific, with owner and re-check date>
```

#### 9.1.1 Identity-based independence

Role separation is not independence in an agentic system. Two Architect instances are the same charter with the same blind spots. A fresh Verifier context inherits the prior context's framing through the artifacts it reads.

The rule, at all depths:

> **The certifying agent identity must differ from the artifact-author identity.** `certifier.agent_id ≠ author.agent_id` and `certifier.session_id ≠ author.session_id`.

The additional rule at L4, and at any depth where `rules.independence: role_and_identity`:

> **The certifying role and agent identity must both be independent of the artifact author.** The certifier's role differs, its identity differs, and it did not contribute to the artifact under certification in any prior session.

`agent_id` is stable per configured agent instance. `session_id` is unique per execution context. Both are recorded in every artifact header and every ledger entry. Missing either field fails the gate mechanically, before any checklist item is read.

Single-agent runtimes: open a new session before certifying. If the runtime cannot produce a distinct `session_id`, a human certifies and the ledger records the human identity.

#### 9.1.2 Immutable evidence references

"Unit tests: 37/37 passed" is an assertion. Evidence identifies the exact execution that produced it, so a reader can re-run it and a defect can be traced to the build that missed it.

Every evidence item records: `claim`, `command`, `commit`, `environment`, `timestamp`, `result_file`, `checksum`. A claim without a `result_file` and `checksum` is not evidence, and the gate fails on it. Result files live under `features/<ID>/evidence/` and are committed, not regenerated on demand.

### 9.2 Gate set

| Gate | Name | Certifier | Layer | Passes when |
|---|---|---|---|---|
| G0 | Requirements readiness | Reviewer | lifecycle (new) | all use cases identified; journeys reviewed; stories complete; every `AC-*` independently verifiable; negative, boundary, failure and recovery scenarios covered; every `SCN-*` risk-scored and every `high`/`critical` scenario adequately deep; NFRs with measurable thresholds and methods; zero unresolved ambiguities from F4; requirements baseline created |
| G0.5 | Independent test challenge | Verifier | lifecycle (new) | Verifier independently reviewed requirements; `TC-*` exist that the `AC-*` do not mention; missing scenarios raised and resolved; test basis established; requirements ↔ test conditions traceability bidirectional. **Mandatory whenever F5 is performed** (Rule D1) |
| G1 | Contract validation | Reviewer | existing | every inter-component interaction has a contract with owner, consumers, version, boundary, errors, an explicit `applicable` decision for each reliability semantic, complete event semantics per §6.4.2, and traces; no consumer depends on an undeclared behaviour; contract baseline created |
| G2 | Impact validation | Reviewer | existing | forward and reverse impact complete; every impacted path has a selected regression test; schema/config/migration impacts addressed |
| G3 | Architecture validation | Reviewer | existing | interaction mechanisms named; dependencies acyclic and explicit; cohesion boundaries justified; every mutable state has exactly one owner; concurrency model complete per §6.6; failure boundaries defined; design principles evaluated; every pattern justified; reuse search recorded; only question-answering models present; alternatives recorded at L3+ |
| G3.5 | Design traceability | Reviewer | lifecycle (new) | `UC → CMP → IFC → DES → IMP` complete in both directions; zero orphans across all classes in §8.4; design baseline created |
| G4 | Executable validation | Verifier | existing | build, unit tests, static analysis and selected coverage thresholds pass, with immutable evidence references; no test weakened or skipped to pass |
| G5 | Frontend conformance | Reviewer | existing | UI conforms to the project's design-system and accessibility rules (UI features only) |
| G6 | Browser/HMI verification | Verifier | existing | rendered surface verified against acceptance criteria on the target surface (UI features only) |
| G7 | **Lifecycle** requirements verification | Verifier | lifecycle (new) | every `AC-*` tested; every applicable `SCN-*` tested at its risk-earned depth; every F10 impacted path tested; selected coverage thresholds met including `risk_coverage` at L3+; zero orphan requirements and zero orphan tests; every evidence item immutable; certified against the current baseline |
| G8 | **Lifecycle** validation readiness and acceptance | Verifier | lifecycle (new) | two parts, §9.3 |

Naming: G7 is the **Lifecycle Requirements Verification Gate**, and G8 the **Lifecycle Validation Readiness and Acceptance Gate**. Neither is Automotive SPICE SWE.6 or VAL.1 itself. §14 maps them; the mapping is not a compliance claim.

Layer column: `existing` gates keep their current implementation and enforcement machinery unchanged (§15.1). The lifecycle adds evidence to them; it does not redefine them.

`CONDITIONAL` is permitted only with a specific, owned, dated condition. It is forbidden at G0, G0.5, G7 and G8, and forbidden anywhere in an L4 feature.

### 9.3 G8 — two parts, and the boundary with H3

G8 brackets F16 rather than only preceding it. This keeps validation evidence inside the lifecycle while leaving the release decision where it already lives.

**Part A — validation readiness.** Certified before F16 begins.

* All development verification passed, with immutable evidence references.
* Evidence package complete and reproducible from the recorded commands and commit.
* Every known defect dispositioned with a rationale.
* Customer-journey scenarios executable in the validation environment, with that environment identified.
* Every `critical` scenario has an F16 case.
* Zero orphans, certified against the current baseline.

**Part B — validation acceptance.** Certified after F16 completes.

* Every `JRN-*` in scope executed in the validation environment, with results.
* Every `critical` and `high` scenario case executed, with results.
* Each `NFR-*` measured by its stated method, with the measured value recorded, not merely a pass assertion.
* Findings from F16 classified: defect, requirement gap, or accepted limitation. Requirement gaps route to F17 with escape point `requirement`.
* Residual known limitations listed explicitly, each with customer impact.
* Evidence package sealed: file list with checksums, commit, environment.

Part B produces a recommendation, not a release decision. `RECOMMEND_RELEASE`, `RECOMMEND_RELEASE_WITH_LIMITATIONS`, or `RECOMMEND_HOLD`. The accept-or-reject decision belongs to **H3** (§15.4). The lifecycle hands H3 a sealed evidence package and a recommendation; H3 owns the outcome.

There is no G9. Adding one would create a second release-governance mechanism competing with H3.

## 10. F12–F16 execution

F12 Implementation: minimal implementation satisfying the assigned `AC-*` set, unit tests written alongside, static analysis clean, code review by a Reviewer identity that did not author the code, `trace.yml` updated in the same change. Contract deviations discovered here go back to Architect; they are never absorbed silently in code. An incompatible contract change routes to H2 (§15.3).

F13 Unit verification: positive, negative, boundary and error-handling cases per unit; error paths exercised, not merely reachable; selected coverage thresholds met. Certified at G4.

F14 Integration verification: component pairs and clusters; contract conformance per `IFC-*`/`EVT-*` including every semantic declared `applicable: true`; duplicate delivery where `duplication.possible` is true; consumer idempotency; ordering; schema compatibility; dead-letter behaviour; data flow; failure injection at each declared failure boundary; the concurrency interleavings named in §6.6.

F15 Software/system verification: end-to-end use cases; the regression suites selected from F10; every `high` and `critical` scenario; performance, security and reliability against `NFR-*` using each NFR's measurement method; the environment, configuration and variant matrix; upgrade, downgrade and rollback paths. Certified at G7.

F16 Validation: real customer scenarios in the real or highest-fidelity available environment, driven by `JRN-*` and `AC-*`, evaluating intended use rather than implemented behaviour. Validation asks whether this serves the customer in their environment, which is not the question of whether the code meets the spec. Bracketed by G8 parts A and B.

## 11. L4 additional controls

Applied when `safety_relevant`, `regulatory`, `security_sensitive`, or irreversible data migration is true.

Hazard, misuse and insufficiency analysis: analyse not only failures but performance insufficiencies and reasonably foreseeable misuse. Carry the resulting requirements into F3 as first-class `AC-*` entries with their own verification. Insufficient specification of intended functionality is itself a defect class, not an acceptable residual.

Additional obligations:

* Dedicated failure-mode scenario sweep in F2, with every resulting scenario risk-scored.
* `rules.independence: role_and_identity` for every gate in the feature (§9.1.1).
* Independent review of F8 and F9 by a reviewer identity that contributed nothing to the feature in any session.
* Explicit derivation record from each regulatory or safety obligation to the requirements that discharge it and the tests that evidence it.
* Security and privacy threat modelling, with mitigations traced as `NFR-*`.
* Data migration with a tested rollback, and the rollback exercised at F15.
* No `CONDITIONAL` gate verdicts anywhere in the feature.
* `risk_coverage` and `decision_coverage` mandatory in the selected coverage set.

## 12. F17 — Defect learning loop

A defect is evidence about two things: the software is wrong, and something in the engineering system either allowed the error or failed to catch it. The first is always corrected. The second is corrected when an artifact or process was genuinely inadequate.

### 12.1 Flow

```
DEFECT
  ▼
Reproduce (deterministic repro recorded, or §12.4 exception)
  ▼
Determine escape point — where was it INTRODUCED?
  ├── requirement            ├── interface contract
  ├── acceptance criterion   ├── detailed design
  ├── scenario (never modelled) ├── implementation
  ├── architecture           └── environment / configuration
  ▼
Determine detection point — where was it CAUGHT?
  unit | integration | system | validation | production
  ▼
Root cause — why was it POSSIBLE, not just what is wrong
  ▼
┌─────────────────────────────────────────────────────────┐
│ Was an engineering artifact or process inadequate?      │
└──────────────┬──────────────────────┬───────────────────┘
              NO                     YES
               │                      │
               ▼                      ▼
      SYMPTOM CORRECTION      SYMPTOM CORRECTION
      only:                   +
      · code fix              ESCAPE CORRECTION:
      · test at the level     · requirement / AC
        that should have      · scenario or matrix dimension
        caught it             · design rule or pattern constraint
                              · contract clause
                              · checklist item
                              · template change
                              · gate criterion
               │                      │
               └──────────┬───────────┘
                          ▼
        REGRESSION VERIFICATION (§12.4)
                          ▼
        Metrics updated (§12.5)
```

### 12.2 Symptom correction and escape correction

Two distinct obligations, and v1.0 conflated them.

**Symptom correction** — fix the software so the defect no longer exists. Always required. Applied wherever the code is wrong, which is usually F12, and often also F9 or F7.

**Escape correction** — fix the lifecycle artifact or process that allowed the defect to be created or to escape detection. Required whenever the root cause identifies an inadequate artifact or process.

> **Every defect requires symptom correction. Every defect additionally requires escape correction where an engineering artifact or process was inadequate.**

The v1.0 instruction to "correct the defect at the escape phase" was directionally right and literally wrong. A missing timeout requirement is not fixed by amending F3 alone. It needs the requirement (`AC-*` added), the design (error path added), the implementation (timeout handled), and tests at the level that should have caught it. Escape correction and symptom correction are both in play, at different phases.

Worked contrast:

| Case | Root cause | Symptom correction | Escape correction |
|---|---|---|---|
| Missing timeout behaviour | F3 never specified it; F4 did not ask | code handles timeout; `DES-11` error path added | `AC-014-11` added; G0 checklist item "every external call has specified timeout behaviour"; F4 question list extended |
| Race in profile apply | requirement, architecture and design all correct; unit test missed one interleaving | fix the interleaving; add the concurrency unit test | **none required.** The design named the serialization mechanism; the test simply missed a case. Adding a checklist item here would inflate the checklist without preventing anything |
| Storage-unavailable path unmodelled | F2 swept the dimension for write but not read | code handles it; `AC-014-9` added; `UT-93`, `IT-35`, `ST-214` added | F2 matrix rule: every persistence dimension swept for both read and write; G0 checklist item added |

The middle row is the case v1.0 mishandled. A correct requirement, a correct architecture, a correct design and a missed test interleaving calls for a new concurrency test, not a new checklist item.

### 12.3 Defect record

Schema: `.lifecycle/schema/defect.schema.json`.

```markdown
# DEF-031
Feature: FEAT-2026-014
Summary: profile silently not applied when storage is unavailable at first selection
Baseline in force when introduced: REQ-BL-003

## Reproduction
Deterministic: yes
Steps: recorded in defects/DEF-031-repro.md
Environment: bench, variant B amplifier, software 26.8.1

## Escape and detection
Introduced at: requirements (AC-014-4 did not cover storage unavailability at first use)
Detected at: system
Escape path: requirements → design → implementation → unit → integration → system

## Root cause
F2 scenario matrix swept "storage unavailable" only for the save path, not the restore path.
The dimension was present, so the coverage rule was satisfied while the risk was not.

## Classification
process_originated: true          # an artifact or process was inadequate
inadequate_artifact: F2-scenarios.md (matrix sweep rule)
inadequate_process: F4 did not challenge dimension symmetry

## Symptom correction
- code: restore path handles STORAGE_UNAVAILABLE, retains current configuration
- design: DES-11 error path added
- tests: UT-93, IT-35, ST-214 added

## Escape correction                # required because process_originated is true
- requirement: AC-014-9 added (baseline REQ-BL-003 → REQ-BL-004)
- F2 rule: every persistence dimension swept for both read and write paths
- checklist: G0 — "persistence dimensions swept in both directions"
- gates reopened: G2, G3.5, G7

## Regression verification
Mode: RED_GREEN
ST-214 verified failing at commit 4d77e10 (pre-fix), passing at commit 5a91b3c (post-fix)
Evidence: evidence/F15-system/ST-214-red-4d77e10.txt (sha256:...),
          evidence/F15-system/ST-214-green-5a91b3c.txt (sha256:...)
```

### 12.4 Regression verification — RED→GREEN, with a controlled exception

The preferred and default rule stands: **the new test fails before the fix and passes after.** Demonstrated, with immutable evidence references for both runs.

Some conditions cannot be reproduced pre-fix: production-only environments, hardware-only failures, timing-dependent failures, nondeterministic races, external backend conditions, unavailable old software builds, and safety validation environments among them.

```
Preferred:
    demonstrate RED → GREEN, both runs evidenced

Exception path:
    RED cannot be reproduced
       ↓
    document WHY, specifically — which of the conditions above applies
       ↓
    provide ALTERNATIVE EVIDENCE (at least two of):
      · code-level proof the fix addresses the mechanism (diff + reasoning)
      · fault injection reproducing the mechanism synthetically
      · unit or integration test at a lower level where the mechanism IS reproducible
      · trace, log or telemetry from the original occurrence matched to the fix
      · a soak or stress run with occurrence rate before and after
      · analysis showing the pre-fix code path could not have behaved correctly
       ↓
    Reviewer approval, recorded with the reviewer identity and the reason accepted
       ↓
    mode: EXCEPTION recorded in the defect record and in the G7/G8 ledger
```

Never permitted: "could not reproduce" → test added → PASS, with no exception record and no alternative evidence. That is the pattern this rule exists to block. A defect record with `Mode: EXCEPTION` and fewer than two alternative-evidence items fails G7.

Exception rate is a tracked metric. A rising share of `EXCEPTION` modes indicates a test-environment fidelity problem, which is itself a process finding.

### 12.5 Escape analysis and metrics

Maintain the escape matrix across features. Rows are introduction phases, columns detection phases; each defect is one cell.

|  | unit | integration | system | validation | production |
|---|---|---|---|---|---|
| requirements | | | | | |
| architecture | | | | | |
| contract | | | | | |
| detailed design | | | | | |
| implementation | | | | | |

Derived indicators: requirement escape rate, architecture escape rate, contract escape rate, design escape rate, implementation escape rate, and phase containment effectiveness per phase, computed as `defects caught in phase / (defects caught in phase + defects escaping phase)`.

Two v1.1 metrics:

* **Preventive control improvement rate** = escape corrections recorded / defects classified `process_originated: true`. **This must be 1.0.** Every process-originated escape results in a preventive control improvement. Defects classified `process_originated: false` are excluded from the denominator, which is what removes the checklist inflation that v1.0's unconditional rule produced.
* **Regression exception rate** = defects with `Mode: EXCEPTION` / total defects. Tracked per environment. A rise is a test-fidelity finding, not a process violation.

The question these answer is not "how many bugs do we have" but "where is our development process failing to prevent defects" — which is the input to changing this specification. Each quarter, the two lowest-containment phases get at least one concrete change to a checklist, template or gate.

## 13. Conformance self-check

Before handing over to H3, Team Lead verifies and records:

- `F0-qualification.md` exists with type, complexity, all impact flags, initial risk profile and declared depth.
- Every phase required by the declared depth has its artifact, or a recorded, reasoned exemption.
- Every gate required by the declared depth has a PASS entry, certified by an agent identity other than the artifact author's, per the independence rule in force.
- Every gate ledger entry names the baseline it certified against, and no PASS relies on a `superseded` baseline.
- Every evidence claim has a `result_file` and a `checksum`.
- `trace.yml` passes the §8.4 orphan check with zero orphans across all ten classes.
- Every `AC-*` and `NFR-*` has at least one executed test with a recorded result.
- Every `high` and `critical` scenario has a case at the depth §5.2.2 requires.
- Every F10 impacted path has an executed regression test.
- Every open defect is dispositioned.
- Every defect classified `process_originated: true` has a recorded escape correction. Preventive control improvement rate is 1.0.
- Every `Mode: EXCEPTION` regression has Reviewer approval and at least two alternative-evidence items.
- G8 parts A and B both have PASS entries, and part B carries a recommendation.
- The H3 handover package (§15.4) is assembled.

If any item fails, the feature is not ready for H3, regardless of whether the code works. `COMPLETE` requires H3 approval.

## 14. Standards alignment

The structure maps onto established process models, which is what makes the artifacts reusable as assessment evidence rather than parallel paperwork. GM's own MBSE framework proposal takes the same position: Automotive SPICE and ISO 26262 work products should be generated from and traced through the same model used to engineer, integrate, verify and validate the product, with bidirectional traceability from intent through evidence, not maintained as a separate documentation exercise.

| This spec | Corresponds to |
|---|---|
| F1–F5 | Automotive SPICE SYS.2 / SWE.1 requirements analysis; ISTQB test analysis and ATDD-style collaborative acceptance-criteria review before implementation |
| F6–F8, G1, G3 | SWE.2 software architectural design |
| F9, F12 | SWE.3 detailed design and unit construction |
| F13, G4 | SWE.4 unit verification |
| F14 | SWE.5 component integration and verification |
| F15, G7 | SWE.6 software verification; SYS.4/SYS.5 system integration and verification |
| F16, G8 | VAL.1 validation |
| §5.2.2, §11 | ISO 26262-6 software development and verification; ISO 21448 intended-functionality insufficiency and misuse analysis; ISO 21434 for security-sensitive features |
| §8 | SPICE bidirectional traceability and consistency between requirements, architecture and verification |
| §8.6 | SPICE configuration management and baseline integrity (SUP.8) |
| §12 | SPICE problem resolution management (SUP.9) and process improvement (PIM.3) |

Treat these as mappings, not as a claim of compliance. Compliance is an assessment outcome; this spec makes the evidence available. G7 and G8 are lifecycle gates named for continuity with the project's existing numbering, not standards processes.

## 15. Integration with the existing framework

This document is the feature-engineering front end. The project's existing gates are the enforcement and decision layers. Duplicating governance would be worse than having none, because two mechanisms disagree.

```
                 FEATURE LIFECYCLE  (this document)
                 ┌────────────────────────────────┐
                 │ requirements · scenarios+risk  │
                 │ design · contracts · impact    │
                 │ state ownership · concurrency  │
                 │ traceability · baselines       │
                 └───────────────┬────────────────┘
                                 │ supplies evidence to
                                 ▼
                 EXISTING EXECUTABLE GATES
                 ┌────────────────────────────────┐
                 │ G1 Contract     G4 Executable  │
                 │ G2 Impact       G5 Frontend    │
                 │ G3 Architecture G6 Browser/HMI │
                 └───────────────┬────────────────┘
                                 │ wrapped by
                                 ▼
                 NEW LIFECYCLE GATES
                 ┌────────────────────────────────┐
                 │ G0 · G0.5 · G3.5 · G7 · G8     │
                 └───────────────┬────────────────┘
                                 │ hands over to
                                 ▼
                 EXISTING HUMAN GATES
                 ┌────────────────────────────────┐
                 │ H1 Architecture approval       │
                 │ H2 Incompatible contract change│
                 │ H3 Release approval            │
                 └────────────────────────────────┘
```

### 15.1 G1–G6 remain unchanged

The existing G1–G6 keep their current definitions, implementations and enforcement machinery. This document does not redefine them. What it adds is the artifact set that makes their checks decidable: contracts with declared reliability semantics for G1, two-directional impact for G2, the state-ownership register and concurrency model for G3, immutable evidence references for G4, and the target-surface matrix for G5/G6.

Where this document's §9.2 descriptions of G1–G6 differ from the project's existing definitions, **the existing definitions win**, and `config.yml` `external_gates` records the authoritative location. The rows in §9.2 are the lifecycle's expectations of what evidence it supplies, not a redefinition.

G0, G0.5, G3.5, G7 and G8 are additive and sit around the existing set.

### 15.2 H1 — Architecture approval

The lifecycle guarantees this inbound package when a feature reaches H1. H1's internal criteria, quorum and outcome semantics are owned by H1 and not asserted here.

| Item | Path |
|---|---|
| Architecture | `F8-architecture.md`, including the §6.6 concurrency model and §6.7 reuse records |
| Alternatives record | `F8-architecture.md` alternatives table, with the selection reason (L3+) |
| State ownership register | `F6-decomposition.md` / `trace.yml` `state_ownership` |
| Contracts | `F7-contracts/*.yml` at the contract baseline |
| Impact analysis | `F10-impact-analysis.md`, both directions |
| Gate ledger | `gates/G1.md`, `gates/G3.md`, both PASS, with baselines named |
| Open items | any `CONDITIONAL` conditions with owners and dates |

Trigger: L3+ features on reaching `ARCHITECTED`, and any feature whose architecture changes after a prior H1 approval. G3 PASS is a precondition for the handover, not a substitute for H1.

### 15.3 H2 — Incompatible contract change

Trigger: any change to a baselined `IFC-*` or `EVT-*` that is not backward compatible. The lifecycle detects this mechanically — `compatibility` field, `version` major increment, or a `changes` entry touching a contract with existing consumers.

| Item | Path |
|---|---|
| Contract diff | old and new `IFC-*`/`EVT-*` at both baselines |
| Compatibility statement | the `compatibility` field and what specifically breaks |
| Consumer list | `trace.yml` `contracts.<id>.consumers` plus F10 reverse impact |
| Reverse impact | `F10-impact-analysis.md` reverse section, listing every affected feature and regression suite |
| Migration plan | how consumers move, in what order, and the rollback |
| Gate ledger | `gates/G1.md`, `gates/G2.md` re-certified against the new baseline |
| Baseline record | `trace.yml` `changes` entry with `gates_reopened` |

The lifecycle blocks implementation of an incompatible change until H2 records approval. The Implementer charter prohibits absorbing it in code.

### 15.4 H3 — Release approval

Trigger: G8 part B PASS. The lifecycle hands over a sealed package and a recommendation. H3 decides.

| Item | Path |
|---|---|
| Recommendation | `gates/G8.md` part B: `RECOMMEND_RELEASE` / `..._WITH_LIMITATIONS` / `RECOMMEND_HOLD` |
| Validation results | `evidence/F16-validation/`, per `JRN-*` and per `critical`/`high` scenario |
| NFR measurements | measured values against thresholds, by each NFR's stated method |
| Evidence package | sealed file list with checksums, commit, environment |
| Gate ledger | every gate required by the depth, PASS, with baselines named |
| Conformance self-check | §13 record |
| Residual limitations | each with customer impact |
| Defect disposition | every known defect, with rationale; every `process_originated` defect's escape correction |
| Traceability | `trace.yml` with a zero-orphan check output |

The lifecycle does not gate release, schedule it, or interpret H3's decision. On `COMPLETE`, Team Lead records the H3 decision reference in `state.json`.

### 15.5 What the lifecycle does not own

Release scheduling, deployment, rollout staging, field monitoring thresholds, program milestones, and resourcing. If a future need pushes any of these into `.lifecycle/`, that is a signal to extend the existing governance instead.

## 16. Machine-readable schemas

`.lifecycle/schema/` holds JSON Schema definitions so the existing G1–G4 machinery can validate lifecycle artifacts mechanically rather than by inspection.

| Schema | Validates | Enforced at |
|---|---|---|
| `state.schema.json` | `state.json`: state names, transition records, `depth_change` entries, charter log | every transition |
| `trace.schema.json` | `trace.yml`: element shapes, baselines, `changes`, risk scores, state ownership | G3.5, G7, G8 |
| `contract.schema.json` | `IFC-*.yml`: boundary, per-semantic `applicable` + `reason`, traces | G1 |
| `event.schema.json` | `EVT-*.yml`: delivery, ordering, duplication, consumer idempotency, replay, retention, dead letter | G1 |
| `gate.schema.json` | `gates/*.md` front matter: authorship identity, baseline, evidence items with checksums | every gate |
| `defect.schema.json` | `defects/DEF-*.md`: escape point, detection point, `process_originated`, corrections, regression mode | F17, G8 |

Two scripts consume them:

* `orphan-check.py` — the §8.4 mechanical check, emitting all ten orphan classes in ledger format. Exits non-zero on any orphan.
* `lifecycle-validate.py` — validates every artifact against its schema, checks the §3.4 depth rules including `gates_must_be_subset_of_phase_requirements`, checks §9.1.1 identity independence, checks §8.6 baseline currency, and checks the §12.5 preventive control improvement rate. Exits non-zero on any violation.

Both are dependency-light and safe to run in CI alongside the existing gate machinery.
