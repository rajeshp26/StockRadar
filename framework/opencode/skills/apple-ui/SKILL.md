---
name: apple-ui
description: Build Apple-glass-grade dark finance UI — the live stock/trading dashboard aesthetic (glassmorphism + Linear precision + Arc/Vercel depth) with verified contrast, a real blur budget, colorblind-safe and market-localized financial signals, live-data patterns, and chart accessibility. Use when designing or building a stock/crypto/portfolio dashboard, watchlist, ticker page, or any finance UI that should feel premium, dense, and trustworthy. Covers glass depth rules, token architecture, component specs, data visualization, and a review mode for auditing existing dashboards. Portable across stacks — ships tokens.css, copy-paste components, a rendered reference.html, and a self-check gate. Trigger on "stock dashboard", "trading UI", "watchlist", "finance app", "crypto dashboard", "portfolio tracker", or any request for a dark glass fintech interface.
---

# Stock UI Skills — Design Skill for Finance Dashboards

You are designing a **live, data-dense, trustworthy** dark finance interface — the kind that makes a trader or investor feel the numbers are correct and the product is fast, not the kind that looks like a generic SaaS dashboard with green/red text bolted on. The goal is a UI that survives real trading hours (constant updates, colorblind users, screen readers, and mid-range hardware), not just a screenshot.

> One sentence: **near-black canvas + purple-soul glass, used only where layers overlap and budgeted like the GPU cost it is; every directional signal is color *and* a shape, verified at its worst case, not its average case.**

## When to use

- Building a stock, crypto, or portfolio dashboard; a watchlist; a ticker/detail page; a trading terminal; any dark finance UI.
- Reviewing/auditing an existing finance dashboard for consistency or correctness (see **Review mode** below).
- The request mentions: stock app, trading UI, crypto dashboard, watchlist, portfolio tracker, or "dark glass fintech interface."

## The 10 philosophy rules (decide by these, in order)

1. **Depth through translucency, not hard shadows** — but blur is GPU cost, and it's budgeted (see `accessibility.md` §Blur budget), not sprinkled everywhere.
2. **Glass is seasoning, not the dish.** Frost only where layers overlap: header, sidebar (permanent, accepted cost), the sticky table header OR a card grid OR an open overlay (pick one — they share a single remaining budget slot). Tooltips, toasts, and popovers are **never** glass.
3. **Data stays king.** Glass never sits over a chart, a live price tick, or any unpredictable content without a scrim verified at its *worst* case.
4. **Color is never the only signal.** Direction gets a glyph (▲▼), magnitude gets a 5-step shade plus a numeric label, categorical series get a line style. This is not optional polish — it's the difference between a dashboard a colorblind trader can use and one they can't.
5. **Every directional token derives from one semantic pair** (`--financial-up` / `--financial-down`), so a market-locale override (e.g. China: red=up) propagates everywhere at once — candles, volume, area fill, heatmap — and can never contradict itself on one screen.
6. **Quiet, purposeful motion.** Respects `prefers-reduced-motion` and `prefers-reduced-transparency` as two *separate* preferences (blur ≠ motion) — and where motion carries meaning (a loading skeleton), reduced-motion gets a real substitute, never silence.
7. **OLED-friendly, and correctly reasoned about.** True black is an opt-in theme and the *safest* contrast case in the system (contrast rises as background luminance falls toward zero) — never treat "more extreme" as "more risk" without checking.
8. **Every accessibility and contrast claim is computed at the worst case that guarantee needs to hold, with the method stated**, and regenerated whenever a primitive or scrim value changes.
9. **Equities-first, multi-asset-extensible, named as such** — the heatmap/threshold system reaches toward crypto and forex on purpose; this is owned, not left as a contradiction with a narrower scope claim.
10. **Rules are checked against a real, boring, default screen** — no modal open, nothing hovered — because that's the state a dashboard spends most of its life in, and where an unbounded rule hides.

## Two modes

- **Build** — new UI. Follow the workflow below.
- **Review** — auditing an existing dashboard for "does this hold up / is this consistent." Use `review.md`: find the real glass/color/contrast surface → score against the token system and the blur budget → return a prioritized, file:line-cited fix list mapped back to tokens. The most common finding is a hardcoded green/red literal that silently ignores the market-locale override.

## Workflow — Build mode (follow in order)

