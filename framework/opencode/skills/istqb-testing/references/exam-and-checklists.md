# Exam Format, Glossary, Traps, and Checklists

Use this reference for CTFL exam preparation and for a final check before you claim a piece of testing work is complete. It contains no official exam questions. All practice prompts here are original.

## Exam format

- Exam: ISTQB Certified Tester Foundation Level (CTFL), version 4.0, current syllabus revision 4.0.1.
- Questions: 40 multiple-choice questions.
- Duration: 60 minutes, with extra time for non-native English speakers where the exam provider allows it. Confirm the allowance with your provider before you book.
- Pass mark: 26 correct out of 40, which is 65 percent.
- No prerequisites. CTFL is the entry point to the ISTQB scheme and a prerequisite for higher ISTQB certifications where Foundation Level is required.

## Question split by chapter

Use this split to allocate study time. Chapter 4 is the largest, and Chapter 5 is larger than most candidates expect.

- Chapter 1, Fundamentals of Testing: 8 questions.
- Chapter 2, Testing Throughout the Software Development Lifecycle: 6 questions.
- Chapter 3, Static Testing: 4 questions.
- Chapter 4, Test Analysis and Design: 11 questions.
- Chapter 5, Managing the Test Activities: 9 questions.
- Chapter 6, Test Tools: 2 questions.
- Total: 40 questions.

Training time in the syllabus, for accredited courses, is 180 minutes for Chapter 1, 130 for Chapter 2, 80 for Chapter 3, 390 for Chapter 4, 335 for Chapter 5, and 20 for Chapter 6. Training time is not the same as exam weight, but both point the same way: Chapters 4 and 5 dominate.

## K-levels: what the verbs mean

- K1, Remember: recognise, remember, or recall a term or concept. Study method: flashcards and definitions, tested from memory.
- K2, Understand: explain why an example fits a concept and why a nearby alternative does not. Study method: explain each concept in your own words, with a counterexample.
- K3, Apply: use a technique or method on a new scenario and work out the answer. Study method: work examples from new scenarios before checking the answer. Most K3 questions come from Chapter 4 techniques and from Chapter 5 planning and estimation.

Question split by K-level: 8 K1 questions, 24 K2 questions, 8 K3 questions. All content in Chapters 1 to 6 is examinable at K1 level, meaning any term in a chapter heading can be asked as a recall question, even if it is not in a specific learning objective.

## Glossary, in plain terms

- Test basis: the documents, code, or other artefacts from which tests are derived, such as requirements, user stories, or code.
- Test condition: an item or event that could be verified by a test, derived from the test basis.
- Test case: a set of preconditions, inputs, actions, expected results, and postconditions, designed to verify a test condition.
- Test procedure: a sequence of test cases in execution order, with setup and teardown steps.
- Testware: everything produced by testing, including plans, cases, data, procedures, results, and reports.
- Test object: the component or system being tested.
- Defect: a flaw in a work product that can cause a failure.
- Failure: behaviour that differs from what was expected, observed during execution.
- Error: a human mistake that can lead to a defect.
- Root cause: the earliest reason an error happened.
- Coverage: the proportion of coverage items exercised by tests.
- Confirmation testing: rerunning a failing test after a fix, to confirm the fix.
- Regression testing: rerunning passing tests after a change, to check for side effects.
- Entry criteria: conditions that must be true before testing can start usefully.
- Exit criteria: conditions that must be true before testing can be declared complete.
- Severity: impact of a defect on the product.
- Priority: urgency and order of fixing a defect, a business decision.
- Product risk: a risk to product quality in use.
- Project risk: a risk to the project's ability to deliver.
- Residual risk: risk left after mitigation.
- Static testing: testing a work product without executing it.
- Dynamic testing: testing by executing the software.

## Trap list: the mistakes that cost marks

- Testing shows the presence of defects, not their absence. Never choose "testing proves there are no defects".
- Exhaustive testing is impossible. Never choose "test every combination" as a feasible plan.
- Testing is not debugging. Finding is testing. Fixing is debugging.
- QA is wider than testing. Testing alone does not create quality.
- Confirmation testing checks the fix. Regression testing checks for side effects. Do not swap them.
- Walkthrough is author-led. Technical review and inspection are moderator-led. Inspection is the most formal review type.
- Branch coverage subsumes statement coverage. Statement coverage does not subsume branch coverage.
- Two-value BVA tests the boundary and one neighbour outside. Three-value BVA tests the boundary and both neighbours. State which version you used.
- Decision table coverage counts feasible columns only. Infeasible combinations are removed, not tested.
- All-transitions coverage includes invalid transitions. Valid-transitions coverage does not.
- Severity is impact. Priority is order of fixing. They are independent.
- Product risks threaten quality. Project risks threaten delivery. Do not swap them.
- Automation checks what it was told to check. Passing automation does not prove the product is right.
- The test pyramid has many component tests at the base and few UI tests at the top. An inverted pyramid is a warning sign, not a goal.

