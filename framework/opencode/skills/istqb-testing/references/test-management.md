# Chapter 5: Managing the Test Activities

Use this reference when you plan testing, estimate effort, manage risk, report status, control testware versions, or write a defect report. This chapter carries 9 of the 40 exam questions, almost as many as Chapter 4, so do not skim it.

## 5.1 Test planning

### Purpose and content of a test plan

A test plan states what will be tested, why, how, by whom, and when, and what counts as done. It is a communication and control document, not a list of test cases. A full skeleton is in `worked-examples.md`.

Typical contents:

- Scope and objectives: what is in scope, what is out of scope, and why.
- Test approach: levels, types, and techniques, chosen by risk and context.
- Entry and exit criteria, as defined below.
- Resources and roles: who does what, including independence considerations from Chapter 1.
- Schedule and milestones.
- Test environment and test data needs.
- Risks and mitigations.
- Deliverables: what testware will be produced and handed over.

A test plan exists at several levels. An organisation test strategy or policy sits above it. A project test plan covers a project. Iteration or release plans cover smaller slices. Match the plan to the SDLC: a waterfall project gets a fuller upfront plan, an Agile team gets a lighter plan updated each iteration. A plan that nobody updates is worse than a short plan that is kept current.

### Tester's contribution to iteration and release planning

Testers add value to planning by estimating test effort, flagging testability problems in stories, identifying risks, defining what "done" means for testing, and planning test data and environments early. A story that cannot be tested, or needs a rare environment, should surface in planning, not on the last day of the iteration.

### Entry criteria and exit criteria

- Entry criteria: conditions that must be true before testing can start usefully. Examples: test basis available and reviewed, test environment ready, test data prepared, testware reviewed, and the build passes smoke tests. Starting without entry criteria wastes execution time on blocked tests.
- Exit criteria: conditions that must be true before testing can be declared complete for a level or release. Examples: planned tests run, defects fixed and retested, coverage targets met, and residual risk accepted by stakeholders. Exit criteria are agreed in advance, not invented at the end to justify stopping.

Example entry set for system testing: staging environment matches production configuration, test accounts exist, test data is loaded, and the build passes a smoke suite. Example exit set: 95 percent of planned system tests pass, no open critical defects, all high-risk areas covered, and the product owner accepts the two known medium risks in writing.

### Estimation techniques

Estimation is a forecast, not a promise. Record the basis and the uncertainty, so a later variance can be explained.

- Metrics-based estimation: use past data and apply it to the new scope. Examples of past data: average test cases per requirement, defects per test hour, or effort per story point from previous releases. It needs reliable historical data. If past data is missing or the new work is unlike past work, say so and do not present a metrics-based number as precise.
- Expert-based estimation: ask experienced testers or the team to estimate, individually or as a group, using judgement. Group methods that surface disagreement beat a single loud opinion. A practical form: each person estimates privately, the group discusses the spread, and the group re-estimates. The spread itself is information about uncertainty.

Worked example, metrics-based. Past releases averaged 4 test cases per requirement and 0.5 hours to design and run each case. A release with 40 requirements forecasts 160 cases and 80 hours, before adding environment setup and defect retesting. If the new release is riskier than past ones, adjust the forecast up and say why. A forecast with no adjustment and no reason is not an estimate, it is arithmetic.

### Test case prioritisation

Run the most important tests first, so if time runs out, the highest-risk, most-used, or most-changed areas are already covered.

Prioritisation factors: product risk, customer usage, recent changes, dependencies between tests, and defect history. A test that blocks many others, for example login, runs early, even if its own risk is moderate, because every later test depends on it.

Example order for a shop release: login and checkout first, then payment refunds, then search filters, then cosmetic pages last. If only half the suite can run, the first half still covers the release-critical flows.

### Test pyramid

The test pyramid is a shape for how many tests to have at each level: many fast, cheap component tests at the base, fewer component integration tests above them, fewer system tests above those, and a small number of slow, brittle end-to-end or UI tests at the top.

