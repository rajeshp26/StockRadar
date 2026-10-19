# Designer Agent — Production-Grade Design (Fact-Checked, No Assumptions)

**Status:** Design proposal for human approval. Not implemented.
**Date:** 2026-10-18
**Author:** primary session (team-lead role)
**Artifact root for generated output:** `.planning/` (git-ignored)

---

## 0. Scope and evidence discipline

This document designs the capability the user asked for:

> a "designer agent" whose job is to design/mock UI using several design skills and
> produce the best 2–3 mockups for human approval, integrated into the agent workflow.

Every factual claim below was verified by opening the file in this run. Citations use
`[VERIFIED: path:start-end]`. Anything not verified is listed under **Unknowns** (section 2)
and is a decision for the human, not an assumption. No external skill is assumed present.

---

## 1. Verified facts

### 1.1 The capability already exists (Rule Zero applies)

| Fact | Evidence |
|---|---|
| A sketch workflow produces **2–3 variants** of throwaway HTML mockups for comparison | `[VERIFIED: framework/opencode/skills/gsd-sketch/SKILL.md:6-17]` |
| Variants are saved under `.planning/sketches/` | `[VERIFIED: framework/opencode/skills/gsd-sketch/SKILL.md:8]`, `[VERIFIED: framework/opencode/gsd-core/workflows/sketch.md:1-9]` |
| The workflow auto-creates `.planning/sketches/` if absent | `[VERIFIED: framework/opencode/skills/gsd-sketch/SKILL.md:16]`, `[VERIFIED: framework/opencode/gsd-core/workflows/sketch.md:88-89]` |
| A companion wrap-up packages findings into a reusable skill and `.planning/sketches/WRAP-UP-SUMMARY.md` | `[VERIFIED: framework/opencode/gsd-core/workflows/sketch-wrap-up.md:1-6]` |
| A UI-SPEC contract agent exists and consumes upstream artifacts | `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:1-21]` |

**Consequence:** a brand-new agent whose *only* purpose is to emit 2–3 mockups would
duplicate `gsd-sketch`. Under Rule Zero ("do not duplicate capabilities already provided")
and Rule One ("do not invoke agents gratuitously; name the specific unmet need"), a new
agent is justified only by a need `gsd-sketch` cannot satisfy. The identified unmet needs
are in section 3.

### 1.2 Enforcement plane (agents cannot edit these)

| Plane path | Evidence |
|---|---|
| `.opencode/**`, `opencode.json`, `AGENTS.md`, `framework.config.json`, `framework/opencode/**`, `framework/plan/**`, `framework/testing/**`, `framework/security/**` | `[VERIFIED: framework/security/enforcement_plane.yaml:16-22]` (list continues to line 33; the run truncated at 22) |
| The same list is mirrored as `edit` denies in config | `[VERIFIED: opencode.json:22-32]` |
| `framework/opencode/**` is denied → **agents cannot create `framework/opencode/agents/*.md` or `framework/opencode/skills/*`** | `[VERIFIED: opencode.json:28]` |
| `.opencode/**` is denied → agents cannot write under `.opencode/` | `[VERIFIED: opencode.json:24]` |

### 1.3 Permissions relevant to this design

| Fact | Evidence |
|---|---|
| `read`, `glob`, `grep`, `list`, `skill` are `allow` globally | `[VERIFIED: opencode.json:10-18]` |
| `question` is `allow` globally (foreground only, see 1.6) | `[VERIFIED: opencode.json:16]` |
| Top-level `edit` default is `ask`; plane paths deny | `[VERIFIED: opencode.json:22-32]` |
| `webfetch` is `deny` globally | `[VERIFIED: opencode.json:33]` |
| The `researcher` subagent has `edit: deny` and `task: deny` | `[VERIFIED: opencode.json:159-167]` |
| The `team-lead` (primary) has `edit: "*": ask` plus the plane denies | `[VERIFIED: opencode.json:111-121]` |
| Configured skill root is exactly one path: `framework/opencode/skills` | `[VERIFIED: opencode.json:453-457]` |

### 1.4 Discovery and handoff

