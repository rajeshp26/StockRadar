# Results — design-skills pilot

Date: 2026-10-20
Fixture: `fixture.html` · Rubric: `RUBRIC.md` · Protocol: `PROTOCOL.md`
Runs: `runs/baseline/findings.md`, `runs/treatment/findings.md`

## Verdict

**REVERT the review-path obligation.** The pre-registered keep rule fails on criterion 1:
treatment produced **no additional seeded defects** (0 lift, required ≥2). Criteria 2 and 3
passed (no regression, no factual error).

The import stays **advisory**. The skill is **not** wired as a mandatory input to the UI review
path, and no plane routing patch is proposed for it. A skill that does not measurably improve
review output does not earn a mandatory slot.

## Scores

| Metric | Baseline | Treatment | Delta |
|---|---|---|---|
| Novel recall (of 6) | 6 | 6 | **0** |
| Control recall (of 5) | 5 | 5 | 0 |
| Total seeded (of 11) | 11 | 11 | 0 |
| Per-defect regressions | — | 0 | — |
| Factual errors | 0 | 0 | — |
| Total findings raised | 29 | 33 | +4 |

### Per-defect match

| ID | Class | Baseline | Treatment | Evidence (finding numbers) |
|---|---|---|---|---|
| D1 remove: no feedback | novel | found | found | B #25, #1 · T #2, #27 |
| D2 remove: no undo | novel | found | found | B #1 · T #2 |
| D3 14 flat options | novel | found | found | B #18 · T #22 |
| D4 nav: no current state | novel | found | found | B #17 · T #14 |
| D5 refresh: no busy state | novel | found | found | B #20, #7 · T #4 |
| D6 share default-on, buried | novel | found | found | B #3 · T #8 |
| D7 error 422, no next step | control | found | found | B #4 · T #3 |
| D8 icon-only, no name | control | found | found | B #6 · T #17 |
| D9 three equal primaries | control | found | found | B #10 · T #10 |
| D10 muted text 3.98:1 | control | found | found | B #12 · T #9 |
| D11 empty state "No data" | control | found | found | B #2 · T #6 |

## What the treatment changed anyway

The treatment raised four more findings in total (33 vs 29). Several are outside the seeded set:

- table clips at narrow widths (`overflow: hidden`, no scroll container) — T #25
- touch targets under 44px, delete targets adjacent to data — T #31
- `button`/`select` do not inherit the page font — T #19
- native checkbox renders the UA blue in a green/charcoal palette — T #13
- two icon scales (20px nav, 16px delete), neither the 24px default — T #16
- "Manage access in Settings → Sharing" points at a destination that does not exist — T #24
- one flex row groups actions, a filter and a privacy toggle at the same 8px proximity — T #21
- aesthetic-usability masking (polish hiding dead controls) — T #33

Baseline had findings the treatment did not, too (row separators at 1.21:1; missing landmarks).
**More findings is not more quality** — precision was not materially different and the
seeded-recall rule is what the protocol pre-registered.

### Scoring note

D1 (no feedback after remove) and D2 (no undo) overlap in source. Baseline finding #25
("no announcement of what was removed") is what makes D1 a baseline match; if that judgment
were rejected, baseline novel recall would be 5 and lift 1 — still below the required 2, so the
verdict is unchanged.

## Why the null result is informative

The seeded "novel" defects were **not novel relative to the six-pillar standard**: Pillar 6
explicitly covers loading, error, empty, disabled and destructive-confirmation states, and
Pillar 2/3 cover icon naming and contrast. The pilot therefore measured *re-finding what the
existing pipeline already targets*, and a competent adversarial reviewer found all of it
without the skill.

That is the finding: **the skill's categories overlap the six pillars more than they extend
them.** Its marginal value on review is vocabulary and rationale, not defect recall.

## Limitations

- One fixture, one run per condition: a pilot, not a powered experiment. It can justify *not*
  mandating; it cannot establish a positive effect.
- `gsd-ui-auditor` is not a spawnable agent in this session, so the six-pillar standard was
  embedded verbatim in both prompts and run on `reviewer`. Both conditions share the
  substitution, so the comparison is fair, but it is not the exact production agent.
- Code-only, no browser: response-time and interaction defects were judged from source.
- Keyword scoring undercounts unusual phrasing; clear matches were recorded as found and are
  listed in the per-defect table.
- The design (sketch) path was **not** tested here. It is judgement-based and remains
  unmeasured. A pre-registered design-path eval (output behaviour, not citation quality) is at
  `design/PROTOCOL.md`; it has not been run.

## Consequence for the wired change

- `framework/design/skills/uiux-design-foundations/` — imported, advisory. **Keep.**
- `.lifecycle/agents/ui-designer.md` — design-craft basis + `## Design basis` output contract.
  **Kept as a pilot**, explicitly marked unproven; it is the one path where the skill has no
  competing checklist.
- Review-path obligation — **not wired.**
- Plane routing patch (`skill-routing.md`, `skill-integration-matrix.md`) — **not proposed.**
  The evidence does not support mandating the skill.
