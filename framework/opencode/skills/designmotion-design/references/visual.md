# Visual patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 1. De-AI Landing Hero

- Source: https://designmotionhq.com/patterns/de-ai-landing-hero
- Takeaway: a generated-looking hero decorates because it has nothing concrete to show; replace each decoration with the product itself and the artificial look fades.
- Rules: drop the adjective-stuffed gradient headline. Name the outcome in the headline and the audience in the subtitle: what it does, for whom, in plain text. Remove the decorative purple blob. Use a neutral background and put the only colour on the product screenshot and the single primary button: one accent, no blobs. Keep one primary button. Demote the second action to a text link with an arrow, shifting visual weight from roughly 50/50 to roughly 90/10. Replace unverifiable social proof ("trusted by thousands" beside unrecognised logos) with one quote carrying a name, a role and a measured result with a unit. Replace the generic three-card row (icon in a circle, one-word labels such as Fast, Secure, Easy) with one product screenshot annotated at three real UI elements.
- Do: name the outcome in the headline and the audience in the subtitle.
- Do not: ship two equal-sized buttons side by side, or a headline full of adjectives like "supercharge" or "seamless".
- See also: Landing Page Skeleton in content.md for the five-section order this hero opens.

## 2. Reverse-Engineered Linear

- Source: https://designmotionhq.com/patterns/reverse-engineered-linear
- Takeaway: the expensive feel comes not from decoration but from density, restrained colour, and fast, consistent alignment: choices any team can copy.
- Rules: density reads as competence: about 13px text and 32px rows, with letter-spacing tightened by about 1%, so the same viewport shows roughly 14 issues instead of 8, without scrolling. Build depth from value, not blur: drop shadows in favour of three stacked background values (base, surface, raised surface) separated by a 1px border at 8% white; hover changes the surface value, not the elevation. Use one colour twice only: the selected row and the primary button. Status becomes a grey icon, not a coloured pill, collapsing seven colours to one deliberate accent. Show every action's keyboard shortcut, with hover feedback near 80ms and transitions under 150ms, with no bounce or overshoot. Work on a 4px grid: 16px icons centred on the text line, labels left-aligned, numbers and dates right-aligned, nothing centred.
- Do: print the shortcut beside every action and keep transitions under 150ms.
- Do not: use drop shadows to separate rows, panels or the sidebar, or encode status with coloured pills.

## 14. Charts That Lie

- Source: https://designmotionhq.com/patterns/charts-that-lie
- Takeaway: the way a chart is drawn can tell the opposite story from the same data, so axis, chart type, aspect ratio, ink and title all have to be honest.
- Rules: start every bar chart's y-axis at zero; truncating the baseline can turn a small rise into a fake explosion. Let the question pick the form: bars compare values, lines show change over time, and pie charts fall apart past about five slices. Balance aspect ratio so the average slope sits near 45 degrees; squishing flattens a trend and stretching turns it into a spike. Maximise data-ink by stripping gridlines, drop shadows, 3D skew and boxed legends, and labelling the line directly. Use colour as encoding, not decoration, with one hero colour for the series that matters, and title the chart with its takeaway rather than just its metric.
- Do: start bar axes at zero and spotlight one series with a single accent colour.
- Do not: crop an axis to exaggerate differences, or reach for a pie chart with more than five slices.

## 16. Design System Kit

- Source: https://designmotionhq.com/patterns/design-system-kit
- Takeaway: random hex values and eyeballed pixels do not scale, so colour, type, spacing, components and motion all need named, systematic scales.
- Rules: swap hardcoded hex for semantic tokens such as brand or error, so intent survives a redesign and one rename updates the whole app. Build a numbered colour scale, 100-900, then map it to semantic names such as brand, success and error. Define a type scale with fixed sizes and weights; giving every text the same size and weight kills hierarchy. Base spacing on a 4px scale, from 4 up to 64, because random gaps such as 7px or 23px read as sloppy while scale-based gaps feel deliberate. Standardise components as variants, sizes and states, and tie motion to intent, with durations from 100ms for micro-interactions to 500ms for complex transitions.
- Do: store every value as a named token and build numbered scales for colour and spacing.
- Do not: hardcode raw hex or pixel values inline, or pick spacing by eye.
- Original example: `:root { --brand: #2563eb; --space-4: 16px; }`
- See also: Design Tokens (68), which is the token layer itself; this entry is the wider kit (colour, type, spacing, components, motion) that tokens serve.

