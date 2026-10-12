# Components — copy-paste snippets

All sizing/color comes from `tokens.css`. Read `accessibility.md` first for the contrast and focus-ring rules referenced below.

## Interaction state contract (applies to every interactive component)

```
Default:  token-defined background + border per component
Hover:    background shifts toward white by 3–4% opacity; border → --border-strong; cursor: pointer
Active:   background shifts toward white by 6–8% opacity; slight translateY(1px)
Focus:    --focus-ring (solid surfaces) / --focus-ring-glass (inside .glass/.glass-strong)
Disabled: opacity 0.4; pointer-events: none

Accent-colored elements: Hover = --accent-600, Active = --accent-700
```

## Buttons

| Variant | Background | Border | Text |
|---|---|---|---|
| Primary | `--accent-600` → `--accent-700` gradient (~5.6:1 verified) | none | white |
| Secondary | `--bg-elevated` | `--border-strong` | `--text` |
| Ghost | transparent | none; `--glass-highlight` on hover | `--text-secondary` |
| Danger | `--negative-text` @ 12% bg | `--negative-text` border | `--negative-text`; opens the Confirmation Dialog below |

```html
<button class="btn btn-primary">Buy</button>
<button class="btn btn-secondary">Cancel</button>
<button class="btn btn-ghost">Dismiss</button>
<button class="btn btn-danger" data-opens="confirm-remove">Remove</button>
```
```css
.btn { height: var(--button-height-md); border-radius: var(--button-radius); padding: 0 var(--space-4); transition: background var(--dur-fast) ease; border: none; cursor: pointer; }
.btn-primary { background: linear-gradient(180deg, var(--accent-600), var(--accent-700)); color: white; }
.btn-secondary { background: var(--bg-elevated); border: 1px solid var(--border-strong); color: var(--text); }
.btn-ghost { background: transparent; color: var(--text-secondary); }
.btn-ghost:hover { background: var(--glass-highlight); }
.btn-danger { background: var(--negative-bg); border: 1px solid var(--negative-text); color: var(--negative-text); }
.btn:focus-visible { box-shadow: var(--focus-ring); outline: none; }
.btn.glass-surface:focus-visible { box-shadow: var(--focus-ring-glass); }
.is-disabled, [disabled] { opacity: 0.4; cursor: not-allowed; pointer-events: none; }
```

## Confirmation dialog

`.glass-strong` Modal, `--confirmation-dialog-max-width` (360px): one-sentence consequence statement, Cancel (Ghost) + Confirm (Danger). No scrim-click-to-dismiss. **`Esc` always maps to Cancel, never Confirm.** Downgrades to solid if opened from within another content-area overlay (see `accessibility.md` §Blur budget).

```html
<div class="modal glass-strong confirmation-dialog" role="alertdialog" aria-modal="true">
  <p>Remove <strong>AAPL</strong> from your watchlist?</p>
  <div class="dialog-actions">
    <button class="btn btn-ghost">Cancel</button>
    <button class="btn btn-danger">Remove</button>
  </div>
</div>
```

## Inputs

Density-aware height token so compact mode doesn't skip inputs. Glass-aware focus ring when nested inside `.glass`/`.glass-strong` (e.g. the command-palette search box).

```css
.input {
  height: var(--input-height-md);
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: var(--radius-md); color: var(--text); font-size: 13px;
  padding: 0 var(--space-3); transition: border-color var(--dur-base) ease, box-shadow var(--dur-base) ease;
}
.input:focus { border-color: var(--accent-500); box-shadow: var(--focus-ring); outline: none; }
.glass .input:focus, .glass-strong .input:focus { box-shadow: var(--focus-ring-glass); }
.input::placeholder { color: var(--text-tertiary); }
.input-error { border-color: var(--negative-text); box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15); }
```

## Toast

Solid `--bg-elevated`, never glass — legibility and read-speed matter more here than depth.

