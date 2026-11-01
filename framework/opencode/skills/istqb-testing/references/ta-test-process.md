# Test Analyst Chapter 1: Tasks in the Test Process

Use this reference when the task is analyst work inside a test activity, or when the task is about testware: cases, oracles, data, environments, scripts, or tools.

## Who the test analyst is, in process terms

The analyst is an independent, specification-based, business-facing tester, working mainly at system, system integration, and acceptance levels. Independence matters because the analyst does not share the developer's assumptions about what the specification meant. Business-facing means the analyst judges behaviour from user tasks, not from code structure.

## 1.1 Testing in the software development lifecycle

Test analysis should begin when the test basis is produced, not when code is finished. For acceptance testing, the test basis is requirements, so analysis begins during requirements work, by reviewing the basis for testability. That early start is what makes defect prevention possible: a defect in the basis, found by analysis, never becomes a defect in code.

How involvement changes by lifecycle:

- Sequential lifecycles: analysis, design, implementation, and execution follow development phases in order, with clear entry and exit criteria per phase. The risk is late feedback if analysis is postponed.
- Incremental lifecycles: each increment repeats the test activities, and regression control becomes central, because each new increment can break earlier increments. Analyst work includes deciding what to regress after each increment.
- Iterative lifecycles: feedback from each iteration improves the next iteration's analysis. Conditions and cases are refined as understanding grows, not frozen at the first pass.
- Hybrid and Agile (including Scrum): the analyst works inside the team and iteration, advising on story testability during planning, designing tests during the iteration, and executing in the same iteration where possible. Refactoring is a risk to watch: a refactor that is meant to change nothing can change behaviour, and regression tests are the safety net that proves it did not.

## 1.2 Involvement in the test activities

### 1.2.1 Test analysis

Test analysis turns the test basis into test conditions, and checks whether the basis itself is fit for testing.

Steps, in order:

1. Read the test basis: requirements, user stories, design, spoken knowledge from stakeholders, and risks. Spoken knowledge counts as a basis, but write it down, or it cannot be traced or retested.
2. Check entry criteria: is the basis available, reviewed, and stable enough to analyse? If not, raise basis defects instead of guessing.
3. Identify test conditions: what needs to be verified, for each part of the basis. A condition is not yet a test case. It is a verifiable item, such as "discount applies once only".
4. Check basis defects: ambiguity, missing information, contradictions, and untestable wording. Log each as a basis defect with a location and a suggested fix.
5. Build traceability: link each condition back to its basis item, so coverage can be reported and impact analysis can work later.
6. Prioritise conditions by risk, so the most important conditions are designed and executed first if time runs out.

Staged conditions help when the basis is large: start with high-level conditions (business processes, major functions), then refine to detailed conditions (rules, boundaries, error cases) as understanding grows. Do not design detailed cases for a condition that is still ambiguous at high level.

### 1.2.2 Test design

Test design turns test conditions into test cases, with pass and fail criteria, and into test charters for exploratory work.

Steps:

1. Choose a technique for each condition, using the selection guide in `references/ta-test-design-experience.md`. The technique determines the coverage items.
2. Derive cases from the condition, using that technique. State the coverage items and the coverage achieved.
3. Write pass and fail criteria that are observable: a value, a message, a state, a file, or a measurable behaviour. "Works correctly" is not a criterion.
4. Keep traceability: each case traces to its condition and to its basis item. A case with no traceable condition is either a duplicate or a test for an unstated requirement. Either way, resolve it, do not just run it.
5. Surface environment and data needs during design, not during execution. If a case needs a specific environment, data state, or external service, record it in the case.
6. Agree exit criteria for the level: what coverage, what pass rate, what defect state, and what residual risk acceptance count as done. Exit criteria agreed during design prevent arguments at the end.

For exploratory work, design means writing a charter, not writing cases. See `references/ta-test-design-experience.md`.

### 1.2.3 Test implementation

Test implementation builds the testware needed to run the cases: test suites, test data, environments, test procedures, and test scripts.

Key distinctions:

- A test suite is a set of cases grouped for a purpose, such as smoke, regression, or a release.
- A test procedure is a sequence of cases in execution order, with setup and teardown steps.
- A test script is an automated or manual sequence that executes cases, often using keyword-driven testing (see below).
- Prioritisation applies again here: order suites and procedures so the highest-risk, most-used, and dependency-blocking tests run first.
- Check readiness before execution: suites built, data loaded, environments available, smoke tests passing. A suite that cannot run in its environment is not ready, even if its cases are written.

