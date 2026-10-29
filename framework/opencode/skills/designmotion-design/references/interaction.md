# Interaction patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 0. CSS Has Selector

- Source: https://designmotionhq.com/patterns/css-has-selector
- Takeaway: let the browser style a parent from state that already lives inside it, instead of copying that state into app code only to switch a class.
- Rules: a card can react when its own checkbox or radio is checked, with support in all major browsers since 2023. Prefer `:user-invalid` over `:invalid` so errors appear only after the user leaves a field, and style border, label and icon from one container rule. Dim a submit button while any field is invalid, with no derived state. Let layout follow the DOM: a rendered sidebar widens the grid, and a quantity query tightens gap, padding and type once a fifth card arrives. Lock page scroll while a dialog is open; closing it reverts the lock with no cleanup effect.
- Do: reach for `:has()` when state already lives in the DOM: checked, open, invalid, or child count.
- Do not: mirror DOM state into framework state only to toggle a class the browser can compute.
- Original example: `.plan:has(:checked) { border-color: var(--accent); }`

## 3. Bulk Actions

- Source: https://designmotionhq.com/patterns/bulk-actions
- Takeaway: bulk selection is a small system of honest counts, persistent selection and forgiving undo, not a lone header checkbox.
- Rules: the header checkbox needs three states: empty, partial (indeterminate dash) and checked, and partial must resolve to select-all, never to clear. Name the number: when select-all only grabs visible rows, offer the full matching scope, for example "Select all 247 matching". Keep the count honest as filters change, updating it live, for example from 247 to 96. Keep selection in application state, not DOM state, so shift-click ranges survive paging. For destructive bulk actions, skip the confirm modal: echo the count, run at once, and offer a 10 second undo with a draining countdown ring.
- Do: give the header checkbox all three states and let the partial dash resolve to select-all.
- Do not: store selection in the DOM, where it resets on a page change.

## 4. Disabled Buttons

- Source: https://designmotionhq.com/patterns/disabled-buttons
- Takeaway: a disabled submit button hides both the block and its reason, so keep the button live and explain what is missing instead.
- Rules: a disabled button drops out of tab order, so keyboard users skip it and screen readers stay silent. Pointer events are dead on a disabled element, so a tooltip meant to explain the block never fires. Greyed labels often fail contrast, near 1.9:1 against a 4.5:1 threshold. Keep the button live and validate on click: highlight blocking fields and move focus to the first one. Keep disabled and loading distinct: during a request, hold focus, show a spinner and report `aria-busy`.
- Do: keep the button enabled, validate on click, flag blocking fields and move focus to the first one.
- Do not: rely on a tooltip to explain a disabled control.

## 5. Hover Trap

- Source: https://designmotionhq.com/patterns/hover-trap
- Takeaway: hover is desktop only, so anything important hidden behind it is unreachable on touch; give every action a tap-reachable home.
- Rules: touch has no hover, so the browser fakes one: the first tap becomes a sticky hover that freezes revealed actions until the user taps elsewhere. Never bury a primary action behind hover; hover should surface extras only. Give hover-only actions a touch home: in the card, behind a swipe, or inside a bottom sheet. Gate hover styles with `@media (hover: hover)` instead of sniffing the user agent. Pair that with `pointer: coarse` to grow controls for a thumb, padding the hit area to 44px even when the visible glyph is only about 20px.
- Do: reveal only secondary extras on hover, keeping every primary action reachable by tap.
- Do not: size a tap target to a 20px icon, or detect touch by user-agent sniffing.

## 6. Behind the Button

- Source: https://designmotionhq.com/patterns/behind-the-button
- Takeaway: a click is a pipeline: fast client checks, strict server re-checks, atomic writes, and server truth repainted in the UI, and money must wait for confirmation.
- Rules: client validation exists for speed, not safety: inline errors fire with no network calls. The server re-runs every check, only stricter; never trust the client, and recompute totals from your own catalogue instead of believing a browser-sent price. Wrap related writes (order, items, inventory, payment) in one transaction: if one row fails, every row rolls back. When the response returns, repaint with server truth, the real order ID the server created, not a locally guessed value. Optimistic UI fits cheap reversible actions (like, favourite, rename); money is different, so hold the spinner until the server confirms.
- Do: validate on the client for speed and on the server for trust, never one instead of the other.
- Do not: use optimistic UI on payments or other irreversible actions.

## 9. Inline Editing

- Source: https://designmotionhq.com/patterns/inline-editing
- Takeaway: inline editing works when the swap is invisible: same size, same place, clear commit and cancel keys, and the cost of a typo decides how free it should be.
- Rules: editable text must whisper its affordance: a pencil on hover or a soft background tint. Keep every pixel in place during the swap: same font, size and padding, with the border going from transparent to accent. Enter commits and Escape cancels; blur is contested (some apps save on click-away, others discard), so pick one rule and never break it. Save optimistically: text updates on screen while the request is in flight, and on failure roll back, keep the draft and say why. Match the mode to the cost of a typo: make every cell editable when mistakes are cheap, or require an explicit Edit action when they are expensive.
- Do: signal editability on hover and keep font, size and padding identical between text and input.
- Do not: change what blur does from one screen to the next.

