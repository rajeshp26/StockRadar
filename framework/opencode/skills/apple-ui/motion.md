# Motion — animation catalog and live-data patterns

Read this when anything is summoned/dismissed (modal, drawer, toast, confirmation dialog, command palette) or when a screen shows continuously-updating data.

## Duration tokens — every one has a real call site

```css
--dur-none: 0ms;    /* theme-toggle transition suppression — 0ms is "no transition," not "fast" */
--dur-fast: 120ms;  /* row hover, tooltip fade — reads as instant, still animates */
--dur-base: 160ms;  /* most enter/exit transitions */
--dur-slow: 240ms;  /* modal entrance */
--dur-lazy: 400ms;  /* page transitions, chart data cross-fade */
```
A token defined with a rationale comment and never consumed anywhere is a debugging trap — every duration above is wired to a specific animation below, not left aspirational.

## Base animation catalog

```css
@keyframes fade-in  { from { opacity: 0; } to { opacity: 1; } }
@keyframes slide-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes scale-in { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }

.animate-enter { animation: slide-up var(--dur-base) var(--ease-out) forwards; }
.animate-toast { animation: slide-up var(--dur-base) var(--ease-out); }
.animate-modal { animation: scale-in var(--dur-base) var(--ease-out); }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

## Live-data flash-on-update

```css
@keyframes flash-positive { 0% { background: var(--positive-bg); } 100% { background: transparent; } }
@keyframes flash-negative { 0% { background: var(--negative-bg); } 100% { background: transparent; } }
.price-cell.flash-up   { animation: flash-positive 900ms var(--ease-out); }
.price-cell.flash-down { animation: flash-negative 900ms var(--ease-out); }
```
Under `prefers-reduced-motion`, replace with a single 300ms opacity fade — no color sweep.

**Live/stale/disconnected indicator:** `--positive-text` pulsing dot = live · `--warning` solid dot = stale (>15s no tick) · `--text-tertiary` dot + "Reconnecting…" = disconnected.

## Skeleton loading — with a real reduced-motion substitute

The global reduced-motion rule above would otherwise turn a shimmering skeleton into a flat gray rectangle, which reads as broken UI, not "loading." A loading state needs *some* non-vestibular signal that still communicates loading:

```css
.skeleton-base {
  background: linear-gradient(90deg, var(--bg-elevated) 25%, rgba(255,255,255,0.06) 50%, var(--bg-elevated) 75%);
  background-size: 200% 100%;
  animation: shimmer var(--dur-shimmer) ease-in-out infinite;
  border-radius: var(--radius-sm);
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

@media (prefers-reduced-motion: reduce) {
  .skeleton-base {
    animation: none;
    background: rgba(255, 255, 255, 0.04); /* visibly distinct, non-animated */
  }
}

.skeleton-metric__label { width: 80px;  height: 14px; }
.skeleton-metric__value { width: 120px; height: 28px; }
.skeleton-metric__delta { width: 64px;  height: 16px; }
.skeleton-row { display: flex; align-items: center; height: var(--table-row-height); padding: 0 var(--space-4); gap: var(--space-4); }
.skeleton-row__cell--ticker { width: 48px;  height: 14px; }
.skeleton-row__cell--name   { width: 120px; height: 14px; }
.skeleton-row__cell--price  { width: 72px;  height: 14px; }
.skeleton-row__cell--delta  { width: 56px;  height: 14px; }
.skeleton-row__cell--chart  { width: 64px;  height: 28px; }
.skeleton-chart { width: 100%; aspect-ratio: 16/9; border-radius: var(--radius-md); }
.skeleton-avatar { width: 32px; height: 32px; border-radius: var(--radius-full); }
```

**Full-page initial load:**
```
0–300ms:  black screen (--bg-deep)
300ms+:   skeleton shell — sidebar icons + header + 3-4 skeleton cards + skeleton table
Content:  fade in per-section as data arrives, staggered 50ms
Error:    if initial load fails past 3s, full-page error state with retry
```

## Nested-overlay resolution

When a second content-area overlay opens while one is already open (e.g. a confirmation dialog triggered from inside the command palette), the earlier overlay downgrades to solid `--bg-elevated` for the duration — only the topmost overlay in a stack is ever glass. See `accessibility.md` §Blur budget for the full reasoning; the CSS hook is:
```css
.overlay-backgrounded { background: var(--bg-elevated) !important; backdrop-filter: none !important; }
```
