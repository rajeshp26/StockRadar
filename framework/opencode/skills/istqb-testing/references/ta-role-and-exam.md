# Test Analyst: Role and Exam

Use this reference first when the task is about the Test Analyst role itself, or about preparing for the Test Analyst exam. For Foundation role material, use `references/fundamentals.md` instead.

## What a test analyst is

A test analyst is the business-facing, specification-based tester. The work is mainly functional, black-box, and experience-based testing, judged from the user's point of view: does the software behave as users expect, for the tasks users actually do?

A test analyst also owns the user-facing quality characteristics in the Test Analyst syllabus: functional suitability, usability (called interaction capability in the current ISO naming), flexibility in its adaptability and installability parts, and compatibility in its interoperability part. Other quality characteristics, and deep technical testing, belong to other roles. See `references/ta-quality-characteristics.md` for the ownership map.

A test analyst works across analysis, design, implementation, and execution. That is the whole point of the role: the analyst does not only execute tests written by someone else. The analyst turns a test basis into test conditions, designs cases, prepares data and environments, runs tests, and learns from results to prevent the next defect. See `references/ta-test-process.md`.

A test analyst is not:

- A test manager. The manager owns the project, process, team, planning, and reporting. The analyst owns the business-facing test work inside that plan.
- A technical test analyst. That role owns technical, non-functional, white-box, and code-level testing.
- A test automation engineer. Automation engineering is a separate ISTQB area. A test analyst may use keyword-driven testing and testware tools, but deep automation engineering is not the analyst's core job.

## Dimensions of competence

Competence has three dimensions, and this book and syllabus focus on the first:

- Cognitive competence: knowledge and thinking skills, such as analysis, critical thinking, and logical reasoning. This is what the exam tests.
- Social competence: communication, teamwork, and stakeholder work. The exam does not test it directly, but real analyst work depends on it, for example in reviews and risk workshops.
- Subject-matter competence: domain knowledge, such as banking, health, or retail rules. Without it, an analyst cannot judge whether behaviour is right for users, even with perfect technique.

An analyst who is strong only in technique, and weak in domain knowledge, will design elegant tests for the wrong behaviour. Build domain knowledge deliberately: read the business rules, talk to users, and check real user tasks, not only specifications.

## What a test analyst should know

Foundation Level is the prerequisite. An analyst is expected to know the Foundation areas: fundamentals, SDLC and levels and types, static testing, test techniques, test management, and tools, at least at Foundation depth. Tool awareness is expected, not deep tool expertise. Other Advanced syllabi are helpful background, not required.

Standard terminology matters more at this level than at Foundation, because exam questions hinge on exact distinctions: analysis versus design, high-level versus low-level cases, risk analysis versus risk control, review types versus review techniques, and so on. Use the ISTQB Glossary terms as defined in the glossary, not as used loosely in a team. Where the book and the current ISO standard use different names for the same idea (for example usability versus interaction capability, flexibility versus portability), translate at first use and then stay consistent.

Standards an analyst should be aware of, as named in the book: ISO/IEC/IEEE 29119, Part 1 concepts and vocabulary, Part 2 test processes, Part 3 test documentation, Part 4 test design techniques (black-box, white-box, experience-based), and Part 5 keyword-driven testing; ISO/IEC 25010, the product quality model with nine characteristics; ISO/IEC 25019, quality in use with three characteristics; IEEE 1044, anomaly classification, used for pattern, trend, and root cause analysis; and ISO/IEC 20246, work product reviews, used for early defect detection. These are background to recognise, not a separate syllabus to memorise in full, but you should know which standard covers which topic, because standards are the reason terminology is shared across teams.

## The Test Analyst syllabus and certificate

The Test Analyst certificate sits in the ISTQB Core Advanced path, after Foundation. The syllabus has five chapters, and this package follows them in order:

