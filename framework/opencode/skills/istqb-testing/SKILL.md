---
name: istqb-testing
description: "Apply ISTQB testing knowledge in one package with clear routing: Foundation Level (CTFL v4.0) fundamentals, SDLC, static testing, test techniques, test management and tools, and Advanced Test Analyst work from Practical Software Test Analysis, including test process and testware, risk-based testing, advanced test design techniques, quality characteristics, and defect prevention. Use when designing tests, choosing a technique, planning or reporting testing, writing a defect report, reviewing a work product, or preparing for the CTFL or Test Analyst exam."
---

# ISTQB Testing: One Package, Two Levels, Clear Routing

Use this skill when you need to design tests, choose a test technique, plan testing, manage risk, write a defect report, run a review, decide what to automate, prevent defects, or prepare for an ISTQB exam. It holds both levels in one place, paraphrased, with original worked examples inside the package. You do not need to open any outside source to use it. See ATTRIBUTION.md for provenance.

This package was built in two stages, and the routing below is how you avoid mixing them up. The Foundation references come from the CTFL v4.0 syllabus structure. The Test Analyst references come from the user-supplied book Practical Software Test Analysis by Adam Roman and Matthias Hamburg, a companion for the Advanced Test Analyst exam. They are complementary, not competing: Foundation gives you the shared vocabulary and the basic techniques, Test Analyst gives you the deeper, business-facing analyst work built on top of it.

## Deterministic routing: run this first, if your agent runs code

If your agent can run code, do not guess the reference. Run the router in this package:

    python3 router.py --task "your task text here"

From the repository root (this package is vendored at `framework/opencode/skills/istqb-testing/`):

    python3 framework/opencode/skills/istqb-testing/router.py --task "your task text here"

It loads `routing.json`, which is the single source of truth for routing, and prints JSON with `primary` (the reference to load first), `references` (every matching reference, in priority order, duplicates removed), `matched_rules`, and `fallback`. The procedure is fixed: normalise the task text to lowercase, scan rules in `routing.json` array order (array order is priority order, most specific rule first), collect every rule whose signal appears in the task text, and deduplicate references in first-match order. If `--type` names a rule id, that rule is first regardless of text. If no rule matches, the router returns `references/fundamentals.md` with `fallback` set to true, which means the task needs clarification, not that fundamentals is the right answer.

Load the primary reference first. Load an additional reference only if the task needs that part. Examples of the deterministic result: "design pairwise tests for checkout config" gives primary `references/ta-test-design-data.md`; "minimise this decision table and check the checksum" gives primary `references/ta-test-design-rule.md` with Foundation `references/test-techniques.md` as an additional reference; "choose regression tests after a discount change" gives primary `references/ta-risk-based-testing.md`, while "explain regression testing" gives primary `references/sdlc.md`. That last pair is deliberate: choosing tests is a selection task, explaining the concept is a Foundation task, and the router distinguishes them by signal, not by guesswork.

If your agent cannot run code, use the instruction routing below instead. It encodes the same priority order (specific before generic, Test Analyst depth before Foundation basic for the same topic), but it depends on the agent following it. When both are available, the code router wins: if its result disagrees with a guess, trust the router.

## Routing: read this first, then read only the reference it names

Start from the task, not from the chapter list. Ask, in order:

1. Is this a Foundation question, a basic test design, or a CTFL exam question? If yes, use the Foundation references only. Do not pull in Test Analyst depth that the question does not ask for.
2. Is this a Test Analyst question, an Advanced exam question, or a deeper analyst task such as domain testing, combinatorial testing, CRUD testing, metamorphic testing, crowd testing, quality-characteristic testing, or defect prevention? If yes, use the Test Analyst references. Use the Foundation references only for the background vocabulary you need.
3. Is the same topic covered in both levels? If yes, use the rule in the overlap table below, and do not merge the two versions into one answer.

### Overlap rule: when both levels cover a topic, which version wins?

