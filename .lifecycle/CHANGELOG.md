# .lifecycle CHANGELOG

## v1.2 — self-optimization addendum (merged 2026-09-12)

Additive only — no change to any v1.1 normative rule, phase, or gate definition.

This repository already shipped the mechanical retrospective half (`framework/retro/ledger.py`, `framework/retro/escape_path.py`) wired into G7, so the v1.2 tooling was merged adaptively: the `.lifecycle` layer landed as-is, and the `framework/retro`/`.opencode` tooling changes (SKILL.md v3 bump, `propose_patch.py`, ledger.py `fix_commit`/denylist additions) were ported as adapted proposals under the enforcement plane rather than overwriting the live files. `escape_path.py` was deliberately not replaced — the existing `containment_map.yaml` machine and its G7 exit-code contract (3 reserved for unverifiable evidence) are richer than the patch's hardcoded version.

### 1. Cross-model review at the three highest-stakes checkpoints

§9.1.1 independence is identity/session-based, which does not guard against two sessions of the same underlying model sharing a blind spot. `config.yml` `cross_model_review` names H1, H2, and G8-B as checkpoints where the certifying review should come from a different model family than the artifact's author, with an explicit, schema-compliant fallback for each: CONDITIONAL where legal (G1–G3.5, feeding H1/H2), a capped Part B recommendation with a named residual limitation at G8-B (CONDITIONAL is schema-forbidden there).

Files: `config.yml` (`cross_model_review` block), `agents/reviewer.md`, `agents/verifier.md`.

### 2. Gate-value counterweight to the retrospective ratchet

`retrospective` only ever tightens the framework. Nothing measured whether an existing gate is pulling its weight. `gate_value_report.py` reads gate ledger entries across a configurable feature window and flags gates with zero non-PASS verdicts as pruning candidates — never auto-pruned, always requiring the same Reviewer concurrence de-escalation already requires.

Files: `scripts/gate_value_report.py` (new), `config.yml` (`gate_value` block).

### 3. Anti-overbuild ceiling on speculative defense

A new shared constraint file bounds four failure modes (unjustified hashing, speculative edge-case handling, ad hoc rubric invention, and overbuilt generality) that a large, review-heavy framework tends to accumulate over time as agents over-index on past findings. Referenced by, not duplicated into, the Implementer and Architect charters.

Files: `agents/_shared-anti-overbuild.md` (new), `agents/implementer.md`, `agents/architect.md`.

### 4. Grilling pass before F1, evidence tags in F10

An active interrogation pass (not just a checklist) is now required before the Researcher fills in F1's tables, to surface ambiguity the checklist format doesn't prompt for on its own. F10's forward and reverse impact rows now carry the same `[direct]/[inferred]/[assumption]` evidence-marker discipline F1 already required, since an unmarked F10 claim dressed as fact is exactly how a reverse-impact miss reaches G2.

Files: `agents/researcher.md`, `templates/F1-context.md`, `templates/F10-impact-analysis.md`, `agents/architect.md`.

### 5. `.opencode/gsd-core` authority split documented

This pack coexists with an independently-versioned `.opencode/gsd-core` workflow engine in the same repository. `INTEGRATION.md` §6 now states explicitly which system is authoritative for depth classification, agent-attribution telemetry, and retrospective ledger placement, so the two do not silently duplicate or contradict each other's self-optimization signal.

Files: `INTEGRATION.md`.

## v1.1 — 2026-08-29

Ten review findings landed. Each entry names the sections and pack files changed.

### 1. Depth rules made internally consistent (§3.4)

v1.0 said "G0 + G0.5 (baseline)" in §2 and the lifecycle diagram, but omitted G0.5 from the L1 gate list. It also excluded F8/F9 from the L2 phase list while a parenthetical required them abbreviated.

Fixed by an explicit five-column depth matrix (requirements / verification / design / implementation / system), plus three named rules:

* **Rule D1** — G0.5 is mandatory whenever F5 is performed. L1 now carries G0.5, proportionally scoped.
* **Rule D2** — L2 includes F8 and F9, one page each. The alternatives record stays L3+.
* **Rule D3** — gates must be a subset of what the depth's phases can produce, checked mechanically.

L2 also gains G3, since it now produces F8.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §3.4, `config.yml` `depths`, `checklists/G0.5.md`, `templates/F0-qualification.md`, `scripts/lifecycle-validate.py`.

### 2. Phases and gates separated in config (§1.3)

