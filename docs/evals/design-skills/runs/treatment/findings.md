# Treatment run — raw findings

Condition: six-pillar audit + required reading:
`design/skills/uiux-design-foundations/{SKILL.md, references/checklists.md, references/ux-laws.md}`.
Agent: `reviewer` subagent. Target: `docs/evals/design-skills/fixture.html`.

## A. Pillar table

| Pillar | Score | One-line justification |
|---|---|---|
| **1. Copywriting** | **2** | CTA labels are short and action-first, but the only error string is a bare HTTP code, the empty state is "No data", and the privacy policy sentence is buried in 10px body text instead of being an explicit control. |
| **2. Visuals** | **2** | No focal point (three identical green buttons compete with a 20px H1), all five nav items are unlabeled icons, and the "Overview" glyph is a plus — a metaphor that collides with "Add holding". |
| **3. Color** | **2** | Token skeleton is sane, but `--muted` fails 4.5:1 on every surface it is used on, four error/button colours are hardcoded outside the tokens, the accent paints three primaries, and the checkbox uses the UA blue. |
| **4. Typography** | **2** | Four sizes (20/14/12/10) with no ratio scale, body at 14px below the 16px floor, a 10px privacy disclosure, and form controls that don't inherit the page font at all. |
| **5. Spacing** | **2** | Roughly half the spacing values are off the 8pt ladder (10, 12, 6, 28) and one flex row groups actions, a 14-option select and a privacy toggle at the same 8px proximity. |
| **6. Experience Design** | **1** | Two dead buttons, a swallowed-error refresh with no loading/disabled state, irreversible one-click deletion with no confirm or undo, a permanent error banner on load, and a global `outline: none`. |

## B. Findings

**1. BLOCKER — Global focus removal** — `:focus { outline: none; }` at line 63, with no `:focus-visible` replacement anywhere.
**Defect:** every interactive element loses its focus indicator.
**Consequence:** keyboard users cannot see where they are; the table, tabs, refresh and delete are all unusable without a mouse.
**Principle:** Buttons-and-states pass ("Focus state is clearly visible for keyboard users"); Flow audit ("sense of control"); Accessibility as both prospect and refuge.

**2. BLOCKER — Irreversible deletion with no confirmation or undo** — `.icon-btn` delete, lines 114–124, wired to `removeRow()` lines 135–141, with a 32×32 target sitting flush against numeric cells.
**Defect:** one click permanently removes a holding; there is no dialog, no undo, no toast, no server call.
**Consequence:** a mis-tap while scanning the income column silently destroys portfolio data.
**Principle:** Flow audit ("undo is available for consequential actions"); Fitts's Law (small, adjacent, high-consequence targets); Action Cycle — the Evaluation stage never happens.

**3. BLOCKER — Error banner rendered unconditionally on load** — `<div class="error" id="error">Error 422.</div>`, line 106.
**Defect:** raw status code, no cause, no affected field, no recovery action, no dismiss, and no code path that ever sets or clears it.
**Consequence:** every visitor is told the page failed before doing anything; they cannot interpret it (422 of what?) and have no next step. It also trains users to ignore the error region, so a real failure goes unnoticed.
**Principle:** Action Cycle (Interpretation — "vague error messages fail here"); UX-writing/NN error-message guidance; Inverted Pyramid (the critical message carries none of the needed detail).

**4. BLOCKER — Refresh produces no feedback and swallows failure** — lines 143–146: `fetch(...).catch(function () {})`, then `setTimeout(..., 4000)` with a `/* values would update here */` no-op.
**Defect:** non-2xx responses are never checked, network failures are silently eaten, no loading state, button never disabled during the request, and nothing visually changes afterwards.
**Consequence:** the user presses a button labelled "Refresh prices" and can never tell whether prices are fresh, stale, or the request failed — while believing the opposite of whichever is true.
**Principle:** Flow audit ("every interaction gets immediate feedback"); Action Cycle (Perception fails); Buttons checklist ("loading buttons block duplicate submission"); the `bg_poll`-style anti-pattern of invisible state.

