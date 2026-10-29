# Motion patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 13. Animation Timing

- Source: https://designmotionhq.com/patterns/animation-timing
- Takeaway: the same modal can feel premium or broken purely from its millisecond timings, so entrance, exit, feedback and stagger each need their own duration.
- Rules: entrances work best at 200-300ms with a cubic ease-out, quick enough to feel responsive but slow enough to read as deliberate. Exits should be faster than entrances, for example about 150ms against a 250ms entrance, so dismissal feels snappy. Tap and button feedback must fire in under 100ms, or it reads as lag even when the action itself is instant. Attention-grabbing motion such as notifications can run 500-800ms and use bounce or overshoot to pull the eye. Stagger list items by about 50ms; 30ms blurs them into one blob, while 100ms makes the list crawl in.
- Do: use ease-out for entrances and make exits roughly 40% faster than their entrance.
- Do not: stretch entrances past about 300ms, or use symmetric in/out timing or linear easing on entrances.
- See also: Easing Curves (20) for the curve shapes behind these durations, and Card Hover Anatomy (63) for a card that applies them.

## 20. Easing Curves

- Source: https://designmotionhq.com/patterns/easing-curves
- Takeaway: the same distance and duration can feel completely different, because the curve shaping change over time is what the eye notices.
- Rules: reserve linear motion for continuous loops such as spinners or marquees, never for UI that starts and stops. Default to ease-out for entrances, since decelerating into place mirrors settling objects. Add slight spring overshoot to presses, modals and confirmations. Reuse one small set of curves across the product. Stagger list and card entrances a few frames apart so they cascade.
- Do: let entrances decelerate and playful confirmations overshoot just a little.
- Do not: use linear easing for starting-and-stopping UI, or bounce so hard the element wobbles.
- See also: Animation Timing (13) for the durations that pair with these curves.

## 63. Card Hover Anatomy

- Source: https://designmotionhq.com/patterns/card-hover-anatomy
- Takeaway: a card feels alive when lift, edge, actions and image move together, while its footprint stays put.
- Rules: lift the card about 8 pixels and grow its shadow over roughly 200 milliseconds, ease-out: faster reads as twitchy, slower as stuck. Claim the cursor with a pulsing accent border or gradient sweep. Cascade hidden actions in, staggered about 60 milliseconds apart and anchored at the bottom. Scale the image to about 1.05 inside an `overflow-hidden` frame while the container stays fixed. Never scale the whole card, which shifts neighbours and breaks the grid.
- Do: stagger revealed actions about 60 milliseconds apart.
- Do not: scale the entire card and shift its neighbours.
- Original example: `.card:hover { transform: translateY(-8px); transition: transform 200ms ease-out; }`
- See also: Perfect Card in visual.md for the static card this hover animates, and Hover Trap in interaction.md for the touch fallback when hover does not exist.

## 67. Scroll-Driven Animations

- Source: https://designmotionhq.com/patterns/scroll-driven-animations
- Takeaway: modern CSS can tie motion directly to scroll position, with no JavaScript scroll handling at all.
- Rules: use `animation-timeline: scroll()` to turn the scrollbar itself into the animation controller, replacing a scroll listener and observer setup. Use `animation-range` to set the exact trigger point, so an animation can fire on entry, on exit, or in between. Use `view()` to target individual elements, so each card or image animates on entering the viewport. Build parallax by giving layers different speeds in pure CSS, work that once took about 30 lines of JavaScript. Layer these timelines on `position: sticky` for shrinking headers and reading-progress bars.
- Do: reach for the native scroll and view timelines first.
- Do not: hand-roll parallax with a scroll listener that CSS now handles.
- Original example: `.reveal { animation-timeline: view(); animation-range: entry; }`
- See also: Depth Layers in visual.md for the parallax speeds that pair with this timeline mechanism.