| Fact | Evidence |
|---|---|
| `gsd-ui-researcher` discovers **project skills** only at `.claude/skills/` or `.agents/skills/` | `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:35]` |
| The researcher MUST read every file in `<required_reading>` before anything else | `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:12-13]` |
| The researcher pre-populates fields answered by upstream artifacts and does not re-ask | `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:70]`, `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:212-217]` |
| The ui-phase orchestrator passes `{SKETCH_FINDINGS_PATH}` inside `<required_reading>` | `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:135-142]` |
| `SKETCH_FINDINGS_PATH` is resolved by globbing `./.opencode/skills/sketch-findings-*/SKILL.md` | `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:35-38]` |
| `null` file paths are omitted from `<required_reading>` | `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:158]` |
| UI-SPEC is written to `{phase_dir}/{padded_phase}-UI-SPEC.md`; frontmatter `status: draft` | `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:146-147]`, `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:210-217]` |

### 1.5 Verified defect: wrap-up writes into a denied plane path

| Fact | Evidence |
|---|---|
| `sketch-wrap-up` writes the findings skill to `./.opencode/skills/sketch-findings-[project]/` | `[VERIFIED: framework/opencode/gsd-core/workflows/sketch-wrap-up.md:1-4]` |
| It also reads/checks that path for an existing skill | `[VERIFIED: framework/opencode/gsd-core/workflows/sketch-wrap-up.md:27]` |
| `.opencode/**` is an `edit` deny | `[VERIFIED: opencode.json:24]` |
| `.opencode/skills/` is **not** in the configured skill root | `[VERIFIED: opencode.json:453-457]` |

**Consequence:** as written, the wrap-up step targets a path agents may not write and
which the skill loader does not scan. Consumers find it only by explicit glob
(`[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:37]`). This is a
pre-existing inconsistency, not caused by this design.

### 1.6 Approval and headless constraint

| Fact | Evidence |
|---|---|
| `question` permission is `allow` | `[VERIFIED: opencode.json:16]` |
| A contract flagged `headless: true` — and every background/supervised task — **must not issue interactive asks** (permission prompts, clarifying questions, human gates); it must emit `BLOCKED` with the decision | `[VERIFIED: framework/opencode/rules/delegation-protocol.md:137-141]` |
| Background tasks use a pub/sub contract; the parent collects after the completion reminder, never polls | `[VERIFIED: framework/opencode/rules/background-tasks.md:3-24]` |
| Subagents spawned via `task()` cannot call `background_output` themselves | `[VERIFIED: framework/opencode/rules/background-tasks.md:39-42]` |

### 1.7 External skills and target directories

| Fact | Evidence |
|---|---|
| No `design/` directory exists in the repo | `[VERIFIED: glob design/** → no files found]` |
| `.planning/` EXISTS (verification/, telemetry/, USER-ASK.md) and is git-ignored | `[VERIFIED: .planning/verification/review_state.json, .planning/USER-ASK.md]`, `[VERIFIED: .gitignore:105-106]` |
| `.opencode/` EXISTS (settings.json, opencode.json, plugins/, gsd-file-manifest.json, ...) and is plane-locked | `[VERIFIED: listing .opencode → settings.json, plugins/, gsd-file-manifest.json, ...]`, `[VERIFIED: opencode.json:24]` |
| `.claude/` does NOT exist; `.opencode/agents/` does NOT exist | `[VERIFIED: glob .claude → path does not exist; Test-Path .opencode/agents → False]` |
| No agent named `ui-designer`/`designer` exists (closest: `gsd-ui-researcher`, `gsd-ui-checker`, `gsd-ui-auditor`) | `[VERIFIED: glob framework/opencode/agents/*.md → 40 files, none designer]` |
| `.planning/` is git-ignored | `[VERIFIED: .gitignore:105-106]` |
| A `docs/` reference root exists and is documented in config | `[VERIFIED: opencode.json:447-452]` |

---

## 2. Unknowns (decisions required — no assumption taken)

| # | Unknown | Why it matters | How to resolve |
|---|---|---|---|
| U1 | Which external design skills, if any, the user wants imported (emilkowalski `prototype`/`emil-design-eng`/`break-ui`, others) | They are absent from the repo; nothing can be built on them until chosen and imported | User selects the set |
| U2 | Where imported skills should live (`design/skills/`, `.claude/skills/`, or a new configured root) | Determines discoverability. Native `skill` loading requires the root in `opencode.json` `skills.paths` (plane, human). Reading via `read` works from any repo path | User picks a location |
| U3 | Whether a dedicated agent is wanted at all, versus using `gsd-sketch` directly | Rule Zero: `gsd-sketch` already emits 2–3 variants | User decision (section 4) |
| U4 | Whether OpenCode natively loads skills from `.claude/skills/` | Not verified in this repo; `skills.paths` names only one root | Would need empirical check or an explicit config root |
| U5 | Whether the wrap-up path defect (1.5) should be fixed now | It is plane-locked; a human edit is required | User decision (section 8, step H3) |

