# Wrap-up path fix (human action — plane-locked)

## The defect

`sketch-wrap-up` (and `spike-wrap-up`) write the packaged findings to
`./.opencode/skills/...`, which is an enforcement-plane path agents may not write, and is
**not** a configured skill root. Verified:

- `sketch-wrap-up` output path — `framework/opencode/gsd-core/workflows/sketch-wrap-up.md:3,27,97,202,248,279`
- `.opencode/**` is `edit: deny` — `opencode.json:24`
- configured skill root is only `framework/opencode/skills` — `opencode.json:453-457`
- the "auto-load" claim ("will auto-load when building the UI," line 252) was already
  false: `.opencode/skills` was never in `skills.paths`.

Every consumer already finds the findings by **explicit glob**, not by the skill loader:
`ui-phase.md:37`, `plan-phase.md:560-561`, `discuss-phase.md:253-254`, `new-project.md:117,120`,
`sketch.md:56,135`, `spike.md:59,136`.

## The fix

Replace the findings root `./.opencode/skills/` with a writable, git-ignored root
`./.planning/skills/` in **every** occurrence below. Keep the glob+read consumption
(it works without any skill-root change); drop the false auto-load claim.

### Occurrence table (25 sites — 9 files)

| File | Lines |
|---|---|
| `framework/opencode/gsd-core/workflows/sketch-wrap-up.md` | 3, 27, 97, 202, 248, 279 |
| `framework/opencode/gsd-core/workflows/spike-wrap-up.md` | 4, 31, 81, 201, 276, 314 |
| `framework/opencode/gsd-core/workflows/ui-phase.md` | 37 |
| `framework/opencode/gsd-core/workflows/plan-phase.md` | 560, 561 |
| `framework/opencode/gsd-core/workflows/discuss-phase.md` | 253, 254 |
| `framework/opencode/gsd-core/workflows/new-project.md` | 117, 120 |
| `framework/opencode/gsd-core/workflows/sketch.md` | 56, 135 |
| `framework/opencode/gsd-core/workflows/spike.md` | 59, 136 |
| `framework/opencode/gsd-core/workflows/help/modes/full.md` | 374, 385 |

### Substitutions

```
./.opencode/skills/sketch-findings-  ->  ./.planning/skills/sketch-findings-
./.opencode/skills/spike-findings-   ->  ./.planning/skills/spike-findings-
```

The value `{SKETCH_FINDINGS_PATH}` that the orchestrator injects is derived from the glob,
so it moves automatically once the glob changes (`ui-phase.md:37`).

### Special case — `sketch-wrap-up.md` step `update_claude_md` (lines 220-230)

That step appends a routing line to `AGENTS.md`, which is also plane-locked
(`opencode.json:26`). Two options:

- **Recommended:** stop editing `AGENTS.md`. Emit the routing suggestion in the completion
  report and let the human add it. The consumer workflows find the findings by glob, so the
  routing line is not required for them to work.
- **If you keep it:** the auto-load form `Skill("sketch-findings-[project]")` only works if
  `.planning/skills` is added to `opencode.json` `skills.paths`. `.planning/` is ephemeral
  and git-ignored (`.gitignore:105-106`), so prefer the explicit-read path instead.

`spike-wrap-up.md` has the same `update_claude_md` behaviour and the same fix.

## After editing

- `framework/opencode/**` is plane-governed. Run
  `python framework/security/check_enforcement_plane.py` and confirm exit 0.
- These are framework/workflow files; if a framework test suite covers them, run it. A
  workflow edit with no executable check is a claim, not evidence.
