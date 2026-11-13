---
name: designmotion-design
description: Apply UX-pattern system rules from designmotionhq on TikTok: choose the right component system, states, feedback timing and failure modes when building a UI, with 76 paraphrased patterns and original example snippets. Use when designing or reviewing a screen, form, table, navigation, feedback surface, or motion, and you need the system rules rather than a code effect or a general design principle.
---

# Designmotion Design

Apply UX pattern system rules from designmotionhq when you build or review a user interface. Use this skill when you need to decide what system a component belongs to, which states it must cover, how fast it must respond, and how it should fail. Use it for screens, forms, tables, navigation, feedback surfaces, overlays, and motion. For pure CSS effects and copy-paste snippets use `framework/design/skills/ania-kubow-design`; for React implementation in this repo use `frontend-react`; for general principles and named UX laws use `framework/design/skills/uiux-design-foundations`. This repository has no `settigation-code` or `practical-ui` skill — do not send a reader looking for either.

**In this repository:** `apple-ui` owns finance visual tokens, motion values and data-viz and
wins on those; this skill owns interaction behaviour and wins where `apple-ui` is silent.
Implement with `frontend-react`. Precedence and mandatory routing:
`framework/opencode/skill-routing.md`.

## Start from the system, not the widget

- Name the system before you build the widget. A toast is one surface inside a notification system. A skeleton is one member inside a loading system. A tab is one control inside a navigation system.
- List every state the system can be in before you write markup. Include default, focus, error, success, disabled, loading, empty, partial, offline, and undo where they apply.
- State the failure mode in the same breath as the happy path. Say what happens when the server rejects, the connection drops, the list changes under the user, or the action cannot be undone.
- Keep one primary action per view. Demote everything else, and isolate only that action with colour, scale, or a badge, never two or three at once.
- Respect the platform the user is on. Put frequent actions within thumb reach on mobile, keep primary navigation visible, and never make hover the only path to an action.

## Choose the right pattern

- Use an interaction pattern when the user acts on something. Use bulk actions for multi-select, destructive actions for danger, drag and drop for reordering, a context menu for right-click or long-press actions, and a command palette as a power-user accelerator beside visible navigation.
- Use a form pattern when the user enters or edits data. Use field states for the six text-field states, validation timing for when errors appear, a stepper wizard for long forms, and the specific input patterns for dates, ranges, masks, passwords, codes, and uploads.
- Use a feedback pattern when the system must answer the user. Use the loading system to pick a waiting pattern, the notification system to pick a surface, toasts for low-priority messages, error states for recovery, and undo for reversible harm.
- Use a navigation pattern when the user moves through the product. Use navigation patterns to pick tabs, sidebar, or hamburger by platform and depth. Use tabs for switching within a view. Use focus states for keyboard travel. Use pagination for stable movement through a changing list.
- Use a visual pattern when the eye must find the right thing first. Use hierarchy for reading order, proximity and Gestalt laws for grouping, grid and golden ratio for layout, tokens and a system kit for scales, and shadow, radius, and depth for cards.
- Use a motion pattern when movement must feel deliberate. Use animation timing for durations, easing curves for curve shapes, card hover for coordinated lift, and scroll-driven animations for motion tied to scroll.
- Use a content pattern when words and order carry the message. Use empty states for first impressions, microcopy for labels and errors, serial position for list order, and the landing skeleton for page order.
- Look the pattern up in references before you apply it. Each reference entry gives the source URL, the takeaway, the concrete rules with numbers and thresholds, and a do and a do-not.

## Apply the cross-cutting rules

- Answer within 400ms. Treat under 200ms as instant, 200ms to 400ms as tolerable, and over 400ms as a disconnect, even if the real work takes longer. Use a skeleton, an acknowledgement, or an optimistic update inside that window.
- Match the waiting pattern to what you know. Show nothing under about 300ms. Use a skeleton only when the content shape is known and the wait exceeds roughly 300ms. Use a spinner for short unknown waits under about 3s. Use a progress bar over about 3s when a percentage is known. Use optimistic updates only for reversible actions.
- Prefer undo over confirmation for reversible harm. Execute at once, echo what happened, and offer a visible countdown. Reserve heavy friction, such as typing a resource name, for actions with no way back. Soft-delete with a recovery window where one applies.
- Keep counts, labels, and selection honest as context shifts. Update a bulk count when a filter changes. Keep selection in application state so it survives paging. Never label a partial set with a bare "all".
- Make every state visible to every input method. Keep focus visible and in DOM order, trap focus in modals and return it on close, support keyboard operation for tabs, sliders, menus, and palettes, and pair colour with an icon, label, or pattern.
- Keep motion coordinated and timed. Let entrances run 200ms to 300ms with ease-out, make exits faster than entrances, fire tap feedback in under 100ms, and stagger list items by about 50ms. Never animate height auto, and never scale a whole card and shift its neighbours.
- Build hierarchy by stacking signals. Use size, colour, contrast, spacing, and weight together for one focal point. Reserve one accent for the primary action. Use spacing contrast to group, and break a grid only after establishing it.
- Name values with tokens, not literals. Layer tokens as primitives, then semantic, then component. Treat dark mode as a token-set swap, not an inversion, with near-black surfaces, layered elevation, desaturated accents, and soft off-white text.