---

## 3. Gap analysis

What exists vs. what the goal needs:

| Need | Status | Gap |
|---|---|---|
| Produce 2–3 mockup variants | **Exists** — `gsd-sketch` | none |
| Save variants to a writable location | **Exists** — `.planning/sketches/` | none |
| Persist design decisions as a reusable skill | **Broken path** — writes to denied `.opencode/skills/` | D1 |
| Load external design skills | **Absent** — no import, no root | D2 |
| A persona restricted to design-only work (cannot ship code) | **Absent** | D3 |
| Foreground human approval of a chosen variant | **Available** — `question` allow | none (must stay foreground) |
| Feed the approved decision into UI-SPEC | **Exists** — `required_reading` + `SKETCH_FINDINGS_PATH` | D1 blocks the feed path |

---

## 4. Options

### Option A — No new agent; use `gsd-sketch`

- Run `gsd-sketch` (foreground) to generate 2–3 variants, wrap up, and hand off.
- **Pros:** zero new plane artifacts; satisfies Rule Zero; uses tested workflows.
- **Cons:** no context/write isolation — the sketching session runs with the invoker's
  permissions; does not, by itself, use external design skills.

### Option B — New human-authored `ui-designer` subagent (recommended if isolation is wanted)

- A thin agent whose job is to (a) load a configured set of design skills by explicit
  `read`, (b) drive the existing `gsd-sketch` workflow to produce 2–3 variants, (c) obtain
  human approval via `question()` in the foreground, (d) write a decision sheet under
  `.planning/`, and (e) hand off to `gsd-ui-researcher`.
- **Pros:** hard write-scope (design artifacts only); explicit skill loading; a named owner
  for the design step; still reuses `gsd-sketch` rather than duplicating it.
- **Cons:** requires a **human** to create the agent file (plane-locked); adds one agent to
  maintain.

### Recommendation

**Option B, only if the user wants isolation and an explicit skill-loading contract.**
Otherwise Option A. Either way, `design/skills/` import (U1/U2) and the wrap-up path fix
(1.5) are independent, human-owned actions.

---

## 5. Recommended design (Option B)

### 5.1 Component: the `ui-designer` agent (human-authored)

Location: `framework/opencode/agents/ui-designer.md` — **plane-locked; a human must write it.**
An agent cannot create it `[VERIFIED: opencode.json:28]`.

Required behaviours in the contract:

1. **Foreground only.** `question()` is permitted only because it runs in the foreground
   `[VERIFIED: opencode.json:16]`. The delegation contract must **not** set `headless: true`;
   if ever run in the background, it must emit `BLOCKED` naming the decision instead of
   asking `[VERIFIED: framework/opencode/rules/delegation-protocol.md:137-141]`.
2. **Load skills by explicit `read`.** `read` is allowed globally `[VERIFIED: opencode.json:10]`;
   the agent reads each design skill's `SKILL.md` from the chosen root (U2). Native `skill`
   loading additionally requires the root in `opencode.json` `skills.paths`
   `[VERIFIED: opencode.json:453-457]` — a plane edit (human).
3. **Treat skill content as untrusted.** Third-party instructions are advisory; repo rules
   win. Follow `untrusted-input-boundary.md`
   `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:23]`.
4. **Write only under `.planning/`.** `.planning/` is git-ignored `[VERIFIED: .gitignore:105-106]`
   and outside every plane path `[VERIFIED: opencode.json:22-32]`.
5. **Reuse `gsd-sketch`** for variant generation rather than reimplementing it.

### 5.2 Artifacts and paths (all writable)

```
.planning/sketches/                      # variant HTML + MANIFEST  (gsd-sketch layout)
  <nnn>-<name>/variant-*.html
  MANIFEST.md
.planning/design/<phase>/DECISION-SHEET.md   # the approval record (new, under .planning)
```