## 24. Golden Ratio

- Source: https://designmotionhq.com/patterns/golden-ratio
- Takeaway: layouts built on 1.618 read as naturally balanced rather than arbitrary, making the same content look cheap or expensive.
- Rules: derive spacing by repeatedly multiplying a base unit by 1.618, for example 8, 13, 21, 34, 55. Split layouts at roughly 62% / 38%, giving primary content the larger panel. Step type by the same factor, for example 16px, 26px, 42px, 68px. Round results to clean pixels. Treat the ratio as a guide, not a law fighting content or an 8px grid.
- Do: let one multiplying factor tie spacing and type together.
- Do not: choose gaps and sizes arbitrarily, or apply the ratio so rigidly it breaks content.

## 25. Grid System

- Source: https://designmotionhq.com/patterns/grid-system
- Takeaway: a 12-column grid creates order, and only against that order does deliberately breaking it read as emphasis.
- Rules: start from 12 columns, dividing cleanly into halves, thirds, quarters and sixths. Use ratios such as 4:8, 6:6, or 3:9. Choose gutters for mood: 8px dense, 24px balanced, 40px editorial. Collapse columns responsively, 12, 6, 4, 1. Then break the grid on purpose, for example a full-width hero bleed.
- Do: anchor every element to shared column edges before adding any break.
- Do not: break the grid before establishing it, or invent arbitrary widths when a clean ratio fits.

## 31. Proximity Rule

- Source: https://designmotionhq.com/patterns/proximity-rule
- Takeaway: spacing alone groups a UI: close elements read as related, distant ones as separate, with no borders required.
- Rules: make within-group gaps smaller than between-group gaps, since equal spacing flattens hierarchy. Let whitespace group before reaching for borders or dividers. In forms, tighten related fields to roughly 12px and open section breaks to roughly 40px. In toolbars and nav, group controls by function: navigate, actions, system, not one evenly spaced row. Split flat lists, such as eight sidebar links, into labelled groups for scannability.
- Do: use spacing contrast to show what belongs together.
- Do not: space everything equally, or add boxes when a larger gap communicates the same grouping.
- See also: Gestalt Laws (70) for the wider grouping laws, of which proximity is one member.

## 35. Shadow Elevation

- Source: https://designmotionhq.com/patterns/shadow-elevation
- Takeaway: shadows are not decoration; they encode hierarchy and depth, and believable depth comes from layered shadows rather than one flat blur.
- Rules: stack three shadows: a tight contact shadow, a mid-distance shadow and a wide soft spread shadow. The tight contact shadow, around 0 1px 3px, anchors the element to the surface so a card feels physically placed rather than floating. A subtle coloured glow, a low-opacity blur in an accent hue, adds a premium branded feel that plain black shadows cannot. Match the glow to the product context, for example purple for creative tools, blue for fintech and green for health, so elevation reinforces brand identity. Elevation is a hierarchy signal: the more elevated an element, the more important it reads, which is why a premium tier looks lifted while a basic one stays flat.
- Do: layer three shadows and reserve the strongest elevation for the elements that matter most.
- Do not: rely on a single flat drop shadow for every surface, or treat shadows as mere decoration.
- Original example: `box-shadow: 0 1px 3px rgb(0 0 0 / .2), 0 8px 24px rgb(0 0 0 / .12);`
- See also: Depth Layers (75) for the three-property depth system, and Perfect Card (74) for the card that uses layered shadows.

## 42. Visual Hierarchy

- Source: https://designmotionhq.com/patterns/visual-hierarchy
- Takeaway: hierarchy is the order in which the eye meets a page, and it is built by stacking several quiet signals at once, not by making one element loud in isolation.
- Rules: let size set the entry point, with the primary element roughly twice the size of body text. Spend colour sparingly: keep the interface neutral and reserve a single accent for the one most important action, since a rainbow of colours flattens everything into noise. Use contrast to separate roles, for example a bold white heading against muted copy, or a filled primary button beside a ghost secondary. Treat whitespace as a signal: give the hero element breathing room and keep secondary items compact. Build reading order with weight alone where useful: heavy headings around 800, regular body around 400, light captions around 300. No single rule carries a layout; size, colour, contrast, spacing and weight must stack into one clear focal point.
- Do: reserve one accent colour for the single action you most want taken.
- Do not: colour every element differently, or lean on size alone while everything else sits at equal emphasis.

