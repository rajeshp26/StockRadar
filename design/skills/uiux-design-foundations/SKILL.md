---
name: uiux-design-foundations
description: Apply the UI and UX foundations from From Zero to UI/UX Hero! by Conrad Böhnke (UI Rocket, 2024) — colour and contrast, typography and type scales, the 8pt spacing system and grids, icons, button systems and states, white space, user research and personas, the UX laws, information architecture, and advanced theory such as cognitive load, mental models, the Action Cycle, and Flow. Use when designing or reviewing a website or app interface, setting design tokens, or backing a design decision with a named principle.
---

# UI/UX Design Foundations

Apply the foundations from From Zero to UI/UX Hero! by Conrad Böhnke (UI Rocket, 2024) when you design or review a website or app interface. Use this skill for the principles, the process, and the review checklists behind a design. When the user wants a pure CSS or HTML pattern with copy-paste code, use the ania-kubow-design skill instead. When the pattern needs JavaScript, React, or motion code, use the settigation-code skill instead.

## Start from the user and the story

- Ask three questions before you design anything. What problem does this solve, what feeling should it evoke, and whose life does it make easier.

- Research before pixels. Pick from interviews, observational studies, surveys, focus groups, card sorting, and usability testing, then analyse the results for patterns before you design.

- Build personas from research, not from stereotypes. Analyse findings, identify characteristics such as goals and frustrations, give the persona a name and a face, write a short backstory, then share it with the team.

- Match the mental models users already hold. Favour familiar patterns, introduce new patterns sparingly, and change the system to fit expectations before you ask users to relearn.

- Keep persuasive techniques ethical. Use reciprocity, social proof, and authority to help users decide, and never use false scarcity or dark patterns.

## Lay the UI foundations

- Build colour on the 60-30-10 rule. Give the dominant colour about 60 percent, the secondary about 30 percent, and the accent about 10 percent, and reserve the accent for calls to action.

- Choose colour with psychology and audience in mind. Colour associations shift with culture and context, so let research and personas settle the palette.

- Hold text contrast at or above the WCAG ratio of 4.5 to 1. Check contrast on real devices and in real lighting, not only in the design tool.

- Set type as a system. Use at most one to three typefaces, pair faces that contrast clearly in role, and build a type scale on a ratio such as major third from a 16px base with a line height around 1.2.

- Space everything on the 8pt system. Use multiples of 8 for spacing and margins, 4 only for fine detail, and let the gap size signal how related two elements are.

- Pick the grid from the content. Use a block grid for long reading, a column grid for structured pages, a modular grid for many equal items, and a hierarchical grid when a few items should dominate.

- Treat icons as a system. Start from an established icon library, use 24px as the default size, keep one style across the product, and pair icons with text labels wherever meaning could be ambiguous.

- Design buttons as a hierarchy. Make the primary action a solid accent button, secondary actions ghost buttons, and tertiary actions text buttons, with short action wording of two to three words.

- Design all six button states. Cover default, hover, focus, active, disabled, and loading, and size button padding by the 1x to 2x rule of 8px vertical and 16px horizontal.

- Use white space to group and to rank. Put more space between groups than within them, and give headings and calls to action the most surrounding space.

## Apply the UX laws

- Name the law behind each decision. The full set with applications lives in references/ux-laws.md.

- Use Miller's Law to chunk content and limit working memory load, Jacob's Law to stay familiar, and Hick's Law to cut and sequence choices.

- Use the Law of Proximity to group, Fitts's Law to size and place targets, and Weber's Law to ship change gradually rather than in one abrupt redesign.

- Use the Aesthetic-Usability Effect knowingly. Beauty raises perceived usability and forgiveness, but it can also mask real problems in testing.

- Use the Endowed Progress Effect and the Zeigarnik Effect for momentum. Give users a head start on progress indicators, and let unfinished steps pull them back to complete.

- Use the Von Restorff Effect sparingly. Make one element in a set stand out, usually the primary call to action, and keep the standout accessible.

## Structure the experience

- Audit content before you structure it. Run a content audit, then card sort with target users to shape categories in their language.

- Make navigation answer three questions at all times. Where am I, where can I go, and how do I get back.

- Audit flows against Don Norman's Action Cycle. Check that users can form a goal, act on it, perceive the result, interpret the feedback, and judge the outcome at every step.

- Design feedback to close the cycle. Confirm every action immediately and write error messages a user can interpret without help.

- Manage cognitive load. Simplify, chunk, signpost the next step, follow conventions, remove unnecessary steps, and declutter so the interface absorbs complexity instead of the user.

- Design for flow. Give clear goals, immediate feedback, and a challenge level matched to skill, use progressive disclosure for depth, remove distractions, and keep the user in control with undo and no forced paths.

- Guide the eye on purpose. Use the structural net focal points, shape axes, and in-image cues such as gaze and gesture to route attention to the most important element.

## Work the process

- Set direction with a moodboard first. Collect typography, colour, aesthetics, layout, shape, and motion references, keep the board consistent, and offer two directions when a client must choose.

- Sketch before you go digital. Move from paper sketches to low, mid, then high fidelity wireframes, and raise fidelity only as the feedback justifies it.

- Evaluate every iteration against three questions. Does it fulfil its purpose, does it match the user needs found in research, and is it feasible in time, budget, and technology.

- Involve developers early and keep them involved. Share a design system or style guide, hand off through a shared workspace such as Figma, and hold regular check-ins rather than one final handoff.

- Test continuously. Combine usability testing, user acceptance testing, and A/B testing, and keep testing after launch because users and competitors change.

## Verify before you present

- Run the review checklists in references/checklists.md for the surface you touched. Cover colour and contrast, type, spacing, icons, buttons, navigation, cognitive load, and flow.

- Ground each rule in references/ui-foundations.md or references/ux-foundations.md when you explain a decision. Both files cite the book page behind each rule.

- Give the worked example from references/code-examples.md when you deliver tokens, a grid, or a button. Every example there is an original implementation of the book rules, not book content.

- Paraphrase the book, never quote its body text. Credit the source through ATTRIBUTION.md and cite page numbers from the references when a rule matters.

- Say what this skill does not cover. The book is a beginner foundations text, so it has no advanced design system operations, no research statistics, and no pattern level CSS or JavaScript, which the two sister skills cover.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [UI Rocket](https://ui-rocket.com) for the author's compiled UX laws material and related articles. The book also points readers to UI Rocket on Instagram and YouTube (@UIRocket) for ongoing tips and design feedback.
- [UX Laws](https://uxlaws.com) for the wider laws collection the book points readers to.

## Alternatives for better results

- Ask whether the user wants a review of an existing design against the checklists, or a fresh layout built on the foundations, before you start.

- Offer the rules as tokens early. A spacing scale, a type scale, and a palette with contrast values settle most later decisions.