## 10. Live Cursors

- Source: https://designmotionhq.com/patterns/live-cursors
- Takeaway: shared cursors should feel like people gliding across a canvas, not jumping between network ticks, and each person should stay recognisable.
- Rules: stream about 10 positions per second and interpolate to 60fps so cursors glide. Hash each user's colour from their ID so it stays stable, rather than assigning colours randomly per session. Show an avatar stack with an overflow count when many people are present. Lock an element in the editor's colour on selection so ownership is visible. Offer follow mode instead of a screen share when someone wants to watch another person work.
- Do: interpolate between ticks.
- Do not: render at the raw tick rate, or assign colours randomly per session.

## 11. Destructive Actions

- Source: https://designmotionhq.com/patterns/destructive-actions
- Takeaway: treat danger as a whole language of placement, colour, wording and delay, rather than trusting a single red button to warn.
- Rules: a hold-to-confirm gesture, with a ring filling over roughly 300ms, can replace a modal; letting go early cancels it. Put the exact verb on the button, such as Delete project versus Keep project, instead of a generic Yes or No that people skim past. Keep delete out of the spot where confirm normally sits, because muscle memory clicks that spot without thinking. Spend red only on destruction; using it for logout or badges makes a real delete look routine. Put deletion in a labelled danger zone at the foot of the page, and give truly irreversible deletion a cancelable grace period, for example 14 days.
- Do: name the action on the button and add friction through a hold, a danger zone, or a cooldown.
- Do not: rely on an unread "Are you sure?" dialog, or scatter red everywhere.
- See also: Undo UX in feedback.md for the recovery side of this pattern.

## 12. Context Menu

- Source: https://designmotionhq.com/patterns/context-menu
- Takeaway: a context menu only works when it measures the screen, groups actions by intent, and survives the diagonal mouse move to a submenu.
- Rules: measure before opening: flip up when there is no room below, mirror left when there is no room to the right, and stay anchored to the cursor inside the viewport. Group a dozen or so actions by intent with dividers, pairing Rename with Duplicate and Share with Copy link, and isolate Delete at the bottom in red. Draw an invisible safe triangle from cursor to submenu so diagonal movement does not kill the submenu. Support keyboard use: arrows walk the list, a letter jumps to a matching item, and Escape closes one level rather than the whole menu. Mobile has no right-click, so a long press should open the same actions as a bottom sheet.
- Do: flip and mirror the menu to fit the viewport, and add the safe triangle for submenus.
- Do not: ship a flat ungrouped list, or a right-click-only menu.

## 18. Drag and Drop

- Source: https://designmotionhq.com/patterns/drag-and-drop
- Takeaway: moving a card is moving state, so the drag must confirm the lift, reveal the landing spot before release, and make a wrong move cheap to reverse.
- Rules: confirm a grab with three cues at once: a slight scale-up, a deeper shadow and a small tilt. Reveal drop zones before release, not after. Match the cue to its scope: an insertion line to slot between items, a filled highlight to land inside a whole column. On structured surfaces, snap to the nearest valid slot and expose slots with dashed outlines while dragging; reserve free positioning for canvases where any coordinate is valid. Pair every drop with a short undo toast, around five seconds.
- Do: confirm pickup with scale, shadow and tilt together, and highlight the exact drop target during the drag.
- Do not: snap a released card into place with no lift or shadow, or make a wrong drop permanent.

## 19. Dropdown Design

- Source: https://designmotionhq.com/patterns/dropdown-design
- Takeaway: a dropdown feels premium when its trigger is unmistakably tappable, its menu never runs off screen, and it works fully from the keyboard.
- Rules: use a 48px trigger with a visible caret and hover state. Flip the menu upward when room below runs out. Support arrows, Enter and Esc. Add in-menu search past roughly 10 items. Animate opening in about 150ms, not 50ms or 500ms.
- Do: build trigger, placement and keyboard behaviour as one system.
- Do not: ship a small low-contrast trigger whose menu clips at the viewport edge.

## 30. Peak-End Rule

- Source: https://designmotionhq.com/patterns/peak-end-rule
- Takeaway: people judge an experience not by averaging it, but by its most intense moment and its final moment.
- Rules: flows with the same average are remembered differently by their finish. Engineer one intentional peak, such as a surprise perk, since one delight can outweigh five neutral steps. Give the ending disproportionate care. Audit every flow's final interaction. Guard the finish, because a broken last step can sink a smooth experience.
- Do: concentrate effort on a deliberate peak and a celebratory, frictionless ending.
- Do not: spread effort evenly while neglecting the finish, or end on friction or a cold dead end.
- See also: Zeigarnik Effect in feedback.md, which covers the pull of an unfinished loop rather than the memory of a peak and an end.