- `.planning/sketches/` is the existing layout `[VERIFIED: framework/opencode/gsd-core/workflows/sketch.md:88]`.
- The decision sheet is new but lives under the git-ignored `.planning/` tree
  `[VERIFIED: .gitignore:105-106]`, so it never lands in the plane and is never committed.

### 5.3 Approval flow (foreground)

1. `ui-designer` generates 2–3 variants under `.planning/sketches/`.
2. It presents the variants and asks the human to choose via `question()`
   (allowed in foreground `[VERIFIED: opencode.json:16]`).
3. It writes the chosen direction to `.planning/design/<phase>/DECISION-SHEET.md`.
4. If the task is headless/background, it **does not ask**; it emits `BLOCKED` with the
   decision `[VERIFIED: framework/opencode/rules/delegation-protocol.md:137-141]`.

### 5.4 Handoff to `gsd-ui-researcher`

- The researcher reads every file in `<required_reading>` first
  `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:12-13]` and pre-populates fields
  answered by upstream artifacts `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:212-217]`.
- The ui-phase orchestrator already carries a `{SKETCH_FINDINGS_PATH}` slot that is omitted
  when null `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:135-142,158]`.
- **Recommended wiring:** add the decision sheet path to the orchestrator's
  `<required_reading>`. Because `SKETCH_FINDINGS_PATH` is resolved by globbing
  `./.opencode/skills/sketch-findings-*/SKILL.md` `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:37]`,
  either (a) fix the wrap-up path (see 5.5) so the glob target is writable and correct, or
  (b) add the decision sheet as a separate explicit path. The orchestrator files are
  plane-locked; this is a human edit.

### 5.5 Wrap-up path fix (addresses D1)

The wrap-up workflow writes to `./.opencode/skills/...` `[VERIFIED: framework/opencode/gsd-core/workflows/sketch-wrap-up.md:1-4,27]`,
which is `edit`-denied `[VERIFIED: opencode.json:24]` and not a configured skill root
`[VERIFIED: opencode.json:453-457]`. Two acceptable fixes (both human edits, plane-locked):

- **Fix A:** change the wrap-up target to a writable path under `.planning/` and update the
  `SKETCH_FINDINGS_PATH` glob accordingly.
- **Fix B:** add `.opencode/skills` (or the chosen root) to `opencode.json` `skills.paths`
  and lift the `.opencode/**` deny for that subtree — a larger plane change; not recommended.

Fix A is smaller and keeps generated content out of the plane.

---

## 6. Permissions mapping

| Action | Who can do it | Evidence |
|---|---|---|
| Create `framework/opencode/agents/ui-designer.md` | **Human only** (deny) | `[VERIFIED: opencode.json:28]` |
| Edit `framework/opencode/gsd-core/workflows/*` (handoff wiring, wrap-up fix) | **Human only** (deny) | `[VERIFIED: opencode.json:28]` |
| Edit `opencode.json` (`skills.paths`) | **Human only** (deny) | `[VERIFIED: opencode.json:25]` |
| Import skills into `design/skills/` | Primary session: `ask`; configured subagents: per allowlist | `[VERIFIED: opencode.json:22]` |
| Agent reads skill `SKILL.md` from any repo path | Allowed | `[VERIFIED: opencode.json:10]` |
| Agent writes under `.planning/` | Allowed (outside plane) | `[VERIFIED: opencode.json:22-32]` |
| Agent asks the human (`question`) | Foreground only | `[VERIFIED: opencode.json:16]`, `[VERIFIED: framework/opencode/rules/delegation-protocol.md:137-141]` |
| Agent `webfetch` external design content | **Denied** globally | `[VERIFIED: opencode.json:33]` |

Note: importing skills requires obtaining them by a means other than `webfetch` (which is
`deny`) — e.g. a human clones them outside the repo and places files in, or the user copies
them in.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Prompt injection from imported third-party skills | Treat skill text as untrusted; repo rules win; follow `untrusted-input-boundary.md` `[VERIFIED: framework/opencode/agents/gsd-ui-researcher.md:23]` |
| Wrap-up silently fails on a denied path | Fix the path (5.5) before relying on the feed |
| Headless run issues an interactive ask | Contract forbids `headless: true`; emit `BLOCKED` instead `[VERIFIED: framework/opencode/rules/delegation-protocol.md:137-141]` |
| New agent duplicates `gsd-sketch` | Agent delegates to `gsd-sketch`; only adds skill-loading + isolation |
| Reviewer/QA expectation mismatch on "designer" scope | Agent contract states single responsibility: design artifacts only |

