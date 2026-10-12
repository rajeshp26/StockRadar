# Data Visualization

This is the highest-risk file in the system: every directional color here must derive from the same semantic pair, or a market-locale toggle silently produces a self-contradicting screen (a red candle sitting on a green volume bar for the same move).

## Directional tokens — derived from `--financial-up`/`--financial-down`, never hardcoded

```css
:root {
  --chart-primary: var(--accent-500);
  --chart-secondary: var(--blue-500);
  --chart-tertiary: var(--cyan-500);
  --chart-grid: rgba(255, 255, 255, 0.05);
  --chart-axis: rgba(255, 255, 255, 0.15);
  --chart-axis-label: var(--text-tertiary); /* solid axis background — fine per accessibility.md */

  --chart-candle-up: var(--financial-up);
  --chart-candle-down: var(--financial-down);
  --candle-wick-width: 1px;
  --candle-body-min-width: 4px;

  --chart-volume-up: color-mix(in srgb, var(--financial-up) 35%, transparent);
  --chart-volume-down: color-mix(in srgb, var(--financial-down) 35%, transparent);
  --chart-area-fill-up: color-mix(in srgb, var(--financial-up) 8%, transparent);
  --chart-area-fill-down: color-mix(in srgb, var(--financial-down) 8%, transparent);
  --chart-crosshair: var(--accent-soft);

  /* Multi-series comparison palette — categorical hue distinguishability was
     NOT run through a named CVD simulator, so rather than assert "verified,"
     this system requires the redundant line-style channel below instead. */
  --chart-series-1: var(--accent-400);
  --chart-series-2: var(--blue-500);
  --chart-series-3: var(--cyan-500);
  --chart-series-4: var(--orange-500);
  --chart-series-5: var(--pink-500);
  --chart-series-6: var(--amber-500);
  --chart-series-7: var(--emerald-400);
}

/* Fallback for the ~4% of traffic without color-mix() support. Known,
   documented degradation: these literals are Western-default and will NOT
   propagate a [data-market="cn"] flip to volume/area fills. Use JS token
   injection instead of this fallback if CN correctness on legacy browsers matters. */
@supports not (color: color-mix(in srgb, red 50%, transparent)) {
  :root {
    --chart-volume-up: rgba(34, 197, 94, 0.35); --chart-volume-down: rgba(239, 68, 68, 0.35);
    --chart-area-fill-up: rgba(34, 197, 94, 0.08); --chart-area-fill-down: rgba(239, 68, 68, 0.08);
  }
  [data-market="cn"] {
    --chart-volume-up: rgba(239, 68, 68, 0.35); --chart-volume-down: rgba(34, 197, 94, 0.35);
    --chart-area-fill-up: rgba(239, 68, 68, 0.08); --chart-area-fill-down: rgba(34, 197, 94, 0.08);
  }
}
```

**Series identity is color + line style past 2 series, never color alone:** line style cycles solid → dashed → dotted → dash-dot every 4 series, always paired with an end-of-line ticker label.

## Magnitude / heatmap scale — derived, equities-scoped by default

```css
:root {
  --heat-up-1: color-mix(in srgb, var(--financial-up) 10%, transparent); /* 0–1% */
  --heat-up-2: color-mix(in srgb, var(--financial-up) 28%, transparent); /* 1–3% */
  --heat-up-3: color-mix(in srgb, var(--financial-up) 48%, transparent); /* 3–5% */
  --heat-up-4: color-mix(in srgb, var(--financial-up) 68%, transparent); /* 5–8% */
  --heat-up-5: color-mix(in srgb, var(--financial-up) 90%, transparent); /* 8%+ */
  --heat-down-1: color-mix(in srgb, var(--financial-down) 10%, transparent);
  --heat-down-2: color-mix(in srgb, var(--financial-down) 28%, transparent);
  --heat-down-3: color-mix(in srgb, var(--financial-down) 48%, transparent);
  --heat-down-4: color-mix(in srgb, var(--financial-down) 68%, transparent);
  --heat-down-5: color-mix(in srgb, var(--financial-down) 90%, transparent);
}
```
**Scope: equities-first, multi-asset-extensible, named as such.** The five color stops are fixed; the percentage breakpoints that select between them are asset-class metadata, not CSS — applying the equity scale to crypto makes everything read as `heat-5` (crypto moves 15-30% daily), and to forex makes everything read as `heat-1` (forex moves 0.3-0.8%):
```js
const heatThresholds = {
  equity: [1, 3, 5, 8],       // default
  crypto: [3, 8, 15, 25],
  forex:  [0.15, 0.4, 0.8, 1.5],
};
```
Always pair a heatmap cell with a visible numeric label — color intensity is a scan aid, never the only carrier of the value.

