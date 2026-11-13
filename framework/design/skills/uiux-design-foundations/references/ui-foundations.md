# UI Foundations — Part 1 of From Zero to UI/UX Hero!

Paraphrased digest of the book's UI part (chapters 1–7). Page numbers are PDF pages of the user-supplied copy. Use this file when you need the rule and its source page; use checklists.md for review passes and code-examples.md for token-level implementations.

## What UI design is (pp. 9–12)
- UI design covers the visible, interactive elements of a site or app: buttons, text, icons, and other on-screen components.
- The goal is an interface that is attractive and effortless to navigate at once, function with form.
- Core toolkit: colour theory, typography, and layout principles.
- The work is collaborative: UI designers work with UX designers, developers, and product managers.
- Good UI is not only about appearance: it shapes the whole experience of using the product and sets up good UX.
- Quality shows in details: a sensible palette, appropriate fonts, and a layout that guides the eye. Poor UI drives users away; strong UI builds engagement and loyalty.
- The book teaches in Figma (cloud-based, browser or desktop, real-time collaboration) but stresses that the principles transfer to any tool. Beginners should learn tool basics first, then advanced features.

## Colour (pp. 13–18)

### Vocabulary (p. 13)
- Hue: a pure colour on the wheel. Tint: hue plus white. Tone: hue plus grey (lower chroma). Shade: hue plus black.
- Saturation: colour intensity. Value: how light or dark a colour is.
- Schemes: monochromatic, analogous, complementary, split-complementary, triadic, tetradic, square. Other groupings: primary, secondary, and tertiary colours; warm versus cool colours, with colour temperature used as a harmony device.
- A tint reads as calmer than its saturated hue, and a pure hue is more saturated than its tint or tone.

### Psychology (pp. 14–15)
- Associations are partly subjective: culture, experience, and context can flip how a colour lands, so audience and setting drive choices.
- Broad working associations: red signals alert or urgency, and in food branding warmth and appetite; blue signals trust and professionalism (common in corporate and tech); green signals growth, wellbeing, and nature (suits eco brands).
- Deliberate colour turns an interface into an emotional experience, not just a visual one. Use research and personas to match colour to audience.
- The field has a long practical history: colour psychology is long established in advertising and designed environments (cheerful palettes in ads versus calming blue and green palettes in hospitals), and Jung linked colours to archetypes.
- One finding the book cites: exposure to red before an exam is associated with increased stress and worse performance, a reminder that context can outweigh the generic association.

