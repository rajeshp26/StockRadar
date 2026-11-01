# Test Analyst Chapter 3.4 to 3.5: Experience-Based Techniques, Selection, and Automating Test Design

Use this reference for test charters, checklists, crowd testing, technique selection, and automating test design. For Foundation exploratory and checklist-based testing, use `references/test-techniques.md` first, then come here for charter structure, checklist design, and crowd testing at Test Analyst depth.

## 3.4.1 Test charters supporting session-based testing

### When to use it

Use session-based exploratory testing when specifications are thin, time is short, or the goal is to learn about a new area, and you need that exploration to be managed, repeatable, and reportable, not just ad hoc clicking.

A session is a time-boxed exploratory testing activity, typically 60 to 120 minutes, guided by a charter. A charter is a short mission statement for the session. Without a charter, exploratory testing cannot be planned, reviewed, or reported. With a charter, it can.

### Charter structure

A good charter has three parts, in this form: Explore [target], With [resources and tools], To discover [information sought].

- Explore: the target area, such as "checkout error handling" or "booking cancellation flows".
- With: the resources, tools, data, and starting points for the session, such as "test accounts, expired cards, and the payment sandbox".
- To discover: the information the session should produce, such as "defects in discount code handling, unclear error messages, and missing recovery paths".

Add, where useful: session duration, tester, and debrief time. A charter that says only "explore checkout" is not a charter. It has no focus and no discoverable outcome to debrief against.

### Session workflow

1. Plan the session: write the charter, set the time box, and prepare data and environments.
2. Run the session: explore, design tests on the fly, execute them, and log findings as you go, with steps, environment, and data.
3. Debrief: after the session, the tester and a reviewer (often the test manager or a peer) discuss what was covered, what was found, what was not covered, and what should be followed up. The debrief is where learning is shared and where the next charter is shaped.
4. Follow up: log defects, update charters for uncovered areas, and feed findings into risk and test design.

### Limitations and open questions

A charter should also record limitations and open questions discovered during the session, such as "could not test refund to wallet because the wallet sandbox was unavailable" and "unclear whether a cancelled booking should release the slot immediately". Limitations are not failures. They are information for the next session and for risk reporting. A session report that hides its limitations overstates its coverage.

### Worked example, original

Charter: "Explore clinic booking cancellation, With test patient accounts, a booked appointment, and a cancelled appointment, To discover defects in slot release, waiting-list notification, and cancellation messages."

Session findings, logged during the session: cancelling a booking releases the slot, but the waiting-list patient is not notified until the next login (defect, with steps); cancelling twice shows a generic error instead of "already cancelled" (defect, with steps); and wallet refunds for cancelled paid bookings could not be tested because the wallet sandbox was unavailable (limitation, to follow up).

## 3.4.2 Checklists supporting experience-based techniques

### When to use it

Use checklist-based testing when you have a maintained list of conditions to cover, built from experience, past defects, and knowledge of likely failure modes, and you want that experience to be reusable by any tester, not only by the tester who first learned it.

### How to create a checklist

1. Collect conditions from past defects, incident reports, stakeholder knowledge, and known failure modes for this product type.
2. Write each condition as a checkable item, not as a vague topic. "Check security" is not a checklist item. "Check that a deleted record cannot be read back, and that a read of a deleted record returns a clear not-found message" is a checklist item.
3. Organise the checklist by area (for example input handling, error handling, data, usability, security) so a tester can use the relevant part for a given task.
4. Review the checklist with peers and stakeholders, and test it on a real task. A checklist that has never been used is a guess, not a tool.
5. Maintain the checklist: add items when new defect types appear, remove items that no longer apply, and adapt it to each product. A stale checklist becomes a ritual.

### Read-do versus do-confirm

- Read-do: read a checklist item, then do it, step by step. Use read-do for complex, unfamiliar, or high-risk tasks, where missing a step matters.
- Do-confirm: do the task from experience, then use the checklist to confirm nothing was missed. Use do-confirm for familiar tasks, where the checklist is a safety net, not a script.

Choose the mode by task familiarity and risk. Using do-confirm for an unfamiliar, high-risk task invites missed steps. Using read-do for a trivial, familiar task wastes time.

### Usability checklists, as an example

