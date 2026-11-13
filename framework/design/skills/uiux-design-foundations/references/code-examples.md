# Worked Examples — Original CSS Implementing the Book's Rules

All code in this file is original, written for this skill. It implements the values the book teaches (8pt spacing, major-third type scale from a 16px base, 60-30-10 colour, 1x–2x button padding, six button states). Adapt the values to the project; keep the structure.

## 1. Design tokens: spacing, type scale, colour

One token block settles most later decisions. Spacing is multiples of 8 with a 4px fine step. The type scale uses the major-third ratio (1.25) from a 16px base, rounded to whole pixels. Colour follows 60-30-10: neutrals dominate, a supporting colour carries surfaces and secondary elements, one accent is reserved for primary actions.

```css
:root {
  /* Spacing: 8pt system, 4px fine step */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;

  /* Type scale: major third (1.25) from 16px */
  --text-overline: 10px;
  --text-caption: 12px;
  --text-body: 16px;
  --text-h6: 20px;
  --text-h5: 25px;
  --text-h4: 31px;
  --text-h3: 39px;
  --text-h2: 49px;
  --text-h1: 61px;
  --line-body: 1.5;      /* book default is 1.2; 1.5 is safer for long text */
  --line-heading: 1.2;

  /* Colour: 60-30-10 */
  --color-bg: #faf9f7;        /* 60: dominant background */
  --color-surface: #efeae4;   /* 30: secondary surfaces */
  --color-ink: #1d2733;       /* text, 12.6:1 on --color-bg */
  --color-primary: #1f5fa8;   /* 30: links, secondary emphasis, 5.9:1 on bg */
  --color-accent: #b34700;    /* 10: primary actions only, 4.6:1 on bg */

  --radius: 8px;
}
```

Contrast note: check every text/background pair you actually use at 4.5:1 or better, including the accent behind white button text (white on the accent above is about 4.6:1, so it passes for large button text; verify in a contrast tool before shipping).

## 2. Relationship spacing ladder

Gap size signals how related elements are. Small gaps inside a group, large gaps between groups and sections (Law of Proximity plus the book's spacing ladder).

```css
.field        { display: grid; gap: var(--space-2); }        /* label to input: 8px */
.field .hint  { margin-top: var(--space-1); }                /* tightly linked: 4px */
.card         { display: grid; gap: var(--space-4); padding: var(--space-6); }
.card-grid    { display: grid; gap: var(--space-8); }        /* between cards: 32px */
.section      { padding-block: var(--space-16); }            /* between sections: 64px */
```

## 3. Page grid

A 12-column desktop grid that steps down to 8 and 4 columns, with margins on the 8pt system. Pick block, modular, or hierarchical arrangements inside it per the content; the grid is the frame, not the layout decision.

```css
.container {
  max-width: 1200px;
  margin-inline: auto;
  padding-inline: var(--space-6);          /* 24px page margin */
}
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: var(--space-6);                     /* gutters */
}
.span-8 { grid-column: span 8; }
.span-4 { grid-column: span 4; }
@media (max-width: 900px) {
  .grid { grid-template-columns: repeat(8, 1fr); }
  .span-8, .span-4 { grid-column: span 8; }
}
@media (max-width: 560px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
  .span-8, .span-4 { grid-column: span 4; }
}
```

## 4. Button system with all six states

Primary (solid accent), ghost (secondary), and text (tertiary) variants; padding follows the 1x–2x rule (8px vertical, 16px horizontal). States: default, hover, focus, active, disabled, loading. The loading state reuses disabled styling and blocks repeat clicks.

```css
.btn {
  font: inherit;
  font-weight: 600;
  padding: var(--space-2) var(--space-4);   /* 8px x 16px: the 1x-2x rule */
  border-radius: var(--radius);
  border: 2px solid transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  transition: background-color 120ms ease, border-color 120ms ease;
}
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { filter: brightness(0.92); }
.btn-ghost {
  background: transparent;
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.btn-ghost:hover { background: color-mix(in srgb, var(--color-primary) 8%, transparent); }
.btn-text { background: transparent; color: var(--color-primary); }
.btn-text:hover { text-decoration: underline; }

.btn:active { transform: translateY(1px); }              /* active: pressed feel */
.btn:focus-visible {                                     /* focus: keyboard only */
  outline: 3px solid var(--color-primary);
  outline-offset: 2px;
}
.btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

.btn .spinner {                                          /* loading */
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: spin 700ms linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .btn { transition: none; }
  .btn .spinner { animation-duration: 2000ms; }
}
```

```html
<button class="btn btn-primary">Book appointment</button>
<button class="btn btn-ghost">Cancel</button>
<button class="btn btn-text">More details</button>
<button class="btn btn-primary" disabled aria-describedby="save-why">
  <span class="spinner" aria-hidden="true"></span> Saving
</button>
<p id="save-why">Available once every required field is complete.</p>
```

Note how the disabled/loading example pairs the state with a nearby explanation, per the book's rule that a disabled button should say why it is unavailable.

## 5. Icon with label (never an icon alone where meaning could be missed)

```css
.icon-btn {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: none; border: none; cursor: pointer; font: inherit;
}
.icon-btn svg { width: 24px; height: 24px; flex: none; }  /* 24px default icon size */
```

```html
<button class="icon-btn">
  <svg viewBox="0 0 24 24" aria-hidden="true"><!-- printer glyph from your icon library --></svg>
  Print
</button>
```

Use one icon library and one style (filled or outlined) across the product, ship icons as SVG, and never replace a universally understood glyph with a clever metaphor.

## 6. Standout call to action (Von Restorff, used once per view)

Make exactly one element in a set distinct (the primary action) and keep everything else in the family style. Distinctness here comes from the accent colour, which nothing else on the card uses.

```css
.plan { border: 1px solid var(--color-surface); border-radius: var(--radius); padding: var(--space-6); }
.plan-recommended {
  border: 2px solid var(--color-accent);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.08);
}
.plan-recommended .btn { background: var(--color-accent); color: #fff; }
```
