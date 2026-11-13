# Review Checklists — From Zero to UI/UX Hero! distilled

Checklists distilled in my own words from the book's rules. Run the relevant list before calling a design or review done. The rule sources are in ui-foundations.md, ux-foundations.md, and ux-laws.md, with book page citations there.

## Colour and contrast
- [ ] Palette follows roughly 60-30-10, with the accent reserved for calls to action.
- [ ] Palette matches the brand character and the audience research, not personal taste.
- [ ] Text contrast is at least 4.5:1 against its background everywhere, including over images and gradients.
- [ ] Contrast verified on a real device and in bright lighting, not only in the design tool.
- [ ] Headings and CTAs are prominent but stay inside the palette family.
- [ ] No information is carried by colour alone.

## Typography
- [ ] At most three typefaces, each with a clear role.
- [ ] Heading and body faces contrast clearly in style or weight.
- [ ] Type scale follows one ratio (major third by default) from a 16px base.
- [ ] Body text is at least 16px, line height at the book's 1.2 default, captions and overlines sized from the same scale.
- [ ] Heading levels H1 to H6 reflect the real content hierarchy, one H1 per page.
- [ ] Decorative faces appear only in headlines, callouts, or branding, never in long text.

## Spacing, layout, and white space
- [ ] Every spacing value is a multiple of 8 (4 only for fine detail).
- [ ] The same relationship gets the same gap everywhere it appears.
- [ ] Gap size matches closeness of relationship: small inside groups, large between groups and sections (8 / 12 / 16 / 32 / 64+ as the ladder).
- [ ] More space sits between groups than within them.
- [ ] Headings and CTAs have the most surrounding space on the page.
- [ ] Grid type matches the content (block, column, modular, hierarchical), with consistent gutters and margins.
- [ ] Key elements sit at strong positions (rule-of-thirds intersections or structural-net focal points), not at dead spots.

## Icons
- [ ] One icon library and one style (filled or outlined) across the whole product.
- [ ] Default size 24px; no icon under 16px; sizes divisible by 8 or 4.
- [ ] Every ambiguous icon has a text label.
- [ ] Icons are SVG vectors, sharp at every size.
- [ ] Metaphors are familiar to the audience; standard glyphs (email, phone, search) are never replaced by clever alternatives.

## Buttons and states
- [ ] One primary button per view, in the accent colour; secondary actions are ghost, tertiary are text.
- [ ] Padding follows 1x vertical (8px) and 2x horizontal (16px) or the token equivalent.
- [ ] Labels are two to three words, action-oriented, and state the outcome of the click.
- [ ] Corner style matches the brand and audience.
- [ ] All six states designed: default, hover, focus, active, disabled, loading.
- [ ] Focus state is clearly visible for keyboard users.
- [ ] Disabled buttons explain why (tooltip or nearby text); loading buttons block duplicate submission.
- [ ] Touch targets are large enough and spaced so neighbours are not hit by accident (Fitts's Law).

## Content and UX writing
- [ ] Key information comes first (Inverted Pyramid); a partial reader still gets the point.
- [ ] Content is chunked with headings, bullets, and white space.
- [ ] Headings attract and preview; page titles and subject lines (microcontent) are sharp enough to stand alone.
- [ ] Active voice by default; passive voice only where it softens blame in sensitive messages.
- [ ] Jargon is removed, or defined and contextualised for a specialist audience.
- [ ] Copy is front-loaded for F-pattern scanning: strong words at line and section starts.
- [ ] Tone matches brand voice and stays respectful, including in error messages.

## Navigation and information architecture
- [ ] A content audit was done before structuring; gaps, duplicates, and inconsistencies were resolved.
- [ ] Categories come from card sorting with target users, in their language, not from internal org charts.
- [ ] On every screen the user can tell where they are, where they can go, and how to get back.
- [ ] Related links are grouped (Law of Proximity); actions are visually separated from navigation.
- [ ] Navigation was tested with real users and the test is repeated as content grows.

## UX laws pass
- [ ] Choices per screen are chunked within working-memory limits (Miller).
- [ ] Patterns match what users know from other products (Jacob); any novelty is introduced gently, with a fallback to the familiar version where possible (Jacob), and change is shipped gradually, in just-noticeable steps rather than one abrupt redesign (Weber).
- [ ] Decisions are few, sequenced into steps, with a recommended option highlighted (Hick).
- [ ] Primary targets are the largest and closest to the user's current position (Fitts).
- [ ] Exactly one element per view is designed to stand out (Von Restorff), and it is the primary action.
- [ ] Progress indicators give an artificial head start where a multi-step goal exists (Endowed Progress).
- [ ] Beauty supports function; no usability problem is being hidden by polish (Aesthetic-Usability).

## Cognitive load pass
- [ ] Nothing on screen fails to serve the user's current goal.
- [ ] Information is chunked and the next step is signposted; the user can never feel lost.
- [ ] Conventions are followed: self-explanatory labels, familiar symbols, prominent Back and Home.
- [ ] Unnecessary steps are removed; defaults and automation do work the user used to do.
- [ ] Extra options are grouped or held in collapsible areas until needed, with explanations where options are unclear.

## Action Cycle audit (per key flow)
- [ ] Goal: the screen makes the achievable goal obvious.
- [ ] Intention: the path toward the goal is visible without hunting.
- [ ] Specification: the required steps are concrete and few.
- [ ] Execution: the controls to perform the steps are present, sized, and labelled.
- [ ] Perception: every action produces immediate, visible feedback.
- [ ] Interpretation: feedback and errors are written so a first-time user understands them unaided.
- [ ] Evaluation: the user can tell whether the outcome matches their goal, and what to do next if it does not.

## Flow audit
- [ ] The goal of the experience is clear from the first screen.
- [ ] Every interaction gets immediate feedback.
- [ ] Challenge matches skill for both novices and experts; depth is behind progressive disclosure.
- [ ] No autoplay, unsolicited pop-ups, or forced paths; undo is available for consequential actions.
- [ ] The layout is clean and consistent enough that nothing competes with the task.

## Prospect-refuge audit
- [ ] Exploration is inviting: navigation, search, and content paths are visible (prospect).
- [ ] Safety is visible: privacy settings, account controls, and security signals are findable (refuge).
- [ ] Public and private spaces are both offered where the product has social features.
- [ ] Accessibility is treated as part of both: everyone can explore, and everyone's needs are respected.

## Process and handoff
- [ ] Direction was set with a moodboard before detailed design.
- [ ] Fidelity rose in steps (sketch, low, mid, high) with feedback at each step.
- [ ] The design passes the three evaluation questions: purpose, user needs, feasibility.
- [ ] Developers were involved before handoff; a design system or style guide defines type, colour, components, and patterns.
- [ ] Testing is planned beyond launch (usability, acceptance, A/B), not treated as a one-time gate.
