# Chapter 3: Static Testing

Use this reference when you need to review a work product, run a review, or decide whether a defect should have been caught statically.

## 3.1 Static testing basics

Static testing examines a work product without executing it. Reviews and static analysis are its two main forms. Dynamic testing, by contrast, finds failures by running the software.

### Work products you can examine statically

Almost any work product can be reviewed: requirements and user stories, design documents, code, test plans and test cases, contracts, project plans, and user documentation. Code can also be analysed by tools. If a question asks "can this be statically tested?", the safe default is yes, unless the work product does not exist yet.

### Value of static testing

- Finds defects early, before code exists or before it runs, when fixes are cheapest.
- Finds defects dynamic testing can miss or finds only with difficulty, for example unreachable code, coding-standard violations, and defects in requirements themselves.
- Improves communication and shared understanding, because reviewers discuss the work product and align on its meaning.
- Can be applied to work products that cannot be executed yet, such as requirements.

### Static versus dynamic testing

Static testing finds defects directly in the work product. Dynamic testing finds failures by execution, and a failure then has to be traced back to a defect. They complement each other. Static testing cannot prove runtime behaviour, such as performance under load. Dynamic testing cannot easily prove that a requirement was misunderstood. Use both.

### Static analysis

Static analysis is tool-supported static testing: a tool examines code or models without running them. Typical findings include unreachable code, unused or uninitialised variables, data-flow anomalies, security weaknesses, and coding-standard violations.

Handle tool output with judgement. Tools report false positives, so a human must judge each finding. Static analysis is not a review, and it does not replace reviews of requirements or design, because a tool cannot judge whether a requirement is right for users.

## 3.2 Feedback and review process

### Benefits of early and frequent stakeholder feedback

Feedback early in development catches misunderstandings while they are cheap to fix, improves the quality of the work product, and builds shared understanding between authors and stakeholders. Feedback late, after other work has been built on the work product, costs rework in every dependent artefact. This is principle 3 from Chapter 1, applied to documents.

### Review process activities

The generic process has five activities. Not every review type runs all of them formally. Informal reviews may skip most of them. Inspections run all of them.

1. Planning: define scope, objectives, review type, participants, entry criteria, exit criteria, and schedule.
2. Initiating the review (kick-off): distribute the work product and supporting material, explain objectives, and answer questions. A kick-off may be a meeting or a written briefing.
3. Individual review: each reviewer examines the work product alone, notes anomalies, and prepares questions. This is where most defects are actually found. Skipping individual review and going straight to a meeting is the most common way to waste a review.
4. Issue communication and analysis: reviewers log issues, discuss them, classify them, and decide which are real defects, which need clarification, and which are out of scope.
5. Fixing and reporting: the author fixes agreed defects, and the review outcome is reported, including defect counts, decisions, and follow-up actions. Unfixed items are tracked, not dropped silently.

### Roles and responsibilities in reviews

- Author: creates the work product and fixes defects found. In inspections, the author must not be the review leader or the scribe, to keep the process independent.
- Manager: decides whether the review happens, allocates time and resources, and ensures follow-up.
- Facilitator (moderator): runs the review meeting neutrally, keeps discussion on track, and ensures issues are logged. In technical reviews and inspections the facilitator is trained and is not the author.
- Review leader: plans the review, invites participants, and is responsible for the review overall. In small reviews this role may merge with facilitator or manager.
- Reviewer: examines the work product, finds anomalies, and raises issues. Reviewers may be peers, subject experts, or stakeholders.
- Scribe (recorder): logs issues accurately during the meeting so nothing is lost in discussion.

### Review types, least to most formal

Learn this order, because exam questions test it directly.

1. Informal review. No defined process, no formal documented output. Main objective: detect anomalies quickly and cheaply. Example: a colleague reads a requirement over your shoulder, known as a buddy check.
2. Walkthrough. Led by the author, who walks reviewers through the work product. Objectives are broad: evaluate quality, build confidence in the work product, educate reviewers, gain consensus, generate new ideas, motivate the author to improve, and detect anomalies. Individual review before the walkthrough is optional, not required.
3. Technical review. Led by a trained moderator, reviewers are technically qualified. Objectives: reach consensus and make decisions on a technical problem, plus detect anomalies, evaluate quality, build confidence, generate new ideas, and motivate the author.
4. Inspection. The most formal type. It follows the full generic process, uses defined roles, checklists, and entry and exit criteria, and collects metrics to improve both the inspection process and the wider development process. Main objective: find the maximum number of anomalies. The author cannot be review leader or scribe.

Traps:

- Walkthrough is author-led. Technical review and inspection are moderator-led.
- Inspection is the most formal review type, not walkthrough.
- If a question says "the author leads the review", the answer is walkthrough, even if the review also finds defects.

### Success factors for reviews

Check a planned review against this list before you run it:

- Choose the right review type for the work product, risk, and time available. Do not run an inspection for a one-paragraph note, and do not run a buddy check for a safety-critical design.
- Set clear objectives and scope, and use checklists that focus reviewers on likely defect types.
- Participants are trained, prepared, and have enough time. Rushing a review defeats it.
- Keep the tone non-judgmental and focus on the work product, not the author. A blame culture kills honest reviewing.
- Management supports the review, protects the time, and acts on the findings.
- Review early, while fixes are cheap, and track issues to closure.
- Measure the review (defects found, effort spent) and use the data to improve, especially for inspections.

### How to run a quick review

Use the checklist in `worked-examples.md` for a short requirement or user story. In brief: read for ambiguity (words like "fast", "user-friendly", "etc."), missing information (what happens on error, what are the limits?), contradictions (two rules that disagree), and testability (can you write a test that passes or fails on this wording?). Log each finding as an anomaly with a location, a description, and a suggested fix, not as a vague comment.
