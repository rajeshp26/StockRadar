# Test Analyst: Worked Examples, Practice Prompts, Traps, and Checklists

Use this reference for Test Analyst practice. All prompts and examples here are original. They are modelled on the book's technique types, not copied from its sample questions or exercises. For Foundation practice, use `references/exam-and-checklists.md` and `references/worked-examples.md`.

## Worked example A: Technique selection for a booking system

Task: choose techniques for a clinic booking system release, with risks ranked as: double-booking a slot (high), wrong refund after cancellation (high), slow search for available slots (medium), and confusing cancellation messages (medium).

Selection, with reasoning:

- Double-booking: state transition testing for the booking lifecycle (Requested, Confirmed, Cancelled, with guards for slot availability), plus CRUD testing (create a booking, read it, update it, delete it, read again to confirm slot release), plus scenario-based testing for the booking journey including a slot taken during booking.
- Wrong refund: decision table testing for refund rules (cancelled before or after cutoff, paid by card or wallet, first or repeat cancellation), plus domain testing for refund amount boundaries, plus metamorphic testing where the exact refund calculation is complex but a relation holds (for example cancelling two identical bookings separately must refund twice the single-booking refund, where no threshold applies).
- Slow search: this is a performance risk, not a Test Analyst functional risk in the first instance. The analyst contribution is to define the user task and the acceptable time for it, and to flag it for performance testing. Do not answer a performance risk with a functional technique alone.
- Confusing messages: exploratory testing with a charter focused on cancellation messages, plus checklist-based testing for error-message quality (what went wrong, how to fix it, what state the booking is in), plus scenario-based reviewing of the cancellation flow before implementation.

If time runs out, run the double-booking and refund tests first, because they are high risk and user- and money-critical. That ordering is risk-based prioritisation, not preference.

## Worked example B: Domain testing, worked with numbers

Rule: a member may borrow if age is at least 18 and outstanding fines are at most $10. Two dimensions: age (boundary 18) and fines (boundary $10).

- ON points: age 18, fines $10. Expect allow.
- OFF points: age 17, fines $10 (expect reject); age 18, fines $11 (expect reject).
- IN points: age 19, fines $9. Expect allow.
- Corner: age 17, fines $11. Expect reject, with the correct rejection reason.
- Equality check: age exactly 18 and fines exactly $10 must both be tested, because a rule implemented as "greater than 18" or "less than $10" would pass a set that never tests the exact boundary.

Simplified coverage uses ON and OFF points per boundary. Reliable coverage adds IN points and corner combinations. State which one you achieved. Do not claim reliable coverage from a simplified set.

## Worked example C: Combinatorial testing, worked with numbers

Parameters: payment method (card, wallet, bank transfer: 3 values), shipping (standard, express: 2 values), discount (none, code: 2 values). Full combinations: 12 tests.

- Each-choice coverage: at least 3 tests, covering all values across the set.
- Base choice: base case card, standard, none, plus vary payment to wallet and bank transfer (2 tests), shipping to express (1 test), discount to code (1 test): 5 tests total. Base-choice size formula: 1 plus the sum of (values minus 1) per parameter, which is 1 + 2 + 1 + 1, or 5.
- Pairwise coverage: a set where every payment-shipping pair, every payment-discount pair, and every shipping-discount pair appears at least once. That set is larger than 5 and smaller than 12, and it is the right choice if payment-shipping interactions are a known risk.

State the strength. "Combinatorial testing" without a strength is not a coverage claim.

## Worked example D: Regression selection under time pressure

Change: a shop changes its discount calculation and adds a new scheduled-payment feature, under time pressure that allows only half the regression suite to run.

Selection, in order:

1. Impact analysis: discount calculation affects checkout, refunds, receipts, and reporting. Scheduled payments affect payment scheduling, reminders, and cancellation. Select tests for those areas first.
2. Risk: among affected areas, checkout and refunds are highest risk (money-critical), so they run before reporting and reminders.
3. History: add tests that have failed before in discount and payment areas, even if they are not in the highest-risk set, because past failures predict future failures.
4. Dependencies: add setup tests for selected tests, such as login and cart creation, or make selected tests self-contained, so the subset does not fail on setup.
5. Report what was not run, and the residual risk it carries. A regression subset reported as "regression passed" without stating what was not run overstates confidence.