---

## 8. Minimal implementation steps

**Human-owned (plane-locked, cannot be done by an agent):**
- **H1.** Author `framework/opencode/agents/ui-designer.md` (section 5.1).
- **H2.** (If external skills wanted) import chosen skills into the chosen root (U2) with
  their license/attribution.
- **H3.** Fix the wrap-up target path and/or `SKETCH_FINDINGS_PATH` glob (5.5).
- **H4.** (Optional) add the design-skill root to `opencode.json` `skills.paths` for native
  loading `[VERIFIED: opencode.json:453-457]`.
- **H5.** Wire the decision sheet into the ui-phase `<required_reading>`
  `[VERIFIED: framework/opencode/gsd-core/workflows/ui-phase.md:135-142]`.

**Agent-doable (after H1–H3):**
- **A1.** Import/copy skill files into the non-plane root if H2 is delegated with the files
  already present in the workspace.
- **A2.** Run the foreground flow end-to-end: brief → 2–3 variants → `question()` approval →
  `DECISION-SHEET.md` → researcher pre-fill.

---

## 9. Decision summary (what I need from you)

1. **U3** — Do you want a dedicated `ui-designer` agent (Option B), or is using `gsd-sketch`
   directly sufficient (Option A)?
2. **U1/U2** — Which external design skills, and where should they live?
3. **U5/H3** — Fix the wrap-up path defect now?

Until U1–U3 are answered, no file is created and no external skill is assumed.

---

## 10. Addendum — decisions taken and corrections from deeper verification

### 10.1 Decisions (from the human)

- **D-a:** Add a dedicated `ui-designer` agent (Option B).
- **D-b:** Import **all relevant** design skills (not a hand-picked three).
- **D-c:** Fix the wrap-up path defect now.

### 10.2 Corrections (supersede earlier text where they differ)

1. **`.planning/` and `.opencode/` DO exist** — dot-path globs hid them (glob default
   `hidden:false`). `.planning/` holds runtime state and is git-ignored
   `[VERIFIED: .gitignore:105-106]`; `.opencode/` holds the GSD installer bookkeeping +
   MCP config and is plane-locked `[VERIFIED: opencode.json:24]`. Earlier statements that
   neither exists were wrong.
2. **The spawnable subagent set is the root `opencode.json` `agent` block.**
   `ui-designer` is absent, so it is not spawnable today
   `[VERIFIED: opencode.json:72-419; only 8 agent keys: security-auditor, team-lead,
   researcher, architect, planner, implementer, reviewer, verifier]`. `gsd-*` markdown
   files are NOT registered subagents (they are read by workflows as instructions, e.g.
   `[VERIFIED: framework/opencode/gsd-core/workflows/ai-integration-phase.md:108]`).
3. **Agent instruction files live at `framework/opencode/agents/<name>.md`** with
   frontmatter `description` + `mode` `[VERIFIED: framework/opencode/agents/implementer.md:1-4]`.
4. **The GSD plugin registers `agents/*.md` into `config.agent` keyed by filename**
   `[VERIFIED: .opencode/plugins/gsd-core.js:475-488]`, but only when `IS_PACKAGE_TREE`
   (`commands/gsd` present) `[VERIFIED: .opencode/plugins/gsd-core.js:93-97,458-459]`, which
   is not the case in this repo.
5. **The wrap-up defect is broader than sketched:** 25 occurrences across 9 workflow files,
   covering BOTH `sketch-findings` and `spike-findings`
   (see `docs/designer-agent/WRAP-UP-PATH-FIX.md`). The `update_claude_md` step also writes
   the plane-locked `AGENTS.md` `[VERIFIED: sketch-wrap-up.md:220-230]`, and the "auto-load"
   claim `[VERIFIED: sketch-wrap-up.md:252]` was already false (`.opencode/skills` was never
   in `skills.paths` `[VERIFIED: opencode.json:453-457]`).

### 10.3 What was done in this run (agent-doable)

- Imported **all 15** design skills into `design/skills/` (outside the plane) with
  `LICENSE` + `ATTRIBUTION.md` + `README.md`, via a new reusable importer
  `framework/tools/import_design_skills.py` (an earlier run imported 13 and excluded
  `write-swift` and `animate-expo`; see 10.6 for why that exclusion was wrong).
