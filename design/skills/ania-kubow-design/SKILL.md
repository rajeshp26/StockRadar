---
name: ania-kubow-design
description: Teach web design through short pure CSS and HTML examples from Ania Kubow on TikTok — visual effects, UI components, shapes, color, theming, layout, and UX patterns, each with a linked source video and copy-paste code. Use when the user wants a CSS-only effect or pattern.
---

# Ania Kubow Design

Teach modern web design through short pure CSS and HTML examples in the style of Ania Kubow on TikTok. Use this skill when the user wants a visual effect, a UI component, a layout pattern, or a theming technique with no JavaScript, and wants a concrete example they can copy and adapt. When the pattern needs JavaScript, React, Framer Motion, canvas, or WebGL, use the settigation-code skill instead.

## Apply the house style

- Keep each example small and declarative. Prefer one CSS idea per example over a full framework setup.

- Prefer native CSS over an image asset or JavaScript when native CSS can do the job. Reach for gradients, filters, clip-path, transforms, and custom properties first.

- Show the effect, name the one CSS mechanism behind it, then list the constraints that keep it usable. Do not bury the mechanism in setup code.

- Keep motion calm and readable. Slow marquee speed, gentle blob motion, and a calm pulse beat fast or alarming animation.

- Keep text readable over any effect. Check contrast over gradients, glass, video, and images before calling an effect done.

- Provide a fallback when a technique depends on newer browser support. Name the fallback in the same example.

- Respect user preferences. Honor reduced motion and respect the OS light or dark preference by default.

## Choose the right pattern

- Use a visual effect for a hero, card, or brand moment. Reserve heavy glass, aurora text, rotating glow, and metaballs for one focal element per view.

- Use an interaction pattern for state. Use a gliding pill for selected tabs, a before or after slider for comparisons, a scroll bar for reading progress, and a pulsating dot for AI listening or activity.

- Use a layout pattern for structure. Use a masonry grid for uneven cards, a 3D carousel for showcase items, and a one value layout switch for mobile stacking.

- Use a theming pattern for systems. Use native color mixing for tints and shades, adaptive text color for varied backgrounds, and a native color scheme for light or dark mode.

- Use a shape pattern for identity. Use SVG for logos, squircles for platform native icons, and brand color sparingly for emphasis.

- Stay inside pure HTML and CSS. When an effect needs JavaScript physics, React, Framer Motion, canvas, or WebGL, switch to the settigation-code skill, which covers those stacks.

## Build each example

- Start from the smallest markup that shows the idea. An avatar in two tags and a grid in one line are the model, not the exception.

- Name the CSS properties that do the work. For a rotating glow border, name the registered custom property and the conic gradient. For a squircle, name corner shape. For a seamless marquee, name duplicated content and looping.

- State the usability rule with the example. For a checkbox, keep native behavior and a clear checked state. For a textarea, set min and max sizes so resizing cannot break layout. For a before or after slider, make the handle large and draggable on touch.

- State the accessibility rule with the example. Keep keyboard focus visible, preserve checkbox semantics, honor reduced motion, and keep focus within styling for form groups and cards.

- State the performance rule with the example. Treat effects on video as costly, keep glass heavy only for overlays, and balance hero image quality against load time.

## Verify before you present

- Check the example against the source catalog in references/design-examples.md. Link the exact TikTok video for the pattern you used.

- Give a copy-paste code example from references/code-examples.md for every pattern you present. Do not describe a pattern without its code.

- Say what the catalog does not cover. It has no Figma, UXPin, prototyping, designer developer handoff, portfolio design, or design system examples from this profile.

- Say what the extraction could not verify. Dates, like counts, comments, and per video hashtags were not visible in logged out view. View counts are grid values from 15 Oct 2026.

- Do not invent a code snippet as if it were her code. Give a minimal pattern in your own words that implements the described effect, and link the source video for her version.

- When a pattern exists in both catalogs, for example tab indicators or glass effects, present this skill's pure CSS version as the default and name the settigation-code version as the React alternative.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [Ania Kubow on TikTok](https://www.tiktok.com/@aniakubow) for the source videos. Carry the pattern name and video URL into any follow up check and verify the video still exists.

## Alternatives for better results

- Ask whether the user wants the effect as pure CSS, or as a reusable component in their stack, before building a full component.

- Offer a calmer reduced motion variant alongside any animated example.
