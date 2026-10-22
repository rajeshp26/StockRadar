# Baseline run — raw findings

Condition: six-pillar audit only. No design-skills reading.
Agent: `reviewer` subagent. Target: `docs/evals/design-skills/fixture.html`.

## A. Pillar scores

| Pillar | Score | Justification |
|---|---|---|
| 1. Copywriting | **2** | One good framing line ("Projected income from your current holdings."), but error copy is a raw `Error 422.`, empty state is `No data`, and half the labels describe behaviour the markup does not implement. |
| 2. Visuals | **1** | No focal point: three identical green buttons outrank the actual numbers, there is no total income, no active-tab state, no focus ring, and the destructive control is a 16px grey icon that reads as disabled. |
| 3. Color | **2** | A token layer exists, but four colours are hardcoded outside it, muted text fails 4.5:1 at every size it is used (3.98/3.69:1), separators are 1.21:1, and green is spent on three CTAs instead of on data. |
| 4. Typography | **2** | Five arbitrary sizes (10/12/14/20 + inherited), no scale tokens, 10px for the privacy disclosure, and identical weight on ticker, shares and income so the number that matters does not lead. |
| 5. Spacing | **2** | Mixed 4/8 base with off-scale 10, 12, 28, radii 6 and 8; grouping does not express relationships (error banner sits unattached between toolbar and table). |
| 6. Experience Design | **1** | No loading state, silent network failure, no confirmation or undo on delete, an empty state with no way back, and controls that are visually live but functionally dead. |

## B. Findings

1. **BLOCKER — Delete buttons (`fixture.html:114`, `118`, `122`, handler `135-141`).** A single click on a 16px icon permanently removes a holding from the DOM. No confirmation dialog, no undo, no aria-label, no persistence call. *Consequence: an easy misclick silently destroys portfolio data with no recovery path.*

2. **BLOCKER — Empty state (`fixture.html:137-140`).** Deleting the last row replaces the whole `<table>` via `outerHTML`, so the table, its headers and its add-row context cease to exist. Copy is `No data` with no explanation and no "Add holding" action. *Consequence: a user who empties the list is stranded; only a page reload restores a usable screen, and any real re-render logic would have no mount point.*

3. **BLOCKER — "Share portfolio" checkbox (`fixture.html:103`, plus claim at `128-131`).** `checked` by default, no handler, and the privacy paragraph states the portfolio is publicly visible to anyone with the link while it is on. The privacy note is not adjacent to the control and the checkbox has no confirmation of state change. *Consequence: users emit a public-share posture they never chose, on a control that does nothing when toggled — the UI asserts a data exposure it cannot perform and the user cannot stop.*

4. **BLOCKER — Error region (`fixture.html:47-50`, `106`).** Statically rendered on every load as `Error 422.` — a raw HTTP status with no cause, no affected action, no retry, no dismiss, no `role="alert"` or `aria-live`. *Consequence: the app looks permanently broken on first paint, screen-reader users are never notified of real errors, and the user cannot tell whether the last refresh worked.*

5. **BLOCKER — Global focus suppression (`fixture.html:63`).** `:focus { outline: none; }` with no `:focus-visible` replacement anywhere. *Consequence: keyboard and switch users cannot see where they are; the 5 icon tabs, range select and three CTAs are unnavigable.*

6. **BLOCKER — Icon-only controls have no accessible name (`fixture.html:72-86`, `114-124`).** Tabs carry only `title` (tooltip, unreliable as a name) and no `aria-label`; delete buttons have neither, and no `aria-hidden` on the SVGs. *Consequence: a screen reader announces five unnamed buttons and three unnamed delete buttons; the user cannot know which holding they are deleting.*

7. **BLOCKER — Refresh flow (`fixture.html:143-146`).** `fetch(...).catch(function () {})` swallows every failure, then a `setTimeout` does nothing (`/* values would update here */`). *Consequence: a failed refresh is indistinguishable from a successful one, prices never visibly update, and the user keeps trusting stale income figures.*

8. **BLOCKER — No destructive-action confirmation, and the destructive control is styled as disabled (`fixture.html:55-58`).** `.icon-btn` uses `color: var(--muted)` and a transparent background, so the delete affordance sits at 3.98:1 and looks inert next to live content, while still being clickable. *Consequence: the control is simultaneously undiscoverable when wanted and easy to trip when not.*

9. **BLOCKER — Dead controls presented as live (`fixture.html:95`, `96`, `97-102`, `103`).** `Export CSV`, `Add holding`, the 14-option range `select`, and the share checkbox have no listeners at all — only `#refresh` is wired. *Consequence: four of five toolbar controls do nothing; the user assumes data loss or a broken build and cannot complete the screen's primary job (adding a holding).*

10. **WARNING — Three equal primary CTAs (`fixture.html:94-96`).** `Refresh prices`, `Export CSV` and `Add holding` all use `.primary` with the same green fill, same padding, same weight, in a single flex row. *Consequence: no primary action exists; the accent is diluted and the eye has four competing targets in one strip.*

11. **WARNING — No total projected income (`fixture.html:108-126`).** The page's stated purpose is projected income, yet only per-row values exist; no sum, no currency label, no annualisation basis. *Consequence: the user must add three numbers mentally — the one figure the screen exists to show is absent.*

12. **WARNING — Muted text contrast (`fixture.html:13`, used at `33`, `37`, `53`, `56`, `61`, `62`).** `#6b7280` measures **3.98:1 on `--bg`** and **3.69:1 on `--panel`**, used at 12px (sub, th) and 10px (privacy). *Consequence: subtitle, column headers, tab icons and the privacy disclosure all fail WCAG AA for their sizes — the weakest text is the text users most need to read.*

