# Worked Examples: One Product, All Chapters

Use this reference when you need a complete example that combines several chapters, or a template you can copy and fill in. All examples are original. The product is a small online shop with login, catalogue, discount codes, checkout, payment, refunds, and order tracking.

## Example A: End to end test design for checkout

Task: design tests for checkout, using Chapter 4 techniques, Chapter 2 levels, and Chapter 5 risk.

Step 1, risk first (Chapter 5). Highest product risks: payment total wrong, discount applied twice, order shipped unpaid, refund to the wrong card. These get the strongest techniques and run first in execution order.

Step 2, equivalence partitioning and boundary analysis for the order total and discount amount.

- Discount code value: valid codes are $5, $10, and $20. Partitions: no code, $5 code, $10 code, $20 code, invalid code. Test one representative per partition.
- Order total boundary for free shipping at $100: two-value BVA tests are $99.99 (no free shipping), $100.00 (free shipping), plus the boundary on the discount side: a $100 order with a $10 code falls to $90, so decide from the requirement whether free shipping is judged before or after discount, and test that rule explicitly. This is the kind of hidden rule decision tables expose.

Step 3, decision table for discount and shipping combined.

Conditions: member yes or no; order total over $100 yes or no; valid promo code yes or no. Start with all 8 combinations, remove infeasible ones (for example a promo code that already includes free shipping makes the member and total conditions irrelevant for shipping, so those columns collapse), and write one test per remaining rule. Check each combination against the requirement. Any combination the requirement does not mention is a defect in the requirement, not a test to skip.

Step 4, state transition testing for the order lifecycle.

States: Created, Paid, Shipped, Delivered, Cancelled, Refunded. Valid transitions: Created to Paid, Paid to Shipped, Shipped to Delivered, Created or Paid to Cancelled, Delivered to Refunded (with a guard: within 30 days). Invalid transitions to attempt: ship from Created, deliver from Paid, refund from Created, pay from Delivered. Under all-transitions coverage, each invalid attempt must be rejected with a clear message and no state change.

Step 5, levels (Chapter 2).

- Component: discount calculation function, tax calculation function, total calculation function, each with EP and BVA cases.
- Component integration: checkout service talking to payment service, with stubbed payment responses for success, decline, and timeout.
- System: full checkout flow in a staging environment close to production, including functional flows and non-functional checks such as checkout under 2 seconds at peak load.
- System integration: shop system talking to the real payment gateway sandbox and to the shipping provider, checking data exchange and error handling.
- Acceptance: business users run real business processes (order, refund, report) and operations checks backup, recovery, and monitoring.

Step 6, experience-based complement (Chapter 4).

- Error guessing fault list for checkout: empty cart checkout, duplicate submit (double-click the pay button), expired card, card declined, network drop during payment, discount code pasted with spaces, negative quantity, and quantity of 9999.
- Exploratory charter, 60 minutes: "Explore checkout error handling, focusing on invalid discount codes, expired cards, and network failures. Log every defect with steps and environment."
- Checklist, maintained from past defects: discount applied once only, total never negative, tax by region, refund to original payment method, order state after each failure.

Step 7, prioritisation and reporting (Chapter 5).

Execution order: login, checkout payment, discount rules, refunds, then search and cosmetic pages. Status report language: "Payment risk is medium: one critical defect open (discount applied twice), checkout tests 90 percent run, refund tests blocked by the payment sandbox outage." That is a status a decision maker can act on. "90 percent pass" alone is not.

## Example B: White-box coverage, worked with numbers

Code under test:

```
def shipping_cost(total, is_member):
    if total >= 100:
        return 0
    if is_member:
        return 5
    return 10
```

Executable statements: return 0, return 5, return 10. That is 3 statements. Branches: true and false of the total check (2), true and false of the member check (2). That is 4 branches. Note: the member check is only reached when the total check is false, so branch counting must follow the code structure, not count every line twice.

Test set 1: total 120, member false. Executes return 0. Statement coverage: 1 of 3, about 33 percent. Branch coverage: true branch of the total check only, 1 of 4, 25 percent.

Test set 2: add total 50, member true. Executes return 5. Statement coverage: 2 of 3, about 67 percent. Branch coverage: true of total check, false of total check, true of member check, 3 of 4, 75 percent.

Test set 3: add total 50, member false. Executes return 10. Statement coverage: 3 of 3, 100 percent. Branch coverage: 4 of 4, 100 percent.

