# Protocol — does the design-skills corpus improve review output?

## Question

Does giving a UI auditor the imported `uiux-design-foundations` checklists produce more of the
defects that the existing six-pillar audit misses, without regressing what it already catches?

## Design

Two runs over the same fixture, same agent, same model, same target:

| Run | Inputs |
|---|---|
| baseline | `framework/docs/evals/design-skills/fixture.html`, standard six-pillar audit |
| treatment | same fixture + `<required_reading>`: `framework/design/skills/uiux-design-foundations/SKILL.md` and `references/checklists.md` |

The fixture contains 11 seeded defects (6 novel, 5 control) defined in `RUBRIC.md`. The auditor
is not told that the fixture is seeded, how many defects exist, or what the rubric contains.

## Constraints

- One fixture, one run per condition: this is a **pilot**, not a powered experiment. It can
  justify *not* mandating a skill; it cannot alone justify mandating one without a second
  fixture. A second fixture is added only if the pilot is positive.
- Scoring is keyword matching against `RUBRIC.md`, not human judgement of quality. It measures
  *coverage of named defects*, not design taste.
- No screenshots: this is a code-only audit. Response-time and interaction defects are judged
  from the source, which is how they were seeded.

## Execution note (added after the runs, 2026-10-20)

`gsd-ui-auditor` is not a spawnable agent in this session. The six-pillar standard was copied
verbatim from `framework/opencode/agents/gsd-ui-auditor.md` into both prompts and run on the
`reviewer` agent. Both conditions share the substitution, so the comparison is unchanged, but
this is not the exact production agent. See `RESULTS.md` → Limitations.

## Procedure

1. Spawn the audit agent twice, foreground, with the prompts in `runs/` (baseline, treatment).
2. Record each raw findings list verbatim under `runs/<condition>/findings.md`.
3. Score each list against `RUBRIC.md`: mark found/not found per defect, note regressions and
   factual errors.
4. Apply the pre-registered keep/revert rule in `RUBRIC.md` and record the verdict in
   `RESULTS.md`.

## What this does not prove

- It does not prove the *design* (sketch) path improves; that path is judgement-based and is
  measured separately if at all.
- It does not prove generalisation beyond this fixture and this agent.
- Keyword scoring undercounts findings phrased unusually; where a finding clearly names a
  defect in different words, it is marked found and the phrasing recorded as an exception.