13. **WARNING — Row separators and card edges invisible (`fixture.html:11`, `52`).** `--line #1f2937` is **1.21:1 against `--panel`** and **1.31:1 against `--bg`**; the panel itself is 1.08:1 against the background. *Consequence: row boundaries and the table's edge dissolve; on a low-brightness display the table reads as an undifferentiated block of numbers.*

14. **WARNING — Privacy disclosure is the smallest text on the page (`fixture.html:62`, `128-131`).** 10px muted, placed last, beneath the table. *Consequence: the single most consequential statement in the screen (public link visibility, 30-day auto-share) is the least legible element.*

15. **WARNING — Hardcoded colours outside the token layer (`fixture.html:40`, `48`).** Button label `#04110a`, error `#2a1215` / `#7f1d1d` / `#fecaca` are inline literals; only six colours live in `:root`. *Consequence: the error styling cannot be themed or audited with the rest of the palette, and future dark/light or high-contrast work will miss it.*

16. **WARNING — Accent misapplied (`fixture.html:14`, `39-42`).** Success-green is used exclusively as a generic button fill and never on the data (yields, income, gains), and three uses push accent well past a 10% share of the screen's colour. *Consequence: green reads as "primary button" rather than "positive money", so the palette gives no financial meaning while still dominating the viewport.*

17. **WARNING — No active tab state (`fixture.html:71-87`).** All five tabs render identically (`--muted`), no `aria-current`, no selected style, and the Dividends screen is not represented in the tab set at all. *Consequence: the user cannot tell which section is open, or that Dividends is a section they are in.*

18. **WARNING — Range selector is both mis-scoped and inert (`fixture.html:97-102`).** Fourteen options (1D…MAX, Since inception, Custom) are offered on a screen about annual projected income; `Custom` has no date inputs; the control has no handler. *Consequence: a false promise of interactivity and a decision the user is asked to make that changes nothing.*

19. **WARNING — No freshness indicator for prices (`fixture.html:94`).** Nothing states when values were last updated, and refresh gives no completion cue. *Consequence: the user cannot judge whether the income figures are current — the core trust question for a portfolio screen.*

20. **WARNING — No disabled/busy state on refresh (`fixture.html:94`, `143-146`).** The button stays enabled through the request and the 4s timer; repeated clicks fire repeated fetches. *Consequence: duplicate refresh requests and no feedback that anything is in flight.*

21. **WARNING — Typographic scale and weight usage (`fixture.html:21`, `28`, `36`, `37`, `41`, `53`, `62`).** Sizes jump 14 → 20 → 12 → 10 with no ratio; weights mix 400/600/700 but 700 is used for both the brand and ordinary buttons, and every table cell is 400 at 14px. *Consequence: hierarchy is carried by colour alone, and the income column does not outrank the ticker column.*

22. **WARNING — Numeric alignment inconsistency (`fixture.html:54`, `110`).** `td.num` is right-aligned with `tabular-nums`, but `Shares` (a numeric column) is left-aligned and non-tabular. *Consequence: digits do not line up down the column, slowing comparison across holdings.*

23. **WARNING — Off-scale spacing values (`fixture.html:39-42`, `49`, `57`, `61`, `62`).** Padding/margins use 10, 12, 28 alongside 4/8/16; radii use both 6 and 8 for equivalent controls (`.icon-btn` 6, `.tab` 8, buttons 8). *Consequence: controls that behave alike do not look alike, and vertical rhythm drifts between sections.*

24. **WARNING — Error banner is unanchored and undismissable (`fixture.html:106`).** It is placed between the toolbar and the table with a 12px gap — the same gap as row spacing — so it reads as page content rather than a transient notice, and there is no close control. *Consequence: the error competes with the data for attention and cannot be cleared from the user's view.*

25. **WARNING — Focus is lost after deletion (`fixture.html:135-141`).** Removing the row leaves focus on a detached node; focus falls to `<body>` with no announcement of what was removed. *Consequence: keyboard and screen-reader users lose their position in the list after every delete and must re-navigate from the top.*

26. **WARNING — Empty header cell for the action column (`fixture.html:110`).** The final `<th>` is empty and unlabelled. *Consequence: screen readers announce a blank column header; the column has no semantic identity.*

27. **WARNING — No landmarks (`fixture.html:69-88`, `108`).** Top bar and tabs are plain `<div>`s with `<button>`s; there is no `<nav>`, `<main>`, or `<header>`, and the table has no `<caption>`. *Consequence: landmark navigation is unavailable, and the table's subject (dividends, per year, per holding) is never stated in the accessibility tree.*

28. **WARNING — Ambiguous export scope (`fixture.html:95`).** `Export CSV` names no dataset, no range, no destination. *Consequence: the user cannot predict whether they are exporting three rows or the whole portfolio, or where the file goes.*

29. **WARNING — Yield basis undefined (`fixture.html:110`).** The `Yield` header gives no basis (trailing? forward? yield-on-cost?) and no corresponding timeframe, while the range selector implies a timeframe that does not apply. *Consequence: a 0.51% and a 1.28% cannot be compared meaningfully, and the user may make allocation decisions on mismatched definitions.*

**Not defects, for the record:** the shell has a single `<h1>`, `lang` is set, the viewport meta is correct, `--text` on panel is 14.39:1, the primary button label is 8.46:1, and the error text on its own background is 12.14:1 — the problem with the error banner is its copy and permanence, not its contrast.