`depth_defaults` mixed both into one list. Replaced with `depths.<L>.phases` and `depths.<L>.gates`, plus `rules.gates_must_be_subset_of_phase_requirements: true` and `rules.required_gate_missing: BLOCK`.

Files: `config.yml`, `scripts/lifecycle-validate.py`, `schema/state.schema.json`.

### 3. Independence is identity-based, not role-based (§9.1.1)

Role separation is not independence when two Architect instances share a charter and its blind spots. Every artifact header and ledger entry now records `agent_id`, `role`, `session_id`, `timestamp` for both author and certifier.

Rule at all depths: `certifier.agent_id ≠ author.agent_id` and `certifier.session_id ≠ author.session_id`.
Rule at L4 and wherever `rules.independence: role_and_identity`: role differs too, and the certifier contributed nothing to the artifact in any prior session.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §9.1, all seven charters, all eleven checklists, `schema/gate.schema.json`, `config.yml` `authorship`.

### 4. F17 process improvement is conditional on root cause (§12.2, §12.5)

v1.0 required every F17 record to change at least one checklist or template. That inflates checklists for defects with no process cause — a correct requirement, correct architecture, correct design, and a unit test that missed one interleaving needs a concurrency test, not a checklist item.

Defects now carry `process_originated: true|false`. Escape correction is required when true. The metric becomes **preventive control improvement rate = escape corrections / process-originated defects, which must be 1.0**. That is stronger than the v1.0 rule because it cannot be discharged by a token checklist edit.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §12, `templates/DEF-defect-record.md`, `templates/escape-matrix.md`, `checklists/G8.md`, `agents/reviewer.md`, `schema/defect.schema.json`.

### 5. Symptom correction separated from escape correction (§12.2)

"Correct the defect at the escape phase" was directionally right and literally wrong. A missing timeout requirement needs the requirement, the design error path, the implementation, and tests — not an F3 amendment alone.

Two defined obligations: **symptom correction** (fix the software; always required) and **escape correction** (fix the artifact or process that allowed it; required when `process_originated`). A three-row worked contrast table shows the distinction, including the race-condition case v1.0 mishandled.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §12.2, §0 rule 4, §7 `DEFECT_LOOP` exit, `templates/DEF-defect-record.md`.

### 6. RED→GREEN gains a controlled exception (§12.4)

Preferred rule unchanged and still default. Exception path added for production-only, hardware-only, timing-dependent, nondeterministic, external-backend, unavailable-old-build and safety-environment cases.

Exception requires: a specific documented reason, at least two alternative-evidence items from a defined list of six, and recorded Reviewer approval. `Mode: EXCEPTION` with fewer than two items fails G7. "Could not reproduce → test added → PASS" is explicitly never permitted. Exception rate is tracked as a test-fidelity indicator.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §12.4, §12.5, `templates/DEF-defect-record.md`, `checklists/G7.md`, `agents/reviewer.md`, `agents/verifier.md`, `schema/defect.schema.json`.

### 7. Risk dimension and combinatorial selection added to F2 (§5.2.1, §5.2.2)

Every `SCN-*` now carries `likelihood`, `impact`, `detectability` (1–5 each) and a derived priority from `likelihood × impact × (6 − detectability)`. Four bands map to test depth: low, medium, high, critical. A high or critical risk hiding behind one nominal case is a G0 finding, which is what closes the "offline has one trivial test" hole.

Selection technique recorded per scenario, from six permitted techniques. "These are equivalent" now requires the partition named and the reason the system cannot distinguish the values. Cartesian expansion remains forbidden.

`risk_coverage` becomes mandatory in the selected coverage set at L3+.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §5.2, §8.5, `config.yml` `risk`, `templates/F2-scenarios.md`, `templates/F5-test-analysis.md`, `checklists/G0.md`, `checklists/G0.5.md`, `checklists/G7.md`, `schema/trace.schema.json`.

### 8. State ownership and concurrency elevated to mandatory artifacts (§6.5, §6.6)

State-ownership register is a mandatory F6 artifact at L2+, and whenever state is shared across components. Every mutable piece of state gets exactly one authoritative owner; two owners is a G3 failure. Records owner, writers, readers, persistence, control scope, synchronization mechanism, consistency model, conflict resolution and invariants.

Concurrency model is a mandatory F8 artifact with nine recorded items. A model naming no serialization mechanism, or leaving the conflict winner non-deterministic, fails G3.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §6.5, §6.6, §8.3, §8.4, `templates/F6-decomposition.md`, `templates/F8-architecture.md`, `checklists/G3.md`, `checklists/G3.5.md`, `agents/architect.md`, `schema/trace.schema.json`.