## Chart accessibility

A chart rendered as canvas/SVG is otherwise invisible to assistive tech:
```html
<figure role="img" aria-label="AAPL price chart, 1 month, up 4.2%, from $182.10 to $189.80">
  <canvas class="chart-canvas" tabindex="0"></canvas>
  <table class="sr-only">
    <caption>AAPL closing price, last 30 days</caption>
    <!-- one row per plotted point: date / close / change -->
  </table>
</figure>
```
Keyboard: the chart canvas is tabbable; ← → move a crosshair between data points; the active point's value is announced through a visually-hidden `aria-live="polite"` region as the crosshair moves.

## Chart interaction spec

```
Crosshair: hover/touch, dashed lines in --chart-crosshair, snaps to nearest point.
Tooltip: solid --bg-elevated (see components.md), 8px offset, pinned to chart bounds.
Time range selector: 1D 1W 1M 3M 6M 1Y 5Y MAX pills; active = --accent-600 background.
  Switching ranges keeps the existing chart visible under a shimmer overlay while loading.
Data transition: new data fades in over --dur-lazy; Y-axis rescales over 200ms ease-out,
  not a shrink→expand morph. Instant swap under prefers-reduced-motion.
Hover highlight: line → 8px --accent-500 dot; area → opacity increase; candle → border highlight.
Zoom/pan (desktop): scroll wheel zooms X-axis, click-drag pans, reset control on zoom.
Touch: long-press activates the crosshair (avoids scroll conflict); pinch to zoom;
  below 480px, hide Y-axis labels by default, show on crosshair hover only.
```

## Sparklines

32–48px inline, 64–96px in a card, 1.5px stroke, no axes/labels, color matches direction, arrow glyph if adjacent to a number.

## Number, currency & financial edge-case formatting

```
Stock price:  $187.42        (2 decimals; up to 4 for sub-$1 assets)
Large cap:    $1.87T         (abbreviate at 100K+, 2 decimals)
Shares:       1,247,382      (comma-separated, no decimals)
Volume:       12.4M
Percentage:   +2.34%         (always signed, − not -)
P/E ratio:    24.3x
EPS:          $6.14
```
`font-variant-numeric: tabular-nums` everywhere numbers appear in a list/table — a price that shifts width as it updates is the fastest way to make a "live" dashboard look janky.

| Edge case | Display |
|---|---|
| Negative P/E | "N/M" (not meaningful), tooltip explains why |
| Sub-penny stock ($0.0001) | 4 decimal places |
| Halted stock | Last price + "Halted" badge, no live dot |
| Pre/post market | Separate line: "Pre-Market: $187.42 +1.2%" |
| Stock split | Historical prices adjusted, small "adjusted" note badge |
| Delisted | Gray text, "Delisted" badge, no live data attempted |
| Extremely large cap ($10T+) | Same 2-decimal abbreviation, no new unit |
| No data available | "—" em-dash — never "N/A" or a blank cell |
| Infinite % change (from $0 base) | "∞" or a "New" badge, never a raw computed value |
| Crypto with 8+ decimals | 2–4 in table view, full precision in the detail page |
