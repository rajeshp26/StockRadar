# Chapter 4: Test Analysis and Design

Use this reference whenever you derive test cases. Name the technique, list its coverage items, derive the cases, then state the coverage achieved. A test list with no technique and no coverage claim is not finished.

## 4.1 Test techniques overview

A test technique is a systematic way to derive test conditions and test cases, so coverage is deliberate, not accidental.

Three families:

- Black-box (specification-based): derive tests from the specification, without using internal structure. Good when the specification is clear and code is not available or not needed.
- White-box (structure-based): derive tests from internal structure, such as code. Good for measuring code coverage and for behaviour that specifications do not describe.
- Experience-based: derive tests from tester knowledge, past defects, and exploration. Good when specifications are thin, time is short, or risk is unusual.

Coverage is the proportion of coverage items exercised by tests, for example partitions covered, branches covered, or states visited. State coverage as a fraction and a percentage, and name the coverage items. 100 percent coverage of one kind does not mean all defects are found. It means that kind of coverage item was exercised.

Choose a technique by the test basis available, the test level, the risk, the time available, and tester skill. Real test suites mix families. A checkout release, for example, needs equivalence partitioning and boundary analysis for amounts, a decision table for discount rules, state transition testing for the order lifecycle, and exploratory testing for usability surprises.

## 4.2 Black-box test techniques

### 4.2.1 Equivalence partitioning (EP)

Method:

1. Identify each input or output domain and its rules.
2. Split the domain into partitions, groups where the system is expected to treat every value the same way.
3. Include valid partitions (values the system should accept and process) and invalid partitions (values it should reject or handle as errors).
4. Test one representative value per partition.

Coverage: partitions exercised divided by partitions identified.

Worked example, library membership age. Rule: standard membership is for ages 18 to 65 inclusive.

- Invalid partition: age below 18. Representative: 10. Expected: reject for standard membership.
- Valid partition: age 18 to 65. Representative: 30. Expected: accept.
- Invalid partition: age above 65. Representative: 70. Expected: reject for standard membership (senior rule applies instead).

Three partitions, three tests, 100 percent EP coverage for this single input.

Multi-parameter note. For several inputs, "each choice" coverage means every partition of every parameter is exercised at least once, not every combination. Example: age has 3 partitions and membership type has 2 partitions. Each-choice coverage needs at least 3 tests that together cover all 5 partitions. Full combination coverage would need 3 times 2, or 6 tests. Do not claim full combination coverage when you only achieved each-choice coverage.

Trap. EP assumes values in a partition behave identically. If that assumption is wrong, for example a hidden special case inside a partition, EP alone misses it. Boundary analysis and error guessing are the usual complements.

### 4.2.2 Boundary value analysis (BVA)

Method: test at the edges of partitions, because off-by-one errors and comparison errors cluster there (using less than instead of less than or equal to, for example).

Two-value BVA: for each boundary, test the boundary value itself and the nearest value in the adjacent partition.

Three-value BVA: test the boundary value and both neighbours, one inside the partition and one outside it. Three-value is more thorough and costs more tests.

Worked example, same age rule, 18 to 65 inclusive.

Two-value BVA, four tests:

- 17: reject (just below the low boundary).
- 18: accept (low boundary itself).
- 65: accept (high boundary itself).
- 66: reject (just above the high boundary).

Three-value BVA, six tests: 17, 18, 19, 64, 65, 66. The extra tests, 19 and 64, are the neighbours just inside the partition.

Coverage: boundary values (and neighbours, depending on the version used) exercised divided by those identified. State which version you used. "BVA coverage 100 percent" without saying two-value or three-value is ambiguous.

Scope note. BVA needs ordered partitions: numbers, dates, lengths, counts. It does not apply to unordered choices such as payment methods, where EP and decision tables fit better.

### 4.2.3 Decision table testing

Method:

1. Identify conditions (inputs or states) and actions (outcomes).
2. List all combinations of condition values.
3. Remove infeasible combinations, combinations that cannot happen in reality.
4. Collapse rules that give the same outcome, marking the condition that does not matter with a dash.
5. Write at least one test per remaining column. Each column is a rule.