### 9. Baseline versioning and immutable evidence added (§8.6, §9.1.2)

`trace.yml` gains `baselines` and `changes`. Baselines are created at G0 (requirements), G1 (contracts) and G3.5 (design). Every baselined element records its baseline. Changing one supersedes the old baseline and records before text, after text, reason, impact set, and gates reopened. A PASS certified against a superseded baseline is not valid evidence — `stale baseline` is a new orphan class.

Gate evidence items now require `claim`, `command`, `commit`, `environment`, `timestamp`, `result_file`, `checksum`. A claim without a result file and checksum fails the gate.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §8.3, §8.6, §9.1, §13, all eleven checklists, `templates/trace.yml`, `schema/trace.schema.json`, `schema/gate.schema.json`, `scripts/orphan-check.py`.

### 10. G7/G8 bound to existing H1/H2/H3 rather than a parallel G9 (§9.3, §15)

No G9. G8 instead brackets F16: **part A** validation readiness before F16, **part B** validation acceptance after. Part B produces a recommendation — `RECOMMEND_RELEASE`, `RECOMMEND_RELEASE_WITH_LIMITATIONS`, `RECOMMEND_HOLD` — and H3 owns the accept-or-reject decision.

New §15 defines a minimal inbound contract per H-gate: what artifacts and ledger entries the lifecycle guarantees to hand over. H-gate internal criteria, quorum and outcome semantics are not asserted. §15.1 states that where this document's G1–G6 descriptions differ from the project's existing definitions, the existing definitions win.

`state.json` gains `VALIDATION_ACCEPTED` and `RELEASE_PENDING`. `COMPLETE` requires an H3 decision reference.

Files: `FEATURE_DEVELOPMENT_LIFECYCLE.md` §9.2, §9.3, §15, §7, §13, `INTEGRATION.md` (new), `config.yml` `external_gates`, `checklists/G8.md`, `agents/team-lead.md`, `schema/state.schema.json`.

### Also changed

* §0 gains the architectural principle verbatim: *the lifecycle must be rigorous in reasoning but proportional in execution*, replacing depth as rule 2.
* §6.2 component cohesion rewritten. "A component with two responsibilities is split or justified" became "one cohesive responsibility boundary; multiple operations allowed when they belong to it". Low cohesion splits, high cohesion retains. G3 checks reasoning, not operation count.
* §6.4.1 contract reliability semantics are declared per semantic with `applicable` and a `reason`, not universally required. New `boundary` field (`in_process` / `ipc` / `network`) sets the expectation.
* §6.4.2 event semantics extended with `duplication`, `consumer_idempotency`, `replay`, `retention`, `dead_letter`. G1 checks the coupling rule that `duplication.possible: true` requires `consumer_idempotency.required: true` with a named mechanism.
* §6.7 existing-mechanism reuse is a hard G3 check with a recorded search: scope, candidates with fit, selection, reason. `searched: false` fails.
* §6.9 state machines mandatory in F9 for lifecycle, async, transient state, retries, focus, connection, user switching and power transitions.
* §6.10 design models minimum-necessary, with the rule **no diagram without a design question it answers**. Class diagrams no longer mandatory.
* §9.2 renames G7 to Lifecycle Requirements Verification Gate and G8 to Lifecycle Validation Readiness and Acceptance Gate, with a `Layer` column marking each gate `existing` or `lifecycle (new)`.
* §14 gains SUP.8, SUP.9 and PIM.3 mappings for baselines, problem resolution and process improvement.
* §16 new: six JSON schemas plus `lifecycle-validate.py`.

### Migration from v1.0

In-flight features may finish under v1.0. Features baselining after adoption use v1.1. For a v1.0 feature that continues:

1. Add `agent_id` and `session_id` to future artifact headers and ledger entries. Past entries stay as-is with a note.
2. Create a requirements baseline retroactively at the current commit, and treat it as `current`.
3. Score existing `SCN-*` for risk before the next G7.
4. Reclassify existing defect records with `process_originated`.
5. No retroactive escape corrections are required for defects closed under v1.0.

## v1.0 — 2026-08-29

Initial normative release. Seven charters, eleven gate checklists, `config.yml` with the Entertainment audio-stack instantiation, nine artifact templates, runtime binding files for five host tools, and `orphan-check.py`.
