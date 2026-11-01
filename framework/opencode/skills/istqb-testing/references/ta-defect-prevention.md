# Test Analyst Chapter 5: Software Defect Prevention

Use this reference when the task is preventing defects, catching defects in the phase where they were created, or stopping the same kinds of defects coming back. For Foundation defect management (logging, lifecycle, severity versus priority), use `references/test-management.md` first. This chapter is about prevention, not only about logging defects after they appear.

## What defect prevention is, and is not

Most defects are created while people build things, not while testers test them, so a test analyst can easily feel prevention is someone else's job. This chapter argues the opposite: prevention belongs to the whole team, and test analysts have distinctive knowledge to contribute, because they see failure patterns, weak specifications, and test gaps that builders often miss.

Prevention has three linked aims:

1. Stop defects from being created, by improving process, training, and early checks.
2. Catch defects in the same phase where they were created, before they travel downstream and become expensive. This is phase containment.
3. Stop the same kinds of defects from coming back, by learning from defects that did occur and changing the process that allowed them.

Late testing is detection, not prevention. A team that tests harder at the end, without changing how defects are created or caught early, will keep finding the same kinds of defects, later and at higher cost.

A defect found in a requirement costs a conversation to fix. The same defect found after release costs debugging, a patch, retesting, and customer damage. That cost curve is the economic case for prevention, and it should be stated in those terms when prevention work needs justification.

## 5.1 Defect prevention practices

### How a test analyst contributes, in practice

1. Join risk analysis early. Use knowledge of likely failure modes to rank areas by risk, choose techniques that match each risk, and push effort toward the riskiest areas first. A risk spotted in analysis can change a design or coding approach before any defect is written.
2. Review requirements, models, and specifications. Early documents are the test basis for everything that follows. Ambiguity, contradiction, gaps, and untestable wording found here prevent both wrong implementations and weak testing later.
3. Take part in retrospectives. Look back at what the test approach actually achieved: whether coverage was real, whether techniques fitted the risks, whether risk ratings were right, and whether data and environments produced false passes or false failures. Then propose one concrete change that would have caught more defects earlier. A retrospective that lists defects but never changes the process is not prevention.
4. Record defect data properly, beyond a short description. At report time, capture test level, severity, and what triggered the failure, for example the test case involved. Later, add defect type, location, phase of introduction, fix effort, time to fix, and root cause. A defect tool used only as a status board wastes this value. A defect tool filled in consistently supports trend analysis and decisions about review, coverage, and training.
5. Join root cause analysis. Bring knowledge of testing gaps and system behaviour to the question of why defects happened, not only what they were. If stateful behaviour is only described informally and keeps producing inconsistent rules, propose modelling it formally, so developers build from the model and testers derive tests from the same model. See section 5.3.2 below.

Prevention work must itself be checked, in agreement with the test manager. Three measures are used throughout the chapter.

### Three measures, with worked numbers

- Defect removal efficiency (DRE): the share of known defects found and fixed before release. Using only defects fixed in a fixed follow-up window after release, plus residual defects found but not fixed, DRE equals defects fixed before release divided by (fixed before release, plus fixed after release, plus residual found but not fixed), times 100.

  Worked example, original numbers: 180 fixed before release, 30 fixed in the six months after release, 10 found but left unfixed. DRE equals 180 divided by 220, about 82 percent. If 15 more field defects surface later, DRE falls to about 77 percent, even though the pre-release work did not change. Two lessons follow: the true total defect count is unknowable, so calculated DRE is an upper bound, not a true rate; and DRE measures removal effectiveness, not cost-effectiveness, despite its name.

- Phase containment effectiveness (PCE): for one phase, the share of defects introduced in that phase that were also caught in that phase. PCE equals defects introduced and detected in that phase divided by all defects introduced in that phase, times 100.

  Worked example, original numbers: 120 defects are introduced while requirements are written, and 36 are caught in requirements review, so PCE for requirements is 30 percent. That is weak: 70 percent escaped into design or code, where fixes cost more. Like DRE, PCE is an upper bound that can fall as late defects surface. It can also be computed per sprint or iteration in Agile work. Tracking PCE phase by phase shows where early detection is strong and where review or testing needs strengthening.