1. **Read `tokens.css`** — drop the `:root` custom properties into the project. Reference everything via `var(--…)`; never hand-roll a hex/px value a token already names.
2. **Read `accessibility.md`** — the contrast contract, the blur budget, and the focus-ring rules. This file is the one most likely to contain the constraint that changes your layout, so read it before you commit to a component arrangement, not after.
3. **Pick component specs from `components.md`** — buttons, inputs, toast, modal, tooltip, confirmation dialog, badges, icons, sidebar.
4. **If the screen shows tabular or chart data** — read `data-viz.md` for the table spec, chart tokens, heatmap, and chart accessibility (aria-label + sr-only data table + keyboard crosshair — charts are otherwise invisible to assistive tech).
5. **For page-level layout** (dashboard, ticker detail, command palette, empty states, responsive/density behavior) — read `patterns.md`.
6. **If anything is summoned/dismissed** (modal, drawer, toast, confirmation dialog, command palette) — read `motion.md` for entrance/exit timing, the live-data flash/skeleton patterns, and nested-overlay resolution (only the topmost overlay is ever glass).
7. **Check against `reference.html`** — open it in a browser. It's a working page, not a mockup: the market-locale toggle, density toggle, and OLED toggle actually flip the tokens live, so you can watch the derivation chain (`--financial-up/down` → candles → volume → heatmap) hold together instead of taking it on faith.
8. **Run the gate** — `checklist.md` before calling it done.

> Portable: these files assume plain CSS custom properties. In React/Vue/etc., translate to your styling system but keep the *exact token values*, the derived-not-hardcoded directional colors, and the budget-of-one-slot glass rule. Match the behavior; don't copy structure that doesn't fit.

## Anti-slop — what makes it look like generic AI fintech output (avoid every one)

- ❌ **Every card is glass.** Glass is a budgeted, scarce effect (rule 2) — a page where the header, sidebar, every metric card, and the table header are all frosted simultaneously is the single most common tell, and it's also the thing that makes the page stutter on mid-range hardware.
- ❌ **Green/red as the only signal.** No arrow glyph, no line-style redundancy, no numeric label on a heatmap cell. Ships fine in a demo, fails for ~8% of men.
- ❌ **Hardcoded green-up/red-down literals scattered through chart code.** The moment a market-locale toggle is added, half the surfaces (usually volume bars and heatmaps) don't flip, producing a screen that contradicts itself.
- ❌ **A default `Chart.js`/`Recharts` palette dropped in unstyled** — default blues and oranges against a near-black canvas read as unfinished, not premium.
- ❌ **Numbers that aren't `tabular-nums`.** Prices that shift width as they update is the fastest way to make a "live" dashboard look janky.
- ❌ **A skeleton loader that goes fully static and gray under `prefers-reduced-motion`.** It stops reading as "loading" and starts reading as "broken."
- ❌ **Confirmation dialogs where `Esc` accidentally confirms**, or where every destructive action gets an interrupting modal (overuse trains click-through — reserve it for genuinely irreversible actions).
- ❌ **Asserting "verified" or "accessible" without a stated method.** A contrast number, a colorblind-safe palette, or a performance budget that can't be reproduced by someone else is not verified — see `accessibility.md` for what "computed" actually means in this system.
- ❌ **A "3 concurrent blur surfaces" rule that's never checked against a real screen.** Header + sidebar + a card grid + a sticky table header is an *ordinary* dashboard state, not an edge case — see `accessibility.md` §Blur budget.

## Self-check (condensed — full gate in `checklist.md`)

- [ ] Every directional chart/heatmap token derives from `--financial-up`/`--financial-down`, none hardcoded.
- [ ] Glass appears only on header/sidebar (accepted permanent cost) plus **one** of: sticky table header, card grid, or an open overlay — never all three plus header/sidebar at once.
- [ ] `--text-tertiary` never appears on scrim-backed glass.
- [ ] Every number-bearing cell uses `tabular-nums`.
- [ ] Direction has a glyph, magnitude has a numeric label, 3+ chart series have a line-style in addition to color.
- [ ] Visually matches `reference.html`, including after toggling its market/density/OLED controls.

## Files in this skill

- `tokens.css` — the `:root` custom properties, three-layer architecture (primitive/semantic/component), portable.
- `components.md` — copy-paste HTML+CSS: buttons, inputs, toast, modal, confirmation dialog, tooltip, badges, icons, sidebar, scrollbar.
- `data-viz.md` — chart/candle/volume/heatmap tokens (all market-derived), multi-series palette, chart accessibility, chart interaction spec, number/edge-case formatting.
- `accessibility.md` — the contrast contract (computed, worst-case, method stated), the blur budget, focus rings, `prefers-*` handling, keyboard models. Read this before committing to a layout.
- `patterns.md` — table spec, empty state, command palette (desktop + mobile), information architecture, responsive/density/safe-area rules.
- `motion.md` — animation catalog, durations, live-data flash/skeleton patterns, nested-overlay resolution.
- `checklist.md` — the standalone "done" gate.
- `review.md` — audit workflow for scoring an existing dashboard against this system.
- `reference.html` — a working, interactive living style guide with live market/density/theme toggles — open it, don't just read about it.
- `examples/ticker-detail.html` — a full worked example (a single-stock detail page: hero, chart with a compare overlay, stats grid with an N/M edge case, order panel with a confirmation dialog, similar-stocks table with a Halted row, news list) composed entirely from `tokens.css`/`components.md`/`data-viz.md`/`patterns.md` — read this when you want to see the system used in a realistic full page, not just isolated pieces.
