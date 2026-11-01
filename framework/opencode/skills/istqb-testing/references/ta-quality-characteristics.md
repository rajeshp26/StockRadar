# Test Analyst Chapter 4: Testing Software Quality Characteristics

Use this reference when the task is testing a quality characteristic, not just a function. For Foundation functional versus non-functional testing, use `references/sdlc.md` first, then come here for the Test Analyst characteristic detail.

## 0. ISO 25010 and who owns what

The product quality model in the current ISO standard has nine characteristics. The Test Analyst syllabus covers a subset, and it uses syllabus names that differ in places from ISO names. Translate at first use, then stay consistent:

- Functional suitability (ISO and syllabus agree).
- Usability in syllabus terms is interaction capability in current ISO terms. This package uses usability, with interaction capability noted, because the syllabus framing is the exam framing.
- Flexibility in syllabus terms is portability in current ISO terms. This package uses flexibility, with portability noted.
- Compatibility in both framings, with interoperability as the part the analyst owns.

Ownership map for the test analyst, as presented in the chapter:

- Primary ownership (the analyst leads this testing): functional suitability, and interoperability (the compatibility part about systems working together).
- Supported ownership (the analyst contributes, with specialists leading): usability and interaction capability, adaptability, and installability.
- Out of scope for the test analyst as presented: scalability, replaceability, and coexistence. Coexistence is named in the chapter but treated as outside the analyst's responsibility, while interoperability is inside it. Do not assign coexistence testing to the analyst on the basis of this chapter.

If a question asks who owns a characteristic, answer from this map, not from general intuition. General intuition often assigns everything to the analyst, which is wrong at this level.

## 1. Functional testing

Functional suitability has three subcharacteristics. Test each separately, because a product can be complete but incorrect, or correct but inappropriate for the task.

### 1.1 Completeness

Completeness asks: does the system provide all functions specified, and all functions needed for the stated tasks?

Test it with a traceability matrix: rows are specified functions, columns are test cases, and each cell says whether the function is covered, and by which cases. Read the matrix for three states:

- No case: a specified function with no test case. That is a coverage gap, and possibly a missing function.
- Failed case: a specified function with a failing case. That is a defect in the function, not a coverage gap.
- Unrun case: a specified function with a case that has not run. That is not evidence either way. Do not report unrun coverage as pass coverage.

A function that is specified but not implemented will show up as no case or failed case, depending on how the matrix was built. A function that is implemented but not specified will not show up in the matrix at all, which is why completeness testing also needs user-task checks: do real user tasks complete, even if every specified function passes?

### 1.2 Correctness

Correctness asks: does the system provide correct results, with the needed precision?

Test it with oracles matched to the calculation: exact expected values for simple calculations, independent calculations or pseudo-oracles for complex ones, and property checks for invariants such as "total never negative" or "counts add up". Pay attention to exactness, accuracy, and precision as separate ideas:

- Exactness: the result matches the specified value, with no rounding or truncation error beyond what the specification allows.
- Accuracy: the result is close to the true value, within an allowed tolerance.
- Precision: the result is given to the needed number of decimal places or significant figures, and rounding is applied as specified.

A result can be precise (many decimal places) but inaccurate (wrong value), or accurate (within tolerance) but imprecise (too few decimal places for the task). State which one a failure violates, because the fix differs.

Rounding is a common correctness defect: rounding at the wrong step, rounding in the wrong direction, or rounding a total instead of rounding line items. Test rounding with values that sit exactly on rounding boundaries, using domain testing.

### 1.3 Appropriateness

Appropriateness asks: does the system provide functions that help users accomplish their tasks, in a way that fits those tasks?

Test it by whole tasks, not by single functions. A system can pass every single-function test and still be inappropriate, if the task requires a sequence the system does not support, or if a function exists but is hard to find, hard to use, or missing a step the task needs. Use scenario-based testing for appropriateness, with real user tasks, and judge by task completion, not by function pass rates.

### 1.4 Measuring functional suitability

Measure suitability by the traceability matrix and by task results together: specified functions covered, specified functions passing, and user tasks completed. A single percentage for "functional suitability" that hides which of the three subcharacteristics failed is not a useful measure. Report completeness, correctness, and appropriateness separately. Useful measures are: proportion of specified functions and requirements implemented; proportion of functions giving correct results; proportion of cases with accurate or precise results; and proportion of functions untraceable to any requirement, which is gold-plating (implemented but never required). Implementation, traced, and executed coverage are three different numbers: with nine requirements, if only four have traced, executed tests, traced coverage is 4 of 9, about 45 percent, even if all nine were implemented. Reporting only implementation coverage hides the other two. Scenario coverage (scenarios tested divided by total scenarios) is stronger than functions tested divided by total functions alone.

## 2. Usability testing

### 2.1 What it means

Usability, in the syllabus framing, is about how easily, efficiently, and satisfyingly users can use the system for their tasks. The current ISO name for this area is interaction capability. The test analyst contributes to usability testing, but detailed usability technique is specialist work, and this chapter gives the analyst's contribution, not the full specialist method.

