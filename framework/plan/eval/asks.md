# Planner evaluation asks (DID-016)

Run the planner on each ask twice: once without the `task-breakdown` skill, once with it.
Score each run: (a) `plan_lint.py` ERROR count, (b) the pass condition below, judged by a human.
Keep the model, temperature and context identical between arms (see DID-015 for pairing).

| # | Ask | What a good plan must do |
|---|---|---|
| 1 | "I see a spike on two dates in the chart. I asked for logging through the whole flow. Did you test it end to end?" | Add a goal-level [e2e] criterion that reproduces the two dates against the real stack; discovery for data lists the real shapes; no mocks under e2e. |
| 2 | "Valuation is wrong for a company holding both CDR and direct shares." | Enumerate every (company, lot kind) combination from real data before fixtures; a [data-invariant] criterion over the real snapshot; per-lot not per-company logic. |
| 3 | "Dividend income looks doubled for some accounts." | Profile the upstream export for duplicated fields first (discovery data VERIFIED with counts); criteria cover the import and the displayed total. |
| 4 | "Stop showing stale prices for delisted tickers." | Research task before implementation while terminal outcomes are OPEN; goal-level criterion that healthy positions are unchanged; reuse record for price resolution. |
| 5 | "Rename the label 'Qty' to 'Quantity' on the holdings table." | Recognise as trivial; must not generate a heavy plan (ENTRY_EXEMPT=TRIVIAL path). |
| 6 | "Make the dashboard better." | Must not plan. Must list at least two interpretations with trade-offs and ask. |

Cases 5 and 6 test restraint: a skill that makes every ask heavy is a regression.