## Keep close relatives distinct

- Keep Loading States System, Skeleton Loading, and Optimistic UI distinct. The first picks the waiting pattern. The second details only the skeleton member. The third details only the instant-update member.
- Keep Toast Notifications and Notification System distinct. The first details toast placement, lifetimes, and stacking. The second decides which surface, toast, banner, modal, or badge, fits the severity.
- Keep Tabs System and Navigation Patterns distinct. The first details the tab control, its indicator, and its panel change. The second decides when tabs, a sidebar, or a hamburger are the right navigation shape.
- Keep Toggle Anatomy and Form Field States distinct. The first details the toggle control, its rail, knob, and async rollback. The second details the six text-field states.
- Keep Design Tokens and Design System Kit distinct. The first details token naming and layering. The second details the wider kit: colour, type, spacing, components, and motion scales.
- Keep Shadow Elevation, Depth Layers, and Border Radius distinct. The first details layered shadows as hierarchy. The second details the three-property depth system. The third details nested corners and a radius scale. Perfect Card combines all three, and its entry says so.
- Cross-link the relative you did not pick. Say which entry you used and which entry covers the neighbouring question, so a later reader does not merge them.

## Apply a pattern in four steps

- Name the pattern and its source from references. Carry the pattern name and its source URL into any follow-up check.
- State the mechanism in one sentence. Name what changes, what triggers it, and what state it lives in.
- State the constraint with the example. Name the timing, the threshold, the keyboard path, the touch fallback, or the recovery window that keeps the pattern usable.
- Give a minimal original example only where the pattern is code. Label it as an original reconstruction, never as the creator's code. Do not describe a pattern without its rule, and do not give code without its constraint.
- Check the result against the pattern's do and do-not list. If the result breaks one, name the break and fix it, rather than calling the pattern done.

## Verify before you present

- Check the pattern against the reference file for its category. Confirm the source URL, the category, and the takeaway before you present it.
- Link the exact source pattern page for every pattern you present. The full catalog lives in references, grouped by category: interaction, forms, feedback, navigation, visual, motion, and content.
- Say what this skill covers. It covers all 76 patterns in the designmotionhq free library, in source index order, one pattern per entry, with no pattern duplicated across reference files.
- Say what this skill does not cover. It does not cover the 5-video gap between the 81-video TikTok profile header and the 76-pattern free library, and it does not cover the creator's paid UX Engine plugin, its skills, commands, or sub-agents. Do not invent either.
- Say what the extraction could not verify. Dates, like counts, comments, and per-video hashtags were not part of the library pages used, and video audio was not the source for this package. The notes are paraphrases of the library breakdowns, which the creator describes as one pattern, one video, one takeaway.
- Do not present a reconstruction as the creator's source. Give a minimal pattern in your own words that implements the described rule, and link the source pattern page for the creator's version.
- Do not duplicate sister skills. When a topic overlaps, keep the system rules here and point to the sister skill for its layer: pure CSS effects to `framework/design/skills/ania-kubow-design`, React implementation to `frontend-react`, principles and laws to `framework/design/skills/uiux-design-foundations`, and checkable finance guideline values to `apple-ui`.

## Where this fits in this repository

- Sister skills are repo paths, not upstream names: `apple-ui` (finance design system),
  `frontend-react` (implementation stack), `browser-verification` (visible-behaviour
  evidence), and the advisory craft corpus in `framework/design/skills/` (including
  `ania-kubow-design` and `uiux-design-foundations`).
- The `muse.*` connector tools and `/opt/muse/...` paths this skill was extracted with do
  not exist in this repository. Do not call them; use the repo tools named above.

## Websites

- [Designmotionhq on TikTok](https://www.tiktok.com/@designmotionhq) for the source videos. Carry the pattern name and video URL into any follow up check and verify the video still exists.
- [Designmotionhq pattern library](https://designmotionhq.com/patterns) for the free breakdowns this skill paraphrases. Carry the pattern name and pattern URL into any follow up check and verify the page still exists.

## Alternatives for better results

- Ask whether the user wants a review of an existing screen against these patterns, or a fresh screen built on them, before you start.
- Offer the system rules as a checklist first when the user needs to audit a screen, and as worked examples only for the patterns that fail the checklist.
