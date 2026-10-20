# Design Examples - Ania Kubow on TikTok

Source: https://www.tiktok.com/@aniakubow - profile "Code with Ania Kubow"
Profile observed 15 Oct 2026 in logged-out view: 17.7K followers, 36 following, 132.6K likes.
Profile header lists 413 videos, but only 79 videos loaded in the grid after scrolling to the bottom. This catalog covers those 79. Of those, 37 were design-related.

Limits:
- No publish dates, like counts, or comments were visible in logged-out view. View counts below are grid values from 15 Oct 2026.
- Per-video hashtag lists were not fully visible. Recurring tags seen across sampled pages: #100daysofcode, #coding, #devcommunity, #csstips, #webdev, #css, #html, #webdevelopment.
- No videos about Figma, UXPin, prototyping tools, designer-developer handoff, portfolio design, or design systems were found in the 79-video grid.
- Summaries below are paraphrases, not transcripts. Open the linked video for her exact demo.

How to use this catalog: pick the pattern, open the video, then copy the matching code example from code-examples.md. Each of the 37 patterns below has a working code block in that file, numbered to match.

---

## 1. CSS Visual Effects and Motion

### 1.1 Album-art effect
- Video: https://www.tiktok.com/@aniakubow/video/7696628831062461728
- Views: 2,630
- Pattern: Build a poster-like album-art graphic with a few lines of CSS.
- Technique: Layered CSS rather than an image asset.
- Use for: Covers, thumbnails, CSS-as-illustration.
- Constraint: Keep code short and declarative.

### 1.2 Shiny / premium card
- Video: https://www.tiktok.com/@aniakubow/video/7694694504372194593
- Views: 3,041
- Pattern: Make a card look premium with a shine effect.
- Technique: Moving highlight suggesting gloss / reflection.
- Use for: Pricing cards, product cards, featured cards.
- Constraint: Keep the shine restrained so text stays readable.

### 1.3 Neon signs / light spill
- Video: https://www.tiktok.com/@aniakubow/video/7694329549047254304
- Views: 2,825
- Pattern: Recreate neon signage with light spilling onto a surface.
- Technique: Layered glow to simulate light falloff, not just a bright outline.
- Use for: Hero headlines, signage-style branding, nightlife themes.
- Constraint: Colour plus blur sells realism more than brightness alone. Consider how glow interacts with nearby surfaces.

### 1.4 Holographic tickets
- Video: https://www.tiktok.com/@aniakubow/video/7690988081171664160
- Views: 2,804
- Pattern: Create holographic-looking tickets with CSS.
- Technique: Gradients to fake iridescent / foil colour shifts, plus ticket shape and sheen.
- Use for: Promo cards, event UI, ticket / coupon patterns.
- Constraint: Shape plus sheen makes a flat element feel physical.

### 1.5 Odometer / rolling numbers
- Video: https://www.tiktok.com/@aniakubow/video/7689465757574516001
- Views: 2,402
- Pattern: Build a rolling odometer-style number display.
- Technique: Animate digits vertically like a mechanical counter.
- Use for: Stats, prices, scores, dashboards.
- Constraint: Keep digit width stable to avoid layout jitter.

### 1.6 Glowing AI voice orb
- Video: https://www.tiktok.com/@aniakubow/video/7683199646872751382
- Views: 2,390
- Pattern: Build a glowing voice-assistant orb from gradients and blur.
- Technique: Gradients plus blur for a soft luminous core, animated subtly.
- Use for: AI product identity, voice UI, listening / speaking states.
- Constraint: One glowing element can carry identity. Animate subtly to suggest state.

### 1.7 Checkerboard gradients
- Video: https://www.tiktok.com/@aniakubow/video/7683954501086121238
- Views: 1,905
- Pattern: Checkerboard patterns using gradients in one CSS property.
- Technique: Repeated gradients to generate pattern without images.
- Use for: Backgrounds, placeholders, transparency indicators.
- Constraint: Compact code makes it reusable across components.