### Building a palette (pp. 15–17)
- Formats: HEX (six-digit hexadecimal values encoding the red, green, and blue amounts in a colour, a unique precise identifier; white is #FFFFFF, black is #000000), RGB (channels 0–255, screen colour), HSL (best for small adjustments that keep a colour's identity).
- Start from the brand's character: luxury leans on black, gold, rich browns, creamy whites; innovative tech leans vibrant; healthcare leans soft blues and greens for calm and safety.
- Use palette generators and moodboards rather than guessing. Tools named: Adobe Color, Coolors, Realtime Colors.
- **60-30-10 rule:** about 60% dominant colour, 30% secondary, 10% accent. Reserve the accent for calls to action.
- Worked example (a coffee shop site): about 60% deep brown (#6F4E37) as the anchor, about 30% light beige (#F6F6E8), which contrasts gently and suits text, and about 10% bright orange (#FF8C00) reserved for call-to-action buttons.
- Role discipline: backgrounds easy on the eyes, text clearly standing out without overpowering, headings and CTAs prominent but inside the same colour family.

### Contrast (pp. 17–18)
- With poor contrast the failures are concrete: text blends into its background, buttons become hard to find, and key information gets missed.
- Contrast has two components: brightness difference and hue difference. Both must be balanced for legibility.
- WCAG rule of thumb: at least **4.5:1** between text and its background.
- Tools named: Adobe Color contrast checker, Contrast Analyzer, Realtime Colors.
- Contrast shifts with device and lighting, so verify on different devices and environments.

## Typography and type systems (pp. 18–24)

### Basics (pp. 18–19)
- Typography arranges type (face, size, spacing) so text is readable, compelling, and hierarchical.
- A typeface is the family; a font is one style or weight inside it.
- Categories: **serif** (end strokes, traditional and formal, common in print, and the strokes help guide the eye along lines of text: Times New Roman, Georgia), **sans-serif** (no strokes, clean and modern, the digital default: Helvetica, Arial, Roboto), **decorative/display** (stylised, for headlines and branding only: Brush Script, Lobster).
- Font size drives legibility. Line spacing (leading) must be balanced against size. Kerning adjusts space between letter pairs.

### Choosing and pairing (pp. 19–22)
- Choose by context and character first (vintage vs polished), then by category: serifs for formal material, sans-serifs for digital products, display faces for creative pieces.
- Serif options named, with character notes: Times New Roman (the classic default), Georgia (a serif that stays legible on screens), Baskerville (elegant, high-contrast strokes), Garamond (versatile across print and digital), Bodoni (high contrast with sharp serifs, favoured by luxury and fashion brands).
- Sans-serif options named, with character notes: Helvetica Neue, Roboto (built for Google's Material Design), DM Sans (sleek and geometric), Open Sans (clean and simple), Inter (friendly and approachable), Lato (humanistic), Poppins (playful, with distinctive letterforms).
- Pairing rules: the two faces should contrast clearly in style and size so roles are distinguishable; a bold sans for headings with a lighter serif or sans for body is a reliable pattern; use at most one to three typefaces and apply them consistently; vary size, weight, and style inside the set to build hierarchy.
- Sources named: Google Fonts, Fontshare, and font brief. Browse typefaces used on sites and apps you admire for inspiration, then test candidates and pairings on a real page mock before committing.
- The book's eight ready-made heading + body pairings: Space Grotesk + Space Mono; Poppins + Roboto; Inter + Inter (one face for both roles); Inter + Lato; Zen Dots + Space Mono; Hyperspace + Andersans (pitched at space-themed sites); Archivo + Inter; Italiana + Roboto.

### Type system and scale (pp. 23–24)
- A type system is a set of styles that gives all materials one visual language; it supports brand identity and consistent communication.
- Beginner shortcut: adopt the Material type system styles. Reference ladder: body 16px, subtitle 14px, caption 12px, overline 10px.
- Heading structure follows HTML levels H1 to H6, main heading down to deep subsections. Captions add context to images; overlines are small labels that introduce a section.
- Pick the text level by how important the information is in the page hierarchy. On a product page, for example, a caption can carry the short product description while an overline calls out a standout feature.
- Build a type scale from a base size with a ratio: major third (1.25) is the recommended default, with minor third and golden ratio as alternatives. Sizes above the base become headings; sizes below become caption and overline; the base is body text.
- Start from a 16px base (18px suits some brands). Default line height 1.2.
- Tool named: the Typescales Figma plugin generates a scale from a chosen ratio and base.

## Spacing, layout, and hierarchy (pp. 25–32)

### Hierarchy and the 8pt system (pp. 25–26)
- Visual hierarchy is how scale, type, placement, and colour control reading order.
- White space is a design element in its own right: it creates balance and steers the eye to what matters.
- **8pt system (from Google):** build all spacing from multiples of 8px; use multiples of 4 only for fine detail. When torn between two values, pick the multiple of 8.
- Apply consistent spacing to consistent relationships: the same element pair gets the same gap everywhere it appears (the book's example is 16px between a title and its body text).
- A baseline grid of fixed vertical intervals gives the page order and rhythm.

### Grids (pp. 27–30)
- Parts: columns (vertical divisions; 12 desktop, 8 tablet, 4 mobile; typical column width 60–80px; more columns means more layout flexibility), rows (horizontal divisions), modules (cells where rows and columns meet), gutters (gaps between columns and rows, typically about 20px), margins (space between the format edge and content; vary by device; also multiples of 8).
- **Block grid:** one column for continuous text or full-width images; articles, blog posts, about pages.
- **Column grid:** multiple columns (3, 6, 9, or 12 common), elements may span columns; symmetric or asymmetric; suits structured pages such as pricing tables. Keep gutters proportional and consistent.
- **Modular grid:** columns plus rows of equal modules; many items at once, such as app home screens, product listings, galleries (in justified, masonry, or hierarchical styles), archives.
- **Hierarchical grid:** loose, freeform placement where larger items win attention; portfolios and personality-led pages.
- Choose the grid type from the content and the goal; every type has trade-offs.

### Balance and proportion (pp. 31–32)
- Golden ratio (1.618): size elements in that proportion and subdivide at the same ratio for harmonious steps. Worked example: a 1000px-wide header becomes 618px tall, then subdivides the same way.
- Rule of thirds: divide the canvas into nine parts; important elements go at line intersections, supporting elements at the others.
- Balance can be symmetrical (mirrored around an axis) or asymmetrical (balanced by visual weight such as size, colour, and texture).
- Reinforce hierarchy with type: headline, subheading, and body sizes guide the eye through the layout.

## Icons (pp. 34–38)
- An icon is a small graphic standing for an object, action, or concept; icons work across languages and cultures.
- Quality bar: instantly recognisable, appealing, functional. Pair icons with text labels to reinforce meaning (a printer glyph beside the word print).
- Default size 24px; keep sizes divisible by 8 (or at least 4) so spacing stays consistent. Context can shift size: a 16px chevron in a dropdown, or large 32px or 64px arrows in a testimonial section.
- Start from an established library rather than drawing your own. Libraries named: Material Design Icons (recommended for beginners), Font Awesome, Tabler, Carbon, Fluent, Phosphor, Feather. Tool named: the Iconify Figma plugin.
- Use one icon style across the whole product and brand. Never mix filled and outlined icons.
- Mistakes to avoid: icons under 16px, too many icons, unclear meaning, mixed styles, irrelevant glyphs, low-quality assets. Prefer vector SVG, which scales without quality loss.
- Metaphors: represent abstract ideas with concrete, familiar images (light bulb for idea, brain for thinking, cloud for online storage). Know the audience's culture, keep the metaphor simple, and never force a metaphor where a universally understood standard glyph exists (email, phone).

## Buttons (pp. 39–46)
- A good button is intuitive, easy to find, clearly labelled, and visually distinct through contrast.
- Anatomy: background (draws attention), border (defines shape), text (states the action), optional icon (adds context), shadow (adds depth and separation).
- Types: **flat** (solid colour, primary actions, minimal designs), **ghost** (transparent with border, secondary presence without dominance), **text** (no fill or border, tertiary actions and links), **floating action button** (circular, floats above content, one primary action, mainly mobile).
- **1x–2x padding rule:** vertical padding 1x (8px), horizontal padding 2x (16px). It balances the button and reduces accidental taps on neighbours.
- Corners are a brand decision: rounded reads soft and approachable, sharp reads modern and authoritative. Match the audience (strongly rounded, roughly a 32–64px radius, for children; sharp for a law firm); a deliberate break from expectation can make one button stand out.
- Colour hierarchy: the primary button takes the brand accent colour so the main action is recognisable at a glance.
- Action hierarchy: primary solid accent, secondary ghost, tertiary text. Keep the system consistent so users learn what each style means.
- Copy: two to three words, action-oriented, tied to the user's goal, so the result of the click is obvious before the click.
- Building in Figma: make the button from a text element with auto-layout (Shift+A) so it resizes with its label; set horizontal spacing 16px and vertical 8px to match the padding rule; fill with the button colour; set corner radius for the chosen brand look. Auto-layout mechanics: direction arrows set the orientation, the anchor-point grid positions the content (centred by default), and the spacing field starts at a 10px default that you override with the padding values.

## Button states (pp. 47–48)
- Six states to design: **default** (resting), **hover** (cursor over; a web pattern, since mobile rarely supports it), **focus** (keyboard navigation highlight, matters for accessibility; its default appearance varies by browser), **active** (the moment of press; the book also names a pressed state separately on p. 46, and notes the active state is often underused), **disabled** (unavailable; pair with a tooltip that says why), **loading** (spinner or changed label while processing; combine with disabled to prevent duplicate actions).
- Workflow: define the purpose of each state first and build outward from the default state.
- State rules: follow familiar behaviour, keep state styling inside the product's visual family, test each state does its job, and keep transitions simple (KISS).

## White space (pp. 50–54)
- White space (negative space) is the empty area between and inside elements. It does not have to be white; any colour or pattern can be negative space.
- It gives elements breathing room, makes designs read as elegant and modern, and helps the message land. Too much feels unfinished; too little feels cramped.
- Space makes a hero a focal point, separates sections into readable groups, and makes navigation and finding information easier.
- Technique: stay on the 8pt scale with at least 8px between elements, treating values as guidelines rather than hard rules.
- Spacing grows with distance of relationship: 8px for tightly linked pairs (icon beside its nav label), 12px inside components (icon to label in a CTA or field), 16px between closely belonging content (two CTAs, a title with its overline), 32px between distinct elements (title to body, text to CTAs), 64px between loosely related blocks, and 64–160px between page sections.
- Give important elements more surrounding space so they stand out, and always put more space between groups than within them.

## Canonical quick numbers (book quiz recap, p. 49)
- The key number in UI design is 8 (the 8-point spacing system).
- Default icon size: 24px.
- Three typeface families: serif, sans-serif, decorative.
- Typical base text size: 16px.