In continuous delivery pipelines, implementation includes making suites runnable in the pipeline, with fast feedback. A suite that takes hours to run cannot give feedback per change, and should be split into fast and slow suites.

### 1.2.4 Test execution

Test execution runs tests, logs results, and triages anomalies before reporting defects.

Steps:

1. Run cases in priority order, following procedures and scripts.
2. Log actual results against expected results, with environment, data, and build recorded, so a failure can be reproduced.
3. Triage anomalies before reporting a defect: is this a real defect, a testware defect, a data problem, an environment problem, or a misunderstood requirement? Reporting a testware defect as a product defect wastes a full triage cycle.
4. Run confirmation testing for fixed defects (the exact failing case, rerun) and regression testing for affected areas (previously passing tests, rerun). See Foundation `references/sdlc.md` for the distinction, and Test Analyst `references/ta-risk-based-testing.md` for how to choose regression scope.
5. Update traceability as results arrive: which conditions are now covered, which failed, which are blocked. Coverage reporting that is not updated during execution lies about readiness.
6. Report status in terms of risk, coverage, and quality, not only pass counts.

Traceability has limits, and an analyst should know them: traceability can be out of date, too coarse (one link covering many cases), or misleading when severity and priority diverge (a traced, high-severity defect that is low priority can look like a blocker, or vice versa). Check traceability quality, do not just trust its existence.

## 1.3 Tasks related to testware

### 1.3.1 High-level and low-level test cases

- A high-level test case states what to test, in general terms, without exact input values or exact steps. Example: "Check that a discount code applies once only."
- A low-level test case states exact inputs, steps, expected results, and data. Example: "Enter code SAVE10 twice on a $60 order; expect total $50, not $40."
- A hybrid case mixes both: high-level intent plus low-level detail where it matters, such as exact boundary values.
- Extra low-level variants add no coverage without new conditions. Ten low-level cases for the same condition, with only cosmetic input changes, do not cover ten times as much. Count conditions, not cases, when you judge coverage.

### 1.3.2 Quality criteria for test cases

Judge every case against these criteria, and fix cases that fail them:

- Feasible: it can actually be run, in the available environment, with available data.
- Precise: inputs, steps, and expected results are exact enough that two testers would run it the same way and judge it the same way.
- Correct: the expected result follows from the test basis, not from a guess or from current (possibly wrong) behaviour.
- Concise: no unnecessary steps or data. Extra steps add failure modes that are not the condition under test.
- Complete: all steps, data, preconditions, and postconditions needed to run it and judge it are present.
- Traceable: it links to its condition and basis item.
- Necessary: it covers a condition that no other case covers, or it covers it in a way no other case does.
- Understandable: a tester who did not write it can read it and run it.
- Consistent: it does not contradict other cases or the basis.
- Maintainable: when the basis changes, the case can be updated without rewriting the whole suite.

Quality debt is the accumulation of cases that fail these criteria. A suite with quality debt looks large and is actually weak: it takes longer to run, fails for the wrong reasons, and hides missing coverage.

### 1.3.3 Test environment requirements

An environment must be fit for the tests it will run, not merely available. Judge an environment by:

- Fidelity of outcome: results in this environment predict results in production, for the conditions under test. A test that passes in a low-fidelity environment and fails in production has not given evidence.
- Testability versus defect detection: an environment that is easy to control (for example with test data injection) may hide defects that only appear in realistic conditions. Balance control against realism.
- Cost and benefit: a production-like environment for every test is expensive. Use lighter environments for early, fast tests and production-like environments for system and acceptance tests where fidelity matters most.
- Robustness and predictability: the environment should behave the same way on rerun, or failures cannot be reproduced. Flaky environments produce flaky results, and flaky results are ignored.
- Timing: environment needs should be identified in two stages, during design (what is needed) and during implementation (is it ready). Discovering an environment need during execution is a planning failure.

Record per-item attributes for each environment need: what data, what external services, what configuration, what access, and what fallback exists if the environment is unavailable.

### 1.3.4 Test oracles

The oracle problem is: how do you know what the correct result should be? Without an oracle, a test can run but cannot pass or fail. It can only be observed.

Oracle types, from weakest to strongest evidence:

