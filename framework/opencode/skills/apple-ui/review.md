# Review mode — auditing an existing dashboard

Use this when the task is "does this hold up" or "make this consistent," not "build new." The goal is a prioritized, `file:line`-cited fix list mapped back to the tokens in this system — not a rewrite.

## Step 1 — Find the real surface

Grep the codebase for the things most likely to have drifted from the system, in this order (highest-yield first):

1. **Raw color literals in chart/heatmap code.** `grep -rn "rgba(34" --include=*.css --include=*.tsx` (and the red equivalent, `rgba(239`). This is the single most common and most damaging finding — a hardcoded literal silently ignores the `[data-market="cn"]` override and produces a screen that contradicts itself (e.g. a red candle over a green volume bar). Every hit here is high priority.
2. **`backdrop-filter` usage.** Count concurrent glass surfaces on the default (no-modal-open) screen state. More than "header + sidebar + one content-area surface" is over budget — see `accessibility.md`.
3. **Hardcoded hex/px values** that duplicate a token already in `tokens.css` — these are drift, not necessarily bugs, but they make future token changes not propagate.
4. **`--text-tertiary` (or its hex equivalent) inside anything with a `backdrop-filter` ancestor** — check whether that glass surface sits over a scrim (chart/image) or a flat background. If a scrim, this is a contrast failure per `accessibility.md`.
5. **Focus-ring definitions.** Search for `box-shadow.*focus` or `:focus-visible` — more than one distinct ring definition in the codebase means components will look inconsistent under keyboard navigation.
6. **Color-only directional signals.** Any price/change cell that renders green/red text with no adjacent glyph, icon, or shape.

## Step 2 — Score against the system

For each finding, classify:
- **Critical** — produces incorrect or contradictory information (market-locale color bugs, a confirmation dialog where `Esc` confirms, a contrast failure on real content).
- **High** — breaks for a real subset of users (colorblind-only signals, no chart accessibility, reduced-motion turning a skeleton fully static).
- **Medium** — inconsistency that will compound (duplicate focus rings, un-tokenized values, ad hoc spacing).
- **Low** — cosmetic drift from the reference.

## Step 3 — Report

```
[CRITICAL] src/components/VolumeBar.tsx:42
  Hardcoded rgba(34,197,94,0.35) for "up" volume bars — does not derive
  from --financial-up. Under [data-market="cn"], candles flip but this
  bar doesn't, producing a contradictory screen.
  Fix: var(--chart-volume-up) — see data-viz.md.

[HIGH] src/components/Chart.tsx
  No aria-label, no sr-only data table. Chart is invisible to screen readers.
  Fix: wrap in <figure role="img" aria-label="..."> per data-viz.md §Chart accessibility.
```

## Step 4 — Fix in priority order, re-run `checklist.md`

The most common real-world finding, by far, is #1 above — a chart or heatmap component built before the market-locale token existed, still holding onto literal colors from an earlier pass. Check it first.
