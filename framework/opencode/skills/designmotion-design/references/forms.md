# Form patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 7. Settings System

- Source: https://designmotionhq.com/patterns/settings-system
- Takeaway: a settings page is a system whose rules should scale with risk: instant for harmless toggles, explicit and guarded for identity and destruction.
- Rules: match the apply model to the blast radius: light toggles commit instantly with a saved confirmation, while identity fields such as email demand an explicit Save/Cancel completed by a real click. Group by task, not by org chart: a flat list of twenty rows becomes three scannable sections once it mirrors user intent instead of the data model. Make settings searchable: one query beats digging through six nested menus. Give every changed value a modified indicator plus a per-setting reset, so someone can revert one override without nuking the rest. Quarantine destructive actions at the bottom behind a visual wall, gated by typing the exact resource name; collapse advanced options behind an expandable section.
- Do: match a setting's apply model to its stakes: instant for low-risk toggles, explicit save for identity.
- Do not: pour every option into one flat list ordered by your schema, or let irreversible actions fire on a single unguarded click.
- See also: Destructive Actions in interaction.md for the danger-zone language, and Toggle Anatomy (40) for the toggle itself.

## 8. Autosave

- Source: https://designmotionhq.com/patterns/autosave-ux
- Takeaway: autosave is only trusted when its status is honest: save after a pause, queue work offline, and never claim "Saved" for a write that never landed.
- Rules: never write on every keystroke. Start a debounce timer when typing pauses, reset it on each key, and commit one clean write after roughly 800ms of silence. Model the status indicator as a state machine: typing, saving, saved, offline, error, and never let it read "Saved" when the write never landed. When the connection drops, push every edit into a local queue and surface a badge counting what is pending; on reconnect, drain the queue in order, oldest first. Two tabs on one document make last-write-wins dangerous, so merge concurrent changes or warn the user, never overwrite in silence. Guard the exit: if unsaved work exists, use the browser's beforeunload prompt to intercept a closing tab.
- Do: debounce writes so one clean save fires after a pause (around 800ms), not on every keystroke.
- Do not: let the pill show "Saved" when the change never reached the server.

## 15. Date Pickers

- Source: https://designmotionhq.com/patterns/date-pickers
- Takeaway: a date picker should respect the user's time by leading with presets, making custom ranges legible, and never forcing repeated clicks to reach a nearby month.
- Rules: presets such as Today, Yesterday, Last 7 days, Last 30 days and Last quarter cover roughly 90% of cases in one click, leaving custom ranges for edge cases. For a custom range, hovering should paint a live preview, the first click locks the start, the second locks the end, and the edges stay draggable to refine without restarting. Show two months side by side, widening to three on large screens, so a range can cross a month boundary naturally. Support the full keyboard: arrows across the grid, direct typing, Enter to confirm, Escape to close, Page Up for a month and Shift+Page Up for a year. On mobile, use a full-screen vertically scrolling sheet with today anchored at the top and a large confirm button within thumb reach.
- Do: lead with presets and render two months at once.
- Do not: force repeated "next" clicks for a nearby month, or shrink the desktop popover onto mobile.

## 23. Form Field States

- Source: https://designmotionhq.com/patterns/form-field-states
- Takeaway: a text field is six states: default, focus, error, success, disabled, loading, and any undesigned state becomes a production bug.
- Rules: keep the label above the field and helper text below, since a placeholder-as-label vanishes on typing. Use a focus ring of at least 3:1 contrast, not a faint glow. Signal errors with colour plus icon plus message, as a red border alone is missed by roughly 12% of users. Confirm success inside the field. Distinguish disabled (greyed fill) from loading (spinner blocking input).
- Do: design all six states explicitly.
- Do not: fake disabled with opacity alone, or rely on a border-only red error.
- See also: Toggle Anatomy (40) for a control with its own state set, and Form Validation Timing (49) for when each state appears.

## 26. Input Masking

- Source: https://designmotionhq.com/patterns/input-masking
- Takeaway: formatting while typing makes long digit strings scannable, provided it never fights editing, pasting, or storage.
- Rules: group card digits four by four. Surface the brand inline from the leading digit: 4 Visa, 5 Mastercard, 3 Amex. Keep the caret just after the typed character when a separator is inserted, not at the field end. Validate on blur, not keystroke, so half-typed entries are not flagged. Strip separators on paste and reformat, rather than rejecting the value. Display formatted text but store only raw digits.
- Do: make long numbers readable, brand-aware and paste-friendly while keeping stored data clean.
- Do not: let the caret jump, error on the first keystroke, or save formatting characters.

## 32. Range Sliders

- Source: https://designmotionhq.com/patterns/range-sliders
- Takeaway: dragging is imprecise: a finger cannot reliably land on an exact value, so sliders must be designed around that imprecision.
- Rules: fill the track left of the thumb. Expand the hit area to the full row, not a 4px hairline. Snap to steps with visible ticks when clean values matter. Float the exact value above the thumb while dragging. Support two-thumb ranges for min/max filters. Make sliders keyboard-operable (arrows, Home/End).
- Do: show a filled track, live readout and full-row drag target.
- Do not: rely on a hairline target, leave values continuous when round numbers are needed, or omit keyboard control.
- Original example: `<input type="range" min="0" max="100" step="5" value="50">` with a filled track and live readout.

## 37. Stepper Wizard