### 2.2 Interaction capability: eight parts

Learn these eight parts as a checklist for usability review and testing:

1. Appropriateness recognisability: can a new user tell at first sight whether the product suits their need? Show the home screen with no help and ask what service it offers and who it is for.
2. Learnability: can a new user learn tasks without lengthy training? Give first-time users a realistic task with no guidance and watch how they discover search, filters, and confirmation.
3. Operability: is the system easy to operate day to day, with responsive, clear, consistent controls? Test routine mid-task changes, such as changing an address before confirming, and count unnecessary steps.
4. User error protection: does the system prevent errors where possible, and aid recovery where it cannot? Prevention is disabling an unavailable action or validating input early; recovery is undo, clear warnings, and confirmations.
5. User engagement: does the product feel inviting and motivating? Test by asking users after a short session how enjoyable it felt, and by comparing design variants.
6. Inclusivity: can people of varied ages, abilities, cultures, languages, genders, and economic situations use it? This is wider than disability access, covering culturally appropriate imagery, language diversity without unexplained idioms, gender-neutral wording where relevant, readable type, low-data options, and plain language.
7. User assistance, also called accessibility in older ISO wording: can people with the widest range of characteristics achieve their goals, including people with disabilities using assistive technologies? See section 2.4.
8. Self-descriptiveness: does the product make its capabilities obvious without hunting or help? Show a screen without interaction and ask what actions are available.

Do not use the older list that puts user interface aesthetics in place of user engagement, inclusivity, and self-descriptiveness. That older list is a different ISO version's set, and mixing the two lists will fail an exam question that asks for the current eight parts.

For each part, write a checkable test idea for the product under test, not just the part name. Example for user error protection: "Deleting a booking asks for confirmation, states what will be deleted, and offers undo or recovery where possible." A part name without a test idea is not a test.

### 2.3 User experience: four factors

User experience is wider than usability. It has four factors:

- Usability: can users use it effectively and efficiently?
- Usefulness: does it do something users actually need?
- Emotional impact: how does using it feel? Frustration, confidence, and trust are part of experience, not extras.
- Meaningfulness: does using it matter to the user, in their context?

A product can be usable but not useful (easy to use, but nobody needs it), or useful but not usable (needed, but hard to use). Test experience by asking users about all four factors, not only by measuring task time. Task time alone would call a fast but useless product a success.

### 2.4 Accessibility

Accessibility means the system can be used by people with disabilities, including visual, hearing, motor, and cognitive disabilities, using assistive technologies where needed.

Test it against recognised levels and laws, in general terms: the Web Content Accessibility Guidelines levels A, AA, and AAA, with AA as the common target; the European Accessibility Act; and Section 508 in the United States. An analyst should know that these exist, what level AA means in general terms (a substantial, achievable accessibility bar), and that accessibility testing needs both automated checks and human testing with assistive technologies, because automated checks alone miss many accessibility defects.

Do not copy a scoring formula from an extracted or garbled source. For questionnaire-based usability measurement, use a verified standard reference for the instrument you are using, and state which instrument and version you used. A garbled formula copied into a skill or a report will produce wrong scores with false confidence.

### 2.5 How the test analyst contributes

The analyst's contributions to usability testing are:

- Reviews: review interfaces, flows, and messages against usability principles and checklists, before and during development.
- Test sessions: run usability test sessions with real users, observing tasks, errors, and recovery, and logging findings with steps and context.
- Questionnaires and surveys: collect user judgements after tasks, using standard instruments where appropriate, and report results with the instrument, sample, and limitations stated.
- Metrics and tools: use usability metrics (such as task completion rate, task time, error rate, and satisfaction scores) and usability tools (such as screen readers for accessibility checks and session recording for observation), and report metrics with their context, not as bare numbers.

A usability metric without context (who the users were, what tasks they did, what environment they used) cannot be compared or acted on.

## 3. Flexibility testing

Flexibility, in syllabus terms, is portability in current ISO terms: how easily a system can be adapted to different environments and installed in different contexts.

### 3.1 Adaptability: what to test

Adaptability asks: can the system be adapted for different environments, configurations, and locales, without major rework?

Test it with:

- Combinatorial and pairwise testing across configurations: operating systems, browsers, devices, languages, locales, and settings, using the combinatorial methods in `references/ta-test-design-data.md`. A configuration matrix that lists environments and test results is the basic artefact: rows are configurations, columns are key functions, and each cell says pass, fail, or not run.
- Configuration checklists: a maintained list of configurations and settings to check for each release, adapted to the product's actual environments, not a generic list.
- Edge locales: dates, numbers, currencies, text direction, and character sets for the locales the product claims to support. A product that claims a locale but formats dates or currency incorrectly for that locale is not adaptable to that locale.
- Dynamic switching: changing configuration during use, such as language or theme, and checking that the change applies cleanly, without restart loss or stale data, where the specification requires it.
- Fallbacks: when an adapted environment is unavailable or unsupported, the system should degrade gracefully, with a clear message and a safe fallback, not a crash or silent wrong behaviour.