- Cost of quality (CoQ): the money story behind DRE and PCE. CoQ has four parts: prevention costs (training, process improvement, quality planning); appraisal costs (testing, reviews, audits); internal failure costs (debugging, fixing, and confirmation testing before release); and external failure costs (support, patches, workarounds, data clean-up, warranty claims, reputation damage, and, in serious cases, liability for harm). Prevention and appraisal costs are largely under the team's control, while failure costs depend on how many defects escape and how much damage they do. External failure costs are typically far larger per defect than internal ones, and internal costs grow steeply with each later test level, so spending more early can lower total cost, but only up to a point of diminishing returns. Spending without limit on prevention does not keep lowering total cost forever.

### Common mistakes in prevention practices

- Treating harder testing at the end as prevention. Late testing is detection, and it leaves the expensive failure costs in place.
- Running retrospectives that list defects but never change the process, the techniques, or the test data and environments.
- Recording defects as status only, without type, phase of introduction, and root cause, so no trend can be learned from them.
- Measuring DRE or PCE as if they were exact true rates, instead of upper bounds that fall as late defects surface.

## 5.2 Supporting phase containment

Phase containment means catching a defect in the phase where it was created, before it travels to a later phase. Two analyst contributions support it: using models to detect anomalies in specifications, and applying review techniques.

### 5.2.1 Using models to detect anomalies in specifications

A model is a simplified representation that keeps the aspects relevant to a question and drops the rest. Building a model from a specification, and then checking the model, finds defects that reading prose misses, because a model forces every state, transition, rule, and data relation to be stated explicitly. Modelling helps containment in three ways: revealing defects in specifications, revealing defects in models that are themselves part of the test basis, and generating tests from a model, which is model-based testing.

Two levels of skill matter. Passive skill means reading and analysing models made by others. Active skill means building a correct model from prose or informal knowledge, which is more valuable for detection, because building the model forces the analyst to resolve every gap and ambiguity that prose can hide.

Models fall into three families, each exposing different defects:

- Data and structure models, such as domain models, class diagrams, entity-relationship diagrams, classification trees, and CRUD matrices. These expose missing entities, wrong relationships, naming clashes, and impossible starting states.
- Rule models, such as decision tables, decision trees, cause-and-effect graphs, and truth tables. These expose overlapping rules, contradictory outcomes, missing combinations, and infeasible combinations.
- Behaviour and workflow models, such as state machines, state charts, sequence diagrams, activity diagrams, and business process models. These expose missing states, dead-end states, wrong or missing transitions, missing or wrong guards, wrong action order, unreachable actions, and badly synchronised parallel flows.

Models in the test basis can themselves be defective: syntax slips, typos, duplicates, inconsistent names, missing or wrong states, improper transitions, wrong guards or actions, redundant or unreachable states, nondeterministic behaviour, missing or dead-end actions, wrong or incomplete guards, missing synchronisation, and, in decision tables, overlapping, inconsistent, infeasible, or incomplete rules. Reviewing a supplied model is therefore containment work, not a preliminary chore. Use one model family for each question: a decision table will not show a dead-end state, and a state model will not show a missing rule combination.

Steps, in order:

1. List the specification's entities, rules, states, events, and actions in plain words.
2. Choose the model family matching the question: state model for state-dependent behaviour, decision table for condition combinations, data model for entities and relationships.
3. Build the model strictly from the specification, marking every place you had to guess, invent a guard, or assume a default. Each guess is a candidate specification defect.
4. Check the model mechanically: every state reachable, every state able to reach a sensible next state, every decision-table column feasible and covered, every CRUD cell accounted for.
5. Design a few tests from the model, including coverage-driven sequences such as pairs of consecutive transitions. If a generated sequence describes behaviour that should be impossible, you have found a specification defect or a model defect. Decide which, fix the right artefact, and record the decision.
6. Discuss the corrected model with stakeholders and update the specification, so the fix survives beyond your notebook. Report each anomaly as a specification defect, with the model element, the specification text it contradicts or completes, and a suggested fix. Do not fix the specification by changing the model silently. The model is a test artefact, not the specification.

Use the validated model as a test basis: derive tests from the model, using the techniques in `references/ta-test-design-behaviour.md` and `references/ta-test-design-rule.md`. Tests derived from a validated model are stronger than tests derived from prose alone, because the model has already been checked for anomalies.

