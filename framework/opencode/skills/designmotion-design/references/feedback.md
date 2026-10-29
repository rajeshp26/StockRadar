# Feedback patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 17. Doherty Threshold

- Source: https://designmotionhq.com/patterns/doherty-threshold
- Takeaway: perceived speed is a design choice, and crossing about 400ms is where a user mentally checks out, so the interface must react inside that window even if the real work takes longer.
- Rules: the Doherty Threshold is 400ms: respond faster and attention holds, slower and engagement starts to break. Response zones split roughly into under 200ms feeling instant, 200-400ms being tolerable, and over 400ms starting to disconnect the user. What matters is perceived speed, not raw speed; the real work can take longer as long as the interface reacts within the threshold. Skeleton loading paints placeholder shapes the instant a screen opens, so it never looks frozen while data arrives. Optimistic UI updates the screen as if the action already succeeded, reconciling only if the server rejects it, while spinners, progress bars and inline status keep an unavoidable wait feeling responsive.
- Do: give visible feedback within 400ms of any interaction, even if it is only a skeleton or acknowledgement.
- Do not: leave the screen blank or frozen while data loads, or wait for a server round-trip before any visual response.
- See also: Loading States System (27) for which waiting pattern fits which wait, and Optimistic UI (51) for the update-first variant.

## 22. Error States

- Source: https://designmotionhq.com/patterns/error-states
- Takeaway: the same failure feels different depending on where it appears, how plainly it is explained, and whether a way out is offered.
- Rules: match surface to severity: inline for field errors, toast or banner for transient problems, modal only for blockers. Always offer retry, support, or expandable detail, never a dead end. Explain what broke, why, and what to do next in plain language. Validate inline as users type, turning criteria green, rather than waiting until submit. Keep field validation small, specific, and anchored to its input.
- Do: give every error a recovery path sized to its severity.
- Do not: interrupt a minor slip with a full-screen modal, or show a raw code with no guidance.
- See also: Notification System (29) for the surface map, and Toast Notifications (39) for toast lifetimes.

## 27. Loading States System

- Source: https://designmotionhq.com/patterns/loading-states-system
- Takeaway: loading is a system matched to what is known about the wait, not one default skeleton for every fetch.
- Rules: show nothing under about 300ms, since a brief flash reads as a glitch. Use skeletons only when content shape is known and the wait exceeds roughly 300ms. Use spinners for short unknown waits under about 3s, never across a full page. Use progress bars over about 3s where a percentage is known, paired with time remaining. Use optimistic UI for reversible actions, updating instantly and surfacing errors only if sync fails.
- Do: choose from what you know: shape, percentage, or neither.
- Do not: skeletonise every fetch, cover a page with an endless spinner, or flash a loader under 300ms.
- See also: Skeleton Loading (53), which is only the skeleton member of this system, and Optimistic UI (51), which is only the instant-update member. Keep all three distinct: this entry picks the pattern, the other two detail one member each.

## 29. Notification System

- Source: https://designmotionhq.com/patterns/notification-system
- Takeaway: notifications are four surfaces at four volumes, and choosing the wrong volume trains users to ignore everything.
- Rules: map severity to surface: toast for low priority, banner for degraded service, modal for blocking problems such as a declined card, badge for passive counts. Respect persistence: toasts auto-dismiss with undo, banners stay until cleared, modals block until acted on, badges sit until resolved. Let toasts stack with breathing room, but never queue modals together. Avoid over-escalation, since routing everything to the loudest surface yields zero attention.
- Do: let severity pick the surface, and let low-priority alerts stack.
- Do not: use a blocking modal for purely informational messages, or stack modals together.
- See also: Toast Notifications (39) for toast placement, lifetimes and stacking limits inside this system.

## 39. Toast Notifications

- Source: https://designmotionhq.com/patterns/toast-notifications
- Takeaway: a toast should pass on information without seizing the screen, so its position, lifetime and exit route all need to be chosen deliberately rather than left to a default.
- Rules: anchor toasts bottom-right on desktop and along the top edge on mobile; never centre them over the work area, where they cover content and block clicks. Match lifetime to severity: routine messages around 4 seconds, warnings around 7 seconds, and critical errors held until the person acknowledges them. Show at most three at once, with the newest arriving at the bottom and older ones drifting up and out, the rest queued. Always offer an exit: a close button on desktop, swipe away on mobile, and a countdown that pauses on hover. Code each type by colour plus an icon and an accent border, since colour alone is unreadable for roughly 6% of users.
- Do: pause the dismiss timer while the user hovers, so the message can actually be read.
- Do not: auto-dismiss a critical error, or stack more than three toasts at once.
- See also: Notification System (29), which decides when a toast is the right surface at all.