## Worked example E: Defect prevention measures, worked with numbers

- DRE: 180 fixed before release, 30 fixed in the six months after release, 10 found but left unfixed. DRE equals 180 divided by 220, about 82 percent. If 15 more field defects surface later, DRE falls to about 77 percent. DRE is an upper bound, not a true rate, and it measures removal, not cost-effectiveness.
- PCE for requirements: 120 defects introduced in requirements, 36 caught in requirements review. PCE equals 36 divided by 120, or 30 percent. That is weak: 70 percent escaped to later phases.
- CoQ: prevention costs (training, process improvement) plus appraisal costs (testing, reviews) are controllable. Internal failure costs (debugging, fixing before release) and external failure costs (support, patches, reputation) grow with lateness. Spending more early can lower total cost, up to diminishing returns.

## Practice prompts, original, with answers to check yourself

Work each prompt before reading the answer. That is the apply and analyse study method for this level.

1. A rule has two numeric boundaries, age 18 and fines $10. List ON, OFF, and IN points for a reliable domain set, and say why the exact boundary values matter. Answer: ON: 18 and $10. OFF: 17 and $11 (just outside each). IN: 19 and $9 (just inside each). Exact values matter because an equality error (greater than instead of greater than or equal to) passes a set that never tests the exact boundary.
2. Three parameters have 3, 2, and 2 values. What is the base-choice test count, and is it pairwise coverage? Answer: 1 + 2 + 1 + 1, or 5 tests. No, base choice is not pairwise coverage. Pairwise coverage requires every pair to appear, which a base-choice set does not guarantee.
3. A search system has no simple oracle, but adding an irrelevant filter must not add new results. What technique fits, and what is the relation? Answer: metamorphic testing. Relation: results with the irrelevant filter must be a subset of results without it. If new results appear, the relation is violated and a defect is present.
4. A defect is found in a rarely used admin report, but it crashes the report. Severity and priority? Answer: severity high (crash), priority low (rarely used, not release-critical). Severity is impact, priority is order of fixing, and they are independent.
5. A review is led by a trained moderator, and reviewers use scenarios to walk through a workflow. Is this a review type or a review technique, and which one? Answer: both, and they are different things. The review type is technical review (moderator-led). The review technique is scenario-based reviewing (walking through scenarios).
6. A team automates execution for a release and claims defect prevention has improved. Is that claim correct? Answer: no, on its own. Automating execution is detection, not prevention. Prevention changes how defects are created or caught early, for example by reviews, models, and process changes. Automating test design from a validated model can support prevention, but automating execution alone does not.
7. A system passes every specified function test, but users cannot complete a booking task because a step is missing. Which functional subcharacteristic failed? Answer: appropriateness. Completeness (specified functions present) and correctness (results right) can both pass while appropriateness (functions fit the task) fails. Test appropriateness by whole tasks, not by single functions.
8. Two systems exchange data correctly, but interpret a code differently. What interoperability failure type is this? Answer: interpretation failure. Transformation would be conversion error, protocol would be message-order or acknowledgement error, and standards would be non-compliance with an agreed standard.
9. A regression suite must be cut in half. What selection order should you use? Answer: impact analysis first, risk second, history third, dependencies fourth, and report what was not run with its residual risk. Running the first half in original order is not risk-based selection.
10. DRE is 82 percent, PCE for requirements is 30 percent. What does that combination tell you? Answer: overall removal before release looks reasonable, but requirements containment is weak, so many defects escaped requirements into later phases where they cost more to fix. The response is stronger requirements review and model-based specification checks, not just more late testing.

## Trap list for the Test Analyst exam