A usability checklist, built from recognised usability principles, might include: system status visible, match to the real world, user control and freedom, consistency, error prevention, recognition over recall, flexibility, aesthetic and minimal design, help with errors, and help and documentation. Each principle becomes one or more checkable items for the product under test, such as "every action that takes more than a few seconds shows progress" and "every error message states what went wrong and how to fix it". Do not copy a generic usability list without adapting it to the product: a checklist item that never applies to this product is noise that hides the items that do apply.

### Strengths, limits, and mistakes

- Strengths: reusable, shareable, and good for covering known failure modes systematically.
- Limits: a checklist only covers what is on it. New defect types, by definition, are not on it yet, so checklists complement exploratory testing, they do not replace it.
- Mistakes: writing vague items that cannot be checked; never maintaining the checklist; and treating checklist completion as coverage, when the checklist itself may be incomplete.

## 3.4.3 Crowd testing

### When to use it

Use crowd testing when you need many diverse users, devices, environments, or usage patterns quickly, and you can manage the logistics that crowd testing creates. Examples: compatibility across many devices and browsers, usability with diverse users, and load or usage patterns that a small team cannot reproduce.

Crowd testing is not beta testing. Beta testing is a late, real-world test by selected users, often for acceptance. Crowd testing is a managed testing activity, with tasks, instructions, reporting, and deduplication, run by a crowd that may be external testers, employees, or customers, depending on the goal and on confidentiality.

### Crowd types

- External crowd: testers recruited outside the organisation, often through a platform. Good for device diversity and fresh eyes. Requires confidentiality controls, because the crowd sees the product before release.
- Employees: staff outside the test team, testing as users. Good for internal products and for confidentiality, but less diverse and less independent than an external crowd.
- Customers: real users, testing in real conditions. Good for realism, but harder to manage, and findings may be reported as complaints rather than as testable defects, so triage matters.

Choose the crowd by goal and confidentiality, not by convenience. A product with sensitive data should not go to an external crowd without masking and access controls.

### Six-stage workflow, in general terms

1. Define the goal, scope, tasks, and success criteria. What should the crowd test, and what counts as a useful finding?
2. Recruit and brief the crowd: select testers, devices, and environments to match the goal, and give clear tasks and reporting instructions.
3. Run the testing: crowd testers execute tasks, explore, and report findings with steps, environment, and data.
4. Triage and deduplicate: the same defect reported by twenty testers is one defect, not twenty. Deduplicate before counting, or defect counts will lie.
5. Fix and verify: developers fix deduplicated defects, and the crowd or the test team verifies fixes, with a focus on the reported environments.
6. Report and close: report coverage (devices, environments, tasks), deduplicated defects, and limitations, such as environments not covered or tasks not completed.

### Safeguards

- Sandboxing: give the crowd a test environment and test data, not production, where possible. If production-like data is needed, mask personal data.
- Confidentiality: use agreements and access controls, and limit what the crowd can see to what the task needs.
- Deduplication: plan for it from the start, with a triage process and a defect tool that can merge duplicates. Without deduplication, crowd testing produces noise, not evidence.

### Strengths, limits, and mistakes

- Strengths: device and user diversity at scale, speed, and fresh perspectives that a small team cannot reproduce.
- Limits: management overhead (recruitment, briefing, triage, deduplication), variable tester skill, and confidentiality risk.
- Mistakes: counting duplicate reports as separate defects; giving the crowd production data without masking; and running crowd testing without a defined goal, so findings cannot be judged against anything.

## 3.5 Applying the most appropriate test techniques

### 3.5.1 Selecting test techniques to mitigate product risks

Technique selection is a risk decision, not a preference decision. For each product risk, ask: which technique, or combination of techniques, best mitigates this risk, given the test basis, the coverage it gives, and the constraints?

Selection factors, in order:

