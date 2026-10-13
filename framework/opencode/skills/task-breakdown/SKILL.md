---
name: task-breakdown
description: Break a change into verifiable tasks before any code is written. Use whenever a request is non-trivial - a new feature, a bug fix across files, a data or valuation change, a migration - and whenever you are about to write or revise a plan, acceptance criteria, or a task list. Covers discovering what is unknown about the current code, architecture, design, environment and data, searching for reuse before inventing, writing observable acceptance criteria with an evidence class, and a final real-stack check of the user's actual outcome. Run it even when the plan feels obvious; vague plans are how defects escape.
---

# Task breakdown

A plan is good only if a stranger could tell, from the plan alone, whether the user's goal was met.
Three failures cause most escapes: criteria nobody can observe, tests that share the code's
assumptions, and facts about the current system that were assumed instead of checked.

Trivial asks (single step, unambiguous) skip this skill; `ENTRY_EXEMPT=TRIVIAL` already covers them.

## Procedure

1. **Restate the ask.** Write what the user wants observed when done, in their words. If two
   readings exist, list both with trade-offs and ask. Do not pick silently (AGENTS.md).
2. **Discover the current state** - one entry per category, each `OPEN`, `VERIFIED` or `NA`:

   | Category | Find out | How to verify (cite it) |
   |---|---|---|
   | code | what exists today, who calls it | `python3 framework/adapters/code_intel.py locate --symbol <name>`, then open the file; cite `path:lines` |
   | architecture | boundaries, contracts, ownership | `framework/architecture_rules.yaml`, `.planning/contracts/`, callers via impact |
   | design | prior decisions, existing docs | `.planning/decisions/`, `docs/` |
   | environment | versions, flags, services, grants | run the command, record it in the claim ledger |
   | data | real shapes, duplicates, nulls, mixed cases | query the real data; note counts; list every distinct shape |

   Anything you can resolve by reading or running something, resolve now. Anything only the user
   knows: ask. An `OPEN` entry blocks the plan; it is not a note to self.
3. **Search for reuse before inventing.** For every new service, repository, helper, retry,
   serializer or state holder: search the repo, then record `<need> -> <existing path>` or
   `<need> -> NEW: <why nothing existing can be extended>`. Equally, do not generalise beyond the
   current criteria (`_shared-anti-overbuild.md`).
4. **Decompose** by the rules below. Put the riskiest unknown first.
5. **Write criteria** that name an input, an observable output or value, and a threshold, each
   tagged with the strongest applicable evidence class.
6. **Pre-mortem.** Assume every task passes and the user still reports the original problem.
   Write three ways that could happen. Add a criterion for each that would catch it.
7. **Lint, fix, repeat:** `python3 framework/plan/plan_lint.py <plan>` until no ERROR remains.
   `g_entry` runs the same lint and refuses dispatch on any ERROR, so a plan that skips this
   step cannot reach an implementer.

## Decomposition rules

- One reviewable outcome per task. Past about 10 files or 8 criteria it is several tasks.
- Vertical slices: each task leaves the system working and testable. No "do all the models first".
- Research is its own task when discovery is not finished. Do not plan implementation on `OPEN`.
- Order by risk, then dependency. Declare `depends_on:` by plan or task id.
- The last task is goal-level: it exercises the real stack and asserts the user's outcome.
- Tests are derived from the requirement and from real data shapes, not from the code you just wrote.

## Criterion format (block list; one-line lists split on commas)

`AC-<n> [evidence] <input> -> <observable result> <threshold or value>`

Evidence tags: `unit` `integration` `e2e` `browser` `contract` `data-invariant` `static` `manual`.
`manual` is reasoning, not executable evidence. At least one criterion must be `e2e`, `browser` or
`data-invariant`, and one tagged `integration`, `e2e` or `data-invariant` must not rely on mocks.
A test that mocks the collaborator under test proves the mock; tag it `unit`.

## Plan template

```
status: draft
title: <outcome in one line>
depends_on:
  - <plan or task id>
files_or_components:
  - <path>
acceptance_criteria:
  - AC-1 [unit] ...
  - AC-2 [e2e] ...
discovery:
  - code [VERIFIED: path:10-40] ...
  - architecture [VERIFIED: path:1-30] ...
  - design [NA: <reason, three words or more>] ...
  - environment [VERIFIED: <command that was run>] ...
  - data [VERIFIED: CLM-123] ...
reuse:
  - <need> -> <existing path | NEW: reason>
open_questions:
```

## Worked example 1 - good (illustrative)

Ask: "positions in delisted tickers must stop showing stale prices as current."

```
acceptance_criteria:
  - AC-1 [unit] a price older than the horizon is never forward-filled; resolve returns no price
  - AC-2 [integration] a position past the horizon is tagged stale with price_age_days equal to the real age, persisted to the snapshot table
  - AC-3 [data-invariant] on the real database, the 113 positions priced within 30 days have unchanged values before and after, no mocking
  - AC-4 [e2e] the portfolio page shows the disclosure indicator for each stale position and none for healthy ones
discovery:
  - data [VERIFIED: CLM-212] 7 tickers have no terminal event; 113 positions are under 30 days old
  - environment [VERIFIED: grant check on cdr_ratio_registry] the grant is missing, which blocks reliable staleness detection
```

Why it works: each criterion has an observable value, AC-3 pins what must not change, AC-4 is what the
user will actually look at, and the data and grant unknowns were found before design.

## Worked example 2 - bad, then fixed (illustrative)

Ask: "valuation is wrong for a company that holds both CDR and direct shares."

Bad: `AC-1 [unit] valuation handles CDR correctly` with fixtures where every pair is the same kind.
It is vague, and the test data shares the code's assumption that a company is one kind or the other.

Fixed:
```
  - AC-1 [unit] a company with one CDR lot and one direct lot values each lot at its own price scale
  - AC-2 [data-invariant] for every position on the real account snapshot, value equals the sum of lot quantity times lot price within 0.01, including a company with mixed lots
  - AC-3 [e2e] the portfolio total shown to the user equals the independent per-lot sum
discovery:
  - data [VERIFIED: query listing every (company, lot kind) combination] mixed combinations exist
```

## Anti-patterns

- "Works correctly", "handles errors gracefully", "all cases": no observable result.
- Tagging a mocked test `e2e` or `integration`.
- A discovery entry marked `VERIFIED` with no path, command or claim id.
- Fixtures drawn only from the shape you already thought of; list the real shapes first.
- A new helper with no reuse search recorded.
- Editing the plan after approval without re-review (`approval_hash` will flag it).
- Counting passing tests as proof the goal was met. Criteria passing is necessary, not sufficient;
  the goal-level criterion is what ties the plan back to the ask.

## What the lint cannot judge

It checks structure and cited evidence (paths exist, tags present, nothing OPEN, no mocks under a
real-stack tag, hash matches). It cannot tell whether a criterion is the right one or whether a
`VERIFIED` claim is true. The reviewer owns both. Rule ids: PL00 list form, PL01 vague, PL02 size,
PL03 evidence tag, PL04 goal-level and mocks, PL05 discovery, PL06 reuse, PL07 dependencies,
PL08 approval hash.