- Chapter 1: The Test Analyst's Tasks in the Test Process.
- Chapter 2: The Test Analyst's Tasks in Risk-Based Testing.
- Chapter 3: Test Analysis and Design.
- Chapter 4: Testing Software Quality Characteristics.
- Chapter 5: Software Defect Prevention.

Business outcomes for the certificate, in paraphrase, are nine: TA-BO1, suitable testing for the lifecycle followed; TA-BO2, risk-based testing; TA-BO3, suitable test techniques for test objectives; TA-BO4, documentation at suitable detail and quality; TA-BO5, deciding functional testing types; TA-BO6, contributing to non-functional testing; TA-BO7, defect prevention; TA-BO8, process efficiency using tools; TA-BO9, test environment and test data requirements. Learning objectives are coded by chapter, section, and sequence, for example TA-1.3.2, with one learning objective per section, listed at the start of each chapter and tied to a business outcome. They use K-levels K2 (understand), K3 (apply), and K4 (analyse). There are no K1-only learning objectives at this level, which means recall alone is not enough: you must explain, apply, and compare. The exception is keywords: keyword definitions are expected at K1 as well as K2.

## Exam format, as presented in the book

Confirm the current format with your exam provider before booking, because versions differ by language and provider, and the book itself flags a wording conflict on the syllabus version date. As presented in the book:

- Questions: 45 multiple-choice questions.
- Duration: 120 minutes, or 150 minutes with 25 percent extra time for a non-native exam language, where the provider allows it.
- Points: 78 points maximum. K2 questions carry 1 point, K3 questions carry 2 points, and K4 questions carry 3 points.
- Pass mark: 51 points, which is about 65 percent.
- Scoring: all-or-nothing per question, with no negative marks. A partially correct answer scores zero for that question. That rule changes exam tactics: a question with two correct options out of four, where you find only one, earns nothing, so check every option.
- Questions are in random order and do not state their learning objective, though knowing the objective helps judge answers. A course is not a prerequisite, though recommended, and the exam can be taken independently.
- Certificate: lifetime, even when a new syllabus version appears, with unlimited retakes where the provider allows them.
- Weighting, as presented in the book, which sums to 45 questions and 78 points: Chapter 1, 8 questions, 9 points (7 K2, 1 K3); Chapter 2, 3 questions, 7 points (1 K2, 2 K4); Chapter 3, 22 questions, 42 points (4 K2, 16 K3, 2 K4), about 54 percent of points; Chapter 4, 4 questions, 4 points, all K2; Chapter 5, 8 questions, 16 points (2 K2, 4 K3, 2 K4). Allocate study time accordingly: Chapter 3 first, then the chapters you are weakest in, not in book order. Chapter 4's small share means less time relative to Chapter 3, not that it is unimportant.
- Question types: seven are allowed. The four most common are Type-A (one correct option out of four), Roman (five numbered statements, options naming a combination of the true ones), Matching Select (two lists of four, options giving a full pairing), and Pick-Two (two correct options out of five). Three newer types are Ordering (sequence four or five items), Matching Drag (match two lists of four), and Grouping (sort four to seven items into two to four groups, none empty, none in two groups). Multi-part types require a fully correct response for credit. Practise on scenarios, not only on definitions.

## How to study for this exam, using this package

- Work the routing in SKILL.md. If a question is about a basic technique, answer from the Foundation reference. If it is about an advanced technique, a quality characteristic, or defect prevention, answer from the Test Analyst reference.
- For every technique, practise the K3 and K4 moves: derive a test set from a new scenario, count coverage items before choosing a set, and compare two candidate sets and say which is stronger and why.
- For every distinction in this package (analysis versus design, risk analysis versus risk control, review type versus review technique, severity versus priority, interoperability versus coexistence), write one sentence that explains the difference and one example that shows it. If you cannot, that distinction is not yet exam-ready.
- Use `references/ta-worked-examples-and-checklists.md` for practice prompts and chapter checklists. Do not use the book's sample questions from memory: this package deliberately does not reproduce them.