- Analysis versus design: analysis produces conditions; design produces cases.
- Risk analysis versus risk control: analysis identifies and ranks; control mitigates, monitors, and reports residual risk.
- Review type versus review technique: type is formality; technique is how reviewers examine the product.
- Interoperability versus coexistence: interoperability is analyst work; coexistence is out of analyst scope in this chapter.
- Usability versus interaction capability, and flexibility versus portability: same areas, different names in syllabus and ISO. Translate at first use.
- Completeness versus correctness versus appropriateness: report them separately.
- DRE versus DDP: DRE counts fixing before release; DDP counts detection only.
- DRE and PCE as upper bounds: both fall as late defects surface.
- Base choice versus pairwise: base choice is not pairwise coverage.
- Simplified versus reliable domain coverage: simplified can miss equality-only faults and corner defects.
- Metamorphic coverage: there is no accepted percentage measure. Report relations tested, not a percentage.
- Crowd testing versus beta testing: crowd testing is managed, with tasks and deduplication; beta testing is late, real-world testing by selected users.
- Automating execution versus automating test design: execution automation is detection; design automation from a validated model can support prevention, but only if the model itself is validated.

## Chapter checklists for Test Analyst study

A chapter is ready only when you can explain its ideas without notes and apply its techniques to a new scenario.

### Introduction and role checklist

- I can explain what a test analyst is and is not, and how the role differs from test manager, technical test analyst, and automation engineer.
- I can explain cognitive, social, and subject-matter competence, and why domain knowledge matters for judging behaviour.
- I can state the Test Analyst exam format, points, and pass mark, and why Chapter 3 carries the largest share.

### Chapter 1 checklist

- I can explain when test analysis starts for each test level, and how involvement changes by lifecycle.
- I can walk analysis, design, implementation, and execution, and say what each produces.
- I can distinguish high-level, low-level, and hybrid cases, and judge a case against the quality criteria.
- I can state environment, oracle, and data requirements, and explain keyword layers and testware tool duties.

### Chapter 2 checklist

- I can identify and assess product risks by likelihood and impact, using quantitative, qualitative, or hybrid approaches, and state which approach fits the data available.
- I can propose mitigations scaled to risk level, monitor them, and report residual risk.
- I can select regression tests by impact, risk, history, coverage, traceability, and operational profile, and repair dependency order.

### Chapter 3 checklist

- I can derive domain tests with ON, OFF, IN, and OUT points, and state simplified versus reliable coverage.
- I can build combinatorial sets for each-choice, base-choice, and pairwise coverage, and count them correctly.
- I can design random tests with a distribution, an oracle or property, and a recorded seed.
- I can build a CRUD matrix and check completeness and consistency.
- I can model states with guards, and design 0-switch, 1-switch, and round-trip tests.
- I can design scenario tests for main, alternative, and exception paths, with loop and parallel-completion coverage.
- I can build, minimise, and checksum a decision table, and explain why a correct checksum does not prove the rules are right.
- I can state a metamorphic relation precisely, and design source and follow-up cases for it.
- I can write a charter in Explore, With, To discover form, and run and debrief a session.
- I can design a checklist in read-do or do-confirm mode, and maintain it.
- I can plan crowd testing with a goal, a crowd type, sandboxing, and deduplication.
- I can select techniques by risk, basis, coverage, skill, lifecycle, regulation, and constraints, and state what each technique in a combination contributes.

### Chapter 4 checklist

- I can state the analyst ownership map for quality characteristics, including what is out of scope.
- I can test functional completeness, correctness, and appropriateness separately, with a traceability matrix and whole-task checks.
- I can use the eight interaction-capability parts and the four user-experience factors as test ideas, not just as names.
- I can state accessibility levels and why automated checks alone are not enough.
- I can test adaptability across configurations and locales, and installability across install, update, and uninstall.
- I can distinguish interoperability failure types, and test interoperability at component, integration, system, and acceptance levels, including negative testing.

### Chapter 5 checklist

- I can explain the three aims of defect prevention, and why late testing is detection, not prevention.
- I can calculate DRE, PCE, and CoQ components, and explain why DRE and PCE are upper bounds.
- I can build a model from a specification, find anomalies in it, and derive tests from the validated model.
- I can distinguish review types from review techniques, and choose among ad hoc, checklist-based, scenario-based, role-based, and perspective-based reading.
- I can run the five test-result analyses, and end each with a concrete change.
- I can classify defects, find a recurring pattern, run root cause analysis, propose a process change, and check whether it worked.