**5. BLOCKER — Dead primary actions** — `<button class="primary">Export CSV</button>` (line 95) and `<button class="primary">Add holding</button>` (line 96) have no handler, no `id`, no form.
**Defect:** two of the three most prominent controls do nothing.
**Consequence:** the two core tasks of the screen — export the data, add a holding — are unreachable. The user retries, then distrusts every control on the page.
**Principle:** Action Cycle (Execution and Evaluation both fail); Flow audit ("clear goals — every button visibly serves the objective"); Aesthetic-Usability Effect caution — the polished dark surface makes dead controls look functional.

**6. BLOCKER — Empty state is two words and a dead end** — `'<div class="empty">No data</div>'`, line 139.
**Defect:** no explanation of why the table is empty, no "Add holding" CTA, no recovery path, and it is produced by destroying the table element.
**Consequence:** a user who removes their last holding lands on a blank screen with no way forward from the state itself — the exact moment they most need the next step.
**Principle:** Empty-state microcopy (state + reason + action); Action Cycle (Goal cannot be re-formed); Hick/Flow ("signpost the next step").

**7. WARNING — Privacy disclosure at 10px and ~3.98:1** — `.privacy` lines 62 and 128–131: `#6b7280` at `10px`.
**Defect:** the only sentence explaining that the portfolio is publicly readable is the smallest, lowest-contrast text on the page.
**Consequence:** users with low vision, or on a phone in daylight, cannot read the consequence of the toggle that governs it — the disclosure exists legally but not perceptually.
**Principle:** Colour checklist (4.5:1 everywhere); Prospect-refuge ("safety is visible… findable"); type-scale checklist (captions sized from the scale, not 10px).

**8. WARNING — Privacy is opt-out by default and outlives the user's attention** — `<input type="checkbox" id="share" checked>` (line 103) plus "Sharing stays on for 30 days after you last open the app" (line 130).
**Defect:** sharing is on by default, the label does not state the consequence, and exposure persists for 30 days after abandonment.
**Consequence:** a user's holdings are publicly linkable without them ever making a choice, and remain so after they stop using the product.
**Principle:** Prospect-refuge (user control and privacy, opt-in/opt-out); persuasive-design ethics (no dark patterns); cognitive load (the default performs the wrong work silently).

**9. WARNING — `--muted` fails 4.5:1 on both surfaces** — `#6b7280` on `--bg #0b0f14` = **3.98:1**; on `--panel #121821` = **3.69:1** (lines 13, 37, 53, 61, 62).
**Defect:** the muted token carries the subtitle, every `<th>`, the empty state and the privacy note — all text.
**Consequence:** column headers ("Ticker", "Shares", "Yield") and the page subtitle are unreadable at 4.5:1 for normal text; the audit trail of what each number means is lost. (The same colour on icons meets the 3:1 non-text threshold — the failure is text-specific.)
**Principle:** Colour-and-contrast checklist ("text contrast at least 4.5:1 everywhere"); no-information-by-colour-alone is respected, but the legibility floor is not.

**10. WARNING — Three primaries, one accent, no focal point** — `button.primary` applied to lines 94, 95 and 96; the single `--accent` is `#22c55e`.
**Defect:** three equal-weight solid accent buttons in one row.
**Consequence:** the accent stops meaning "the action here"; the eye has no entry point and the user must read all three labels to find the main task. Accent coverage also breaks the 10% budget of 60/30/10.
**Principle:** Von Restorff (exactly one standout, and it is the primary); Buttons checklist ("one primary button per view"); 60/30/10 with accent reserved for CTAs.

**11. WARNING — Green accent carries a second, financial meaning** — `--accent: #22c55e` (line 14) used for CTAs on a portfolio screen while no gain/loss colour encoding exists anywhere.
**Defect:** in a finance context green is a data signal (a gain), not only a brand/action colour, and here it is used exclusively for chrome.
**Consequence:** as the table grows to include gain/loss, the accent and the data palette will collide; users already primed by trading apps may read the CTA colour as a positive figure.
**Principle:** Jacob's Law / mental models (finance colour conventions are strong and pre-existing); Colour checklist ("palette matches the brand character").

**12. WARNING — Four hardcoded colours outside the token set** — `color: #04110a` (line 40), `background: #2a1215`, `border: 1px solid #7f1d1d`, `color: #fecaca` (line 48).
**Defect:** the error palette and the on-accent text bypass `:root` entirely.
**Consequence:** the error state cannot be re-themed, drifts on any palette change, and the literal `#04110a` ties the primary button to this exact green — change `--accent` and the button contrast silently changes with it.
**Principle:** Colour-as-a-system / 60-30-10 token discipline; checklist "headings and CTAs stay inside the palette family".

