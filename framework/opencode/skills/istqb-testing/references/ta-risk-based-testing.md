# Test Analyst Chapter 2: Risk-Based Testing

Use this reference when the task is risk analysis, risk control, or choosing regression tests. For basic risk definitions, use Foundation `references/test-management.md` first, then come here for the analyst depth.

## Big picture

Risk-based testing answers the Foundation problem that exhaustive testing is impossible. You cannot test everything, so you test the riskiest things most thoroughly, earliest, and with the strongest techniques, and you test low-risk things lightly, with stakeholder agreement.

The test analyst's contribution is business-facing: the analyst brings impact knowledge (what happens to users and the business if this fails) and contributes to likelihood judgement (how likely is this to fail, given complexity, change, and history). The test manager owns the overall risk process. The analyst owns the product-risk detail inside it.

Risk work has two parts, and confusing them is the most common error in this chapter:

- Risk analysis: identify risks, assess likelihood and impact, and rank them.
- Risk control: mitigate risks by testing and by other means, monitor whether mitigation works, and report residual risk.

## 2.1 Risk analysis

### Identification

Identify product risks before you assess them. Identification techniques include discussion and workshops with stakeholders, interviews with users and developers, checklists of known risk areas, and review of past defects and incidents. Use more than one technique: workshops find risks that checklists miss, and checklists find risks that workshops forget.

Assess risk per test item, not only per product. A product can have a low-risk area (for example a help page) and a high-risk area (for example payment) in the same release. Per-item assessment is what makes prioritisation possible. A single product-level risk rating cannot guide test design.

### Assessment: likelihood, impact, and risk level

Risk level combines two attributes:

- Likelihood: how probable it is that a defect in this item will cause a failure. Factors include complexity, change frequency, developer experience with this area, and past defect history.
- Impact: how bad it would be if it failed. Factors include user harm, financial loss, legal or regulatory consequences, and reputational damage.

Risk level is a function of both, not an average and not a sum. A high-impact, low-likelihood risk can still be high level, depending on the scale the team agreed. Agree the scale before you assess, or every assessment becomes an argument about numbers.

### Three ways to express likelihood and impact

- Quantitative: express likelihood as a probability and impact as an expected loss in money or time, and multiply them to get expected loss. Example: a payment rounding defect has a 10 percent chance of occurring in a release and would cost $50,000 in refunds and rework if it did, so expected loss is $5,000. Quantitative assessment is precise only if the numbers are real. Invented probabilities produce false precision. Use quantitative assessment where historical loss data exists.
- Qualitative: express likelihood and impact on ordered scales, such as low, medium, and high, and read risk level from a matrix. Qualitative assessment is faster and works without loss data, but it has traps: ordinal scales are not numbers, so you cannot average them or multiply them as if they were; and matrices are often deliberately asymmetric, treating high impact more seriously than high likelihood, because impact is harder to undo. State the matrix rule you are using, and do not invent a matrix rule mid-assessment.
- Hybrid (interval): express likelihood and impact as ranges, such as "likelihood 10 to 30 percent, impact $20,000 to $50,000", and combine ranges to get a risk range. Hybrid assessment shows uncertainty honestly, instead of hiding it in a single number or a single label.

Choose the approach that fits the data you actually have. Quantitative with invented data is worse than qualitative with honest judgement.

### Mitigation proposals, scaled to risk level

Risk analysis should end with mitigation proposals, not only a ranked list. Scale mitigation to risk level:

- High risk: strongest techniques, earliest testing, most experienced testers, highest coverage targets, and independent testing where it helps.
- Medium risk: standard techniques, normal coverage, normal timing.
- Low risk: light testing, with stakeholder agreement that the residual risk is acceptable. Light testing is a decision, not an oversight, and it should be recorded as such.

A risk list with no mitigation proposal for its top risks has not finished analysis. It has only described the problem.

## 2.2 Risk control

### Mitigation and monitoring