- Generated the single apply-able patch `docs/designer-agent/ui-designer.patch` with
  `framework/tools/emit_designer_agent_patch.py` (11 paths, 26 hunks:
  the new agent file, the `opencode.json` entry, the 25 path-fix sites, and the
  `AGENTS.md`-write / auto-load prose corrections). `git apply --check` exits 0.
- Staged the two plane-locked artifacts for the human:
  - `docs/designer-agent/ui-designer.md` → copy to `framework/opencode/agents/ui-designer.md`
  - `docs/designer-agent/AGENT-REGISTRATION.md` → the `opencode.json` `agent` entry + steps
  - `docs/designer-agent/WRAP-UP-PATH-FIX.md` → the exact 25-site fix

### 10.4 U6 — RESOLVED by execution (spawn + approval gate both verified)

The wire-up question was answered by running it, not by re-reading config. Both probes ran
against the applied patch, in foreground:

| Probe | Result | Session |
|---|---|---|
| Spawn `ui-designer`, have it read its own definition + charter, report five charter facts | Spawned; returned the pointer line verbatim (`` Read `.lifecycle/agents/ui-designer.md` and act only within that charter. ``), the three mandatory outputs with paths, the precedence order `AGENTS.md > agent definition > charter > skill content`, the unverifiable-not-passing rule, and the headless `BLOCKED` rule | `ses_eae078ec9ffe2EkmBpAY1niNAF` |
| Exercise the role's only gate with one `question()` call | `question` succeeded and reached the human (answered "Gate works"); no refusal, no error | `ses_eae069114ffeQvusGt3MqxKZnS` |
| `python framework/validate.py --profile framework` | `VALIDATION PASSED [profile=framework; 0 fail, 0 warn, 5 not-applicable]` — `[1]` agent set, `[2]` delegation topology, `[20]` model/temperature/rationale, `[30]` charter single-source all green | — |
| `python framework/security/check_enforcement_plane.py` | `OK: enforcement plane consistent (8 paths)`, exit 0 — re-run **after** the model-field patch touched `opencode.json` | — |

Consequence: spawnability comes from the root `opencode.json` `agent` block, and the prompt is
delivered by `framework/opencode/agents/ui-designer.md`. Whether the GSD plugin *also*
auto-loads that file is now immaterial — prompt delivery is demonstrated, not inferred.

What this does **not** prove: a real design brief end to end (mockups rendered, screenshot +
console evidence captured, decision sheet written). No such run has been performed; the two
probes deliberately stopped before design work.

### 10.5 Status

- Design: complete and fact-corrected.
- Skill import: **done** (all 15).
- Agent file + config entry + wrap-up fix: **applied** as `docs/designer-agent/ui-designer.patch`.
- Model/temperature/rationale completion: **applied** as `docs/designer-agent/ui-designer-model.patch`
  (F1 in `framework/validate.py` landed directly — not plane-locked).
- Routing/dispatch wiring: **staged as `docs/designer-agent/ui-designer-routing.patch`**,
  `git apply --check` exit 0 — plane-locked → human (see §10.7).
- Static verification: **green** (`--profile framework` 0 fail; plane checker exit 0).
- End-to-end usability: spawn and approval gate **verified** (§10.4); a full design run is
  still unperformed.

### 10.6 Correction — the repo is not web-only (Flutter mobile app exists)

The earlier exclusion of `write-swift` and `animate-expo` was justified with "this web
(React/Tailwind/shadcn) repo". That justification was an **unverified assumption**, and it
was wrong. The repo has two client surfaces:

| Surface | Evidence |
|---|---|
| `web/` — Next.js 15 / React 19 / Tailwind 3 / Radix (shadcn) / `motion` ^13 / recharts | `[VERIFIED: web/package.json:27-100]` |
| `mobile/` — a **Flutter / Dart** app (`stockerpro`): `flutter_riverpod`, `go_router`, `fl_chart`, `shimmer`, and a glass design system | `[VERIFIED: mobile/pubspec.yaml:1-35; mobile/lib/shared/widgets/glass_card.dart exists]` |

There is still **no React Native / Expo code and no Swift code** in the repo:

- `git ls-files mobile` lists only `.dart`, `.yaml`, `.sh`, and `web/` assets — no `ios/`,
  `android/`, `*.swift`, or `package.json`.