## 43. Z-Index Mastery

- Source: https://designmotionhq.com/patterns/z-index-mastery
- Takeaway: layering fails are usually not about the number being too small; they are about stacking contexts, and a bigger number cannot rescue an element whose parent already lost the contest.
- Rules: a z-index only works on a positioned element, so a static element with a huge value does nothing; give it relative, absolute, fixed or sticky positioning first. Each stacking context is its own universe: a child at 9999 can never rise above its parent's siblings if the parent itself sits below them. An escalating arms race of 9999, then 99999, is a symptom, not a fix; the real cause is almost always an unexpected stacking context higher up the tree. Use `isolation: isolate` to spin up a fresh stacking context in one line, so a component's internal layers stop leaking into the rest of the page. Inspect the real stack in Chrome DevTools' Layers panel, which renders the page in 3D, instead of guessing by trial and error.
- Do: position the element first, then contain component stacking with isolation.
- Do not: keep escalating the number to force a child above another branch.
- Original example: `.card { position: relative; z-index: 1; isolation: isolate; }`

## 52. Gradient Design

- Source: https://designmotionhq.com/patterns/gradient-design
- Takeaway: cheap-looking gradients usually fail in three quiet ways: travelling too far across hue, reversing lightness, or being used as a surface instead of ambiance.
- Rules: neighbouring hues, such as teal to cyan, blend cleanly, while opposites, such as orange to blue, create a muddy grey dead zone in the middle. Keep lightness moving in one direction; a gradient that gets darker, then lighter, then darker again reads as banding. Gradients work best as ambiance, not surface: a soft radial glow behind content beats a full-bleed linear wash on top of it. Subtle grain on top of a gradient hides banding on cheap displays and adds perceived texture. In practice, stay within about 60 degrees of hue travel, add 2-3% noise, and test on a low-quality screen.
- Do: stay within 60 degrees of hue travel, add 2-3% noise, and test on a low-quality screen.
- Do not: put body text directly on a gradient's mid-transition zone, where contrast is unpredictable.
- Original example: `background: radial-gradient(circle at 30% 20%, rgb(45 212 191 / .25), transparent 60%);`

## 65. Icon Design Rules

- Source: https://designmotionhq.com/patterns/icon-design-rules
- Takeaway: a premium icon set is judged by consistency across the set, not by any single icon.
- Rules: size optically, not mathematically: circular and organic shapes need to sit 5-8 percent larger than squares to read the same size. Snap every shape to a 24-pixel grid, or 16 pixels for dense interfaces, because sub-pixel drift blurs edges. Hold a single stroke weight, 2 pixels in the source, across the whole set. Keep the bounding box fixed even as the shape changes, so toolbars stay legible. Commit set-wide to fill or to outline, rather than choosing per icon.
- Do: scale round icons 5-8 percent larger than square ones.
- Do not: mix fill and outline styles at random within one set.

## 68. Design Tokens

- Source: https://designmotionhq.com/patterns/design-tokens
- Takeaway: one well-named token change should replace dozens of hunted-down edits across a product.
- Rules: name tokens by meaning, not by value, so `color-primary` survives a rebrand while a literal colour name becomes a lie when the colour changes. Structure tokens in three layers: primitives, semantic, and component, each referencing the one above. Let one primitive change cascade through every component that points to it, turning 47 edits into one. Define a scale and snap everything to it, so stray 13-pixel padding or 17-pixel gaps collapse to 12 and 16. Treat dark mode not as inverting colours, but as swapping one token set for another.
- Do: layer tokens primitives, then semantic, then component.
- Do not: bake literal values into token names or hardcode raw values across components.
- Original example: `:root { --color-primary: var(--blue-600); }`
- See also: Design System Kit (16) for the wider kit, and Dark Mode (72) for the token-set swap that dark mode actually is.

## 69. Color Accessibility