Mitigation by testing means testing the risky area with techniques, coverage, and independence matched to its risk. Mitigation by other means includes reviews, static analysis, prototyping, and design changes that remove the risk. Testing is not the only mitigation, and for some risks (for example a misunderstood requirement) a review mitigates more than any test suite.

Monitoring means keeping the risk register alive: update likelihood and impact as understanding grows, check whether mitigation is working (for example defects found in a high-risk area confirm the rating; no defects found may mean the rating was wrong, or the tests were weak), and report residual risk. Residual risk is the risk left after mitigation, and it is the input to the release decision. A release decision made without residual risk information is made blind.

Monitor defect patterns as risk signals: defects clustering in an area that was rated low risk mean the rating was wrong, and the rating should be revised and testing reprioritised. Defects not clustering where expected may mean tests are weak, not that the area is safe. Either way, the register changes, and testing changes with it.

### Selecting regression tests

Regression selection is the analyst's most practical risk-control job: after a change, which previously passing tests should rerun, when there is not time to rerun everything?

Selection methods, and when each fits:

- Impact analysis: use traceability and knowledge of interfaces to find which areas the change could affect, and select tests for those areas. This is the most principled method, but it depends on traceability quality. If traceability is stale, impact analysis will miss affected areas.
- Risk-based selection: select tests for the highest-risk affected areas first. This is impact analysis plus prioritisation: it answers not only "what could be affected?" but "what matters most among the affected?"
- History-based selection: select tests that have failed before, or that cover areas with high past defect density. Past failures predict future failures, because defects cluster (Foundation principle 4). A Bayesian-style update is the formal version: start with a prior failure rate, update it with recent results, and select tests with the highest updated failure probability.
- Coverage-based selection: select tests that cover the changed code or the changed requirements. Plain coverage selection can be misleading: a test that covers a changed line but does not check its behaviour adds no protection. Additional-coverage selection (tests that cover something no other selected test covers) is stronger than plain coverage, because it avoids duplicates.
- Traceability-matrix selection: use the matrix that links requirements, code, and tests to select tests linked to changed items. This is impact analysis made mechanical, and it inherits the same traceability-quality dependency.
- Operational-profile selection: select tests that match real usage, so the most-used flows are regressed first. This fits products where usage data is available and where user impact depends on usage frequency.

Combine methods when one method alone is weak. A common combination is impact analysis to find affected areas, risk-based prioritisation to order them, and history-based selection to add tests that have failed before in those areas.

### Dependencies and ordering

Regression tests have dependencies: a test that needs a logged-in user, a created order, or a configured environment must run after its setup, or it will fail for the wrong reason. Repair dependency order when you select a subset: if you select a test but not its setup test, add the setup test, or make the selected test self-contained. A regression subset that fails on setup, not on product defects, wastes the regression window.

### Exercise pattern, in general terms

A typical regression-selection exercise gives a changed area, a new feature, and a time limit, and asks which tests to run and in what order. The correct approach is: impact analysis first (what could the change affect?), risk second (what matters most among the affected?), history third (what has failed before?), dependencies fourth (what setup must run first?). An answer that lists tests without that reasoning, or that runs everything in original order under time pressure, has not applied risk-based selection.

## Traps in this chapter

- Risk analysis versus risk control: analysis identifies and ranks; control mitigates, monitors, and reports residual risk. A ranked list is not control.
- Product risk versus project risk: product risk threatens quality in use; project risk threatens delivery. Testers mitigate product risk by testing. Project risk is managed by planning and escalation.
- Quantitative versus qualitative: quantitative needs real loss data. Invented probabilities are false precision. Qualitative scales are ordinal, not numbers: do not average or multiply them.
- Plain coverage versus additional coverage: a test that covers a changed line without checking it adds no protection. Prefer tests that add unique coverage.
- Residual risk: a risk that was mitigated is not a risk that disappeared. Report what remains, and let stakeholders accept it explicitly.
- Traceability dependency: impact analysis and traceability-matrix selection are only as good as the traceability they use. Validate traceability before trusting a selection made from it.
