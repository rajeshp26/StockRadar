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
| U2 | Where imported skills should live (`framework/design/skills/`, `.claude/skills/`, or a new configured root) | Determines discoverability. Native `skill` loading requires the root in `opencode.json` `skills.paths` (plane, human). Reading via `read` works from any repo path | User picks a location |
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
Otherwise Option A. Either way, `framework/design/skills/` import (U1/U2) and the wrap-up path fix
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
| Import skills into `framework/design/skills/` | Primary session: `ask`; configured subagents: per allowlist | `[VERIFIED: opencode.json:22]` |
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
   (see `framework/docs/designer-agent/WRAP-UP-PATH-FIX.md`). The `update_claude_md` step also writes
   the plane-locked `AGENTS.md` `[VERIFIED: sketch-wrap-up.md:220-230]`, and the "auto-load"
   claim `[VERIFIED: sketch-wrap-up.md:252]` was already false (`.opencode/skills` was never
   in `skills.paths` `[VERIFIED: opencode.json:453-457]`).

### 10.3 What was done in this run (agent-doable)

- Imported **all 15** design skills into `framework/design/skills/` (outside the plane) with
  `LICENSE` + `ATTRIBUTION.md` + `README.md`, via a new reusable importer
  `framework/tools/import_design_skills.py` (an earlier run imported 13 and excluded
  `write-swift` and `animate-expo`; see 10.6 for why that exclusion was wrong).
- Generated the single apply-able patch `framework/docs/designer-agent/ui-designer.patch` with
  `framework/tools/emit_designer_agent_patch.py` (11 paths, 26 hunks:
  the new agent file, the `opencode.json` entry, the 25 path-fix sites, and the
  `AGENTS.md`-write / auto-load prose corrections). `git apply --check` exits 0.
- Staged the two plane-locked artifacts for the human:
  - `framework/docs/designer-agent/ui-designer.md` → copy to `framework/opencode/agents/ui-designer.md`
  - `framework/docs/designer-agent/AGENT-REGISTRATION.md` → the `opencode.json` `agent` entry + steps
  - `framework/docs/designer-agent/WRAP-UP-PATH-FIX.md` → the exact 25-site fix

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
- Agent file + config entry + wrap-up fix: **applied** as `framework/docs/designer-agent/ui-designer.patch`.
- Model/temperature/rationale completion: **applied** as `framework/docs/designer-agent/ui-designer-model.patch`
  (F1 in `framework/validate.py` landed directly — not plane-locked).
- Routing/dispatch wiring: **staged as `framework/docs/designer-agent/ui-designer-routing.patch`**,
  `git apply --check` exit 0 — plane-locked → human (see §10.7).
- Skill-library integration (`designmotion-design` + the 17-skill advisory corpus): **applied**
  as `framework/docs/designer-agent/design-skills-integration.patch`, post-apply `--profile framework`
  0 fail (see §10.8).
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
| `mobile-native` | **to `web/` only** | It is a web-app-on-a-phone skill (CSS/meta-tag fixes) `[VERIFIED: framework/design/skills/mobile-native/SKILL.md:3,16]`; it does not cover Flutter |
| `apple-design` | conceptually yes, code no | Its code is web-platform (CSS, Pointer Events, rAF, Motion) `[VERIFIED: framework/design/skills/apple-design/SKILL.md:16]`; the craft transfers, the snippets do not |
| `animate-expo` | **no** | Explicitly React Native / Expo + Reanimated `[VERIFIED: framework/design/skills/animate-expo/SKILL.md:3,21]` |
| `write-swift` | **no** | Swift 6.x `[VERIFIED: framework/design/skills/write-swift/SKILL.md:3,18]` |

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

