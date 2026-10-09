# Skill-Integration Matrix - canonical contract

Status: v1.0, ratified P1 deliverable. Consolidates the role/skill/artifact/evidence/gate
routing previously scattered across `.opencode/skill-routing.md`, `.opencode/rules/evidence.md`,
the agent charters in `.opencode/agents/`, and `framework/gates/EXIT_CODES.md`. This file is
the single binding contract: which role loads which skill, produces which artifact, and is
judged by which gate. Functional routing (condition -> skill -> agent) stays operational in
`skill-routing.md`; this matrix is the contract that gate reviewers and G-T1 verify against.

Critic claims covered: #3 (skills as verifiable artifacts of the control plane), #5 (a
functional, consolidated integration matrix), #9 (G-EXEC execution-integrity gate, row in
section 5, file in construction).

## 1. Role -> Skills (mandatory bindings)

| Role | Mandatory skills | Source |
| --- | --- | --- |
| team-lead | requirements-authoring for every feature request; karpathy-guidelines when ambiguity/uncertainty exist; consult routing matrix for every delegation; record required skills in Tool Plan | skill-routing.md:59-62 |
| researcher | technical-validation for any material unknown | skill-routing.md:66 |
| architect | software-architecture-design for L3/L4; technical-validation; api-design before contract-authoring; database-schema-design for data-model changes | skill-routing.md:64-68 |
| planner | verify required skills listed per task; consume architect outputs (architecture + contracts + data design); never redesign architecture | skill-routing.md:70-73 |
| implementer | load ALL skills named by Team Lead / Planner; apple-ui + frontend-react for any UI work; unit-test-authoring for business logic; karpathy-guidelines for surgical changes and avoiding overcomplication | skill-routing.md:75-78 |
| reviewer | verify implementation vs architecture; contract compliance; required-skills-used; unit-test-authoring adequacy standards | skill-routing.md:80-84 |
| verifier | performance-testing when material; browser-verification for visible behavior; name applicable evidence class per requirement shape | skill-routing.md:86-89; evidence.md:1-19 |

## 2. Skill dependency route

(from skill-routing.md:24-55)

```
requirements-authoring
  -> technical-validation
  -> software-architecture-design
       |- apple-ui + frontend-react (UI work) -> implementer
       |- api-design (API changes) -> contract-authoring -> implementer
       |- database-schema-design (data changes) -> implementer
       `- implementer -> unit-test-authoring (business logic)
            -> reviewer -> verifier
            -> performance-testing (performance-sensitive)
            -> browser-verification (visible behavior)
```

A skill lower in the chain may only be reached after the ones above it are loaded; skipping
a required skill is a G-T1 tool-utilization gap.

## 3. Artifact -> Owner -> Gate binding

| Artifact | Produced by | Consumed by | Gate |
| --- | --- | --- | --- |
| SPEC.md / requirements | team-lead | planner, implementer | G-ENTRY |
| PLAN.md | planner | all roles | G-ENTRY, G9 |
| architecture design | architect | planner, implementer | G3 |
| OpenAPI contracts | architect + implementer | implementer, verifier | G1 |
| schema + migrations | architect + implementer | implementer, verifier | G1 (doc-only) |
| source code | implementer | reviewer, verifier | G2, G4, G5, G10 |
| tests | implementer | reviewer, verifier | G2, G4 |
| VERIFICATION.md + browser specs | verifier | reviewer, history | G6, G-T1 |
| claim ledger entries | any role | verifier | G11, G14 |
| tool plan | team-lead | implementer | G-T0 |
| tool evidence | verifier | reviewer | G-T1 |
| handoff (SUMMARY.md) | completing role | successor | G8 (open blockers) |

## 4. Evidence class -> Requirement shape -> Gate

(from evidence.md:3-16)

| Evidence class | Requirement shape | Gate |
| --- | --- | --- |
| contract / integration test, exit code | API returns a status | G1 |
| unit test | business rule produces a value | G4 |
| type check + build | type or interface correctness | build |
| browser screenshot + DOM inspection | visual alignment or styling | G6 |
| browser navigation + console output | interaction flow end to end | G6 |
| dependency / security scanner | no unauthorised dependency | scanner |
| integration test vs running system | authorisation denies a role | G1/G4 |
| measured benchmark | latency budget | G4 / perf |
| executed migration in disposable env | migration applies and rolls back | migration |
| Playwright run at declared viewport | responsive layout at a width | G6 |
| G5 stack conformance exit code | mandated tool/library is used | G5 |
| ledger entry naming requirement + approver | conditional visual tool permitted | G5 |

Unverifiable is never a pass: no driver -> exit 3, no harness -> exit 3, absent tool ->
BLOCKED 2 (evidence.md:21-30).

## 5. Gate -> Binds -> Verdict

Exit semantics are authoritative in `framework/gates/EXIT_CODES.md`; this table binds each
gate to the contract row it judges and adds the new G-EXEC row.

| Gate | Binds | Verdict source |
| --- | --- | --- |
| G-ENTRY | plan pre-flight (SPEC/PLAN approval, scope, no open questions) | EXIT_CODES.md:161-171 |
| G1 | OpenAPI contract + generated types + contract tests | EXIT_CODES.md:9 |
| G2 | impact mapping to tests | EXIT_CODES.md:10 |
| G3 | architecture boundaries (architecture_rules.yaml) | EXIT_CODES.md:11 |
| G4 | executable checks | EXIT_CODES.md:12 |
| G5 | frontend stack conformance | EXIT_CODES.md:13 |
| G6 | browser specs for visible behavior | EXIT_CODES.md:14, 26-31 |
| G7 | retro ledger | EXIT_CODES.md:15, 33-37 |
| G8 | open blockers | EXIT_CODES.md:16, 39-45 |
| G9 | changed source vs declared scope | EXIT_CODES.md:17, 47-51 |
| G10 | permission policy structure | EXIT_CODES.md:18, 54-71 |
| G11 | claim validity + provenance | EXIT_CODES.md:21, 93-97 |
| G12 | provider health pre-dispatch | EXIT_CODES.md:22, 99-110 |
| G13 | task event stream | EXIT_CODES.md:23, 112-122 |
| G14 | claim integrity E1-E8 | EXIT_CODES.md:24, 124-134 |
| G-T0 | tool lifecycle pre-flight | EXIT_CODES.md:19, 73-78 |
| G-T1 | tool evidence in verification artifacts | EXIT_CODES.md:20, 80-85 |
| G-EXEC | execution-integrity matrix (failure_injection.py) | 0 = 38/38 pass; 1 = deviations listed; 2 = BLOCKED (no python3); 4 = NOT_APPLICABLE (no matrix module) |

G-EXEC (critic #9): `framework/gates/g_exec.sh` wraps
`python3 framework/adapters/failure_injection.py`. Exit 0 -> pass; non-zero -> fail with the
deviation summary printed; python3 absent -> BLOCKED; no matrix module -> NOT_APPLICABLE.
The EXIT_CODES.md row is added when the gate is created (P1, in progress).

## 6. Contract verification method

- Rows 1-2: read from skill-routing.md (full read, 89 lines).
- Row 3: source from agent charters (read) + gates inventory (glob, 19 files).
- Row 4: read from evidence.md (full read, 42 lines).
- Row 5: gates read from EXIT_CODES.md (full read, 171 lines).
- G-EXEC: gate created, executed, exit code recorded (todo 9, next).