- No `**/*.swift` and no `mobile/**/package.json` match anywhere in the tree.

So the honest applicability statement is:

| Skill | Applies to this repo? | Why |
|---|---|---|
| `mobile-native` | **to `web/` only** | It is a web-app-on-a-phone skill (CSS/meta-tag fixes) `[VERIFIED: design/skills/mobile-native/SKILL.md:3,16]`; it does not cover Flutter |
| `apple-design` | conceptually yes, code no | Its code is web-platform (CSS, Pointer Events, rAF, Motion) `[VERIFIED: design/skills/apple-design/SKILL.md:16]`; the craft transfers, the snippets do not |
| `animate-expo` | **no** | Explicitly React Native / Expo + Reanimated `[VERIFIED: design/skills/animate-expo/SKILL.md:3,21]` |
| `write-swift` | **no** | Swift 6.x `[VERIFIED: design/skills/write-swift/SKILL.md:3,18]` |

They are imported anyway (per the human's decision, and the importer is all-or-nothing), and
the agent prompt treats the corpus as advisory, so an inapplicable skill costs nothing but is
never silently "applied".

**New open item — U7: there is no Flutter design skill in the corpus.** The mobile surface is
Flutter, and every mobile-ish skill in the corpus targets React Native or the web platform.
If Flutter UI design is in scope, a Flutter/Cupertino or Material design skill must be
sourced or written. Not assumed; not started.

### 10.7 Verified defect — the agent was registered but nothing routed to it

Running the thing (rather than reading it) surfaced a third gap after F1/F2:

**Nothing in the framework dispatches `ui-designer`.**

- The routing matrix is the mandatory dispatch table — *"Every delegation must consult this
  matrix before selecting skills"* `[VERIFIED: framework/opencode/skill-routing.md:4]` — and
  its only UI row sends UI work to the Implementer:
  `| UI change | apple-ui + frontend-react | Implementer | ... |`
  `[VERIFIED: framework/opencode/skill-routing.md:21]`.
- `framework/opencode/skill-integration-matrix.md` §1 (role → mandatory skills) has a row for
  every role including `security-auditor` `[VERIFIED: .../skill-integration-matrix.md:16-25]`,
  and §3 binds artifacts to owners and gates `[VERIFIED: ...:49-63]`. No `ui-designer` row.
- No GSD workflow mentions the agent at all (`grep designer framework/opencode/gsd-core/**`
  → no matches), and the two consumers that *do* consume sketch output do so by explicit glob:
  `ui-phase.md:37` and `plan-phase.md:561` `[VERIFIED: ...]`.

So the delivered feature was inert: spawnable, validated, and undispatchable. A delegator
following the contract would have selected the Implementer every time.

**Fix — staged as `docs/designer-agent/ui-designer-routing.patch`** (3 files, 4 hunks,
7 inserted lines, 0 removals; `git apply --check --verbose` exit 0). All three targets are
under `framework/opencode/**` (edit-deny), so it goes to the human like the others:

| # | File | Insertion |
|---|---|---|
| A | `skill-routing.md` | routing row: design direction undecided → `gsd-sketch` + `frontend-react` + `apple-ui` → **ui-designer** (added *above* the Implementer row, which stays — implementation is its job) |
| B | `skill-integration-matrix.md` §1 | `ui-designer` role → mandatory skills row |
| C | `skill-integration-matrix.md` §3 | artifact row: sketch deliverables → produced by ui-designer → consumed by team-lead, planner, implementer → gate `none (human approval only; not a gate outcome)` |
| D | `gsd-sketch/SKILL.md` | executor note: run in-session **or** delegated to `ui-designer`, which drives this same workflow and stops at the approval gate |

**Honest limit on this fix.** No gate parses either table — `grep skill-routing\|skill-integration
framework/**/*.{py,sh}` returns only source comments, and `[29]` router-table conformance
covers `gsd-ns-workflow`, not these. Routing is therefore an *instruction-level* contract:
the row is necessary for the delegator to find the agent, but nothing executable asserts
that dispatch happened. The self-check that does run is the emitter's own (anchor
uniqueness, pure-insertion invariant, per-table pipe counts, hunk re-application fidelity).

**Verification after applying:**

```bash
python framework/validate.py --profile framework    # 0 fail
python framework/security/check_enforcement_plane.py # exit 0
git status --short                                    # shows the 3 routed files
```