### 1.8 Frosted / real glass
- Video: https://www.tiktok.com/@aniakubow/video/7680604504600923414
- Views: 59.3K
- Pattern: A more realistic frosted-glass treatment where glass bends / distorts.
- Technique: Go beyond flat blur toward refraction / distortion.
- Use for: Hero overlays, modals, glassmorphism moments.
- Constraint: Test legibility of text over the glass layer. Reserve heavy glass for hero / overlay moments, not dense UI.

### 1.9 Infinite marquee
- Video: https://www.tiktok.com/@aniakubow/video/7679118200755195158
- Views: 12K
- Pattern: A smooth, actually seamless scrolling marquee.
- Technique: Duplicate content and loop it so the seam is invisible.
- Use for: Logos, tickers, announcement strips.
- Constraint: Keep speed slow enough to read.

### 1.10 Pulsating dot (AI apps)
- Video: https://www.tiktok.com/@aniakubow/video/7678759297852968214
- Views: 18.9K
- Pattern: The pulsating dot used in AI app UIs.
- Technique: Small pulsing indicator signaling activity / listening.
- Use for: AI state, listening, loading, live indicators.
- Constraint: Use calm animation timing, not alarming. Keep indicator language consistent so users recognise AI state.

### 1.11 Pixel art in HTML/CSS
- Video: https://www.tiktok.com/@aniakubow/video/7676132475768147222
- Views: 2,626
- Pattern: Pixel art made with HTML and CSS.
- Technique: Grid-based pixels forming recognisable icons / characters.
- Use for: Tiny illustrations, icons, teaching layout and colour discipline.
- Constraint: Pure-CSS art avoids image assets for tiny illustrations.

### 1.12 Aurora inside letters
- Video: https://www.tiktok.com/@aniakubow/video/7673906649320394006
- Views: 12.8K
- Pattern: Aurora / gradient effect clipped inside letterforms using background-clip.
- Technique: Clip a gradient background to text for a luminous headline.
- Use for: Headlines, hero text, brand moments.
- Constraint: Keep body copy plain so the effect stays a headline accent. Check contrast - decorative text still needs to be readable.

### 1.13 CSS video effect
- Video: https://www.tiktok.com/@aniakubow/video/7670995930413436162
- Views: 21.1K
- Pattern: A striking CSS effect applied to video.
- Technique: CSS styling video, not just static boxes.
- Use for: Hero video treatments.
- Constraint: Test performance - effects on moving media cost more. Use as hero treatment, with a fallback if unsupported.

### 1.14 Metaball effect
- Video: https://www.tiktok.com/@aniakubow/video/7669854145901268246
- Views: 20.2K
- Pattern: Blobs that merge like metaballs using CSS filters.
- Technique: Blur plus contrast fusing separate shapes into one organic form.
- Use for: Playful / friendly brand moments, animated backgrounds.
- Constraint: Keep motion gentle to avoid a distracting background.

### 1.15 Rotating glow border (@property)
- Video: https://www.tiktok.com/@aniakubow/video/7668718334518512918
- Views: 114.3K - most-viewed design video in this set.
- Pattern: A rotating glowing border built with the CSS @property rule.
- Technique: Register a custom property so an angle can animate smoothly. Rotating conic glow around a card.
- Use for: Premium cards, featured plans, callouts.
- Constraint: Provide a static fallback where @property is unsupported.

### 1.16 Scroll-driven bar fill
- Video: https://www.tiktok.com/@aniakubow/video/7667605988626779414
- Views: 6,300
- Pattern: A bar that fills as the user scrolls, with no JavaScript.
- Technique: Tie progress to scroll position natively.
- Use for: Article reading progress, long-form pages.
- Constraint: Keep the bar thin and unobtrusive.

---

## 2. UI Components and Interaction

### 2.1 Gliding pill
- Video: https://www.tiktok.com/@aniakubow/video/7689123896787848481
- Views: 3,143
- Pattern: A pill indicator that glides between options.
- Technique: Animate the active indicator rather than jumping it.
- Use for: Tabs, segmented controls, nav.
- Constraint: Gliding motion clarifies which option is selected.

### 2.2 Avatar from two HTML tags
- Video: https://www.tiktok.com/@aniakubow/video/7688024681655438614
- Views: 2,166
- Pattern: An avatar illustration made with only two HTML tags.
- Technique: Minimal markup plus clever CSS shapes.
- Use for: Placeholder / default avatars, minimal illustration.
- Constraint: Constraint forces clever use of CSS shapes.