Lesson to carry: a suite with 100 percent statement coverage can still miss a branch. In this code, test sets 1 and 2 together give 67 percent statement coverage but miss the non-member, under-$100 branch entirely, which is exactly the branch a shopper without membership hits.

## Example C: A defect report, filled in

Use this template for every defect. A report missing any field will come back with questions, which costs a full round trip.

- Title: Checkout total is $10 too low when a $10 discount code is applied twice.
- Environment: build 2.4.1, staging, Chrome 126 on Windows 11, test account shopper01, order with 2 items totalling $60.
- Steps to reproduce: 1. Add 2 items totalling $60 to the cart. 2. Go to checkout. 3. Enter code SAVE10 and click Apply twice quickly. 4. Observe the total.
- Expected result: total $50, code applied once.
- Actual result: total $40, code applied twice.
- Severity: high. Customers are undercharged, and revenue and tax calculations are wrong.
- Priority: high. Checkout is the release-critical flow and the defect is easy for a shopper to trigger by double-clicking.
- Attachments: screenshot of the $40 total, and the order log showing two discount applications.
- Status: new.

Severity and priority are separate here, and they happen to agree. See `test-management.md` for cases where they do not.

## Example D: A test plan skeleton, filled in for one release

Copy this skeleton and fill in each heading. A heading left blank is a decision not made, not a heading to delete.

- Scope and objectives: system and acceptance testing for the checkout release, covering payment, discount, shipping, and refunds. Out of scope: catalogue search redesign, which ships in the next release.
- Test approach: component tests by developers, system tests by testers, acceptance tests by business users, plus exploratory sessions for checkout error handling. Techniques: EP and BVA for amounts, decision tables for discount rules, state transition for the order lifecycle.
- Entry criteria: staging matches production configuration, test accounts exist, payment sandbox available, build passes smoke tests.
- Exit criteria: 95 percent of planned system tests pass, no open critical defects, all high-risk areas covered, product owner accepts residual risks in writing.
- Resources and roles: 2 testers, 1 test manager, business users for acceptance testing, payment sandbox owner on call.
- Schedule: component testing during development, system testing in week 3, acceptance testing in week 4, with regression after every fix.
- Environment and data: staging environment, payment sandbox, test cards for success, decline, and timeout, discount codes for $5, $10, $20, expired, and invalid.
- Risks and mitigations: payment sandbox outage (mitigation: stubbed payment service for system tests, sandbox reserved for integration tests); discount rule ambiguity (mitigation: decision table review with the product owner before test design).
- Deliverables: test plan, test cases, test data, defect reports, test progress reports, test completion report.

## Example E: A review checklist for a requirement

Use this checklist in individual review, before any review meeting, following Chapter 3.

- Ambiguity: does any word have two meanings? Flag "fast", "user-friendly", "etc.", "usually", and "as needed".
- Missing information: what happens on error? What are the limits, ranges, and formats? What happens at boundaries?
- Contradictions: do two rules disagree? Does this requirement disagree with another requirement?
- Testability: can you write a test that passes or fails on this wording? If not, the requirement is defective, not the test.
- Completeness: are all inputs, outputs, states, and error cases covered? Use a decision table or state diagram to check.
- Traceability: does the requirement link to a business need, and does it have an identifier so tests can trace to it?

Worked finding. Requirement: "Discount applies to orders over $50." Review findings: ambiguity, "over" could mean strictly greater than $50 or $50 and over; missing information, is the total judged before or after returns, before or after tax, and before or after other discounts?; testability, a tester cannot write a passing test for a $50 order until those questions are answered. Log each finding as an anomaly with a location, a description, and a suggested fix.

## Example F: An automation decision, worked

Task: decide what to automate for the shop regression suite.

Automate: login smoke test, checkout happy path, discount calculation cases (stable rules, run every release), tax calculation cases, and the order lifecycle happy path at component and integration level. These are repetitive, stable, high-value, and run often.

Keep manual: exploratory checkout sessions, usability checks on the new checkout page, one-off checks for a new payment method in its first release, and visual checks of receipts and emails. These are exploratory, usability, or one-off work, where automation costs more than it saves.

Revisit after the checkout redesign: UI automation written against the old checkout page will break, and its maintenance cost must be weighed again before it is carried forward. That revisit is part of the decision, not an afterthought.
