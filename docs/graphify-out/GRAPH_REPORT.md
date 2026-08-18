# Graph Report - docs  (2026-08-16)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 26 nodes · 27 edges · 5 communities (3 shown, 2 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `91db98e6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- calculate_expected_tfsa_v3.py
- reconstruct_holdings_at_date
- calculate_expected_tfsa_v2.py
- accurate_tfsa_calculation.py

## God Nodes (most connected - your core abstractions)
1. `main()` - 5 edges
2. `reconstruct_holdings_at_date()` - 4 edges
3. `get_price_on_date()` - 3 edges
4. `get_symbol_to_company_id()` - 3 edges
5. `load_tfsa_transactions()` - 3 edges
6. `main()` - 3 edges
7. `load_tfsa_transactions()` - 2 edges
8. `get_holdings_cost_basis()` - 2 edges
9. `Calculate expected TFSA portfolio values from CSV + historical stock prices.…` - 1 edges
10. `Load all TFSA transactions from CSV.` - 1 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `reconstruct_holdings_at_date()`  [INFERRED]
  calculate_expected_tfsa_v4.py → calculate_expected_tfsa_v3.py

## Import Cycles
- None detected.

## Communities (5 total, 2 thin omitted)

### Community 0 - "calculate_expected_tfsa_v3.py"
Cohesion: 0.31
Nodes (8): get_price_on_date(), get_symbol_to_company_id(), load_tfsa_transactions(), main(), Calculate expected TFSA portfolio values from CSV + historical stock prices.…, Load all TFSA transactions from CSV., Map ticker symbols to company_ids., Get closing price on or before target_date.

### Community 1 - "reconstruct_holdings_at_date"
Cohesion: 0.40
Nodes (5): Reconstruct holdings at a given date from transactions., reconstruct_holdings_at_date(), load_tfsa_transactions(), main(), Calculate expected TFSA portfolio values from CSV + historical stock prices.…

## Knowledge Gaps
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `reconstruct_holdings_at_date()` connect `reconstruct_holdings_at_date` to `calculate_expected_tfsa_v3.py`?**
  _High betweenness centrality (0.163) - this node is a cross-community bridge._
- **Why does `main()` connect `calculate_expected_tfsa_v3.py` to `reconstruct_holdings_at_date`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._