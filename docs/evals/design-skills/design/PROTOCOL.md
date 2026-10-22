# Design-path eval — protocol

## Question

Does the `Design craft basis` obligation change the **design output** — not just the wording of
the decision sheet?

## Design

Two runs of `ui-designer`, same brief, same model, different required reading:

| Run | `<required_reading>` |
|---|---|
| baseline | `AGENTS.md`, `frontend-react/SKILL.md`, `apple-ui/SKILL.md`, `gsd-sketch/SKILL.md` |
| treatment | the same four **plus** `uiux-design-foundations/SKILL.md`, `references/checklists.md`, `references/ux-laws.md` |

Both blocks are present, so the experiment isolates the skill rather than the presence of a
reading block. Both conditions read the charter (the agent definition requires it).

Sketch dirs: `.planning/sketches/eval-design-baseline/`, `.planning/sketches/eval-design-treatment/`.

## Constraints

- One brief, one run per condition: a pilot. It can justify *not* keeping an obligation; it
  cannot establish a general effect.
- The designer must render each variant per its charter. Scoring reads the HTML, not the images.
- The run is an evaluation, not an adoption. The prompt says no direction will be adopted and
  the designer must not ask for approval; it stops after the decision sheet. This is the only
  deviation from an adoption run and is recorded here. The user's go-ahead authorises the
  process, not a design direction.
- The designer must not read `CHECKS.md` or this protocol.

## Procedure

1. Spawn `ui-designer` for the baseline with the brief and the baseline block.
2. Spawn `ui-designer` for the treatment with the brief and the treatment block.
3. Score the recommended variant against `CHECKS.md`; record per-check pass/fail.
4. Apply the keep/revert rule in `CHECKS.md`; record the verdict in `RESULTS-design.md`.

## What this does not prove

- It does not prove the review path improves; that was measured separately and was null.
- It does not prove the skill improves taste or visual craft.
- One brief cannot represent the product. A second brief is added only if the pilot is positive.