- Source: https://designmotionhq.com/patterns/stepper-wizard
- Takeaway: a long form feels like a wall until it is chunked into meaningful steps, each with its own progress, validation and saved state.
- Rules: chunk long forms into small groups: three fields read effortlessly, but twelve in a row trigger scroll fatigue. Group fields by context, not by count, such as Personal, Shipping, Payment and Review; each step should earn its own screen. Always show progress, picking one indicator such as a linear bar, numbered dots or step labels. Validate inside each step rather than at the end, blocking Next while a field is still invalid. Prefer inline errors over final-screen rejection, and persist state on every step change so Back navigation and a page refresh preserve entered data.
- Do: split forms into steps grouped by meaning, show progress, and save entered data on every step.
- Do not: surface a step-one error only at the final step, or let Back or refresh discard everything already typed.

## 40. Toggle Anatomy

- Source: https://designmotionhq.com/patterns/toggle-anatomy
- Takeaway: a convincing toggle does not jump between states; it morphs, with every visible property changing together, and it stays honest while a network request is still in flight.
- Rules: size the rail at twice the knob diameter and pad the knob by its own radius, so it stays centred in both positions. Animate the flip over about 250ms with an ease-out curve, never as an instant snap. Change four things at once: rail colour, knob position via translateX, knob shadow, and the state label, rather than sequencing them. Make it keyboard and screen-reader friendly: Space flips it when focused, a visible ring shows focus, and aria-checked announces the state. For an async toggle, flip optimistically at once, show a spinner inside the knob while waiting, and roll back with a shake and an error toast if the server fails.
- Do: flip immediately, spin the knob while pending, and roll back cleanly on failure.
- Do not: leave the switch looking stuck during a request, or ship a mouse-only toggle.
- Original example: `.toggle-knob { transition: transform 250ms ease-out, box-shadow 250ms ease-out; }`
- See also: Form Field States (23) for the wider state system, and Optimistic UI in feedback.md for the flip-first, reconcile-later rule behind the async case.

## 49. Form Validation Timing

- Source: https://designmotionhq.com/patterns/form-validation-timing
- Takeaway: validation timing is a trade-off between too late and too early, and the sweet spot is to check on blur, then switch to live feedback once a field has already errored.
- Rules: validating only on submit is too late: users fill ten fields, commit, then get hit with a wall of errors all at once. Validating on every keystroke is too early: it flags a field as wrong before the user has even finished typing. The sweet spot is on blur, checking a field the moment focus leaves it, so feedback lands after the user is done but before submit. Once a field has errored, switch to live validation for that field so the error clears the instant it is corrected. Success is feedback too: a green check tells users a field is right, not only when something is wrong.
- Do: validate on blur, revalidate live after an error, and confirm correct fields with a green check.
- Do not: hold every error until submit, or fire red errors on each keystroke before the user finishes typing.

## 55. File Upload UX

- Source: https://designmotionhq.com/patterns/file-upload-ux
- Takeaway: upload is a system of states, drag feedback, honest progress, error recovery, preview and queue, not a bare file input.
- Rules: a dropzone has to answer back the moment a file hovers over it, with border, glow and copy shifting to give three signals before the drop. A spinner hides the truth, so show percent complete and time remaining, letting the user decide to wait or walk away. When an upload dies at 90%, never make the user start over; inline retry keeps the file loaded and resumes in one tap. A filename is not feedback, so show thumbnail, type and size as visual proof the right file was received. In a multi-file queue, each item gets its own progress and its own retry, so one failure never blocks the other nine.
- Do: react to drag-over with border, glow and copy changes, show percent and estimated time remaining, and offer inline retry that keeps the file loaded.
- Do not: rely on a spinner that hides real progress, force a full restart after a failed upload, or treat a bare filename as confirmation.

## 56. Password Field UX

- Source: https://designmotionhq.com/patterns/password-field-ux
- Takeaway: password strength lives in real-time feedback and entropy, not in a checkbox tally of characters and symbols.
- Rules: strength is entropy, not a tally: a longer passphrase beats a mandatory symbol every time. Show the requirements checklist as users type and tick each rule green before submit, never revealing the rules only after a failed attempt. A live strength meter coaches in real time, with a growing bar saying "almost", while post-submit errors only punish after the fact. Add an eye toggle to unmask the field, since masked dots cause silent typos users cannot catch. Never block paste, because password managers fill longer, stronger passwords than anyone types by hand, and the strongest pattern is to offer a generated password in one tap for a unique, saved, never-reused credential.
- Do: surface a live checklist and strength meter, offer a visibility toggle plus a one-tap generated password, and allow paste.
- Do not: hide the rules until after submit, treat a capital-and-symbol checkbox as proof of strength, or block paste.

## 59. OTP Input

- Source: https://designmotionhq.com/patterns/otp-input
- Takeaway: a one-time code field is a small system around one code, not six unrelated boxes.
- Rules: treat paste as the main path: strip spaces and non-digits, then spread digits across all boxes. Auto-advance focus per digit, and let backspace on an empty box move back and clear the previous digit. Model the code as a single string, with boxes only as its view. On mobile use `inputmode="numeric"` and `autocomplete="one-time-code"` for one-tap SMS autofill. Gate resend behind a visible 30-second countdown, since unthrottled resends can trigger a 429 ban. Give instant feedback: shake and clear a wrong code, lock a correct one green.
- Do: store one string and render boxes from it.
- Do not: leave a wrong code sitting silently.