## 33. Search Experience System

- Source: https://designmotionhq.com/patterns/search-experience-system
- Takeaway: search is a five-part system: placeholder, recents, autocomplete, keyboard flow, and zero-results recovery, and most apps skip several parts.
- Rules: write descriptive placeholders, not a bare "Search". Surface recent searches on focus. Rank autocomplete by clicks, not alphabetically, tag suggestions with category badges, and prefer three sharp results over ten noisy ones. Keep the flow keyboard-driven with a visible focus ring. Never leave zero results as a dead end: offer popular searches or alternate spellings.
- Do: onboard via the placeholder and turn empty results into recovery paths.
- Do not: ship a bare placeholder, sort suggestions alphabetically, or leave "No matches" with nowhere to go.
- See also: Command Palette (57) for the keyboard-driven command system that sits beside visible search and navigation.

## 36. Star Rating

- Source: https://designmotionhq.com/patterns/star-rating
- Takeaway: five stars look trivial, but hover preview, half-fills and honest averages are where the widget usually breaks.
- Rules: preview on hover rather than waiting for the click, so users see the value they are about to commit. Keep preview separate from the committed value, snapping back to the saved rating when the pointer leaves without clicking. For averages, render fractional stars: a 4.4 is four full stars plus a fifth clipped to 44%, not five full stars rounded up. Stagger the fill by about 30ms per star, left to right. Use fractional fill for input precision too, and pair stars with a summary view: an average ring plus a distribution breakdown.
- Do: fill stars ahead of the cursor on hover and render partial fills for averages.
- Do not: round averages up to full stars, or leave the preview stuck on the hovered value after the pointer leaves.

## 41. Tooltip Design

- Source: https://designmotionhq.com/patterns/tooltip-design
- Takeaway: a tooltip should feel like a quiet hint that arrives only when wanted, points unambiguously at its trigger, and gets out of the way on demand.
- Rules: wait about 300ms before showing a hover tooltip, so a passing cursor does not trigger it on every graze. Attach it to its trigger with an arrow; without one, a label floating over a row of icons leaves people guessing what it describes. Flip it to the opposite side when the trigger is near a viewport edge, so it is never clipped off-screen. Make it dismissible in every way that matters: mouse leave, Escape, loss of focus, and a tap outside. Keep copy tight, roughly 300px wide and one sentence long; if the explanation needs a paragraph, it is documentation, not a tooltip.
- Do: delay briefly, point with an arrow, and flip near edges.
- Do not: fire instantly on every cursor pass, or cram documentation-length text into one tip.

## 46. Swipe Actions

- Source: https://designmotionhq.com/patterns/swipe-actions
- Takeaway: swipe actions are invisible by default, so without a hint, a safe commit step and a visible alternative, they stay undiscovered, or worse, delete things by accident.
- Rules: show an affordance hint, such as a peek of the action on first scroll or an onboarding nudge. Add friction to destructive swipes: reveal the button on a partial swipe and require a tap to commit, or pair a full swipe with an undo toast. Colour-code by consequence, with neutral actions on surface tones and destructive actions in red, keeping that mapping consistent across every list. Never make swipe the only path: every swipe action needs a visible fallback, such as a long-press menu or a button in the detail view. Keep the set small and left/right meanings consistent app-wide, so users build muscle memory.
- Do: pair each swipe action with an undo window, and keep left/right semantics consistent everywhere.
- Do not: hide more than two actions per side, or make a destructive swipe commit on one unguarded gesture.

## 48. Bottom Sheets

- Source: https://designmotionhq.com/patterns/bottom-sheets
- Takeaway: on tall phones the top of the screen is a dead zone for one-handed use, so menus and actions belong at the bottom where the thumb naturally rests.
- Rules: screens keep getting taller while thumbs stay the same length, turning the top into a dead zone. Anchor menus and actions to the bottom instead of the top-right corner most navs default to. Unlike a full modal that blocks everything, a bottom sheet keeps the underlying page visible so users never lose their place. Add snap points so the sheet can rest half-open or expand to full height. Support drag-to-dismiss, and dim the background with a scrim while locking body scroll so only the sheet moves.
- Do: place primary actions within thumb reach at the bottom, keep the page visible behind the sheet, and offer snap points and drag-to-dismiss.
- Do not: bury frequent menus in the top-right dead zone, or leave the background scrollable while the sheet is open.
- See also: Modal Hierarchy (64) for choosing between a sheet, a drawer, a popover and a blocking modal.

## 54. Color Picker UX

