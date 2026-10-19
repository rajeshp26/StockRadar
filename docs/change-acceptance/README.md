# Change acceptance: two bindings cherry-picked from the external `10x` skill set

Delivered as **two** patches. Patch 1 added the policy; patch 2 makes it enforceable and
wires it into the one workflow step that asks the question.

| Patch | File | State |
| --- | --- | --- |
| 1 — policy | `docs/change-acceptance/change-acceptance.patch` | **APPLIED 2026-10-19** (validate.py: 0 fail / 0 warn; enforcement plane: 8 paths consistent) |
| 2 — enforcement | `docs/change-acceptance/change-acceptance-enforcement.patch` | **ready, pending** |

## Why this exists

An external skill set (`C:\Users\rajes\Downloads\design`) was assessed for adoption. It was
written for a different product's skill store (`muse`), in a format this repository does not
load (sidecar `skill.yaml`, no `SKILL.md` frontmatter), with two of its three skills missing the
`references/` catalogs they instruct an agent to read.

Most of it restates capability this framework already enforces executably — delegation and
isolation contracts, verification evidence, gates, retrospectives, minimal-code discipline. Rule
zero (non-duplication) rejects those. Two ideas were genuinely absent, so they are adopted here
as small bindings on existing governance, not as a new skill:

| Adopted | Was missing where | Lands in |
| --- | --- | --- |
| A. Prompt shape (Goal / Context / Validation) | `delegation-protocol.md` defines the contract *fields* but never the shape of a complete prompt that fills them | `framework/opencode/rules/delegation-protocol.md` |
| B. Merge acceptance tiers | the framework states which classes pause a human *during execution* (`team-lead.md` "Human gates") and the vendored `gsd-core` ship workflow offers an unpoliced Skip/Self/Request review choice; the merge-time policy deciding between them was never written down | `framework/opencode/agents/team-lead.md` |

Deliberately **not** adopted: a "10x native AI developer" skill (duplicates team-lead + evidence +
gates + retro + `karpathy-guidelines`), and the two design-pattern skills (hollow without their
catalogs; overlap `animate` / `break-ui` / `prototype`).

## Patch 1 — the policy (applied)

| File | Insertion | Anchor |
| --- | --- | --- |
| `framework/opencode/rules/delegation-protocol.md` | `### Prompt shape (Goal / Context / Validation)` | before `## Checkpoints` |
| `framework/opencode/agents/team-lead.md` | `### Merge acceptance tiers` | under `## Human gates` |

43 added lines, 0 removed.

Both are `framework/opencode/**` — enforcement-plane, edit-deny (`opencode.json`
`permission.edit`), which is why they arrived as a patch a human applies.

## Patch 2 — the enforcement (pending)

| File | Insertion | Why |
| --- | --- | --- |
| `framework/opencode/skills/gsd-ship/SKILL.md` | a `<runtime_note>` binding the tier table to the workflow's `optional_review` step | the Skip/Self/Request review question now has a decided answer instead of a preference |
| `framework/validate.py` (suite [9]) | `check("delegation-protocol carries the prompt shape", ...)` | without it the shape can be deleted silently |
| `framework/validate.py` (suite [8]) | `check("team-lead defines merge acceptance tiers", ...)` | without it the tier table can be deleted silently |

33 added lines, 0 removed.

**Why the ship binding is a skill note and not an edit to `ship.md`.**
`framework/opencode/gsd-core/workflows/ship.md` is vendored GSD-core — it carries upstream
issue references (#2589, #1950, ADR-2008), and the repo tracks local upstream divergence
separately in `gsd-core-upstream.patch` (which patches `bin/install.js`). Adding local policy
to the vendored workflow creates a divergence every upstream pull must rebase. The local wrapper
skill is where this repo's policy about that workflow belongs — the same pattern used for the
`ui-designer` executor note on `gsd-sketch`.

**Why `validate.py` is a patch and not a direct edit.**
`framework/validate.py` is *not* enforcement-plane, so an agent could edit it directly — but it
carries uncommitted work from a concurrent session (claims-ledger isolation, suites 22/24/26/28).
Mixing two authors' in-flight changes is the defect this avoids.

## Apply

```powershell
# patch 1 — already applied
git apply --check docs/change-acceptance/change-acceptance.patch
git apply         docs/change-acceptance/change-acceptance.patch

# patch 2 — apply AFTER the concurrent validate.py session commits
python framework/tools/emit_change_acceptance_patch.py      # regenerate against the committed tree
git apply --check docs/change-acceptance/change-acceptance-enforcement.patch
git apply         docs/change-acceptance/change-acceptance-enforcement.patch
```

Regenerating before applying matters: the emitter reads the live files, and `validate.py` is
still dirty with the concurrent session's work. Its hunks carry 3 lines of context, so a
stale patch fails loudly (`git apply` refuses) rather than silently — but regenerate anyway.

## Verify (after each patch)

```powershell
python framework/validate.py --profile framework     # expect 0 fail / 0 warn
python framework/security/check_enforcement_plane.py # expect exit 0
```

`validate.py` must be run with `--profile framework`; a bare invocation infers `--profile app`
and exits before the agent-level checks.

## Regenerating

```powershell
python framework/tools/emit_change_acceptance_patch.py
```

The emitter asserts: every anchor is unique, every edit is a pure insertion (zero removals),
per-file line endings are preserved, and the emitted hunks re-applied independently reproduce
the intended post-image.

> Do **not** re-add edits A and B to the emitter. They are already in the working tree, so the
> anchors still match exactly once and a regenerated emitter would silently insert a *second*
> copy of both sections.

## How the bindings behave

| | Prompt shape | Merge acceptance tiers |
| --- | --- | --- |
| Loaded via | `opencode.json:5-8` `instructions: ["AGENTS.md", "framework/opencode/rules/*.md"]` — every session | the team-lead agent definition (`mode: primary`) |
| Consulted at | delegation-authoring time (before `task-register`) | the merge decision (`/gsd-ship` `optional_review`) |
| Enabled by | nothing — unconditional, always in context | nothing — unconditional once team-lead runs |
| Enforced by | patch 2's `check(...)` (presence only) | patch 2's `check(...)` (presence only) |

Neither is a gate: they are policy plus a presence assertion. They bind the *decision*, not the
process — and in this repository agents cannot merge at all (`git push*` / `git merge*` are deny),
so the tier table governs who must accept the change while the human performs the merge.
