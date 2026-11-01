# Chapter 2: Testing Throughout the Software Development Lifecycle

Use this reference when you need to fit testing to a development model, choose test levels and types, or scope maintenance testing.

## 2.1 Testing in the context of an SDLC

The SDLC shapes when testing can happen, what test levels exist, and how much documentation is useful. No single SDLC fits every project. Judge a test approach against the SDLC it lives in.

### Sequential models

Waterfall runs phases in order: requirements, design, implementation, testing, deployment. The V-model pairs each development activity with a matching test level, so requirements pair with acceptance testing, system design with system testing, detailed design with integration testing, and code with component testing.

- Strength: clear gates and traceability from each development artefact to a test level.
- Weakness: feedback arrives late if testing is left to the end, and late defects are expensive (Chapter 1, principle 3).

### Iterative and incremental models

Work is delivered in small increments. Each increment is tested, and feedback feeds the next increment. Testing repeats every iteration, and regression testing grows with each increment, which is why regression automation matters more here than in a single-release model.

### Agile

Short iterations, working software each iteration, testers embedded in the team, whole-team quality ownership, and documentation that is just enough to be useful. Testers contribute during story writing and planning, not only during a test phase at the end of the iteration.

### DevOps

Development and operations merge, delivery is continuous, and testing is automated in the pipeline so every change can be built, tested, and released quickly. Testing must be fast, automated where it pays, and monitored in production, because production behaviour becomes test evidence too.

### Good testing practices across SDLCs

- Test every development activity, not only code. Review requirements, design, and testware.
- Test early. Involve testers from the start of a story, feature, or release.
- Keep traceability between the test basis and testware.
- Adapt the test approach to the context, following principle 6 from Chapter 1.

### Testing as a driver for development (test-first)

In test-first work, tests are written before the code they test, so they define the expected behaviour and drive a small, testable design.

- Test-driven development (TDD): write a failing component test, write just enough code to pass it, then refactor. The cycle is short and repeats many times a day.
- Acceptance test-driven development (ATDD): the team agrees acceptance tests for a story before building it, so "done" is defined in advance and shared by business, development, and testing.
- Behaviour-driven development (BDD): acceptance tests are written in a shared, plain-language Given-When-Then form, so business, development, and testing share one understanding of the behaviour. Example: Given a shopper with a valid $10 code, When they apply it at checkout, Then the total falls by $10 and the code cannot be applied again.

Test-first does not remove later test levels. Component tests written first still need system, integration, and acceptance testing around them.

### Shift left

Shift left means moving testing earlier: reviewing requirements before coding, static analysis in the editor, component tests in the same sprint as the code, and test data prepared during planning. It finds defects when they are cheapest to fix and shortens feedback loops. It does not mean "only test early". Later levels still catch integration, system, and user-need defects that early testing cannot see.

### Retrospectives and process improvement

At the end of an iteration or release, the team reviews what worked, what did not, and what to change. Apply the same loop to testing: measure (defects found, escaped, coverage, effort), learn (which technique or activity found the most valuable defects?), change one thing, and check whether it helped. Change one thing at a time, or you will not know what worked.

## 2.2 Test levels

Each level has its own test basis, test objects, typical defects, and people responsible. Levels are not a ranking. A defect missed at one level may be caught at another, and each level catches a different defect type best.

1. Component testing (unit testing). Tests a single component in isolation, usually by the developer, often with stubs (stand-ins that return fixed data) and drivers (harnesses that call the component). Test basis: detailed design and code. Finds defects early, in the smallest scope, where they are cheapest to fix.
2. Component integration testing. Tests interfaces and interactions between components. Finds interface defects, wrong assumptions about data formats, and communication failures between components that each pass alone.
3. System testing. Tests the whole integrated system against its specified requirements, in an environment close to production. Covers functional and non-functional behaviour of the complete system.
4. System integration testing. Tests interactions between systems, for example between an ordering system and a payment gateway, or between a system and an external service. Focuses on cross-system interfaces, data exchange, and end-to-end flows that no single system test covers.
5. Acceptance testing. Checks whether the system is acceptable to users and stakeholders, against business and user needs, not only against specifications. Forms:
   - User acceptance testing (UAT): by users or business representatives, checking business processes and user procedures.
   - Operational acceptance testing: by operations staff, covering backup, recovery, monitoring, and operational procedures.
   - Contract acceptance testing: against criteria written in a contract.
   - Regulatory acceptance testing: against laws, regulations, and standards.
   - Alpha testing: at the developer site, by users, in a controlled environment.
   - Beta testing: at user sites, in the real environment, after alpha testing.

## 2.2 Test types

Test types describe what is being checked, and they cut across test levels.

- Functional testing: does the system do what it should? Based on functions, business processes, use cases, and rules. Example: checkout applies the right tax for the right region.
- Non-functional testing: how well does the system do it? Covers performance (response time, throughput, load, stress), usability, security, reliability, portability, compatibility, and maintainability. Example: checkout stays under 2 seconds at peak load.
- Black-box testing: tests are designed from specifications without looking at internal code. The tester sees inputs and outputs only.
- White-box testing: tests are designed from internal structure, such as code paths and branches. It needs access to code and usually happens at component level.

Note the overlap, because it is tested: functional and non-functional describe what is being checked; black-box and white-box describe what information the test design uses. A functional test can be black-box. A performance test can be black-box too. A white-box test can check a functional rule by tracing its code path.

## Change-related testing

- Confirmation testing (retesting): rerun the exact failing test after a fix, to confirm the defect is fixed. It is targeted, not broad.
- Regression testing: rerun previously passing tests after a change, to check nothing broke. It is broad by design and a strong automation candidate, because the same tests run after every change.

Trap: retesting checks the fix; regression checks for side effects. If a question says "the developer fixed the defect, what do you run first?", the answer is confirmation testing on that defect, followed by regression testing on affected areas.

## 2.3 Maintenance testing

Maintenance covers more than bug fixing:

- Corrective changes: fix defects.
- Adaptive changes: adapt to a new environment, platform, or regulation.
- Perfective changes: improve performance, usability, or maintainability.
- Preventive changes: stop future problems before they happen.

Triggers include planned enhancements, patches, migrations, decommissioning, and hotfixes after release.

Scope is decided by impact analysis: which parts of the system could the change affect? Use traceability, risk, and knowledge of interfaces to choose regression tests. Without impact analysis, teams either test too little and miss side effects, or test everything every time and waste effort.

Watch for three maintenance risks in particular:

- Regression risk in areas that were not changed but depend on changed components.
- Data migration correctness when data structures or formats change.
- Testware decay: old tests, data, and environments that no longer match the maintained system, and that must be updated or retired.

Example. Migrating a payment system to a new provider changes only the payment component, but impact analysis shows checkout, refunds, receipts, and reporting all call it. Regression tests must therefore cover all four flows, plus confirmation tests for the defects fixed in the migration, even though only one component changed.
