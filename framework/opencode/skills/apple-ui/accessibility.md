# Accessibility & Performance — read this before committing to a layout

This file holds the parts of the system most likely to change your layout decisions, not just your CSS values. Read it before you decide how many glass surfaces a screen has, not after.

**The standard this file holds itself to:** every claim below is computed at the case it actually needs to hold (worst case, not average case), with the compositing/derivation method stated so someone else can reproduce the number — not asserted with more confidence than a stale or unverified claim deserves.

---

## The blur budget — bounds real GPU cost on an ordinary screen

A naive "glass everywhere" approach stacks 5+ concurrent `backdrop-filter` regions on the single most common screen state (header + sidebar + a card grid + a sticky table header, no modal open) — that's the jank-on-mid-range-hardware scenario, not an edge case.

**Baseline (accepted, permanent, by design): header + sidebar = 2 concurrent blur regions.** This is a deliberate cost, paid on every screen — not "exempt," just a cost the product has decided is worth it.

**Content-area budget: 1 — not 3.** Exactly one of the following renders as blur at a time; the rest render solid `--bg-elevated`:
- the sticky table header, OR
- the card-grid glass treatment (first 3 cards), OR
- an open overlay (modal / command palette / drawer)

**Default recommendation:** card grids render **solid** by default. Reserve glass for the sticky table header — it's the more distinctive single surface and appears on more screens. A product that wants glass metric cards instead should keep the table header solid to stay inside the same budget.

```css
.card-grid .glass:nth-of-type(n+4) {
  background: var(--bg-elevated); backdrop-filter: none; border-color: var(--border);
}
```

**Nested overlays.** Opening a confirmation dialog from inside the command palette stacks two `glass-strong` surfaces — over budget, and it breaks the "never nest glass-on-glass more than one layer deep" rule. Resolution: **when a second content-area overlay opens, the earlier one downgrades to solid `--bg-elevated` for the duration.** Only the topmost overlay in a stack is ever glass.

```css
.overlay-backgrounded { background: var(--bg-elevated) !important; backdrop-filter: none !important; }
```

**Mechanism for "the table header goes solid when an overlay opens"** (a requirement earlier drafts stated without naming the CSS hook):
```css
.app:has(.modal-open) .table thead,
.app:has(.command-palette-open) .table thead,
.app:has(.drawer-open) .table thead {
  backdrop-filter: none; background: var(--bg-elevated);
}
/* :has() fallback for unsupported environments: toggle a data attribute
   on a shared ancestor when any overlay opens/closes. */
[data-overlay-active] .table thead { backdrop-filter: none; background: var(--bg-elevated); }
```

### Component glass-depth table

| Component | Blur | Budget category |
|---|---|---|
| Header, Sidebar | 24px | Baseline (permanent, accepted cost) |
| Command palette / Modal / Drawer | 20–40px | Content-area (budget of 1); downgrades if a second overlay opens on top |
| Sticky table header | 20px | Content-area — default holder of the budget-of-1 slot |
| Metric card (in a grid) | 16px | Content-area — solid by default; only glass if the product hasn't put the table header there instead |
| Tooltip, Popover, Toast | — | **Never glass, never budgeted** |
| Empty-state icon container | 20px | Decorative, single instance |

---

## The scrim contrast guarantee — computed at its worst case, method stated

Glass never floats directly over unpredictable content (a chart, an image) without a scrim:
```css
.scrim-behind-glass {
  background: linear-gradient(180deg, rgba(5,5,6,0.6), rgba(5,5,6,0.85));
}
```

The scrim is a gradient over genuinely unknown content — a guarantee here has to hold at the worst case, not a representative one. **Method:** composited in sRGB gamma-encoded space (how CSS actually alpha-blends), at the scrim's *minimum* alpha stop (0.6) over a worst-case bright background (#FFFFFF), with `--glass-bg` composited over that result:

```
Step 1: rgb(5,5,6) @ 0.6 alpha over #FFFFFF  → ≈ rgb(105,105,106)
Step 2: rgba(18,18,22,0.65) over that result → ≈ rgb(48,48,51)
Step 3: contrast of --text-tertiary (#84848C) against rgb(48,48,51) ≈ 3.5:1
```