### 3.2 Installability: what to test

Installability asks: how successfully a product can be installed, uninstalled, updated, and reconfigured in a specified environment, with minimal effort and without harm. Installation is often the first user experience: a failed install breeds distrust and support calls, and a dirty uninstall (leftover files, registry entries, shortcuts, or services) can poison future installs.

Four objectives organise it:

1. Procedures work across configurations: use combinatorial techniques for parameters, negative testing for invalid paths, read-only locations, missing disk space, restricted resources, and interruptions such as cancellation, plus checklists for preconditions, validation, cleanup, and rollback.
2. The product works after installation or update: verify with a smoke test, regression tests, and end-to-end scenarios, not merely by noting that the installer finished.
3. Install, uninstall, and update are easy: review documentation against the actual process, and run scenarios covering clean install, reinstall over an existing install, default and custom options, restricted user mode, full uninstall, and cancelled partial uninstall.
4. Permission behaviour is correct, especially on mobile: use boundary analysis for minimum and maximum permissions, state transition testing for granted, denied, and later-revoked states, decision tables for combinations (for example location plus notifications plus camera), and scenario testing for varied security configurations.

A state view helps: not installed, installing, installed, updating, uninstalled, and failed or rolled back. Verify preconditions, clean completion, post-install running, upgrade preserving data and settings without duplication, uninstall removing files, registry entries, shortcuts, and services, and rollback cleaning up after partial failure. Common mistakes are stopping at "installer finished" without a post-install smoke test, testing only clean installs and never upgrades, reinstalls, or interrupted installs, and forgetting to check what uninstall leaves behind.

## 4. Compatibility testing

Compatibility asks: can the system work with other systems, products, and environments as required?

### 4.1 Interoperability versus coexistence

- Interoperability: systems exchange information and use the exchanged information correctly. This is the analyst's compatibility responsibility.
- Coexistence: systems share an environment without harming each other, for example sharing resources without conflict. This is treated in the chapter as outside the analyst's responsibility. Do not assign coexistence testing to the analyst on the basis of this chapter, and do not report coexistence results as analyst results.

### 4.2 Interoperability at each test level

Test interoperability at the level where the interface lives, using architecture and design documentation to find interactions, including undocumented ones:

- Component level: a single component handles data or calls from others correctly, for example parsing API responses in different versions. Usually a developer or technical test analyst task.
- Component integration level: small groups interoperate correctly, for example a payment module passing currency values with correct precision and separators. Usually a developer or technical test analyst task.
- System level: the whole system operates correctly as a whole, for example a front end sending order data to a back end with consistent date formats and item codes. Typically a test analyst task.
- System integration level: the system interoperates with external systems in a real or simulated environment, for example a hospital system exchanging records under a health standard. Typically a test analyst task.
- Acceptance level: stakeholders see the whole system interoperate in its real environment, often with third-party systems, for example a shop platform integrating with a logistics provider. In theory clients perform this; in practice test analysts often do.

A test that passes at component level but fails at system level has found an integration defect, not a contradiction. Each level tests a different scope of the same interface.

### 4.3 What failures look like, and what to test

Interoperability failures fall into types. Learn them, because a failure report that names the type is faster to fix:

- Transformation failures: data is converted incorrectly between formats, such as date, currency, or encoding conversions.
- Interpretation failures: data is exchanged correctly but interpreted differently by the two sides, such as a code that means one thing in one system and another in the other.
- Protocol failures: communication does not follow the agreed protocol, such as wrong message order, missing acknowledgements, or timeout handling.
- Standards failures: a side does not follow the agreed standard, even though it claims to.
- End-to-end failures: each interface works alone, but the complete flow across systems fails, because of a missing step, a timing issue, or a state mismatch.
- Documentation failures: the interface is documented incorrectly, so implementers on either side build to the wrong specification. Documentation is part of the interface, and testing it is interoperability testing, not paperwork.

Test interoperability with negative testing as well as positive testing: send invalid, incomplete, and out-of-order data across the interface, and check that the receiving side rejects it clearly, without corrupting its own state. A system that accepts invalid interface data silently is not interoperable. It is fragile.

## Traps in this chapter

- Completeness versus correctness versus appropriateness: a product can pass one and fail another. Report them separately.
- Usability versus interaction capability: same area, different names in syllabus and ISO. Translate at first use.
- Flexibility versus portability: same area, different names. Translate at first use.
- Interoperability versus coexistence: interoperability is analyst work; coexistence is out of analyst scope in this chapter. Do not swap them.
- Accessibility levels: AA is the common target. A and AAA are different bars, and a claim of "accessible" without a level is not a claim at all.
- Usability metrics without context (users, tasks, environment) cannot be compared or acted on.