```css
.toast { border-left: 3px solid var(--toast-border-info); background: var(--bg-elevated); box-shadow: var(--shadow-md); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); }
.toast--success { border-left-color: var(--toast-border-success); }
.toast--error   { border-left-color: var(--toast-border-error); }
.toast--warning { border-left-color: var(--toast-border-warning); }
```
**Stacking:** bottom-to-top, newest on top; `--space-2` gap; max 3 visible (oldest dismissed if exceeded); each has its own independent auto-dismiss timer; container is fixed-position, unaffected by page scroll.

## Modal / Dialog

`.glass-strong`, `--modal-max-width` (480px), full-screen scrim (`rgba(5,5,6,0.7)`), `--z-modal`. Subject to the nested-overlay downgrade rule in `accessibility.md`.

## Tooltip

Solid surface, never glass — referenced everywhere in this system (number formatting, chart crosshair, contrast contract) so it's specified once, here:
```css
.tooltip {
  background: var(--bg-elevated); border: 1px solid var(--border-strong); box-shadow: var(--shadow-md);
  border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); font-size: 12px;
  max-width: var(--tooltip-max-width-data); /* or --tooltip-max-width-label for a single line */
}
```
Positioning: above trigger by default, flips below if <12px from viewport top, 8px offset. Behavior: 300ms show delay (prevents flicker on mouse-paths), 100ms hide delay (allows diagonal movement), no delay on keyboard focus, dismiss on scroll/Escape/click-outside. Animation: fade, `--dur-fast`; instant under reduced motion.

## Badge / tag / pill

```css
.badge { border-radius: var(--radius-full); background: var(--bg-elevated); color: var(--text-secondary); font-size: 11px; text-transform: uppercase; padding: 2px var(--space-2); }
```

## Sidebar

```html
<nav role="navigation" aria-label="Main navigation" class="sidebar glass">
  <a href="/discover" aria-current="page" class="sidebar-item is-active"><!-- icon --></a>
  <a href="/watchlist" class="sidebar-item"><!-- icon --><span class="sidebar-badge sidebar-badge--count">3</span></a>
  <!-- Portfolio, News, Alerts -->
  <a href="/settings" class="sidebar-item sidebar-item--bottom"><!-- icon --></a>
</nav>
```
```css
.sidebar { width: var(--sidebar-width); }
.sidebar-item.is-active { background: var(--accent-glow); border-radius: var(--radius-md); }
.sidebar-item.is-active::after { content: ''; /* persistent 2px accent underline — colorblind-safe active state */ }
.sidebar-badge {
  position: absolute; top: 2px; right: 2px; width: 8px; height: 8px;
  border-radius: var(--radius-full); background: var(--negative-text);
  border: 2px solid var(--bg-deep); pointer-events: none;
}
.sidebar-badge--count { min-width: 16px; height: 16px; font-size: 10px; font-weight: 600; display: flex; align-items: center; justify-content: center; color: white; }
```

## Icon system

Pick one library, hold it consistent (Lucide or Phosphor — MIT, consistent stroke, matches Inter's geometry). Three sizes only:
```css
.icon      { width: 20px; height: 20px; stroke-width: 1.75; color: var(--text-secondary); flex-shrink: 0; }
.icon--sm  { width: 16px; height: 16px; stroke-width: 2; }    /* inline / table cells */
.icon--md  { width: 20px; height: 20px; stroke-width: 1.75; } /* nav / buttons — default */
.icon--lg  { width: 24px; height: 24px; stroke-width: 1.5; }  /* empty states / headers */
.icon--accent { color: var(--accent-soft); } .icon--muted { color: var(--text-tertiary); }
.icon--positive { color: var(--positive-text); } .icon--negative { color: var(--negative-text); }
```

## Scrollbar

```css
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
* { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; }
```

Tabs, dropdown/select, toggle/switch, progress bar, breadcrumbs, and pagination reuse the tokens above (button height scale, `--radius-md`, `--focus-ring`) rather than inventing new values.