Worked example, original: a clinic booking specification says a booking can be cancelled, and a cancelled slot can be rebooked, but never says whether a cancelled booking's payment is refunded automatically or held. Building a state model forces the question: from Cancelled, is there a transition to Refunded, and under what guard? The missing transition is the anomaly, and it is a specification defect, found before any code is written. Without the model, the defect would surface as a payment defect after release.

Models also support defect prevention in a second way: when developers build from the same model that testers test from, the model becomes shared understanding, and misunderstandings that would have become defects are resolved before implementation.

### 5.2.2 Applying review techniques

Review types and review techniques are different things. Do not confuse them.

- Review types (Foundation `references/static-testing.md`): informal review, walkthrough, technical review, inspection. A review type describes how formal the review process is.
- Review techniques (this chapter): how reviewers actually examine the work product inside a review, whatever its type. A technique can be used inside any review type, but the technique determines what defects are found.

Five review techniques:

1. Ad hoc reviewing: reviewers examine the work product without a structured method, relying on experience and intuition. Fast and flexible, but coverage is unrepeatable and depends entirely on reviewer skill. Use it for quick checks and for areas where no checklist or scenario exists yet. Do not use it as the only review method for high-risk work products.
2. Checklist-based reviewing: reviewers use a checklist of likely defect types, built from past defects and experience, and check the work product against each item. Systematic and reusable, but only as good as the checklist, and checklists must be maintained. See `references/ta-test-design-experience.md` for checklist design.
3. Scenario-based reviewing: reviewers walk through the work product using scenarios, such as user journeys or operational scenarios, and check whether the work product supports each scenario correctly. Strong for workflows and user tasks, because it tests the work product against real use, not against abstract rules.
4. Role-based reviewing: each reviewer takes a specific role, such as user, developer, tester, or operations, and reviews the work product from that role's perspective and needs. Strong for finding defects that only one stakeholder would notice, such as an operations need missing from a design, or a user need missing from a requirement.
5. Perspective-based reading (PBR): a structured form of role-based reviewing, where reviewers follow a defined procedure for their perspective, including what to look for, what questions to ask, and what to record. PBR is more systematic than informal role-based reviewing, because the procedure guides the reviewer, but it requires training and preparation, and it takes longer.

Choose a technique by the work product and the risk: ad hoc for quick, low-risk checks; checklist-based for known defect types; scenario-based for workflows; role-based or perspective-based for stakeholder-specific needs and for high-risk work products where a single perspective would miss defects.

Common mistakes across review techniques:

- Using a review type as if it were a technique, for example saying "we did an inspection" without saying how reviewers examined the product inside it.
- Using ad hoc reviewing for high-risk work products, where coverage cannot be shown.
- Using a stale checklist that does not reflect current defect types.
- Running role-based reviewing without defining the roles, so every reviewer reviews from the same perspective and the technique adds nothing.

## 5.3 Mitigating the recurrence of defects

Recurrence mitigation asks: defects have happened, so what do we change so the same kinds of defects do not happen again? Two analyst contributions support it: analysing test results, and supporting root cause analysis with defect classification.

### 5.3.1 Analysing test results to improve defect detection

Analyse test results, not only defect counts, using five analyses. Each answers a different question about why defects were missed or found late.