Notation: T means true, F means false, dash means the condition does not matter for that rule, and infeasible combinations are marked and removed, not tested.

Worked example, shop discount and shipping. Conditions: (a) member, yes or no; (b) order total over $100, yes or no. Actions: 10 percent discount, free shipping.

Full table before collapsing, four rules:

- Member yes, over $100 yes: discount yes, free shipping yes.
- Member yes, over $100 no: discount yes, free shipping no.
- Member no, over $100 yes: discount no, free shipping yes.
- Member no, over $100 no: discount no, free shipping no.

Four feasible columns, four tests, 100 percent decision table coverage for this rule set.

Collapsed example. Suppose a promo code gives free shipping regardless of membership and total. Then for the free-shipping action, the member and total conditions become dashes in the promo-code rule, and several columns collapse into one promo-code test. Collapsing is safe only when the outcome really does not depend on the dashed condition. Check that before you collapse, because collapsing on a guess hides a missing rule.

Coverage: feasible columns exercised divided by feasible columns identified.

Value. Decision tables expose missing combinations and contradictory rules that prose requirements hide. If a requirement in prose leaves a combination unmentioned, the table forces a decision about it.

### 4.2.4 State transition testing

Method:

1. Model states, events, transitions, and guard conditions (conditions that must hold for a transition to happen).
2. Draw or list the diagram and the transition table.
3. Design tests that walk through transitions and check the resulting state and any actions.

Coverage levels, weakest to strongest:

- All states coverage: visit every state at least once.
- Valid transitions coverage: exercise every valid transition at least once.
- All transitions coverage: exercise every valid transition and attempt every invalid transition, checking that each invalid attempt is rejected.

Full all-transitions coverage is recommended for safety- or mission-critical software, because invalid transitions are where many state defects hide.

Worked example, order lifecycle. States: Created, Paid, Shipped, Delivered, Cancelled. Events: pay, ship, deliver, cancel.

Valid transitions:

- Created to Paid, on pay.
- Paid to Shipped, on ship.
- Shipped to Delivered, on deliver.
- Created to Cancelled, on cancel.
- Paid to Cancelled, on cancel.

Invalid transitions to attempt under all-transitions coverage, with expected rejection:

- Ship from Created (an unpaid order must not ship).
- Deliver from Paid (an order must ship before it can be delivered).
- Pay from Delivered (a delivered order cannot be paid again).

A valid-transitions suite walks each valid arrow once. An all-transitions suite also tries each invalid arrow and expects rejection, not a silent state change.

Test design tip. For a state diagram, also test the guard conditions. Example: cancel from Paid is valid only if the order has not shipped yet. Test cancel from Paid before shipping (valid) and cancel from Shipped (invalid), because the guard is the shipping step.

## 4.3 White-box test techniques

### 4.3.1 Statement testing and statement coverage

Coverage items are executable statements. Statement coverage equals statements exercised divided by total executable statements, times 100.

Worked example. Code:

```
if age >= 18:
    status = "adult"
else:
    status = "minor"
print(status)
```

Executable statements: the adult assignment, the minor assignment, and the print. That is 3 statements. The if line itself is a decision, not counted as a statement here.

- One test with age 30 exercises the adult assignment and the print: 2 of 3 statements, about 67 percent statement coverage.
- Add a test with age 10, which exercises the minor assignment and the print: 3 of 3 statements, 100 percent statement coverage.

100 percent statement coverage does not mean every decision outcome was tested in a meaningful way. A test can execute a statement without checking the other branch of its condition, and a test can execute all statements while never checking a data-dependent defect.

### 4.3.2 Branch testing and branch coverage

Coverage items are branches, meaning each outcome of each decision: each true and false outcome of an if, each case, each loop exit. Branch coverage equals branches exercised divided by total branches, times 100.

Branch coverage subsumes statement coverage: if every branch is exercised, every statement on those branches is exercised too. The reverse is false.

Worked example, same age code. Branches: true outcome of the age check, false outcome of the age check. That is 2 branches.

- Age 30 alone exercises the true branch only: 1 of 2 branches, 50 percent branch coverage, even though statement coverage was 67 percent.
- Age 30 plus age 10 exercises both branches: 2 of 2 branches, 100 percent branch coverage, and 100 percent statement coverage as a consequence.

