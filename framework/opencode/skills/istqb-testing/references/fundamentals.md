# Chapter 1: Fundamentals of Testing

Use this reference when you need to explain what testing is, justify why it is needed, or check a test approach against the seven principles.

## What testing is

Testing is a process that includes planning, monitoring and control, analysis, design, implementation, execution, and completion. Running code is only one activity inside it. Reviews and static analysis are testing too, even though nothing is executed.

Use these test objectives to judge whether a test plan is complete. A plan should say which of these it serves, not just list test cases:

- Find defects in requirements, design, and code.
- Check that the system meets specified requirements and user needs.
- Build confidence in the quality of the product.
- Give decision makers information about risk and release readiness.
- Prevent defects by finding problems in documents early, before they become code.

## Testing versus debugging

- Testing finds a failure or a defect and reports it.
- Debugging finds the root cause of a defect, fixes it, and is done by the developer.
- Confirmation testing (retesting) then checks that the fix worked. It is testing again, not debugging.

Example. A tester reports that checkout totals are wrong when a discount code is used twice. That report is testing. The developer tracing the total calculation and fixing the double application is debugging. The tester rerunning the exact failing case after the fix is confirmation testing.

## Why testing is necessary

Testing reduces the risk that a released product fails users, loses money, harms safety, or breaks the law. It does this by finding defects early, by checking quality characteristics, and by giving evidence for release decisions.

Testing and quality assurance (QA) are not the same thing. QA is the wider set of process activities that prevent defects and build quality in, such as process standards, audits, and training. Testing is one activity inside that wider effort. Testing alone cannot create quality. A team that tests hard at the end of a poor process will still ship poor quality, later and at higher cost.

## Error, defect, failure, and root cause

Keep this chain exact, because exam questions and defect triage both test it:

- Error: a human mistake. Example: a developer misreads a requirement.
- Defect (also called a bug or fault): the wrong thing left in a work product. Example: wrong code, or a wrong requirement.
- Failure: the system behaving differently from what was expected when it runs.
- Root cause: the earliest reason the error happened. Example: unclear requirements, time pressure, or a skipped review.

Two cautions:

- A defect does not always cause a failure. Dead code, a defect on a path never taken, or a defect masked by another condition can sit quietly until conditions change.
- A failure does not always mean a defect in code. It can mean the requirement was wrong, the test data was wrong, or the environment was wrong. Check all three before you log a code defect.

Worked chain. A product owner writes "discount applies to orders over $50" but means "over $50 after returns". That omission is the error. The specification and the code both use the pre-return total. That is the defect. A customer who returned an item still gets the discount. That is the failure. The root cause is that the return rule was never stated in the requirement.

## The seven testing principles

Use these as a checklist for any test plan or test claim. If a plan violates a principle, say so and say what you will do instead.

1. Testing shows the presence of defects, not their absence. Passing tests lower risk. They never prove that zero defects remain. Never write "the product has no defects" in a test report. Write what was tested, what coverage was achieved, and what risk remains.
2. Exhaustive testing is impossible. Inputs, combinations, paths, and environments are too many to test all of them. Prioritise by risk, as described in Chapter 5. Any claim of "we tested everything" is false on its face.
3. Early testing saves time and money. A defect found in a requirement costs far less to fix than the same defect found after release, because less rework, retesting, and user impact are involved. This is the reason for reviews, static analysis, and shift left work in Chapter 2.
4. Defects cluster together. A small number of modules usually holds most defects. Use past defect data to steer extra testing to those modules, without ignoring the rest. A module with no past defects is not automatically safe; it may simply be untested.
5. Tests wear out. Repeating the same tests finds fewer new defects over time. Review suites regularly, add new cases, retire cases that no longer find anything, and add exploratory testing. The older name for this idea is the pesticide paradox.
6. Testing is context dependent. Safety-critical software, a banking app, and a games app do not get the same test approach, depth, or documentation. Judge a test approach against its context, not against a universal checklist.
7. Absence-of-defects fallacy. A product can pass all its tests and still be wrong for users if the requirements themselves missed what users needed. Verification (did we build the product right, against the specification?) is not enough. Validation (did we build the right product, for real user need?) matters too, and acceptance testing is where it is checked most directly.

## Test activities, in order

The activities overlap and iterate. Do not treat them as a strict waterfall inside testing itself.

- Test planning: define objectives, scope, approach, resources, schedule, and risks.
- Test monitoring and control: compare progress against the plan, report status, and take corrective action when there is a gap.
- Test analysis: turn the test basis (requirements, user stories, code, risks) into test conditions, and check whether the basis is testable. If a requirement cannot be tested, raise that as a defect in the requirement, not as a testing problem to solve later.
- Test design: turn test conditions into test cases and other testware, using the techniques in Chapter 4.
- Test implementation: build testware, organise cases into procedures, prepare data and environments, and check entry criteria before execution starts.
- Test execution: run tests, log actual results, compare with expected results, and report defects.
- Test completion: collect data, evaluate exit criteria, report, and hand over reusable testware for maintenance and regression testing.

## Testware and traceability

Testware is everything testing produces: test plans, test conditions, test cases, test data, test procedures, test results, defect reports, and test completion reports. Put testware under version control, like code. An unversioned test suite cannot be rerun reliably.

Traceability links the test basis to testware and back. It answers two questions: which requirement does this test cover, and which tests cover this requirement? Use it for coverage reporting and for impact analysis when a requirement changes. If a requirement changes and its linked tests are not rerun, coverage reporting will lie.

## Roles in testing

- Tester: designs, implements, runs, and evaluates tests, and reports defects clearly.
- Test manager: plans, monitors, controls, reports, and manages resources, risks, and stakeholders.
- In small or Agile teams one person may do both jobs, but the responsibilities stay distinct. A plan written by the same person who executes it still needs monitoring against its own exit criteria.

## Essential skills and good practices

Skills to develop, in order of how often they decide whether testing helps:

- Analytical thinking and curiosity: ask what could go wrong, not only what should happen.
- Attention to detail: read requirements for ambiguity, missing information, and contradictions.
- Clear communication: a defect report that a developer cannot reproduce is wasted work. See the defect report template in `worked-examples.md`.
- Domain knowledge and technical understanding: know the business rules and know enough about the technology to test interfaces, data, and failure modes.

Good practices that recur through the whole syllabus:

- Whole team approach: everyone owns quality. Developers test their own code, testers test early and coach the team, and quality is not thrown over a wall to testers at the end.
- Independence of testing: the more independent the tester is from the author, the more likely they are to find different defects, because they do not share the author's assumptions. Degrees, from least to most independent: the author tests their own work; a peer tests it; an independent tester in the same team tests it; a separate test team or outside organisation tests it.
- Balance independence with domain knowledge. An outside tester may be independent but know too little about the domain, and communication can slow down. Choose the degree of independence that fits the risk.
- Start testing early, base testing on risk, keep testware maintainable, and communicate status in terms of risk and quality, not only pass counts.

## Chapter 1 traps

- "No defects found" does not mean "no defects exist".
- "We tested everything" is not a defensible claim.
- Finding a defect is not debugging. Fixing it is not testing.
- QA is wider than testing. Testing alone does not create quality.
- Severity is impact. Priority is order of fixing. They are decided separately, and Chapter 5 explains why.