1. Objective: what are you trying to find or prove? A calculation defect needs domain or decision-table testing. A workflow defect needs scenario or state testing. A usability defect needs exploratory or usability testing.
2. Product risk and defect type: match the technique to the risk. High-risk areas get stronger techniques and higher coverage. A technique that is strong for one defect type may be weak for another.
3. Coverage strength: how much of the risk does this technique actually cover? State coverage items and coverage achieved, not only technique names.
4. Test-basis form: what basis is available? A clear specification supports black-box techniques. Code supports white-box techniques. No specification supports experience-based techniques, but with weaker coverage claims.
5. Recurring defects: if the same defect type keeps appearing, choose a technique that targets that type, and add a checklist item for it, so the next release tests for it systematically.
6. Tester skill: a technique the team cannot apply well will not mitigate risk, however strong it looks on paper. Choose techniques the team can apply, and train for the techniques the risk requires.
7. Lifecycle: early phases support reviews, models, and static techniques. Later phases support dynamic techniques. A technique chosen for the wrong phase wastes effort.
8. Contract and regulatory requirements: some contracts and regulations require specific techniques or coverage levels, for example in safety-critical domains. Where a regulation applies, it overrides preference. Check the applicable regulation for the product, do not assume a general rule. As summarised in the book, IEC 61508 uses Safety Integrity Levels SIL 1 to SIL 4, where higher levels require or highly recommend more thorough measures, including boundary analysis, checklists, error guessing, inspections, statement and branch coverage, and, at the highest level, modified condition and decision coverage and state models. DO-178C for airborne software uses Level A (catastrophic failure) requiring modified condition and decision coverage, Level B (hazardous or severe or major) requiring decision coverage, Level C (major) requiring statement coverage, and Levels D (minor) and E (no effect) requiring no structural coverage. Those standards concern white-box structural coverage, outside this chapter's techniques, but they illustrate the principle: higher risk, higher mandated coverage.
9. Project constraints: time, budget, environments, and data limit what can be run. A technique that cannot be run in the available environment is not a mitigation, however strong it is in theory.
10. Combining techniques: most risks need a combination, not a single technique. Example: a payment rule needs domain testing for boundaries, decision-table testing for combinations, state testing for the payment lifecycle, and exploratory testing for usability surprises. State the combination and what each technique contributes, so a missing technique is visible as a gap, not hidden.

### Technique-selection guide, condensed

- Numeric rule with boundaries: domain testing, plus equivalence partitioning and boundary analysis for single dimensions.
- Many interacting parameters: combinatorial testing (pairwise or base choice, by risk).
- No simple oracle, but a known relation: metamorphic testing.
- Data created, read, updated, deleted: CRUD testing.
- State-dependent behaviour: state transition testing, with switch coverage by risk.
- Whole user journey: scenario-based testing.
- Combination rule: decision table testing, minimised.
- Thin specification, new area, or time pressure: exploratory testing with charters, plus error guessing.
- Known failure modes: checklist-based testing, maintained.
- Many devices, users, or environments: crowd testing, with deduplication and sandboxing.
- Quality characteristic: see `references/ta-quality-characteristics.md` for the characteristic-specific techniques.

### 3.5.2 Benefits of automating the test design

Automating test design means generating test cases from a model, rather than writing each case by hand. The model becomes the single source of truth: change the model, regenerate the cases, and the cases stay consistent with the model.

Benefits:

- Consistency: generated cases follow the model exactly, without transcription errors.
- Coverage: generation can systematically cover states, transitions, or combinations that hand-written cases miss, and can state coverage precisely.
- Maintenance: when the model changes, regeneration updates the whole set, instead of editing cases one by one.
- Minimisation: generation can produce minimal sets, for example minimal transition sequences that cover all transitions, using graph methods. A minimal set that covers the same items as a larger hand-written set saves execution time without losing coverage. One method, as presented in the book's case study in miniature, turns a state model into a graph, balances the graph by adding artificial transitions from the final state back to the initial state so every transition can be traversed in one circuit, splits that circuit at each arrival at the final state into separate cases, and replaces any artificial transition with the shortest real path between its endpoints. The method only works because the model was correct and artificial transitions were handled explicitly. A model error would propagate into every generated case.

Risks, and the counter to each:

- Model error: if the model is wrong, every generated case is wrong in the same way, and generation will not catch it. Validate the model with stakeholders and with reviews before generating from it. The model is a specification, and it needs the same review discipline as any specification.
- False confidence: a generated set with high model coverage does not prove the model matches the real system. Test the model against the system, with exploratory testing and with real user scenarios, not only with generated cases.
- Tool dependence: generation depends on the tool and the model format. Keep the model readable and versioned, so it can be maintained without the tool if needed.

Automating test design is not the same as automating test execution. You can generate cases and run them manually, or you can generate and execute them automatically. Decide each separately, by the same rule as in Foundation `references/test-tools.md`: automate what is repetitive, stable, and high-value, and keep exploratory and one-off work manual.
