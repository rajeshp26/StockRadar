# Checklist — the "done" gate

Run this before calling any build finished.

## Tokens
- [ ] No hardcoded hex/px value where a token in `tokens.css` already names it.
- [ ] Every directional chart/heatmap token derives from `--financial-up`/`--financial-down` (`data-viz.md`) — none hardcoded as raw green/red.
- [ ] Every token introduced has a real, checkable call site — grep for it before shipping.

## Glass & blur budget
- [ ] Header + sidebar are the only permanent glass surfaces.
- [ ] Exactly one of {sticky table header, card-grid glass, open overlay} is glass at a time — not all three plus header/sidebar simultaneously.
- [ ] Glass never sits directly over a chart, live price tick, or image without a scrim.
- [ ] Tooltips, popovers, and toasts are never glass.
- [ ] If two content-area overlays can stack, the earlier one downgrades to solid when the second opens.

## Contrast & accessibility
- [ ] `--text-tertiary` never appears on scrim-backed glass — `--text-secondary` or `--text` instead.
- [ ] White/light text never sits directly on `--accent-500` — use `--accent-600`+ for text-bearing accent surfaces.
- [ ] `--focus-ring` on solid surfaces, `--focus-ring-glass` inside any `.glass`/`.glass-strong` container (including nested inputs).
- [ ] `prefers-reduced-transparency`, `prefers-reduced-motion`, and `prefers-contrast: more` are handled as three independent preferences.
- [ ] Skeleton loaders have a non-animated but still-visible substitute under reduced motion.
- [ ] Charts have an `aria-label`, an sr-only data table, and keyboard crosshair navigation.
- [ ] Table has the full keyboard model (Enter navigates, Space toggles selection — not the same key for both).
- [ ] Confirmation dialogs map `Esc` to Cancel, never Confirm.

## Data & formatting
- [ ] Every direction (price change) has a glyph (▲▼), not just color.
- [ ] Every heatmap cell has a visible numeric label, not just color intensity.
- [ ] Multi-series charts (3+ series) use line style in addition to color.
- [ ] All numeric table/list values use `tabular-nums`.
- [ ] Financial edge cases (halted, delisted, negative P/E, infinite % change, no data) render per `data-viz.md`'s table, not ad hoc.

## Layout & responsive
- [ ] Mobile command palette uses the full-width takeover behavior, not a shrunk desktop modal.
- [ ] Table converts to stacked cards below 768px.
- [ ] Safe-area insets applied to any fixed bottom bar.
- [ ] Density mode (`data-density`) affects spacing/row-height/input-height only — not typography hierarchy.

## Final check
- [ ] Visually matches `reference.html`, including after toggling its market-locale, density, and OLED-theme controls.
- [ ] No section of this checklist was skipped because "it probably still holds" — re-verify anything a recent change touched.