- Risk: for a basic risk definition, likelihood and impact, and product versus project risk, read Foundation `references/test-management.md`. For risk analysis and control as analyst work, including regression selection methods, read Test Analyst `references/ta-risk-based-testing.md`. The Test Analyst version is the deeper one, and it wins for regression scope decisions.
- Decision tables: for the basic method, read Foundation `references/test-techniques.md`. For minimisation, infeasible columns, extended entries, and checksums, read Test Analyst `references/ta-test-design-rule.md`. Do not claim a table is minimal unless you have applied the Test Analyst minimisation steps.
- State transitions: for the basic method and coverage levels, read Foundation `references/test-techniques.md`. For extended state machines, guards, switch coverage, and round-trip coverage, read Test Analyst `references/ta-test-design-behaviour.md`.
- Reviews: for review types and the review process, read Foundation `references/static-testing.md`. For review techniques (ad hoc, checklist-based, scenario-based, role-based, perspective-based reading) and using models to find specification defects, read Test Analyst `references/ta-defect-prevention.md`. Review types and review techniques are different things. Do not confuse them.
- Exploratory testing and charters: for the basic idea, read Foundation `references/test-techniques.md`. For charter structure, session-based testing, and checklist design, read Test Analyst `references/ta-test-design-experience.md`.
- Test process and testware: for the basic test activities, read Foundation `references/fundamentals.md` and `references/sdlc.md`. For the analyst's work inside each activity, high-level versus low-level cases, oracles, test data, keyword-driven testing, and testware tools, read Test Analyst `references/ta-test-process.md`.

## Foundation references

- For what testing is, why it is needed, the seven principles, test activities, testware, roles, and tester skills, read `references/fundamentals.md` (CTFL Chapter 1).
- For SDLC models, shift left, test-first practices, the five test levels, the four test type groups, confirmation versus regression testing, and maintenance testing, read `references/sdlc.md` (CTFL Chapter 2).
- For static testing, work products you can review, static analysis, the review process, review roles, the four review types, and review success factors, read `references/static-testing.md` (CTFL Chapter 3).
- For Foundation test techniques, with step by step derivation and worked coverage calculations, read `references/test-techniques.md` (CTFL Chapter 4).
- For test planning, entry and exit criteria, estimation, prioritisation, the test pyramid, testing quadrants, risk management, monitoring, reporting, configuration management, and defect management, read `references/test-management.md` (CTFL Chapter 5).
- For tool categories, tool selection and rollout, and the benefits and risks of test automation, read `references/test-tools.md` (CTFL Chapter 6).
- For end to end Foundation worked examples, plus a test plan skeleton, a defect report template, and a review checklist, read `references/worked-examples.md`.
- For the CTFL exam format, question split, K-levels, glossary, trap list, and chapter checklists, read `references/exam-and-checklists.md`.

## Test Analyst references

- For the Test Analyst role, how it differs from test manager and technical test analyst, competence dimensions, standards, business outcomes, and the Test Analyst exam format, read `references/ta-role-and-exam.md` (book Introduction and Part I).
- For the analyst's tasks in the test process, including analysis, design, implementation, execution, high-level and low-level cases, case quality, environment requirements, oracles, test data, keyword-driven testing, and testware tools, read `references/ta-test-process.md` (book Chapter 1).
- For risk-based testing as analyst work, including risk identification and assessment, qualitative, quantitative and hybrid approaches, risk control, monitoring, residual risk, and regression test selection, read `references/ta-risk-based-testing.md` (book Chapter 2).
- For data-based techniques (domain, combinatorial, random testing), read `references/ta-test-design-data.md` (book Chapter 3, section 3.1).
- For behaviour-based techniques (CRUD, state transition, scenario-based testing), read `references/ta-test-design-behaviour.md` (book Chapter 3, section 3.2).
- For rule-based techniques (decision table, metamorphic testing), read `references/ta-test-design-rule.md` (book Chapter 3, section 3.3).
- For experience-based techniques (test charters, checklists, crowd testing) and for selecting techniques by risk and automating test design, read `references/ta-test-design-experience.md` (book Chapter 3, sections 3.4 to 3.5).
- For quality characteristics (functional suitability, usability and interaction capability, flexibility, compatibility and interoperability), read `references/ta-quality-characteristics.md` (book Chapter 4).
- For defect prevention (prevention practices, phase containment, model-based specification checks, review techniques, test-result analysis, root cause analysis with defect classification), read `references/ta-defect-prevention.md` (book Chapter 5).
- For Test Analyst worked examples, practice prompts, traps, and exam checklists, read `references/ta-worked-examples-and-checklists.md`.

## How to use this skill

- When you design tests, always name the technique, the coverage items, and the coverage you achieved. A test list with no technique and no coverage claim is not finished.
- When you answer an exam-style question, first classify it: Foundation or Test Analyst, and remember, understand, apply, or (Test Analyst only) analyse. An apply question needs a worked example, not a definition. A Test Analyst analyse question needs a comparison or a judgement between options, not only a recall.
- When you report status, report risk, coverage, and quality, not only pass counts. A pass count that hides which risky area failed is misleading.
- Keep severity and priority separate in every defect report. Severity is impact. Priority is order of fixing.
- When a topic appears in both levels, say which level you are using and why. That one sentence prevents most cross-level confusion.