**13. WARNING — Native checkbox renders off-palette** — line 103, no `accent-color`, no custom styling.
**Defect:** the share toggle paints the user-agent default (system blue on Chromium/Windows) inside a green-on-charcoal palette.
**Consequence:** the most consequential control on the page is the only element not wearing the product's colours, lowering its perceived importance and breaking visual cohesion.
**Principle:** 60-30-10 discipline; Jacob's Law is satisfied but brand consistency is not; checklist "cohesive style unifies elements".

**14. WARNING — Icon-only navigation with no accessible name and no current state** — `.tabs`, lines 71–87; each `<button class="tab" title="…">` contains only an `<svg>`.
**Defect:** the accessible name depends on a `title` attribute (unreliable on touch, inconsistent across AT), there are no visible labels, no `aria-current`, no selected styling, and the current screen ("Dividends") is not among the five destinations at all.
**Consequence:** the user cannot answer "where am I / where can I go / how do I get back" — the navigation answers none of the three questions, and the Dividends screen is unreachable from its own nav.
**Principle:** Navigation/IA checklist (all three questions answerable on every screen); Icons checklist ("every ambiguous icon has a text label"); Miller (recognition over recall).

**15. WARNING — "Overview" is represented by a plus glyph** — line 73: `<path d="M3 12h18M12 3v18"/>`.
**Defect:** a plus is the universal "create/add" affordance, and the same page already has an "Add holding" CTA that should own that meaning.
**Consequence:** users will click the plus expecting to add something, or skip it as an add button; two controls now mean "add" and neither is labelled.
**Principle:** Jacob's Law and the metaphor checklist ("standard glyphs are never replaced by clever alternatives"); mental-model match.

**16. WARNING — Two icon scales, neither on the 24px default** — `.tab svg { width: 20px }` (line 35) and `.icon-btn svg { width: 16px }` (line 59).
**Defect:** primary navigation uses 20px, table actions use 16px — 16 is the documented floor, and neither is the 24px system default.
**Consequence:** the destructive control is the smallest icon on the page while being the most dangerous, and the two icon families read as different systems.
**Principle:** Icons checklist (24px default, no icon under 16px, sizes divisible by 8/4); consistency across the product.

**17. WARNING — Delete buttons have no accessible name and their column has no header** — `<th></th>` at line 110; the `<button class="icon-btn">` at lines 114, 118, 122 contains only an unlabelled `<svg>`.
**Defect:** no `aria-label`, no `<title>` inside the SVG, and the SVG is not `aria-hidden`, so it contributes no name; the column header is empty.
**Consequence:** a screen-reader user hears "button" three times, in an unnamed column, with no indication that activating it permanently deletes a holding.
**Principle:** Icons/aria pass ("every ambiguous icon has a text label"); Action Cycle for non-visual users — the goal cannot even be formed.

**18. WARNING — No type scale; body below the 16px floor** — `font: 14px/1.45` (line 21), `h1 { font-size: 20px }` (line 36), `.sub`/`th` `12px` (37, 53), `.privacy` `10px` (62).
**Defect:** four sizes (20/14/12/10) with no shared ratio; 14 below 16, 12 and 10 sized ad hoc rather than from the scale.
**Consequence:** the density reads as cramped, the two smallest sizes are the ones carrying meaning (headers and the privacy note), and any further component has no scale to inherit.
**Principle:** Typography checklist ("type scale follows one ratio… from a 16px base"; "body text at least 16px"; "captions sized from the same scale").

**19. WARNING — Form controls don't inherit the page type** — `button.primary` (39–42) and `select` (43–46) set no `font` or `font-size`.
**Defect:** `<button>` and `<select>` do not inherit `font` by default, so both fall back to the UA font (~13.33px) rather than the body's 14px system-ui.
**Consequence:** every CTA label and the range control are a different size (and potentially a different family) from the surrounding copy — a visible inconsistency exactly where the user is reading the action.
**Principle:** Type-as-a-system / typography checklist ("at most three typefaces, each with a clear role"); Jacob's Law consistency.