**Fix — staged as `framework/docs/designer-agent/ui-designer-routing.patch`** (3 files, 4 hunks,
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

### 10.8 Design-skills integration — `designmotion-design` + the 17-skill corpus

Four defects, one integration. They were all "the file is on disk, so it must be wired":

1. `designmotion-design` sat under `framework/opencode/skills/` but was **untracked and routed
   nowhere** — spawnable content, no dispatch path.
2. `apple-ui` and `frontend-react` never pointed at it, and its own `SKILL.md` still pointed at
   skills that do not exist here (`settigation-code`, `practical-ui`) plus `muse.*` connector
   tools and `/opt/muse/...` paths from its upstream extraction. A pointer to a nonexistent
   skill is worse than no pointer: the reader stops looking.
3. The imported craft corpus in `framework/design/skills/` (17 skills) was **not in `skills.paths`**, so it
   was unreachable by name even though the importer had written it.
4. `framework/opencode/skills/ROUTES.md` was not a router. It was 113 lines of literal
   `diff --git` output pasted into a markdown file instead of applied — its own first body line
   is `-diff --git a/framework/opencode/skills/ROUTES.md b/framework/opencode/skills/ROUTES.md`
   `[VERIFIED: framework/docs/designer-agent/design-skills-integration.patch:86-95]` — and it duplicated
   `skill-routing.md`, the authoritative table.

**Decisions taken (with the trade-off that drove each).**

| Decision | Why, and what it costs |
|---|---|
| Extend the two existing routers; do not add a third | `skill-routing.md` is the table the delegation rule names. A second table splits the single source. Cost: the UI region of that table is now four rows instead of two |
| Mandatory UI loading stays limited to `apple-ui`, `frontend-react`, `designmotion-design` | Three mandatory skills is the most a UI task can hold and still be read. `designmotion-design` is mandatory only when the surface introduces or changes a pattern/system, not on every CSS tweak |
| All 17 corpus skills **discoverable, none mandatory** | Discoverability is a `skills.paths` entry; mandate is a routing row. Keeping the corpus advisory preserves the recorded eval verdict (corpus is reference, not rule) and avoids a 20-skill mandatory load |
| `apple-ui` wins finance tokens/motion/data-viz; `designmotion-design` wins behaviour where `apple-ui` is silent; a direct conflict resolves to `apple-ui` and the plan records it | Precedence has to resolve *conflicts*, not suppress *loading*. Silence is the only place a second voice is useful |
| Delete `ROUTES.md` and `designmotion-design/skill.yaml` | `ROUTES.md` duplicated the router and was corrupted. `skill.yaml` declared `include_in_prompt: false` — upstream muse metadata that contradicted the skill being first-class here |

**Deliverable — `framework/docs/designer-agent/design-skills-integration.patch`** (plane-locked; emitted by
script, applied by the human — never by an agent):

| # | File | Change |
|---|---|---|
| A | `opencode.json` | `skills.paths` += `framework/design/skills` (2 inserted, 1 removed line) |
| B | `skill-routing.md` | `designmotion-design` row, advisory-corpus row, "UI design precedence" section, Implementer checkbox |
| C | `skill-integration-matrix.md` | implementer + ui-designer role bindings, dependency-route line, §6 routing-resolution bullet |
| D | `skills/apple-ui/SKILL.md` | pairing paragraph (behaviour layer + precedence pointer) |
| E | `skills/frontend-react/SKILL.md` | behaviour-layer pointer, corpus-is-advisory note |
| F | `skills/designmotion-design/SKILL.md` | repo-real pointers: no `settigation-code`, no `practical-ui`, no `muse.*`, no `/opt/muse` |
| G | `skills/designmotion-design/skill.yaml` | **deleted** (muse metadata, `include_in_prompt: false`) |
| H | `skills/ROUTES.md` | **deleted** (corrupted diff, duplicate router) |

`git apply --check --verbose` exit 0 across 8/8 files; `git apply --stat` → 8 files changed,
57 insertions, 127 deletions. The 127 deletions are the two whole-file removals, not churn.

Two non-plane files changed alongside it, because they state the rule the patch depends on:
`framework/tools/import_design_skills.py` (the importer's notice now says *discoverable but
advisory*, and warns that upstream skill names may be phantom here) and `framework/design/skills/README.md`
(regenerated from that notice).

The emitter is one-shot by construction: it rewrites *current* content, so once the patch is
applied its anchors no longer match and it stops with `anchor occurs 0 times, expected exactly 1`
(or `target does not exist`, for the two deleted files) instead of silently re-emitting a patch
against an already-changed tree.

**New executable check — this is the part §10.7 lacked.** `framework/validate.py` now derives
its skill roots from `opencode.json` instead of hardcoding one path, and asserts: every
configured path exists; every configured path is populated; each `SKILL.md` parses and its
`name:` equals its directory; no name is declared by two configured roots; and every skill named
in the `Required Skill` column of `skill-routing.md` resolves on a configured path
`[VERIFIED: framework/validate.py:715-768]`. Resolution is now a gate verdict, not a reading.

**Pre-apply proof of the post-image.** The workspace cannot be validated against a patch it has
not applied, so the emitter asserts the target state itself: it reads the *post-image*
`opencode.json` and *post-image* `skill-routing.md`, then re-runs the same checks
`[VERIFIED: framework/tools/emit_design_skills_integration_patch.py:199-263]`, called before the
patch is written `[VERIFIED: framework/tools/emit_design_skills_integration_patch.py:419]`:

```
target check: 108 skills across 2 roots; 23 routed, all resolve
files: 8, hunks: 13, removed: 127, added: 57, self-check: OK
```

The check carries teeth: a fixture row naming `not-a-real-skill` must be reported, otherwise the
routing assertion would only ever be green because it parsed nothing. Writing this exposed a
real defect in the emitter — `git diff` prints a file that exists only on the source side with
the *same* path token twice, so both deletion headers carried a stray `OLD/` token. `git apply`
tolerated it; `patch -p1` and a human reader would not. The emitter now rebuilds every header as
`a/<path> b/<path>` and refuses any header whose two sides disagree.

**Residual limit, stated plainly.** The new check proves a routed skill *exists and parses*. It
does not prove the router *selects* it at runtime — resolution is not dispatch. §10.7's gap is
therefore narrowed (the table is now checked, not just written) but not closed: nothing asserts
that a UI task actually loaded `designmotion-design`.

**Observed after applying (this session).** The patch was applied by the human and the gate
re-ran on the real tree:

- `python framework/validate.py --profile framework` → `VALIDATION PASSED [profile=framework;
  0 fail, 0 warn, 5 not-applicable]`, now including `PASS  skills path is populated
  (framework/design/skills)`, frontmatter and name/directory checks for all 17 corpus skills, and
  `PASS  every skill routed in skill-routing.md resolves on a configured path`. The two checks
  that were vacuous pre-apply are now real.
- Runtime discovery moved from inferred to observed: the harness surfaced 14 of the 17 corpus
  skills as available. The other three — `pick-ui-library`, `prototype`, `review-animations` —
  are **not** a discovery failure: each declares `disable-model-invocation: true` in its own
  frontmatter, i.e. explicit-invocation-only by upstream design. 17 on disk, 14 auto-surfaced,
  3 opt-in, 0 missing.
- `git add -A framework/opencode/skills` warned that `karpathy-guidelines/SKILL.md` will have
  CRLF replaced by LF. That file is not part of this change; the warning is `core.autocrlf`
  normalisation on re-add and leaves its content identical.
- `git apply --check --reverse` on the same patch exits 0, which proves the tree now in place is
  byte-identical to the post-image that was emitted — no drift between what was reviewed and
  what landed. `python framework/security/check_enforcement_plane.py` still reports
  `OK: enforcement plane consistent (8 paths)` after `opencode.json` changed.

So: discovery at the OpenCode layer is **verified**, and selection by the router is still
instruction-level. The remaining gap is narrower than §10.7's, and it is stated rather than
assumed.

**Verification after applying:**

```bash
git apply framework/docs/designer-agent/design-skills-integration.patch
git add -A framework/opencode/skills     # designmotion-design/ is untracked: its edited
                                         # SKILL.md and deleted skill.yaml need staging
python framework/validate.py --profile framework      # adds: skills path is populated (framework/design/skills)
                                                      # + frontmatter and name/directory checks for
                                                      #   all 17 corpus skills
python framework/security/check_enforcement_plane.py  # exit 0
git status --short                                    # 6 modified, 2 deleted, 1 new directory
```

Pre-apply, those checks do not run at all: `framework/design/skills` is not a configured root until the
patch lands, so the pre-apply run is green *without* them. That is why the emitter's
`verify_target` exists rather than a promise to check later.

### 10.9 Selection is now enforced, not promised

10.8 closed the discovery half: the corpus resolves, and every routed skill is checked for
existence. It left the selection half as instruction. The concrete failure that survived was
this shape:

> `apple-ui` resolves, so `validate.py` is green. A plan touches
> `web/src/features/portfolio/components/DividendsTab.tsx`, names `frontend-react` and
> `unit-test-authoring`, and omits `apple-ui`. `skill-routing.md:24` says the pair is
> unconditional. Dispatch proceeds, the implementer never loads the design system, and every
> gate that ran was telling the truth about something else.

Three things were added, all of them exit codes.

**1. `framework/tools/skill_coverage.py` + `framework/gates/g_skill_coverage.sh`.** The
plan is the last artifact before work starts, so it is where selection is forced. Two
independent sources are read:

| Source | Rules | What it proves |
|---|---|---|
| declared file scope | SC02, SC03 | a plan touching UI paths names `apple-ui` + `frontend-react`; a new UI surface also names `designmotion-design` |
| the ask's Capability Matrix | CM01-CM05 | every dimension the matrix declares has a verdict, and every `yes` appears in a task's `required_skills` |

The Capability Matrix instance is a `CAPABILITY-MATRIX.yaml` next to the plan
(`scope: task | phase`). The *dimension list* is not duplicated in code: it is parsed from the
Capability Matrix table in `team-lead.md`, so adding a row to the doc changes what the check
demands. A matrix that exists can no longer say `yes` while the plan requires nothing.

`g_entry.sh` composes the gate, so the check is on the dispatch path, and it shares
`framework/plan/lint_mode` with the DID-016 plan lint - one switch, one meaning.

**2. `G-T1` no longer reads "no artifact" as clean.** It derives the required depth from the
plan (`framework/tools/evidence_level.py`): L2+ or any `integration` / `e2e` / `browser` /
`data-invariant` criterion makes a missing artifact a FAIL (1); an L0/L1 plan whose criteria
are unit/static/manual makes it NOT_APPLICABLE (4); no plan context is NOT_APPLICABLE with
`plan_context: absent` recorded, because the gate refuses to invent a depth. The env var is
never the source - an agent can set one, and the plan is the artifact under review.

**3. A latent crash fixed in passing.** `g_tool_utilization.sh` built its gap message with an
f-string containing single quotes (`f'... {', '.join(gaps)}'`), which is a syntax error before
Python 3.12. The gate would have crashed exactly when it had something to report - a failure
mode that hides failures. Replaced with concatenation.

**4. `G-SKILL-USE` closes the invocation gap — but with the sensor that already exists.**
`framework/tools/skill_use.py` + `framework/gates/g_skill_use.sh` diff the plan's
`required_skills` against the skills actually recorded as invoked. The important decision here
is what it reads: `framework/opencode/plugin/telemetry.ts` already captures the `skill` tool
call into each session record's `skills_loaded` (line 275) and flushes it on every heartbeat
and final write. A new recorder log would have been a second source of truth for one fact, kept
in agent-writable space - the measured party editing the measurement. So the gate reads
`.planning/telemetry/records.jsonl` and the sensor stays in the plane.

Attribution matters: a skill loaded while working on `T-01` is not evidence for `T-02`, so the
gate filters records by task. With no task it judges every session and records that weaker
claim in its evidence rather than assuming a stronger one.

**What this does not do.** G-SKILL-COVERAGE proves the plan REQUIRED the skill; G-SKILL-USE
proves the call was RECORDED. Neither proves the skill's instructions reached the model's
context, and a recorded call cannot be distinguished from an exploratory one. A PASS reads as
"the call happened", never as "the skill was applied".

**Verified in this run**

```bash
python framework/tools/skill_coverage.py --self-test        # 22/22
python framework/tools/skill_use.py --self-test             # 8/8
bash framework/gates/test_g_skill_use.sh                    # 14/14

# Controlled experiment: these two plans differ by ONE line (`- apple-ui`) and both pass
# plan_lint with 0 errors, so the verdict flip is attributable to required_skills alone.
ENTRY_PLAN=framework/docs/designer-agent/cases/ce-no-design.md   bash framework/gates/g_entry.sh  # exit 1, SC02
ENTRY_PLAN=framework/docs/designer-agent/cases/ce-with-design.md bash framework/gates/g_entry.sh  # exit 0

ENTRY_PLAN=<plan with a matrix missing api-design> bash framework/gates/g_entry.sh # exit 1, CM01
ENTRY_PLAN=<plan, matrix yes browser-verification omitted> bash framework/gates/g_entry.sh # exit 1, CM04
bash framework/gates/g_tool_utilization.sh                     # exit 4, plan_context: absent
ENTRY_PLAN=<L2/browser plan> bash framework/gates/g_tool_utilization.sh # exit 1
ENTRY_PLAN=<L1 unit-only plan> bash framework/gates/g_tool_utilization.sh # exit 4
ENTRY_PLAN=<plan requiring apple-ui + frontend-react> bash framework/gates/g_skill_use.sh
#   exit 1, SU01 (1 recorded call was 'unknown') + SU02 x2 — against the real record store
```

The SC02 comparison is the controlled pair above, committed as
`docs/designer-agent/cases/ce-{no,with}-design.md`. `diff` between them is one added line,
`  - apple-ui`, and both are lint-clean, so nothing but selection explains the flip. The
observed failure is:

```
[skill_coverage] ERROR SC02 required_skills: plan touches UI files
  (web/src/features/portfolio/components/DividendSectorChart.tsx) but does not require
  apple-ui; skill-routing.md:22-24 is unconditional for a UI change
```

The last line is not a hypothetical. The real `.planning/telemetry/records.jsonl` contains one
session with `skills_loaded: ["unknown"]` while `tools.skill.count` is 1 — the skill call
happened and its name was not captured. See 10.10.

### 10.10 What is still instruction-level

Two items from the same review are not closed, and both need a human-applied patch because
they touch the enforcement plane (`framework/opencode/**`, `opencode.json`) - which is the
point of the plane, not an obstacle to route around.

**The skill-load sensor is installed, wired into a gate, and broken (one line).** The recorder
exists: `telemetry.ts:275` reads the `skill` tool call's name into `skills_loaded`. It reads it
from `input?.args?.name`, and in this harness the args are not on `input.args` - the same
defect the file already documents two blocks earlier for the `task` tool
(`telemetry.ts:240-244`: "args were read from input?.args, which is undefined in this
harness - the task tool delivers them under input.input"), which is why `normalizeTaskArgs`
exists and is already imported. The skill line was never converted, so every skill call is
recorded as `"unknown"`.

The evidence is in the store, not in the code reading:

```
records=622 sessions=1 skills=0 unknown_calls=1
tools.skill.count = 1            # the call happened
skills_loaded     = ["unknown"]  # its name was not captured
```

Both facts come from the same session record, so this is a sensor defect and not "the agent
never loaded a skill". The fix is one statement, reading the args the way the rest of the file
already does:

```ts
if (input?.tool === "skill") {
  const a = normalizeTaskArgs(input)
  rec.skills_loaded.add(String(a?.id ?? a?.name ?? "unknown"))
}
```

`id` first because that is the `skill` tool's documented parameter (`{"id": "<skill-id>"}`);
`name` is kept as a fallback so the line is correct under either shape. Until this lands,
`g_skill_use.sh` fails honestly with SU01 + SU02 rather than passing, which is the intended
behaviour for a broken instrument — but it also means the gate cannot go green yet. The fix is
in `framework/docs/designer-agent/remaining-plane-patches.patch`.

**Channel A bounding.** The permissions model supports exactly the boundary the review asked
for - `{action: "skill", resource: "<skill-id>", effect: "deny"}` with per-agent rules under
`agents.<id>.permissions`, and a `deny` both hides the skill from the model and rejects
loading. Two corrections to the original proposal:

- The resource is the **skill ID**, not a path. `framework/design/skills/*` is not a matchable pattern;
  the 17 corpus IDs have no common prefix, so a per-agent deny needs 17 rules or a rename.
- This repo's `opencode.json` is V1-shaped (`permission`, `bash`, `task`), yet the V1 shape is
  demonstrably live on this runtime, not inert: a probe `edit` on
  `framework/opencode/skill-routing.md` was refused with `Permission denied: edit` before any
  content was matched, which is the `permission.edit` deny working. So the file does not need a
  V2 rewrite in order for its rules to take effect. What is still unproven is the per-agent
  key: V1 nests it as `agent.<id>.permission` while V2 documents
  `agents.<id>.permissions`, and nothing in this run exercised either. Settle that one key with
  a throwaway subagent before writing a per-agent deny, or the rule will be silently inert even
  though the top-level denies work.

**Why the three silent corpus skills are silent.** `pick-ui-library`, `prototype` and
`review-animations` set `disable-model-invocation: true` in their frontmatter, which is
documented as equivalent to `metadata.opencode/autoinvoke: false`: the skill stays registered
and loadable by ID but is omitted from the model's available list. Their descriptions say so
in prose ("Only runs when explicitly invoked"). This is intentional in the imported corpus,
not a missing description or a name mismatch - the other 14 surface because they carry a
description and do not opt out. `review-animations` is the one worth revisiting: three other
skills point at it ("for critiquing existing motion use review-animations"), so a user asking
for that review will not be routed to it automatically.

**Capability Matrix row count.** The table in `team-lead.md` has 13 rows, not 14, and it
carries neither `apple-ui` nor `designmotion-design`. The UI skills are therefore enforced
only by the path rule (SC02/SC03), not by the declared matrix. The schema parser reads whatever
the table declares, so the check widens automatically when the rows land -- verified by feeding
the parser the real document plus the two rows (`skill_coverage.py --self-test`, case "a new
doc row becomes a required dimension").

**The matrix key is the skill ID, not the dimension label.** This is the one sharp edge in
`CAPABILITY-MATRIX.yaml`, and it is the intuitive first mistake:

```yaml
dimensions:
  apple-ui: yes            # correct: keys are compared to the schema's skill IDs
  ui-design-system: yes    # wrong: a label. Reports CM01 AND CM03, not a silent pass
```

`parse_schema` extracts the backticked name from column 3 of the table
(`Frontend implementation | yes/no | frontend-react`), and `check_matrix` compares matrix keys
against that list directly. So a label key answers nothing: CM01 fires for the real row it
meant to answer, and CM03 fires for the key no row declares. Loud, not silent -- pinned by the
self-test case "label used as key -> CM01 + CM03" so a future refactor cannot turn it quiet.

All three plane changes above are emitted as one reviewed patch:

```bash
python framework/tools/emit_remaining_plane_patches.py
# framework/docs/designer-agent/remaining-plane-patches.patch   (3 files, 4 hunks)
git apply --check framework/docs/designer-agent/remaining-plane-patches.patch && git apply $_
```

The emitter refuses to write a patch whose hunks do not reproduce the intended post-image, and
it asserts the *effect* rather than the bytes: the patched table parses to 15 dimensions
including both design skills, the patched telemetry block no longer reads `input?.args?.name`,
and `verifier.md` names the gate in both its sequence and its recorded gate map.

Note that `opencode.json` needs no change for any of this. The V1-shaped `permission` block is
live on this runtime -- an `edit` on `framework/opencode/**` is refused with
`permission.rejected` before content is even matched -- so there is no V1/V2 rewrite to make
before rules are written. A rewrite to the V2 `permissions` array is a separate decision.