**`--text-tertiary` over worst-case scrim-backed glass ≈ 3.5:1 — fails normal-text AA (needs 4.5:1).** (Different valid compositing orders land in a 3.0–3.6:1 range; the fail conclusion is robust to that spread even though the exact decimal isn't.) **`--text-tertiary` is not permitted on scrim-backed glass** — use `--text-secondary` (≈5.1:1 there) or `--text` instead.

---

## Contrast contract — generated output, recomputed whenever an input changes

| Surface | `--text` | `--text-secondary` | `--text-tertiary` |
|---|---|---|---|
| `--bg-deep` / `--bg` | ✅ ~18:1 | ✅ ~7.8:1 | ✅ ~5.5:1 |
| `--bg-elevated` | ✅ ~16:1 | ✅ ~7.4:1 | ✅ ~5.1:1 |
| OLED `--bg-deep` (#000000) | ✅ ~18.7:1 | ✅ ~8.1:1 | ✅ **~5.7:1 — higher than default, not lower; pure black is the best-case background for light text, never the worst** |
| `--glass-bg-strong` (over `--bg-deep`, no scrim) | ✅ | ✅ | ✅ ~5.0:1 |
| **Scrim-backed glass, worst case** | ✅ ~9–10:1 | ✅ ~5.1:1 | ❌ **~3.5:1 — not permitted, use secondary or better** |

**"Large text" = ≥18px regular, or ≥14px bold** (WCAG's threshold), referenced rather than restated per row.

**Why OLED is the safe case, not the risky one:** contrast ratio is `(L_light + 0.05) / (L_dark + 0.05)`. As background luminance falls toward zero, the denominator shrinks and the ratio *rises*. Pure black is mathematically the best-case background for light text — a "more extreme" input (darker) is not automatically higher-risk; check the direction before flagging it. The genuine narrowest margin in this system is scrim-backed glass, which composites *toward a lighter* background under worst-case content — the opposite direction from OLED.

**White text on `--accent-500` (#8B5CF6) is ~4.2:1 — fails AA for normal-size UI text.** Use `--accent-600` (~5.6:1) as the background for any text-bearing accent surface (primary buttons, filled badges); reserve `--accent-500` for glows, borders, and non-text decorative fills.

**Maintenance rule:** any time `--gray-400`, a scrim alpha, or a theme background changes, recompute this table — don't reuse old numbers, and don't assume a "more extreme" change is automatically riskier without checking the formula's direction.

---

## Focus rings

One canonical ring per surface type, referenced everywhere, never redefined per component:
```css
--focus-ring: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-500);        /* solid surfaces */
--focus-ring-glass: 0 0 0 2px rgba(0,0,0,0.5), 0 0 0 4px var(--accent-500); /* inside .glass/.glass-strong */
```
A `--bg`-based halo looks muddy over translucency — anything rendered inside a glass container (including inputs, e.g. the command-palette search box) uses `--focus-ring-glass`, applied via a parent selector or modifier class:
```css
.btn.glass-surface:focus-visible { box-shadow: var(--focus-ring-glass); }
.glass .input:focus, .glass-strong .input:focus { box-shadow: var(--focus-ring-glass); }
```

---

## `prefers-*` — three independent preferences, never conflated

- **`prefers-reduced-transparency`** → glass surfaces fall back to solid `--bg-elevated`, no blur.
- **`prefers-reduced-motion`** → animation/transition durations collapse to ~0 — **except** a loading skeleton, which needs a non-animated but still-visible substitute (a flat gray rectangle reads as broken UI, not "loading"). See `motion.md`.
- **`prefers-contrast: more`** → borders and hover states widen, `--gray-400` bumps to `#93939B` (~7:1). This system leans on deliberately subtle borders (`rgba(255,255,255,0.06)`) and hover states (`0.03`); under high-contrast preference, function beats aesthetics.

Blur is not motion, and motion is not contrast — treat all three as separate media queries, never let one stand in for another.

---

## Keyboard models

**Table** — Enter and Space are not the same action:
```
Tab:            focuses the first cell of the first data row
Arrow keys:     move between cells
Home / End:     jump to first / last cell in the current row
Ctrl+Home/End:  jump to first / last row
Enter:          navigate to the detail view (primary action)
Space:          toggle row selection (.is-selected)
Click:          toggle row selection
Escape:         exit table focus
```
(Enter = activate, Space = toggle state — native list/file-manager convention.)

**Chart** — otherwise invisible to a screen reader; see `data-viz.md` §Chart accessibility for the full `aria-label` + sr-only table + `aria-live` crosshair pattern.

**Confirmation dialog** — `Esc` always maps to Cancel, never Confirm. A destructive-action gate must never let the "get me out of here" key trigger the destructive action.

**Sidebar** — `role="navigation"`, `aria-label`, `aria-current="page"` on the active item.