**20. WARNING — Spacing is half off the 8pt ladder** — `10px 16px` (41), `8px 12px` (45), `10px 12px` (49), `10px 12px` (52), `28px 12px` (61), `6px` radius (57), `12px` row margin (38).
**Defect:** 10, 12, 6 and 28 appear alongside 8/16/24/32 with no rule distinguishing fine detail from layout spacing.
**Consequence:** vertical rhythm drifts between the button row, the error banner and the table cells; nothing aligns to a shared baseline, which reads as "slightly off" without the user knowing why.
**Principle:** Spacing checklist ("every spacing value is a multiple of 8, 4 only for fine detail"; "the same relationship gets the same gap everywhere").

**21. WARNING — One flex row mixes three different kinds of control** — `.row` lines 93–104: three action buttons, a 14-option range select, and a privacy checkbox, all at `gap: 8px`.
**Defect:** actions, a data filter, and a settings toggle are given identical proximity and identical visual weight.
**Consequence:** the user cannot tell which controls change the data, which navigate away, and which change who can see it; the privacy switch reads as just another toolbar button.
**Principle:** Law of Proximity (group by real relationship, separate differently-purposed items); navigation checklist ("actions are visually separated from navigation"); cognitive-load grouping.

**22. WARNING — Fourteen range options, two of them unactionable** — `<select id="range">`, lines 97–102.
**Defect:** 1D through MAX plus "Since inception" and "Custom", in one flat list, with no custom-range UI behind "Custom", and a vague `aria-label="Range"`.
**Consequence:** decision time is spent on options that cannot be honoured ("Custom" is a dead end) and on granularity (1D, 1W) that is meaningless for an *annual* income projection.
**Principle:** Hick's Law (minimise choices, highlight a recommended one, sequence rather than dump); cognitive load ("hide extras until needed, explain unclear options"); IA — a filter should match the content's dimensionality.

**23. WARNING — The page's stated purpose is never computed** — H1 "Dividends" + "Projected income from your current holdings" (90–91), but the table (108–126) lists per-row income with no total.
**Defect:** no portfolio total, no forward-12-month figure, no "as of" date, no currency qualifier on "Annual income".
**Consequence:** the user must add three (or thirty) rows in their head to answer the question the page exists to answer — the interface pushes its own arithmetic onto the user.
**Principle:** Inverted Pyramid (key information first); cognitive load ("the interface absorbs complexity instead of the user"); Miller (chunk into a summary, not a list).

**24. WARNING — Instruction points at a control that does not exist** — "Manage access in Settings → Sharing", lines 129–130.
**Defect:** Settings is an unlabeled gear icon (line 84) and no "Sharing" destination exists in the nav.
**Consequence:** a user worried about exposure follows the one piece of guidance offered and hits a dead end, with no way to revoke sharing from this page.
**Principle:** Prospect-refuge ("safety is visible… settings findable"); navigation checklist ("the user can tell where they can go"); Action Cycle (Intention — the path is not visible).

**25. WARNING — No responsive strategy; the table clips instead of scrolling** — `table { width: 100%; overflow: hidden; border-radius: 8px }` (line 51) with five columns at `padding: 10px 12px` (52).
**Defect:** `overflow: hidden` on the table clips overflow rather than providing a scroll container, and no wrapper or column-collapse strategy exists.
**Consequence:** at narrow widths the Yield and action columns are cut off with no way to reach them — the delete control and a data column become untouchable rather than merely cramped.
**Principle:** Layout/grid checklist (grid type matches content, consistent gutters); Fitts's Law (targets pushed outside the reachable region).

**26. WARNING — No disabled states anywhere on the screen** — Refresh (94), Export CSV (95), Add holding (96), select (97).
**Defect:** none of the six button states beyond default is implemented (no `:hover`, `:focus-visible`, `:active`, `:disabled`, loading); Export stays enabled with an empty table.
**Consequence:** the user gets no affordance feedback on hover/press, can export nothing, and can fire duplicate refreshes.
**Principle:** Buttons checklist ("all six states designed"; "disabled buttons explain why"; "loading blocks duplicate submission").