- Human oracle: a person judges the result against their knowledge. Flexible, but slow, inconsistent, and not repeatable.
- Pseudo-oracle: another implementation, an older version, or a simplified model that produces an expected result to compare against. Useful, but if both implementations share a misunderstanding, both agree and both are wrong.
- Model-based oracle: a formal or semi-formal model of expected behaviour, from which expected results are derived. Strong, but the model itself must be validated, or it becomes a second specification that may be wrong.
- Property-based oracle: a property that must hold for every result, such as "total never negative" or "sorted output is in order". It does not give the exact expected result, but it catches violations reliably.
- Metamorphic oracle: a relation between related inputs and outputs, such as "adding an irrelevant item must not change the discount for other items". See `references/ta-test-design-rule.md` for metamorphic testing.

Choose the strongest oracle available for the risk. High-risk calculations need a model or a pseudo-oracle, not a human glance. Low-risk display checks may be fine with a human oracle, if the check is recorded.

### 1.3.5 Test data requirements

Test data must be designed, not just found. Judge data by:

- Purpose: each data set should serve a named condition, such as a boundary, an error case, or a realistic user journey.
- Coverage: data should cover the partitions, boundaries, and combinations the technique requires.
- Format: data must match the format the system expects, including edge formats such as empty, very long, and special-character values.
- Production versus synthetic data: production data is realistic but may contain personal data, may be out of date, and may not contain the edge cases you need. Synthetic data can be designed for coverage, but may miss realistic distributions. Use synthetic data for edge cases and personal-data safety, and production-like data for realistic journeys, with personal data removed or masked.
- Confidentiality: personal, financial, and health data in test environments must be protected like production data, or not used at all.
- Maintainability, dependencies, and availability: data should be versioned, its dependencies recorded (for example an order needs a customer and a product), and it should be available when tests run, not created by hand each time.
- Data ageing: data that was valid last release may be invalid now, because rules, dates, or reference data changed. Refresh data as part of test implementation, not as an afterthought.

### 1.3.6 Keyword-driven testing and test scripts

Keyword-driven testing separates what to test from how to automate it. A test script is built from keywords, each keyword being a named action or check with parameters.

- Action keywords perform an action, such as "CreateUser" or "ApplyDiscountCode".
- Verification keywords check a result, such as "CheckTotal" or "CheckOrderState".
- Domain-layer keywords express business actions, such as "PlaceOrder". Interface-layer keywords express technical actions, such as "ClickButton" or "EnterText". Domain keywords are more stable and more readable; interface keywords change whenever the interface changes.
- Atomic keywords do one thing. Composite keywords combine atomic keywords into a larger business step. Composite keywords are easier to read, but harder to reuse if they hide too much.
- Roles: the test analyst defines the keywords and the test logic in business terms. The automation implementer implements the keywords technically. That separation is the point: analysts can write and maintain tests without writing automation code, and implementers can change implementation without rewriting tests.
- Quality rules: keywords should be named clearly, take explicit parameters, do one thing, and be maintained as a library, with duplicates removed and outdated keywords retired. A keyword library that is not maintained becomes a second codebase with its own defects.

### 1.3.7 Tools for managing testware

Tools an analyst uses, by purpose:

- Test management tools: organise cases, suites, execution, and reporting, with traceability.
- Defect management tools: log, classify, track, and report defects.
- Test data tools: create, mask, version, and load test data.
- Configuration management tools: version testware, so the right version is tested and results are reproducible.
- Requirement management tools: hold the test basis and its traceability links.

The analyst's duties with tools are organising (structure cases and suites so they can be found and reused), metadata (record enough information that a case can be understood and rerun later), traceability (keep links current), regression management (keep regression suites current as the product changes), and configuration (use the right version of each testware item). A tool does not do these duties. It only makes them possible. A test management tool full of outdated, untraced cases is worse than a small, current set, because it looks complete.

## Traps in this chapter

- Analysis versus design: analysis produces conditions; design produces cases. A condition is not a case, and a case without a condition is unaccountable.
- High-level versus low-level: more low-level variants do not mean more coverage. Count conditions.
- Confirmation versus regression: confirmation checks the fix; regression checks for side effects. Both are needed, in that order.
- Oracle strength: a human glance is an oracle, but a weak one. Match oracle strength to risk.
- Keyword layers: domain keywords are stable; interface keywords are brittle. If every interface change breaks every test, the keyword layering is wrong.
