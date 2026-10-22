# Prompts used (verbatim)

Both runs used the `reviewer` subagent. The only difference is the `<required_reading>` block
in the treatment.

## Baseline

```
You are performing a code-only six-pillar UI audit of exactly one file.

Target: C:\Project\StockerPro\StockerPro\docs\evals\design-skills\fixture.html
Context: StockerPro is a dark-theme portfolio app; this file is the "Dividends" screen markup.

Hard scope rules:
- Read the target file. Do NOT open any other file under docs/evals/design-skills/ (RUBRIC.md, PROTOCOL.md, RESULTS.md are out of scope and must not be read).
- No dev server, no screenshots. Judge from the source.
- Do not write or modify any files. Return everything in your final response.

Audit against the six pillars, scoring each 1-4 (4 excellent, 3 good, 2 needs work, 1 poor):
1. Copywriting — CTA labels, empty-state copy, error copy.
2. Visuals — focal point, icon-only labels/aria, hierarchy via size/weight/colour.
3. Color — accent usage, hardcoded colours, 60/30/10, contrast ratios.
4. Typography — number of sizes and weights, scale consistency.
5. Spacing — consistent scale, arbitrary values, grouping.
6. Experience Design — loading, error, empty states, disabled states, confirmation for destructive actions.

Return, in this order:
A. A pillar table: pillar | score | one-line justification.
B. A numbered findings list. For each: severity (BLOCKER/WARNING), the element, the defect, and the user consequence.

List every finding you can support from the source — do not stop at the top three. Do not soften scores.
```

## Treatment

Identical to the baseline, plus this block before the audit and one extra sentence in the
findings instruction.

```
Before the audit, you MUST read these files in full:
<required_reading>
- C:\Project\StockerPro\StockerPro\design\skills\uiux-design-foundations\SKILL.md
- C:\Project\StockerPro\StockerPro\design\skills\uiux-design-foundations\references\checklists.md
- C:\Project\StockerPro\StockerPro\design\skills\uiux-design-foundations\references\ux-laws.md
</required_reading>
```

```
In addition to the six pillars, apply the named principles and checklist passes from the required reading: UX laws, cognitive load, the Action Cycle, flow, information architecture, and prospect-refuge. Name the principle that applies in each finding.
```