### 2.3 3D carousel (pure CSS)
- Video: https://www.tiktok.com/@aniakubow/video/7683565314172275990
- Views: 4,059
- Pattern: A 3D carousel built in pure CSS.
- Technique: Transforms to arrange items in depth.
- Use for: Showcase carousels, galleries.
- Constraint: Pure-CSS version avoids JS for showcase. Keep interaction simple (e.g. hover / scroll) for usability.

### 2.4 Before / after slider (clip-path)
- Video: https://www.tiktok.com/@aniakubow/video/7675015571968363799
- Views: 11K
- Pattern: A before / after comparison slider using clip-path.
- Technique: Clip one layer to reveal the other as the handle moves.
- Use for: Edits, redesigns, product comparisons.
- Constraint: Make the handle large and draggable on touch.

### 2.5 Boring buttons + overlays
- Video: https://www.tiktok.com/@aniakubow/video/7652016231926500610
- Views: 8,100
- Pattern: Improve plain buttons by adding overlays.
- Technique: Layering gives flat buttons depth and affordance.
- Use for: Primary / secondary buttons, CTAs.
- Constraint: Hover / active states should change visibly. Do not let decoration reduce clickable clarity.

### 2.6 Custom checkbox styling
- Video: https://www.tiktok.com/@aniakubow/video/7651625506730757398
- Views: 6,900
- Pattern: Style a checkbox beyond the browser default.
- Technique: Replace native look while keeping native behaviour.
- Use for: Forms, settings, todo lists.
- Constraint: Checked state must be unmistakable. Preserve keyboard focus and accessibility semantics.

### 2.7 Textarea resize
- Video: https://www.tiktok.com/@aniakubow/video/7654633542646828290
- Views: 3,000
- Pattern: Control how a textarea can be resized.
- Technique: Decide whether users may resize, and in which directions.
- Use for: Comment boxes, feedback forms, editors.
- Constraint: Prevent resizing from breaking surrounding layout. Set sensible min / max sizes.

---

## 3. Shapes, Icons and Brand

### 3.1 Logo from SVG
- Video: https://www.tiktok.com/@aniakubow/video/7693978139231276320
- Views: 1,944
- Pattern: A logo built from an SVG shape.
- Technique: Vector shapes.
- Use for: Logos, icons, marks.
- Constraint: Vector logos stay crisp at any size. Simple shapes scale better than detailed artwork.

### 3.2 Apple icon shapes / squircles
- Video: https://www.tiktok.com/@aniakubow/video/7685797806006684960
- Views: 3,015
- Pattern: Apple-style icon shapes are squircles, not rounded squares.
- Technique: Squircle curves feel softer than a standard rounded rect.
- Use for: App icons, icon systems.
- Constraint: Shape choice is part of platform visual identity. Match platform shape language for native-feeling icons.

### 3.3 Squircle via corner-shape
- Video: https://www.tiktok.com/@aniakubow/video/7681710685687975191
- Views: 5,140
- Pattern: Use corner-shape for squircle corners in CSS. Message: move beyond defaults and be more artistic.
- Technique: Newer CSS can produce true squircle corners directly.
- Use for: Cards, buttons, icons, containers.
- Constraint: Small shape tweaks change the feel of an entire UI. Avoiding defaults is a quick way to look less generic.

### 3.4 Brand colours from a website
- Video: https://www.tiktok.com/@aniakubow/video/7665380503607954710
- Views: 2,800
- Pattern: Pull a site's branding automatically from its URL.
- Technique: Derive brand colours from an existing site for consistency.
- Use for: Themed / white-label setups, brand onboarding.
- Constraint: Always verify extracted colours against the real brand.

### 3.5 Highlighting brand colours
- Video: https://www.tiktok.com/@aniakubow/video/7652786988030086422
- Views: 2,700
- Pattern: Highlight brand colours in a design.
- Technique: Use brand colour sparingly for emphasis, not everywhere.
- Use for: Key actions, key words, highlights.
- Constraint: A highlight draws the eye to the key action / word. Pair brand colour with neutral surfaces for contrast.