1. Predicted versus actual defect cluster analysis: predict clusters before testing from history, complexity, change frequency, authorship, and business criticality, then compare prediction with reality. A match validates the model. An unexpected hotspot is a warning, because more hidden defects are likely there, so test it harder and ask what the prediction missed. A predicted cluster that does not appear may mean the area was genuinely better, or that testing there was too weak, so do not automatically cut effort next time. Prediction quality can be tested with a Poisson test, since defects behave like relatively rare events: given an expected count, ask how unlikely the observed count would be if the expectation were correct. Below a chosen level, commonly 5 percent, treat the difference as real. Above it, there is no evidence of mismatch, which is not proof the prediction was exactly right. Do not declare a quiet predicted hotspot safe without checking whether testing there was simply weak.
2. Defect detection percentage (DDP) analysis: DDP counts detection only, not fixing. For a phase, DDP equals defects detected in that phase divided by (defects that entered that phase plus defects introduced in that phase), times 100, equivalently detected divided by (detected plus escaped) for that phase. Only defects detectable in that phase count, which is why knowing each defect's introduction phase matters. DDP differs from DRE: DRE counts defects fixed before release; DDP counts defects detected, whether fixed or not. A high DDP with a low fix rate points to a fixing bottleneck, not a detection problem. A low DDP points to weak detection, and the response is stronger techniques, better coverage, or earlier testing, not just more testing of the same kind. Worked example, original numbers: component testing faces 40 detectable defects and finds 20, DDP 50 percent, 20 escape; integration testing faces those 20 plus 60 new defects, 80 in total, and finds 24, DDP 30 percent, 56 escape; system testing faces 56 plus 44 new defects, 100 in total, and finds 30, DDP 30 percent, 70 escape. Even if overall removal looks respectable, the per-phase picture points at integration and system testing as weak links. Severity sharpens it further: a phase can look strong on raw DDP while letting high-severity defects through. Do not judge a level by raw defect count, which confuses a clean area with a weakly tested one.
3. Structural coverage analysis: check whether test coverage actually covered the structures where defects were found. Statement coverage is the share of executable statements run; branch coverage is the share of control-flow branches taken. Coverage finds untested code, targets new tests at complex logic, and can reveal unreachable code, which may itself be a defect. If defects were found in code or conditions that coverage claimed were covered, the coverage measure was misleading, or the tests covered the structure without checking the behaviour. If defects were found in uncovered structures, the response is to extend coverage to those structures, not to rerun the same covered tests. Coverage has two hard limits: high coverage does not guarantee effectiveness, since it says nothing about whether the test checked the right result; and coverage can be gamed by adding meaningless statements that tests always run, so teams should never be judged by coverage alone. Do not chase 100 percent everywhere, which wastes effort on low-risk code. Use coverage as a guide, balanced against risk.
4. Test gap analysis: combine static information from version control, showing what changed since the last release, with dynamic information from test execution, showing what was actually run, including manual tests. Refactoring that does not change behaviour is filtered out. The result is a map: unchanged components need no new testing; changed or new components that were tested need no further work unless the change was large; changed or new components that were not tested are gaps, and they are the priority, because new and changed code is far more fault-prone than long-stable code tested in earlier releases. Overall coverage can look healthy because an untouched area was heavily tested before, while gap analysis correctly ignores that area and flags untested new code as urgent. Do not treat low coverage in old, stable code as equal in urgency to untested new code.
5. Defect arrival pattern analysis: plot defects found over time, by phase or by iteration. A pattern that rises late suggests late detection, and the response is earlier testing and phase containment. A pattern that falls steadily suggests detection is working, but check whether it falls because defects are being found, or because testing stopped. A pattern with spikes after changes suggests regression risk, and the response is stronger regression selection (see `references/ta-risk-based-testing.md`). A well-known pattern is the Rayleigh model, a single-peaked curve that rises, peaks, and tails off slowly. Fitted to defect counts over time, it supports a rule of thumb: by the time the curve reaches its peak, roughly 40 percent of all defects have been found. That lets an analyst estimate the total from early data and how many defects would remain if testing stopped at a given point. Worked example, original numbers: defects per iteration are 12, 25, 33, 40, 38, 30, 22. The peak is iteration 4, cumulative to the peak is 110, so the estimated total is 110 divided by 0.40, or 275. After seven iterations, 200 have been found, so roughly 75 would remain if testing stopped there. A flat pattern deserves special suspicion: if actual finds stay far below the modelled curve, weak testing is the likely explanation, not excellent code. Do not read a low defect count as proof of quality without checking it against an expected arrival pattern. Poisson and Rayleigh are decision support, not proofs: Poisson assumes rare and independent defects, and Rayleigh assumes a single-peaked arrival shape.

Each analysis should end with a concrete change: a risk rating revised, a technique added, a coverage target changed, a checklist item added, or a review technique changed. An analysis that ends with a chart and no change is not prevention.

### 5.3.2 Supporting root cause analysis with defect classification

Root cause analysis (RCA) asks why a defect happened, not only what the defect was. The usual RCA steps are: define the problem, symptoms, context, and conditions; gather evidence such as documents, reports, measurements, screenshots, and user feedback; generate candidate causes, using repeated why questions, fishbone diagrams, or fault trees; identify the most likely root causes; and agree preventive actions with stakeholders. Analysing every defect individually is usually impossible, so classification groups defects into a small number of categories, and RCA is done once per group. Categories should be few, clear, and consistently applied, and designed with RCA in mind: grouping by impact alone helps triage but not causal analysis.

Four classification approaches are presented:

