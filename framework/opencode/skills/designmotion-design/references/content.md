# Content patterns

Patterns are in source index order. Each entry gives the source pattern URL, the takeaway in paraphrase, the concrete rules, and a do and a do-not. Code snippets are original minimal reconstructions, not the creator's code.

## 21. Empty States

- Source: https://designmotionhq.com/patterns/empty-states
- Takeaway: an empty screen is a first impression and teaching moment, not a blank to leave behind.
- Rules: signal intention with a small illustration or icon, since blank screens look like failures. Write warmly, not in log-file wording. Give one primary action pointing at the next real step, such as creating a project. Tailor copy and action to first run, no results, error, and filtered-out cases. Show a ghost preview of a real item to teach the feature early.
- Do: pair a human explanation with one obvious next step for that situation.
- Do not: leave a bare "No data" screen, or offer only a generic refresh.
- See also: Microcopy (50) for the wording inside empty states, and Search Experience System in interaction.md for the zero-results variant.

## 34. Serial Position

- Source: https://designmotionhq.com/patterns/serial-position
- Takeaway: recall is U-shaped, so people remember the first and last items in a sequence and forget the middle, which makes item order a design decision rather than an afterthought.
- Rules: recall peaks at both ends and bottoms out in the centre, as in a nine-item test where primacy and recency dominate. Treat the first and last slots as bookends, giving highest-value content those positions rather than the buried middle. In navbars, lead with the logo and close with the primary call to action, letting secondary links sit in the forgettable middle. On landing pages, open with the strongest unique selling point and end with the strongest proof, such as testimonials, metrics or guarantees. In onboarding, the first slide should hook and the last should deliver the payoff, while middle steps carry setup nobody will recall verbatim.
- Do: anchor your single most important item at both the start and the end of a sequence.
- Do not: bury critical calls to action or key information in the middle, or order items arbitrarily and assume every position is remembered equally.
- See also: Peak-End Rule in interaction.md, which is about the intensity of a peak and the quality of an ending, not about position in a list.

## 50. Microcopy

- Source: https://designmotionhq.com/patterns/microcopy
- Takeaway: the same form with different words can convert differently, because labels, errors, empty states and tone carry as much weight as layout.
- Rules: button labels should name the reward, not the mechanic: "Create my free account" feels like a gift, while "Submit" feels like a chore, for the same action. Turn errors into help: instead of a bare "Invalid input", name the problem and offer the next move, such as pointing out an email is taken and asking whether to log in. Treat empty states as onboarding, not dead ends: instead of a blank inbox, show the first step the user can take right now. Placeholder text is not a label, since it vanishes the moment typing starts and leaves fields unidentified; keep a persistent label above the input. Write like a person, matching the tone a helpful colleague would use, rather than system-speak such as "operation failed".
- Do: label actions with the reward the user gets and turn error messages into a next step.
- Do not: rely on placeholder text as a stand-in for a persistent label, or ship system-speak errors.
- See also: Empty States (21) and Error States in feedback.md, which are the surfaces this wording lives on.

## 66. Landing Page Skeleton

- Source: https://designmotionhq.com/patterns/landing-page-skeleton
- Takeaway: converting landing pages follow one fixed five-section order, and breaking that order costs trust or clarity.
- Rules: use the five sections in order: hero, proof, problem, solution, and call to action. Make the hero answer what is offered, who it is for, and why it matters in about 3 seconds, with a headline, a subhead, and one call to action. Place social proof directly after the hero: logos, one testimonial, and one hard number. Agitate the problem before pitching the solution, naming its cost in time, money, and frustration. Sell outcomes, not features, capped at three benefits framed as results. Repeat the exact same call to action at top and bottom.
- Do: put proof directly below the hero.
- Do not: hide the hero message inside a carousel or slider.
- See also: De-AI Landing Hero in visual.md for how the hero section itself should look, and Serial Position (34) for why the first and last sections carry the most weight.