## The ideas that come up most

- Testing shows the presence of defects, not their absence. Passing tests lower risk. They never prove zero defects remain.
- Exhaustive testing is impossible. Prioritise by risk, because you cannot test every combination.
- Early testing saves time and money. A defect found in a requirement is far cheaper to fix than the same defect found after release.
- Defects cluster together. A small number of modules usually holds most defects. Use past defect data to steer extra testing there.
- Tests wear out. Repeating the same tests finds fewer new defects over time, so review suites, add new cases, and use exploratory testing.
- Testing is context dependent. Safety-critical software, a banking app, and a games app do not get the same approach.
- Absence of defects is a fallacy. A product can pass all its tests and still be wrong for users if the requirements missed what users needed.
- Testing and debugging are different. Testing finds a failure or a defect. Debugging finds the root cause and fixes it. Retesting confirms the fix.
- Confirmation testing checks the fix. Regression testing checks for side effects. Do not confuse the two.
- Branch coverage subsumes statement coverage. Statement coverage does not subsume branch coverage.
- Risk level combines likelihood and impact. Higher risk areas get more tests, stronger techniques, earlier testing, and higher coverage targets.
- Defect prevention has three aims: stop defects being created, catch defects in the phase where they were created, and stop the same kinds of defects coming back. Late testing is detection, not prevention.
- Automate repetitive, stable, high-value tests that run often. Keep exploratory, usability, and one-off tests manual. Most automation belongs at the base of the test pyramid, not in the UI layer.

## Technique choice at a glance

- Use equivalence partitioning when inputs fall into groups treated the same way, such as age ranges or price bands.
- Use boundary value analysis when partitions are ordered, such as numbers, dates, or lengths, and edge errors are likely.
- Use domain testing when a rule has boundaries in one or more dimensions and you need to test on, off, inside, and outside each boundary, including multi-dimensional domains.
- Use combinatorial testing when many parameters interact and full combinations are too many, and you need pairwise or base-choice coverage instead.
- Use random testing when inputs are many, varied, or operationally distributed, and you have an oracle or a property that can judge each random case.
- Use decision table testing when behaviour depends on combinations of conditions, such as discount or approval rules.
- Use state transition testing when behaviour depends on current state, such as an order, a login session, or a device mode.
- Use CRUD testing when data is created, read, updated, and deleted, and you need to check every operation and every read after every change.
- Use scenario-based testing when a user journey matters as a whole, including branches, loops, and exceptions, not only single functions.
- Use metamorphic testing when there is no simple oracle, but a known relation must hold between related inputs and outputs, such as a search that must not change results when the order of irrelevant inputs changes.
- Use statement and branch testing when you have code and need an objective coverage measure, usually at component level.
- Use error guessing when you know likely fault types from past defects, such as null handling, empty input, or rounding.
- Use exploratory testing when specifications are thin, time is short, or you need to learn about a new area. Run it in time-boxed sessions with a written charter.
- Use checklist-based testing when you have a maintained list of conditions from experience and past defects.
- Use crowd testing when you need many diverse users, devices, or environments quickly, and you can manage deduplication and confidentiality.
- Use collaboration-based approaches when a story is being written or its acceptance criteria are being agreed. Write testable acceptance criteria before building, and agree acceptance tests with the whole team.

## Scope boundary

- This skill covers Foundation Level and Advanced Test Analyst level only. It does not cover Advanced Test Manager or Technical Test Analyst in depth, and it does not teach a specific automation framework or programming language.
- The previous Foundation-only package, named `istqb-foundation-testing`, is superseded by this merged package. Do not use both. This package is the single package for ISTQB testing work.
- For how to run AI coding agents day to day, use the companion `10x-native-ai-developer` skill. For how to architect agentic systems, use `agentic-framework`. For UI design rules and patterns, use the design skills in this set. This skill owns testing concepts, techniques, planning, and management, and the other skills do not duplicate it.
- This skill is an unofficial study and practice aid. It is not an ISTQB accredited course, and it does not replace the official syllabus or official sample exams. For either exam, confirm the current syllabus version and exam rules with your local ISTQB member board or exam provider before you book.