- Source: https://designmotionhq.com/patterns/color-accessibility
- Takeaway: contrast is a ratio, not a colour, so the same text can read crisp on one background and disappear on another, and most failures hide in muted greys.
- Rules: the exact same off-white can read crisp on a dark panel and disappear on a light one, because the background decides legibility. Aim for WCAG thresholds of 4.5:1 on body text and 3:1 on large text; below 3:1, text degrades from large-only to flat-out invisible. Most failures hide in "decorative" muted greys, with nav links, card labels and secondary headings routinely sitting at 1.5-2:1 and quietly falling below the line. Never encode meaning with colour alone: for roughly 8% of users with colour vision deficiency, a red error and a green success collapse into the same muddy tone. Add a second signal alongside every colour cue, such as an icon on error text, trend arrows on stats, or textures and patterns in charts, so the message survives when colour does not.
- Do: check every text-on-background pair against WCAG, pair colour with an icon, label or pattern, and darken or lighten muted text until it clears the threshold.
- Do not: rely on red-versus-green alone to separate errors from success, or ship low-contrast greys for nav links and card labels just because they look sleek.

## 70. Gestalt Laws

- Source: https://designmotionhq.com/patterns/gestalt-laws
- Takeaway: the brain groups and completes shapes automatically, so working with its pre-attentive laws makes a layout feel instantly organised rather than busy.
- Rules: Closure: the eye completes incomplete shapes, so icons and outlines still read even with gaps, without every line drawn. Similarity: elements sharing a property such as colour, shape or size read as one group, so recolouring rows can instantly split a flat grid into Navigation, Content and Actions. Continuity: the eye follows the smoothest path, so aligning items on a shared axis lets it flow, while scattered placement forces it to jump erratically. Figure-Ground: blurring and dimming the background pushes a modal forward as the focal figure, which is what makes a dialog feel deliberate instead of floating. Common Region: a shared border or container groups elements even when they sit far apart, so wrapping settings in cards signals belonging without moving them closer.
- Do: give related items a shared property so they read as one group, align related controls on a common axis, and wrap loosely placed elements in a bordered card when proximity alone cannot group them.
- Do not: scatter navigation or list items at varied angles and positions, or lean on a modal alone without dimming what is behind it.
- See also: Proximity Rule (31), which is the spacing member of this set.

## 71. Border Radius

- Source: https://designmotionhq.com/patterns/border-radius
- Takeaway: one CSS rule can separate a card that looks off from one that looks expensive, because nested corners, a shared scale and size-appropriate radii make curves read as intentional.
- Rules: nested corners follow maths: inner radius equals outer radius minus padding, and when concentric curves line up, a card reads as intentional instead of "off". Pull every value from one radius scale, such as 4, 8, 12, 16 and 24, instead of picking numbers per component, since consistency is what makes UI look expensive. Scale radius with element size: tooltips around 4px, inputs around 8px, cards around 12px, modals around 16px and panels around 24px, with bigger surfaces earning bigger corners. Radius carries personality: small and sharp reads corporate, while large and round reads friendly, so pick the range that matches the brand's tone.
- Do: derive the inner radius from the outer radius minus padding, commit to a single radius scale, and scale radius with element size.
- Do not: pick radius values at random per component, nest a rounded card inside another without adjusting the inner corner, or mix a playful oversized radius into a serious brand.
- Original example: `.card { border-radius: 12px; } .card-inner { border-radius: 8px; }`
- See also: Perfect Card (74) and Depth Layers (75) for the other two members of the card-depth trio. Radius is the corner rule, shadows are the elevation rule, depth is the combined system.

## 72. Dark Mode