Trap. A suite that executes both branches of one if, but never takes the false branch of a second, nested if, still falls short of 100 percent branch coverage, even if statement coverage looks complete. Count branches per decision, not per code block.

### 4.3.3 Value of white-box testing

Strengths:

- Covers the whole implementation, including code paths specifications do not describe.
- Finds defects even when specifications are vague or incomplete.
- Gives an objective coverage measure that can be tracked over releases.
- Can be applied statically by tracing paths through code before execution.

Weaknesses:

- Cannot detect missing requirements. Code that was never written has no branches to cover.
- High coverage does not guarantee correct behaviour. It guarantees exercised structure, not correct logic, correct data, or correct user experience.

## 4.4 Experience-based test techniques

### 4.4.1 Error guessing

The tester anticipates where defects are likely, from experience of past defects, typical developer mistakes, and failures in similar systems, then designs tests to expose them.

Fault attacks are the structured form: build a list of plausible faults and design a test for each. A starter fault list for most systems: null handling, empty input, very long input, zero and negative numbers, overflow, off-by-one, timezone and date boundaries, rounding, duplicate submissions, and concurrent access.

Strength: fast, targeted, finds defects formal techniques miss. Weakness: depends entirely on tester experience, and coverage cannot be measured the same way as for EP or branch coverage. Record the fault list so the work is repeatable by another tester.

### 4.4.2 Exploratory testing

Test design, execution, and learning happen at the same time. The tester explores the system, follows what they learn, and adapts the next test.

Run it as session-based testing: a time-boxed session guided by a test charter, which states the mission, scope, and focus for that session. Example charter: "Explore checkout error handling for 60 minutes, focusing on invalid discount codes, expired cards, and network failures. Log every defect with steps and environment." Findings are logged and debriefed after the session, so learning is shared, not kept in one tester's head.

Best when specifications are incomplete, time is short, or the goal is to learn about a new area. Effectiveness depends heavily on tester skill and on charters that keep sessions focused. Exploratory testing without a charter and without logging is just ad hoc clicking, and it cannot be repeated or reported.

### 4.4.3 Checklist-based testing

Tests are designed from a checklist of conditions to cover, built from experience, past defects, and knowledge of likely failure modes.

Maintain the checklist: add items when new defect types appear, remove items that no longer apply, and adapt the list to the product. A stale checklist becomes a ritual, not a technique.

Difference from error guessing: checklist-based testing works from a written, reusable list; error guessing works from the tester's immediate anticipation. Both are experience-based, but only the checklist is directly reusable by the next tester.

## 4.5 Collaboration-based test approaches

### 4.5.1 Collaborative user story writing

The whole team (business, development, testing) writes user stories together, so testers can ask "how would we test this?" while the story is still being shaped. Stories that are vague, untestable, or too large get fixed before building starts, which is cheaper than fixing them after code exists.

Good stories are small, testable, and written from the user's perspective, with a clear value statement. A story that cannot be tested in its current wording is a defect in the story, not a testing problem to solve later.

### 4.5.2 Acceptance criteria

Acceptance criteria are the conditions a story must meet to be accepted. They are testable, precise, and agreed before or during development.

Example story: "As a shopper, I want to apply a discount code, so I save money." Acceptance criteria:

- The code applies once only, even if the shopper submits it twice.
- An expired code is rejected with a clear message naming the code as expired.
- The discount never makes the total negative; the minimum total is zero.
- The code works with sale items unless the code terms say otherwise.

Each criterion becomes one or more tests. Poor acceptance criteria ("works well", "fast enough") cannot be tested and should be rewritten with numbers or observable behaviour before development starts.

### 4.5.3 Acceptance test-driven development (ATDD)

The team creates acceptance tests from the acceptance criteria before implementation, often in workshops where business, development, and testing agree examples together. The acceptance tests become the shared definition of done and the regression safety net for that story.

ATDD is about collaboration and shared understanding first, automation second. Automating a misunderstood test only locks in the misunderstanding faster. Agree the examples, then automate the agreed examples.