**27. WARNING — Dynamic changes are silent to assistive tech** — error `div` line 106 has no `role="alert"`/`aria-live`; row removal and the empty-state swap (135–141) are unannounced.
**Defect:** no live region anywhere on a screen with three asynchronous or destructive interactions.
**Consequence:** a screen-reader user deletes a row and hears nothing — no confirmation, no count change, no announcement that the table is now empty.
**Principle:** Action Cycle (Perception and Interpretation for AT users); feedback-design rule ("confirm every action immediately").

**28. WARNING — Empty state destroys the table and drops focus** — `document.querySelector('#holdings').outerHTML = '<div class="empty">No data</div>'`, lines 138–139.
**Defect:** the whole `<table>` (thead, column headers, semantics) is replaced by a div; the activating button is removed from the DOM, so focus falls to `<body>`.
**Consequence:** keyboard and screen-reader users lose their position, the column structure disappears, and there is no way back to the table state short of a reload.
**Principle:** Action Cycle (Evaluation — the outcome is not interpretable); Flow audit (control after action); Proximity/structure consistency.

**29. WARNING — No freshness signal to evaluate against** — "Refresh prices" (94) with no timestamp, no "as of", no diff.
**Defect:** the page never states when the prices or projections were last updated, so the refresh action has nothing to be judged against.
**Consequence:** even if the refresh worked, the user could not complete the Action Cycle — there is no before/after to compare, so they cannot decide whether the outcome matches their goal.
**Principle:** Action Cycle (Evaluation); microcontent sharpness (a status line is the only contact the user has with data age).

**30. WARNING — Mixed numeric alignment** — `.num { text-align: right }` (54) applied to income and yield but not to Shares (`<td>24</td>`, line 113); `<th>Annual income</th>` carries no currency or period qualifier.
**Defect:** two of three numeric columns are tabular/right-aligned, one is left-aligned, and the money column's unit is only implied by a `$` in the cells.
**Consequence:** scanning a column of holdings to compare income is slowed by the misaligned middle column, and the header doesn't tell the user whether the figure is gross, net, trailing or forward.
**Principle:** F-pattern/scanning pass (structure for partial reading); layout consistency; UX-writing (microcontent must stand alone).

**31. WARNING — Touch targets below the comfortable size, packed together** — `select` at `padding: 8px 12px` ≈ 35px tall (45), `.icon-btn` 32×32 (57), `.tab` 40×40 (32).
**Defect:** the two highest-traffic controls on mobile (the range select and the delete buttons) sit under the 44px guidance, and the delete targets are adjacent to data cells.
**Consequence:** range selection becomes fiddly and deletion becomes prone to mis-taps — compounding finding 2, because the mis-tap has no undo.
**Principle:** Fitts's Law ("on mobile, size interactive elements for fingers and space them to prevent accidental taps on neighbours"); touch-target checklist.

**32. WARNING — Weak labels where precision matters** — `aria-label="Range"` (97), "Export CSV" (95), "Sharing stays on for 30 days…" (130).
**Defect:** "Range" doesn't say *of what*; "Export CSV" names the file format rather than the outcome (export holdings / download statement); the 30-day rule is stated as prose about the system's behaviour rather than as a user-facing choice.
**Consequence:** users must infer what a control does before using it, and the one consequential policy is phrased as trivia rather than a decision point.
**Principle:** UX writing ("labels are two to three words, action-oriented, and state the outcome"); microcontent sharpness; cognitive load ("self-explanatory labels").

**33. WARNING — Polish is masking the failures** — dark surfaces, tabular numerals, a restrained palette and a tidy table (lines 8–62, 108–126) over an error banner, two dead CTAs and an uncommunicative refresh.
**Defect:** the screen reads as finished while three of its six interactive surfaces do nothing or lie.
**Consequence:** reviewers and testers will over-credit usability (and under-report defects) because the surface is attractive — the exact failure the book warns about, and it is happening here.
**Principle:** Aesthetic-Usability Effect caution ("beauty can mask real usability problems during testing; never prioritise appearance over function").

**Scoring note (not softened):** Experience Design is the only 1, because it fails on four independent axes at once — no loading, no disabled, no confirmation/undo, and no feedback after any action. Color and Typography would each be a 1 on strict WCAG/copybook reading (a shared token used for all secondary text fails 4.5:1; body is under 16px); they hold at 2 only because the token architecture and the base text contrast are genuinely sound. Every score above is supportable from the source alone; nothing here required a browser.