- Orthogonal defect classification (ODC): defects are described by eight attributes. Opener attributes, usually known at report time, are activity, trigger, impact, and target (the entity fixed). Closer attributes, usually known at fix time, are defect type, qualifier (missing, wrong, or irrelevant), source, and age (new, old, rewritten, or a fix for a previous defect). Because the scheme is independent of any one product or phase, patterns can be compared across projects. Combining attributes is the key: a group sharing activity, trigger, impact, type, and source is a strong RCA candidate.
- IEEE 1044 classification for software anomalies: a shared vocabulary and consistent attributes, including asset and artefact, versions detected and corrected, priority, severity, probability of recurrence, effect on requirements, type, mode (wrong implementation, unnecessary addition, or omission), insertion activity, and final disposition, giving comparable data for causal analysis and process improvement.
- Severity-based classification: defects grouped only by impact, typically critical, major, minor, and trivial. This is simple and useful for triage, but it does not group defects by cause, so it cannot by itself drive RCA. Use it to order RCA work, starting with the most serious groups.
- Defect taxonomies: hierarchical groupings by nature, source, or impact, such as Beizer's taxonomy, covering requirements, features and functionality, structure, data, implementation, integration, system and architecture, test definition and execution, and other defects. Quality models, such as the ISO software product quality model, can also serve as a taxonomy.

Steps for classification-supported RCA:

1. Ensure defect records carry classification attributes, not only a description. Without trigger, type, source, and introduction information, grouping will be guesswork. Classify each defect by type (for example logic error, interface error, data error, documentation error, requirement error), by phase of introduction (requirements, design, code, test), by location (component, module, interface), and by root cause category where known.
2. Group defects by combined attributes, not a single field, starting with large groups, which offer the biggest prevention return. Look for patterns: a type that recurs, a phase that introduces most defects, a location that produces most defects, or a root cause that explains many defects.
3. For the dominant pattern, run RCA: ask why that type, phase, or location produces defects, using evidence from defect data, reviews, and process, not only opinion. Common root causes include unclear requirements, missing reviews, weak test design for a technique, time pressure, and skill gaps. Do not stop at the first plausible cause, when the deepest cause is often a process gap, not a coding slip.
4. Propose a process change that addresses the root cause, not only the defect: a review technique for unclear requirements, a model for stateful behaviour, a checklist for a recurring data error, training for a skill gap, or a technique change for a test-design weakness. Vague actions such as "be more careful" are not preventive actions, and actions that nobody owns or checks will not happen.
5. Track whether the change works: does the same defect type fall in later releases? If not, the root cause was wrong, or the change was not implemented, and RCA should be revisited. A root cause that is never checked is a guess, not an analysis.

Worked example, original: over three releases, 40 percent of defects are data errors in booking records, introduced in design, where the data model never stated what happens when a booking is cancelled and rebooked. Classification shows the pattern (data, design, booking). RCA finds the root cause: no data model was built for booking lifecycle, so designers guessed. The process change is: build a data model and a state model for every lifecycle entity before design sign-off, and review them with the test analyst. Later releases are tracked for booking data defects to check whether the change worked.

Common mistakes:

- Classifying defects by symptom only (for example "crash"), without type, phase, and root cause, so no pattern can be found.
- Running RCA on a single defect and generalising to the whole process, without checking whether the pattern recurs.
- Proposing a change that addresses the defect, not the root cause, such as "test more" for a requirements defect that testing cannot prevent.
- Never checking whether the change worked, so the same root cause keeps producing defects under a new label.

## Traps in this chapter

- Prevention versus detection: late testing is detection. Prevention changes how defects are created or caught early.
- Phase containment versus DRE: PCE asks, for one phase, what share of defects introduced there were caught there. DRE asks, overall, what share of known defects were fixed before release. They are different measures, and a good DRE can hide a weak PCE in one phase.
- DDP versus DRE: DDP counts detection, DRE counts fixing before release. A high DDP with a low fix rate is a fixing problem, not a detection problem.
- DRE and PCE as upper bounds: both fall as late defects surface, because the true total defect count is unknowable. Do not present them as exact true rates.
- Review types versus review techniques: types describe formality; techniques describe how reviewers examine the product. An inspection without a technique is a process without a method.
- Automating execution is not defect prevention, and it is treated in the chapter as outside the analyst's prevention role. Automating test design from a validated model can support prevention, but automating execution alone does not prevent defects from being created.