An inverted pyramid, many UI tests and few component tests, is slow, flaky, and expensive to maintain. The pyramid is a guide, not a quota. The right shape depends on risk and architecture, but a suite that is mostly UI tests should be challenged, because it will cost more to maintain than it saves in defect detection.

### Testing quadrants

Quadrants classify tests by two dimensions: business-facing versus technology-facing, and supporting the team versus critiquing the product.

- Q1, technology-facing and supporting the team: component and component integration tests, usually automated, written by developers with testers.
- Q2, business-facing and supporting the team: functional tests, story tests, examples, and prototypes that check the team built the right thing.
- Q3, business-facing and critiquing the product: exploratory testing, usability testing, and user acceptance testing, which judge the product from the user's side.
- Q4, technology-facing and critiquing the product: performance, load, security, and other non-functional tests, which judge technical qualities.

Relationship to levels and types: quadrants cut across levels. A system test can sit in Q2 (a functional story test) or Q4 (a load test). Use quadrants to check for blind spots. A suite with only Q1 and Q2 has no critiquing tests, and a suite with only Q3 and Q4 has no fast, automated safety net.

## 5.2 Risk management

### Risk definition and risk attributes

Risk is the possibility of a negative event. It has two attributes: likelihood (how probable it is) and impact (how bad it would be if it happened). Risk level combines the two, often on a simple scale or matrix. The exact scale is agreed by the team. What matters is consistent use, not the numbers themselves.

Worked matrix, using low, medium, and high for each attribute:

- Likelihood high and impact high: risk level high.
- Likelihood high and impact low: risk level medium.
- Likelihood low and impact high: risk level medium to high, depending on the team's scale. Agree the rule in advance, because this combination is where teams disagree most.
- Likelihood low and impact low: risk level low.

Example. A payment rounding defect has medium likelihood but very high impact, because it charges customers wrongly, so its risk level is high and it gets thorough testing. A typo on an internal help page has high likelihood of being noticed but low impact, so its risk level is low.

### Project risks and product risks

- Project risks threaten the project's ability to deliver: late delivery, staff shortage, unclear requirements, tool failure, environment unavailability, and scope change.
- Product risks threaten the product's quality in use: wrong calculations, data loss, security holes, poor performance, and usability failures.

Testers manage project risks by planning, escalation, and contingency, and manage product risks by testing. Confusing the two leads to testing the schedule instead of the product, or to reporting a product risk as if it were a project delay.

### Product risk analysis

Product risk analysis identifies product risks, assesses likelihood and impact, and ranks them. It uses requirements, past defects, stakeholder input, and domain knowledge.

Risk analysis influences thoroughness and scope: higher-risk areas get more tests, stronger techniques, more experienced testers, earlier testing, and higher coverage targets. Lower-risk areas get lighter testing. This is risk-based testing, and it is how principle 2 from Chapter 1 (exhaustive testing is impossible) is handled in practice.

Risk analysis is repeated as understanding grows. A risk found late, or a risk whose likelihood changes after a design change, should reprioritise testing. A risk register written once at project start and never revisited is decoration.

### Product risk control

Responses to analysed product risks:

- Mitigate by testing: test the risky area thoroughly, with appropriate techniques, coverage, and independence.
- Mitigate by other means: reviews, static analysis, prototyping, or design changes that remove the risk.
- Accept: consciously accept a low risk, with stakeholder agreement, rather than spending disproportionate effort on it.
- Transfer: shift consequences to another party, for example insurance or a supplier contract, where that is possible.
- Contingency plan: prepare actions in advance for what to do if the risk materialises, for example a rollback plan or a manual workaround.

Risk monitoring watches whether mitigations work, reports residual risk (risk left after mitigation), and captures new or changed risks. Report residual risk in status reports, because a release decision is a decision about residual risk, not about test counts.

## 5.3 Test monitoring, test control, and test completion