---

## 4. Colour, Typography and Theming

### 4.1 CSS colour mixing
- Video: https://www.tiktok.com/@aniakubow/video/7665008733876915478
- Views: 2,806
- Pattern: Mix colours natively in CSS.
- Technique: Native mixing creates tints / shades without a preprocessor.
- Use for: Palettes, hover states, gradients, theming.
- Constraint: Consistent mixing keeps a palette coherent.

### 4.2 Auto-changing text colour
- Video: https://www.tiktok.com/@aniakubow/video/7654245313527532822
- Views: 1,300
- Pattern: Text colour that adapts automatically for readability.
- Technique: Let text adapt to its background instead of hard-coding one colour.
- Use for: Text over images, gradients, varied surfaces.
- Constraint: Readability should hold across light and dark surfaces. Test against varied images / gradients, not just flat colours.

### 4.3 Light / dark mode in two lines
- Video: https://www.tiktok.com/@aniakubow/video/7620825821749546262
- Views: 3,600
- Pattern: Add light / dark mode in about two lines of CSS.
- Technique: Use a native colour-scheme approach for a quick theme switch.
- Use for: Whole-site theming, quick dark mode.
- Constraint: Theming should cover backgrounds, text, and borders together. Respect the user's OS preference by default.

---

## 5. Layout, Responsive and UX

### 5.1 Pinterest responsive grid
- Video: https://www.tiktok.com/@aniakubow/video/7649788877418319126
- Views: 3,900
- Pattern: Recreate a Pinterest-style responsive masonry grid in one line of CSS (noted as experimental).
- Technique: Masonry-style grid handles uneven card heights elegantly.
- Use for: Galleries, feeds, discovery UIs.
- Constraint: One-line solutions depend on browser support - check compatibility.

### 5.2 One-letter mobile layout change
- Video: https://www.tiktok.com/@aniakubow/video/7662795431050628374
- Views: 2,000
- Pattern: Change one letter / value to completely change a mobile layout.
- Technique: Tiny layout values can flip a design between stacked and side-by-side.
- Use for: Responsive layout switches.
- Constraint: Test the breakpoint on real phone widths. Prefer layout that adapts without separate mobile markup.

### 5.3 Zooming forms on mobile
- Video: https://www.tiktok.com/@aniakubow/video/7662022263293627670
- Views: 1,500
- Pattern: Why forms zoom on mobile and how to stop it.
- Technique: Small input font sizes trigger auto-zoom on some mobile browsers. Size inputs so users can type without the viewport jumping.
- Use for: Forms, checkout, login, any mobile input.
- Constraint: Stable forms reduce input errors and abandonment.

### 5.4 Focus-within / child focus
- Video: https://www.tiktok.com/@aniakubow/video/7667227786238512406
- Views: 3,009
- Pattern: CSS can react when a child element receives focus.
- Technique: Style a parent when any child is focused.
- Use for: Form groups, cards, menus.
- Constraint: Visible focus states help keyboard and screen-reader users. Use it for form groups, cards, and menus.

### 5.5 Reduced motion
- Video: https://www.tiktok.com/@aniakubow/video/7660917425998695702
- Views: 2,400
- Pattern: Respect users who prefer reduced motion.
- Technique: Honour the reduced-motion preference for animation-heavy UIs.
- Use for: Any animated UI.
- Constraint: Offer a calmer alternative, not just removal of delight. Accessibility preference is part of UX, not an edge case.

### 5.6 Hero images loading
- Video: https://www.tiktok.com/@aniakubow/video/7660552059262962966
- Views: 1,800
- Pattern: How hero images load and why it matters.
- Technique: Prioritise the hero image so the first view feels fast.
- Use for: Landing pages, heroes, above-the-fold content.
- Constraint: Loading behaviour affects perceived performance and UX. Balance image quality against load time for the hero.

---

## Excluded from this catalog

Excluded as non-design from the same grid: pure JS / logic, APIs, backend, AI voice / translation tools, Preply / Synthesia promos, career / interview tips, generic "learn HTML" and vague-caption videos that could not be confirmed as design-related from logged-out text alone.
