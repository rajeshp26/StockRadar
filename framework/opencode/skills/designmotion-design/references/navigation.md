# Navigation patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 28. Navigation Patterns

- Source: https://designmotionhq.com/patterns/navigation-patterns
- Takeaway: navigation is one system chosen by platform and depth: bottom tabs on mobile, persistent sidebar on desktop.
- Rules: use mobile bottom tabs with 3-5 top destinations always visible, since hiding them in a hamburger drops engagement by roughly 40%. Use a persistent desktop sidebar for 5 or more hierarchical sections. Treat the hamburger as secondary only, since hiding desktop menus drops engagement by roughly 56%. Offer a command palette (Cmd/Ctrl K) for power users, but pair it with visible nav. Reserve breadcrumbs for hierarchies deeper than two levels.
- Do: match pattern to platform and depth, keeping primary destinations visible.
- Do not: hide primary nav in a hamburger, make a palette the only path, or breadcrumb a flat structure.
- See also: Tabs System (38) for the tab control itself, and Command Palette in interaction.md for the palette that supplements this system.

## 38. Tabs System

- Source: https://designmotionhq.com/patterns/tabs-system
- Takeaway: treat tabs as a connected system for navigation and switching, not as a lone decorative widget; the indicator, the panel change and the mobile form all have to move together without jumping.
- Rules: let the active indicator glide with a spring, timed to the panel fade, entering slowly and leaving quickly. Never wrap an overflowing row onto a second line; scroll it sideways, hint at hidden tabs with edge fades, and add chevrons on desktop. Support arrows to move between tabs, Home for the first, End for the last, and Tab to leave the group. Keep the focus ring and the active state in different colours so keyboard position and selection are never confused. Cross-fade panels with about an 80ms pause and matched heights, so nothing shifts. On mobile, use a segmented control below five tabs and a bottom sheet above five.
- Do: glide the indicator and fade the panel as one coordinated change.
- Do not: shrink the desktop tab bar down for mobile or wrap the row.
- Original example: `.tabs-indicator { transition: transform 250ms ease-out; }`
- See also: Navigation Patterns (28), which decides when tabs are the right navigation shape at all.

## 45. Focus States

- Source: https://designmotionhq.com/patterns/focus-states
- Takeaway: keyboard navigation is only usable when focus is always visible, follows the order people actually see, and never leaks out of a dialog or vanishes when it closes.
- Rules: removing the default outline is not a styling choice but an accessibility failure, unless it is replaced with something better. A proper ring needs three qualities: about 2px thick, about 2px offset, and enough contrast to stay visible on both light and dark backgrounds. Use `:focus-visible` to tell mouse and keyboard apart, so a click shows no ring while a Tab press does. Focus follows DOM order, not visual layout, so reordering columns with CSS while leaving the DOM untouched makes Tab jump across the page; keep visual and DOM order in sync. Inside a modal, trap focus so Tab cycles and wraps within the dialog, Escape closes it, and focus returns to the element that opened it. Put a skip link first on the page, invisible until focused, so it jumps past dozens of navigation links in one keypress.
- Do: replace any removed outline with a contrasting, offset custom ring, and place a skip link first.
- Do not: strip the outline with no replacement, or let a modal leak focus to the page behind it.
- Original example: `:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }`

## 60. Pagination

- Source: https://designmotionhq.com/patterns/pagination
- Takeaway: paging must stay stable when the list changes, or items will be duplicated or skipped.
- Rules: prefer cursor paging, anchored to a specific row, when rows change often, because offset paging drifts as the list shifts. Choose the style by job: numbered pages for jumping anywhere, load-more for on-demand appends, infinite scroll for continuous feeds. Truncate long ranges to first, last, current and neighbours, with an ellipsis for gaps. Keep the page number in the URL, for example `?page=500`, so refresh and sharing land on the same page. On return from a detail view, restore scroll position instead of dumping the user at the top.
- Do: persist the page in the URL.
- Do not: render hundreds of numbered links that spill off-screen.