- Test monitoring collects data about testing and compares actual progress with the plan.
- Test control takes action when there is a gap, for example adding resources, reprioritising tests, changing scope, or extending the schedule.
- Test completion checks exit criteria, reports, and archives testware for reuse.

### Metrics used in testing

Use a few metrics that answer a real question, not every metric available. Metrics by family:

- Progress: test cases designed, run, passed, failed, blocked; milestones met.
- Defect: defects found, fixed, reopened, by severity and priority; defect density; time to fix.
- Coverage: requirements covered, risks covered, code coverage, test conditions covered.
- Risk: residual risk level per area.
- Cost and effort: test effort spent versus planned, cost of testing, cost of fixing.
- Product quality: response time, availability, mean time to failure, where relevant.

A metric without a decision attached to it is reporting theatre. Before you add a metric, say which decision it will inform.

### Purpose, content, and audience for test reports

- Test progress report: written during testing, for the current period. Contents: status against plan, tests run and passed or failed, defects found, risks, and plans for the next period.
- Test completion report: written at a completion milestone. Contents: evaluation against exit criteria, deviations from the plan, product quality assessment, defect summary, residual risks, and lessons learned.

Audience matters. Managers need risk and release readiness. Developers need defect details and reproduction steps. Users need a plain-language quality summary. One report does not serve all three well. Tailor the detail, not the facts.

### Communicating the status of testing

Report in terms of risk, coverage, and quality, not only pass counts. "87 percent of tests pass" hides whether the failing 13 percent cover payment. "Payment risk is still high: two critical defects open, and refund tests are blocked by the environment" is a status a decision maker can act on. Always pair a pass rate with what did not pass, what risk it carries, and what is blocked.

## 5.4 Configuration management

Configuration management controls versions of testware and test objects so the right version is tested, changes are traceable, and results are reproducible.

It covers: version control of test plans, cases, data, and scripts; baselining, meaning freezing a version for a test run; change control for testware; and traceability between versions of requirements, code, and tests.

Without configuration management, a defect cannot be reproduced because nobody knows which build, which data, and which test version were used. With it, a failed test can be rerun against the exact same configuration, and a fix can be verified against the exact configuration that failed.

## 5.5 Defect management

Defect management is the process of finding, logging, classifying, fixing, retesting, and closing defects, with clear ownership at each step.

### A good defect report

Include, in order:

- A clear title that states the problem and where it happens.
- Environment: build, device, browser, operating system, and test data used.
- Steps to reproduce, short and exact, so another person can repeat them.
- Expected result.
- Actual result.
- Severity (impact on the product) and priority (urgency of fixing, a business decision).
- Attachments such as screenshots, logs, or data files.
- Status, following the lifecycle below.

Example title done well: "Checkout total is $10 too low when a $10 discount code is applied twice." Example title done poorly: "Checkout broken." The first can be triaged, reproduced, and fixed without asking the reporter for clarification. The second cannot.

### Severity versus priority

Severity is impact on the product. Priority is order of fixing, decided by the business. They are independent, and exam questions test the combinations:

- Low severity, high priority: a cosmetic typo on the homepage that ships tomorrow and will be seen by every visitor.
- High severity, low priority: a rare crash in an admin tool that few users hit and that has a workaround.
- High severity, high priority: a payment calculation error on the live checkout.
- Low severity, low priority: a typo on an internal help page that few people read.

Never set priority from severity alone, and never set severity from priority alone.

### Defect lifecycle, typical states

New, assigned, fixed, retest, closed, rejected, deferred. Rejected means the report is not a defect, for example it works as designed, and the reason is recorded. Deferred means it is a defect but will be fixed later, with a reason and a date or release recorded. A defect is closed only after confirmation testing passes, not when the developer says it is fixed. A defect that fails confirmation testing returns to the fixed or assigned state, and its reopen count is a useful metric: a defect reopened several times signals a misunderstood root cause.
