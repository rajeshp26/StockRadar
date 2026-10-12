# Patterns — page-level layout and recipes

## Table (desktop) — the most-used surface in the product

```css
.table { background: var(--bg-elevated); border-radius: var(--radius-lg); }
.table thead {
  position: sticky; top: 0; background: var(--glass-bg-strong);
  backdrop-filter: blur(20px); /* content-area budget slot — see accessibility.md */
  border-bottom: 1px solid var(--border-strong);
  z-index: var(--z-sticky-header); height: var(--table-header-height);
}
.table th { font-size: 11px; text-transform: uppercase; font-weight: 500; color: var(--text-tertiary); }
.table th[aria-sort] { cursor: pointer; }
.table th[aria-sort="ascending"] .icon, .table th[aria-sort="descending"] .icon { color: var(--text); }

.table tr {
  height: var(--table-row-height);
  border-bottom: 1px solid var(--border);
  transition: background var(--dur-fast) ease;
}
.table tr:hover { background: rgba(255,255,255,0.03); }
.table tr.is-selected { background: var(--selection-bg); border-left: 2px solid var(--accent-500); }

.table td { font-variant-numeric: tabular-nums; padding: var(--space-3) var(--space-4); }
.table td.ticker { font-weight: 600; color: var(--text); }
.table td.name-cell {
  color: var(--text-secondary);
  display: inline-flex; align-items: center; gap: var(--space-inline); /* ticker + exchange badge */
}
.table td.price, .table td.change, .table td.volume { text-align: right; }
.table td.sparkline { width: 64px; height: 28px; }

.table-scroll { overflow-x: auto; position: relative; }
.table-scroll::after {
  content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 24px;
  background: linear-gradient(90deg, transparent, var(--bg-elevated));
  pointer-events: none;
}
.table td:first-child, .table th:first-child { position: sticky; left: 0; } /* if >8 columns */
```

Keyboard model and horizontal-scroll accessibility (`aria-label`, arrow buttons, discoverability hint) live in `accessibility.md`.

Empty table → **Empty State** below. Error row → subtle red left border, muted row text, inline retry link.

## Empty state

```
┌───────────────────────────────┐
│      ◐ soft radial glow        │  ← --accent-glow, blurred, behind icon
│     ┌───────────────┐          │
│     │   [chart icon] │         │  ← .glass card, --radius-xl
│     └───────────────┘          │
│   "No stocks tracked yet"      │  ← 28–36px, weight 600
│   Search above to get started  │  ← --text-secondary
│   [ Join Discord ]             │  ← ghost button, soft warning-glow on hover
└───────────────────────────────┘
```
Reused for: empty watchlist, empty table, no search results (echo the query + suggestions), empty portfolio — same shape, swapped icon/copy/CTA per context. This is a brand moment, not a footnote — give it the same care as the command palette.

## Search → Command Palette

```css
.search-wrapper {
  position: relative; border-radius: var(--radius-lg); padding: 1px;
  background: linear-gradient(90deg, var(--grad-start), var(--grad-mid), var(--grad-end));
  box-shadow: var(--shadow-glow);
}
.search-inner { border-radius: 15px; background: var(--glass-bg-strong); backdrop-filter: blur(20px); }
.command-palette { max-width: var(--palette-max-width); max-height: var(--palette-max-height); }
```

**Desktop** — centered 15% from top, `.glass-strong` + scrim, opens on `⌘K` / `Ctrl+K`. Counts against the content-area budget of 1 (`accessibility.md`) — opening it forces the table header/card grid to solid.

**Mobile (<768px)** — the desktop sizing doesn't fit a phone viewport:
```
- Full-width, edge-to-edge (ignore --palette-max-width below 768px)
- Position: top 0, full-height, safe-area padding top/bottom
- Input sticky at top; results scroll below
- Close: swipe-down + back gesture + Escape (external keyboard)
```

**Results** — section headers 11px uppercase `--text-tertiary` (fine here — `.glass-strong` at 0.82 alpha is not the low-alpha scrim case). Row height 44px; ticker (bold) + name (`--text-secondary`) + exchange badge + mini sparkline + live delta with arrow glyph; active row `--bg-elevated` + left accent bar; fuzzy match in `--accent-soft`.

**Keyboard** — ↑↓ navigate, ↵ select, `esc` close, `tab` → "Search on web" fallback.

## Information architecture

Sidebar icon rail, top → bottom: `Discover → Watchlist → Portfolio → News → Alerts`, `Settings` pinned below a hairline. Width: `--sidebar-width` (default 64px). Active item = purple glass pill + glow + persistent accent underline (colorblind-safe).

## Responsive strategy

```css
--breakpoint-sm: 640px; --breakpoint-md: 768px; --breakpoint-lg: 1024px;
--breakpoint-xl: 1280px; --breakpoint-2xl: 1536px;
```
- **Desktop (≥1024px):** icon rail + main content.
- **Tablet (768–1023px):** icon rail collapses to icon-only or a bottom tab bar; labels hidden.
- **Mobile (<768px):** bottom tab bar (`.glass-strong`, safe-area aware); command palette uses the mobile behavior above; the Table converts to stacked cards (ticker/price/delta per row).

```css
@supports (padding: env(safe-area-inset-bottom)) {
  .bottom-tab-bar { padding-bottom: env(safe-area-inset-bottom); }
  .page-content { padding-bottom: calc(var(--space-8) + env(safe-area-inset-bottom)); }
}
```

Responsive typography: below 768px, Display → 24–28px, Section headers → 12px non-uppercase (uppercase at small sizes hurts legibility further); below 480px, Page title → 18–20px.

## Print & export

```
Print:        Not supported. Use export mode for screenshot-to-share workflows.
Export mode:  [data-mode="export"] disables glass + shadows for a flat, clean capture.
```
```css
[data-mode="export"] .glass, [data-mode="export"] .glass-strong { backdrop-filter: none; background: var(--bg-elevated); }
[data-mode="export"] { --shadow-md: none; --shadow-lg: none; }
```