## Chapter checklists

Use these to mark each chapter as studied, practised, or ready. A chapter is ready only when you can explain its ideas without notes and apply its techniques to a new scenario.

### Chapter 1 checklist

- I can explain testing versus debugging, with an example.
- I can walk the error, defect, failure, root cause chain for a new scenario.
- I can state all seven principles and give an example and a violation for each.
- I can list the test activities in order and say what each produces.
- I can explain testware and traceability, and why testware needs version control.
- I can explain whole team approach and degrees of independence, with their trade-offs.

### Chapter 2 checklist

- I can explain how sequential, iterative, Agile, and DevOps models change testing.
- I can explain shift left, TDD, ATDD, and BDD, and what each drives.
- I can list the five test levels and say, for each, its basis, objects, and typical defects.
- I can distinguish functional, non-functional, black-box, and white-box testing, including their overlap.
- I can distinguish confirmation testing from regression testing, with examples.
- I can explain maintenance triggers and how impact analysis scopes regression testing.

### Chapter 3 checklist

- I can list work products examinable by static testing.
- I can explain the value of static testing and how it differs from dynamic testing.
- I can list the five review process activities in order.
- I can name the six review roles and say what each does.
- I can order the four review types by formality and say who leads each.
- I can list review success factors and spot a review plan that violates them.

### Chapter 4 checklist

- I can derive EP partitions, including valid and invalid partitions, for a new rule.
- I can derive two-value and three-value BVA sets for a new range, and state the coverage.
- I can build a decision table, remove infeasible combinations, collapse rules safely, and state the coverage.
- I can build a state model, list valid and invalid transitions, and state which coverage level I achieved.
- I can calculate statement coverage and branch coverage for a small code sample, and explain why branch coverage subsumes statement coverage.
- I can explain error guessing, exploratory testing with charters, and checklist-based testing, and say when each fits.
- I can write testable acceptance criteria and explain ATDD as collaboration first, automation second.

### Chapter 5 checklist

- I can list the contents of a test plan and explain entry versus exit criteria.
- I can estimate effort by a metrics-based method and by an expert-based method, with the basis and uncertainty stated.
- I can prioritise a test set by risk, usage, change, and dependency.
- I can draw the test pyramid and explain the testing quadrants, including their relationship to levels and types.
- I can assess risk level from likelihood and impact, distinguish product from project risks, and list product risk control responses.
- I can choose metrics by family and say which decision each metric informs.
- I can distinguish a test progress report from a test completion report, and tailor a report to its audience.
- I can explain configuration management and why it matters for reproducibility.
- I can write a defect report with all required fields, and explain severity versus priority with examples.

### Chapter 6 checklist

- I can list tool categories by the activity they support.
- I can check a tool for fit, team skill, budget, integration, and ownership, and describe a pilot.
- I can list benefits and risks of test automation, and explain why passing automation does not prove correctness.
- I can apply the decision rule: automate repetitive, stable, high-value tests that run often; keep exploratory, usability, and one-off tests manual.

## Practice prompts, original, with answers to check yourself

Work each prompt before reading the answer. That is the K3 study method.

1. A field accepts ages 18 to 65 inclusive. List the two-value BVA set. Answer: 17, 18, 65, 66.
2. Same field. List the three-value BVA set. Answer: 17, 18, 19, 64, 65, 66.
3. A defect is found in a rarely used admin report, but it crashes the report. The release ships tomorrow and the report is not in the release notes. Is severity high or low, and is priority likely high or low? Answer: severity high (crash, data loss risk), priority low (rarely used, workaround exists, not release-critical). Severity and priority are independent.
4. A developer fixes a defect. What do you run first, and what do you run after? Answer: confirmation testing on the exact failing test first, then regression testing on affected areas.
5. A review is led by the author, who walks reviewers through a design. Which review type is it? Answer: walkthrough.
6. A suite executes every statement but misses one branch of a nested if. What can you claim? Answer: statement coverage may be 100 percent, but branch coverage is below 100 percent. Branch coverage subsumes statement coverage, not the reverse.
7. A test suite is mostly UI tests, with few component tests. What is wrong with its shape? Answer: it inverts the test pyramid. It will be slow, flaky, and expensive to maintain.
8. A team automates 500 regression tests and they all pass. Can the team claim the product has no defects? Answer: no. Automation checks known cases only. It does not prove absence of defects, and it does not cover misunderstood requirements or usability problems.