## 44. Zeigarnik Effect

- Source: https://designmotionhq.com/patterns/zeigarnik-effect
- Takeaway: unfinished business stays in active memory while finished business is dropped, so a visible, meaningful gap can quietly pull people back, whereas a fully closed loop gives them no reason to return.
- Rules: the mind holds open tasks and releases closed ones, so open loops keep drawing attention back. A meter stuck at about 80% creates return pressure; a checklist shown as fully done removes that pull. In onboarding, deliberately leave one box unchecked, so the visible gap nudges people to come back and finish setup. Profile-completion meters are the everyday version of the same mechanic, with an 80%-done state acting as a persistent, low-friction pull. The effect only fires for outcomes the user genuinely wants; a manufactured progress bar on something nobody asked for creates no pull at all.
- Do: leave a visible gap tied to an outcome the user actually cares about.
- Do not: close every loop at 100%, or fake progress on chores nobody requested.
- See also: Peak-End Rule in interaction.md, which is about remembered peaks and endings, not about the pull of an open loop.

## 47. Undo UX

- Source: https://designmotionhq.com/patterns/undo-ux
- Takeaway: undo is kinder and faster than asking permission for everything, because the action happens at once and regret gets a second chance, while real irreversibility is the only place that earns heavy friction.
- Rules: undo beats confirmation: a blanket "Are you sure?" punishes everyone for one person's mistake, while undo punishes nobody. Treat deletion as a state, not an event: soft-delete by setting a flag, keep the item in trash for about thirty days, then purge it. Reserve heavy friction for actions with no way back, such as requiring the user to type a repository name before deleting it. One undo is a toast, but a stack is a time machine: an undo stack lets Cmd+Z walk back through every step in order. Use delayed send to turn a delay into a feature, holding a sent email for about ten seconds. Show the countdown visibly, with a draining ring or bar, so people know exactly how long their second chance lasts.
- Do: execute immediately, then offer a time-limited undo with a visible countdown, and soft-delete with a recovery window.
- Do not: block every destructive action behind a confirmation dialog, or hard-delete data the instant someone clicks.
- See also: Destructive Actions in interaction.md for the friction that belongs before the action, and Bulk Actions for the 10-second undo on bulk deletes.

## 51. Optimistic UI

- Source: https://designmotionhq.com/patterns/optimistic-ui
- Takeaway: an interface feels instant when it updates the moment the user acts and reconciles with the server in the background, rather than making the user wait for confirmation.
- Rules: update the UI the instant the user acts, then sync with the server in the background instead of blocking on the response. The brain reads anything under 400ms as instant, while a spinner past that threshold makes the action feel broken. When the request fails, roll back cleanly: undo the like and restore the count, as if it never happened. The core bet is to trust the success case, which is almost always what happens, and handle the rare failure gracefully. Reserve this for reversible, low-stakes actions such as likes, toggles and reorders, where an occasional rollback costs nothing.
- Do: update the interface immediately, reconcile behind the scenes, and roll back cleanly on failure.
- Do not: use it for payments, transfers or anything that cannot be safely undone, or show a charge or booking before the server has actually cleared it.
- See also: Loading States System (27), which chooses optimistic UI only for reversible actions, and Behind the Button in interaction.md, which forbids it for money.

## 53. Skeleton Loading

- Source: https://designmotionhq.com/patterns/skeleton-loading
- Takeaway: a spinner says something is happening but not what or how long, and that uncertainty is what makes waits feel slow, while a well-shaped skeleton lets the brain start parsing the layout early.
- Rules: a spinner gives zero information about what is coming or how long it will take, and that uncertainty stretches perceived waiting time. Skeleton screens preview the shape of incoming content, such as an avatar circle, text bars and an image block, so the brain starts parsing layout before data arrives. The shimmer sweep matters: a static skeleton reads as broken, while an animated one reads as in progress. Match the skeleton to the real content dimensions; a skeleton that jumps to a different layout on load is worse than a spinner. For actions the user just performed, such as posting or liking, skip loading states entirely, render the result optimistically and reconcile in the background.
- Do: shape skeletons to mirror the final layout, animate them, and keep them under about two seconds before showing partial content.
- Do not: use skeletons for sub-300ms loads, where a flash of skeleton is noise, or mix spinners and skeletons in the same view.
- See also: Loading States System (27), which is the chooser for skeletons versus spinners versus progress bars.