- Source: https://designmotionhq.com/patterns/dark-mode
- Takeaway: dark mode is not black mode; a premium dark theme is built from near-black surfaces, layered elevation, desaturated accents and soft off-white text.
- Rules: build on a near-black base such as #121212, not pure #000000, so shadows and depth stay visible. Signal elevation with layered surfaces, each step up getting a lighter grey from base to surface to elevated, the way shadows do the job in light mode. Desaturate accent colours by roughly 20%, since full-saturation buttons and highlights vibrate and strain the eye against a dark background. Never use pure white text, since #FFFFFF glares on dark UI; calibrate it down to a soft off-white for comfortable reading. Build text hierarchy with opacity, not new colours, stepping high-emphasis, medium and disabled text down in white opacity.
- Do: base the darkest layer on a near-black grey, lighten each surface as it elevates, and desaturate accents so they sit calmly against the background.
- Do not: use pure black as the background, ship fully saturated accents, or set text to pure white.
- Original example: `:root { --surface: #121212; --surface-raised: #1e1e1e; --text: rgb(255 255 255 / .87); }`
- See also: Design Tokens (68), since dark mode here is a token-set swap, not an inversion.

## 73. Von Restorff Effect

- Source: https://designmotionhq.com/patterns/von-restorff
- Takeaway: what is visually different gets noticed and remembered, but only against a uniform baseline, so isolating one element steers choice while highlighting several cancels the effect.
- Rules: the isolation effect means an item that breaks the pattern draws the eye automatically. It only works against a uniform baseline: three identical cards give the eye nowhere to go, since contrast is relative, so keep everything else calm and change just one thing. In pricing, isolate the target plan by scaling it up, adding a "Most Popular" badge and dimming the alternatives, so the choice steers itself. Break the pattern with a single call to action, lifted by colour, scale and glow, while nav links recede. In forms, emphasise the primary action and mute secondary ones, and differentiate with more than colour, combining scale, elevation and glow so the standout reads reliably, including for colour-blind users.
- Do: isolate the one action you want taken, using scale, colour and a badge against a uniform baseline, and limit emphasis to a single element per view.
- Do not: highlight two or three elements at once, ship identical options and hope users pick the intended one, or lean on colour alone.

## 74. Perfect Card

- Source: https://designmotionhq.com/patterns/perfect-card
- Takeaway: the gap between a card that looks free and one that looks premium can come down to four changes: spacing, typography, shadows and hover.
- Rules: padding is the biggest tell: moving from cramped 12px to 40px with a 24px border-radius instantly reads as intentional instead of cheap. Build a real type hierarchy by pushing the title to 600 weight and about 38px, then shrinking the body and dropping it to 55% opacity so the eye lands on the title first. Stack two shadows for believable depth: a tight, darker one for contrast plus a wide, soft one for ambient elevation. Add a hairline border at roughly 12% opacity to define the card's edge against a dark background. Add a hover state that lifts the card about 8px, scales to 1.02 and deepens the shadow, signalling it is clickable.
- Do: layer a tight shadow with a soft ambient one plus a subtle border around 12% opacity, set the description to about 55% opacity, and give the card a hover lift.
- Do not: cram content against the edges with tiny padding and near-zero border-radius, or give title and body the same weight and full opacity so nothing guides the eye.
- Original example: `.card { padding: 40px; border-radius: 24px; } .card p { opacity: .55; }`
- See also: Shadow Elevation (35), Border Radius (71) and Depth Layers (75). This entry is the card that combines them; the others are the individual rules.

## 75. Depth Layers

- Source: https://designmotionhq.com/patterns/depth-layers
- Takeaway: the same layout and colours can turn from flat to dimensional through three properties alone, without a redesign.
- Rules: depth does not require a redesign: the same layout and colours work, with three CSS properties doing the whole job. Layered shadows beat a single drop shadow: stack a tight one around 2px, a mid spread around 12px and a large ambient one around 32px to mimic how real light falls off. Parallax scroll sells distance by moving layers at different speeds, with background slow, midground medium and foreground fastest, roughly 1x, 2.5x and 5x. Z-translation on hover makes an element react to the cursor: lift it toward the viewer with translateZ plus a slight scale of 1.03 and a soft glow. Depth also lives in border and shadow intensity, not just position, so brightening the border on hover reinforces the lift.
- Do: stack multiple shadows at increasing blur and offset, keep hover lifts subtle at a few pixels plus about 3% scale, and vary scroll speed per layer.
- Do not: redesign the layout or palette to fake depth when three properties already do it, or push parallax offsets or hover scale so far they pull attention off the content.
- Original example: `.card:hover { transform: translateZ(12px) scale(1.03); }`
- See also: Shadow Elevation (35) for shadow layering alone, and Perfect Card (74) for a card built from these layers.