- Source: https://designmotionhq.com/patterns/color-picker-ux
- Takeaway: a colour picker should be a decision tool whose every choice cascades into the rest of the UI, not just a gradient with a slider.
- Rules: offer OKLCH next to hex: hex is for machines, while OKLCH lightness, chroma and hue let one changed number produce a predictable shade. Give the picker memory: recent swatches and saved palettes put the last five picks one tap away. Show a live contrast ratio at pick time, with a badge that flips red to green, to kill failing pairs before they ship. Preview alpha over a checkerboard on both light and dark backgrounds, since transparency lies on a white canvas. Turn one pick into a system by generating tints and shades from a single hue to produce ten tokens from one decision.
- Do: expose human-readable formats such as OKLCH, surface recent swatches and saved palettes, and validate contrast live while picking.
- Do not: preview alpha only on white, or ship a bare gradient-and-slider picker with no memory, contrast check or palette output.

## 57. Command Palette

- Source: https://designmotionhq.com/patterns/command-palette
- Takeaway: a command palette should be a complete command system, not a narrow search box.
- Rules: match fuzzy subsequences, so partial abbreviations still surface commands. Group results under labels like recent items, actions and pages. Keep it fully keyboard-driven: arrows move, Enter runs, Esc closes or steps back. Prefill recent or suggested commands, never opening empty. Show async work with an inline spinner, keeping the palette open. Allow drill-in to a sub-menu with a breadcrumb.
- Do: prefill so there is always something to act on.
- Do not: demand an exact match, then show a dead "no results" state.
- See also: Search Experience System (33) and Navigation Patterns in navigation.md. The palette is a power-user accelerator, not the only path.

## 58. Filter Chips

- Source: https://designmotionhq.com/patterns/filter-chips
- Takeaway: a few taps should visibly shrink a large result set, and users should always see why it shrank.
- Rules: give each chip three distinct states: idle, active (filled, with a check), and disabled when nothing lies behind it. Make logic legible: OR inside one group widens results, AND across groups narrows them. Update the result count on the same frame as the tap. Provide one clear-all reset paired with a live count. Keep overflowing chips in one horizontally scrolling row with a fade hinting at more. Pin active filters in a sticky summary bar.
- Do: make active and idle states clearly different.
- Do not: wrap chips into rows that push results below the fold.

## 61. Accordion Disclosure

- Source: https://designmotionhq.com/patterns/accordion-disclosure
- Takeaway: a smooth expanding panel comes from a few small coordinated choices, not one large animation.
- Rules: do not animate `height: auto`, which snaps; use a grid transition from `grid-template-rows: 0fr` to `1fr`, or a measured pixel height. Drive chevron rotation from the same curve as the panel, since a few frames of lag reads as broken. Match the open rule to content: one at a time for steps, many open for FAQs. Make the header a real `<button>` with `aria-expanded` and `aria-controls` wired to the panel. Anchor a lower item's header on expansion, so the list does not jump.
- Do: move chevron and panel as one unit.
- Do not: animate `height: auto` and expect a transition.
- Original example: `.panel { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 250ms ease-out; } .panel[open] { grid-template-rows: 1fr; }`

## 62. Data Table

- Source: https://designmotionhq.com/patterns/data-table
- Takeaway: a table should behave as a navigable system, not as a loose grid of divs.
- Rules: make sorting tri-state: ascending, descending, then back to the original order, so a binary flip cannot lose it. Right-align numeric columns and use tabular figures, so digits line up. Keep the header sticky vertically and freeze the first column horizontally, each with a subtle shadow. Treat density as a token, switching row heights such as 36, 48 and 60 pixels. Make the whole row the selection target, with tint, an accent bar and a checkbox. Show partial selection as empty, then indeterminate dash, then checked.
- Do: right-align numbers with tabular figures.
- Do not: rely on a tiny checkbox-only hit target.
- See also: Bulk Actions (3) for the selection system that sits on top of a table.

## 64. Modal Hierarchy

- Source: https://designmotionhq.com/patterns/modal-hierarchy
- Takeaway: most overlay mistakes come from picking the wrong overlay weight for the job.
- Rules: start by asking whether the action blocks the user; if yes, use a modal, and if no, choose by context among sheet, popover and drawer. Reserve a centred modal with a full scrim for a single critical or destructive decision. Use a bottom sheet as the mobile-first default, sliding up with a drag handle and snap points while keeping the screen behind partly visible. Use an edge drawer for navigation, sliding in from the side while the app stays alive behind it. Keep a popover small, about 200 pixels wide and anchored to its trigger, for lightweight menus, never for blocking flows.
- Do: reserve modals for decisions that demand a response.
- Do not: bury navigation inside a blocking overlay when a drawer fits.
- See also: Bottom Sheets (48) and Context Menu (12) for the lighter overlay options in this hierarchy.
