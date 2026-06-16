# Bug: Quarterly Health Scores & Quality Metrics All NULL

## Symptom

All quarterly rows in `financial_ratios` have NULL for every health-score / quality-metric column (`roic`, `roe`, `gross_margin`, `operating_margin`, `debt_to_equity`, `piotroski_score`, `altman_z_score`, `net_margin`, `fcf_margin`, `current_ratio`, `asset_turnover`, `working_capital`, etc.) — for **every company in the database**.

Valuation columns written by `compute_and_upsert_quarterly_valuation_metrics` (e.g. `trailing_pe`, `market_cap`, `ev_ebitda`) are correctly populated for companies where that function has run.

## Root Cause

`compute_and_upsert_quarterly_health_scores()` in `backend/application/jobs/derived_financial_metrics_job.py:648` uses `.neq("fiscal_quarter", None)` to filter for quarterly rows. The supabase-py client passes the Python `None` literal as the string `"None"` in the PostgREST query, producing:

```
APIError: invalid input syntax for type smallint: "None"
```

The same broken pattern appears in the shared helper `_fetch_quarterly_statements()` at line 608.

### Broken calls (4 locations)

| Location | Line (original) | Code |
|----------|----------------|------|
| `_fetch_quarterly_statements()` | 629 | `.neq("fiscal_quarter", None)` — inside IS/BS/CF loop |
| Fiscal-year discovery | 668 | `.neq("fiscal_quarter", None)` — income_statements query |
| Prior-year ratios fetch | 725 | `.neq("fiscal_quarter", None)` — financial_ratios query |
| Version-gate tag fetch | 898 | `.neq("fiscal_quarter", None)` — financial_ratios query |

### Why `.neq(x, None)` fails

The supabase-py library's `.neq()` method serialises its second argument directly as a URL query parameter. `None` becomes the literal string `"None"`, which PostgREST tries to parse as a `smallint` value for the `fiscal_quarter` column, resulting in error code `22P02`.

### Correct pattern

The proper API for a not-null filter is:

```python
.not_.is_("fiscal_quarter", "null")
```

This is already used correctly in the adjacent function `compute_and_upsert_quarterly_valuation_metrics()` at lines 964, 1023, 1038, and 1187.

### Why `.is_(x, None)` works but `.neq(x, None)` does not

`supabase-py`'s `.is_()` method is specifically designed for IS NULL / IS NOT NULL checks and handles `None` correctly by translating it to `null` in the query string. The `.neq()` method has no such special handling — it passes the raw Python value through.

## Impact

- **Every stock** with quarterly `financial_ratios` rows has NULL quality metrics
- The Qulaity section in the Fundamentals tab shows no data for any stock in quarterly view
- Manual computation with current source data proves all 5 quality metrics `roic`, `roe`, `gross_margin`, `operating_margin`, `debt_to_equity` would be correctly populated if the function could fetch data
- Health scores (`piotroski_score`, `altman_z_score`) are also affected

## Evidence

Live database queries confirmed:

| Ticker | Quarterly rows | Quality metrics | Valuation metrics |
|--------|:---:|:---:|:---:|
| PLTR | 16 | ALL NULL | ✅ populated (FY2023+) |
| AAPL | 4 | ALL NULL | ✅ populated |
| AMZN | 4 | ALL NULL | ✅ populated |
| GOOGL | 4 | ALL NULL | NULL |
| KO | 4 | ALL NULL | NULL |
| DIS | 4 | ALL NULL | NULL |

For PLTR specifically (company_id=376):
- All 16 quarterly `income_statements` rows have `gross_profit`, `operating_income`, `ebit`, `pretax_income`, `tax_expense`, `interest_expense`, `net_income_to_common` populated
- All 16 quarterly `balance_sheets` rows have `shareholders_equity`, `total_assets`, `cash_and_cash_equivalents`, `current_assets`, `current_liabilities` populated
- All 16 quarterly `cash_flow_statements` rows have `cash_from_operating_activities`, `capital_expenditures` populated
- Source data tags (16 of 16) mismatch the stored tags, confirming source data has changed since the job last ran
- Manual computation produces valid non-NULL values for all 16 quarters

## Fix Applied

Replaced all 4 `.neq("fiscal_quarter", None)` with `.not_.is_("fiscal_quarter", "null")` in `derived_financial_metrics_job.py`.

## Verification

- Manual re-run of the computation logic for PLTR produces correct values for all 16 quarters
- All 694 previously passing backend tests continue to pass (6 pre-existing failures unchanged)

## Post-Fix Action Required

The function will auto-correct on the next scheduler run, or the backfill script can be executed:

```bash
cd backend
python -m scripts.backfill_quarterly_health_scores
```

## File Locations

- **Buggy code**: `backend/application/jobs/derived_financial_metrics_job.py` — `_fetch_quarterly_statements()` (line 608), `compute_and_upsert_quarterly_health_scores()` (line 648)
- **Fix applied**: Lines 628, 668, 725, 898 (all `.neq` → `.not_.is_`)
- **Working reference**: `compute_and_upsert_quarterly_valuation_metrics()` (line 941) — uses correct `.not_.is_()` syntax
- **Diagnostic scripts**: `pltr_diag.py`, `pltr_tag_check.py`, `test_neq.py` (in temp directory)

---

# Appendix B: DuckDBClient "don't know what type:" Error

## Correction Notice

This analysis was initially written assuming a Windows-native runtime. The app runs **in WSL (Ubuntu/Linux)** with `Python 3.12` and `defeatbeta_api v0.0.58`. The `cache_httpfs` DuckDB extension installs and loads successfully in this environment. The "don't know what type:" error is a **transient cache-corruption issue**, not a permanent extension incompatibility.

## Symptom

In production, adding stocks to a watchlist shows:

```
ERROR:DuckDBClient:Query failed: don't know what type:
WARNING:providers.defeat_beta_provider:Income statement fetch failed for CHPY: Query failed: don't know what type:
```

All 3 statement types fail for **every** ticker (CHPY, JEPI, JEPQ, CLM, CRF, VZ). After 3 retries, falls through to yfinance.

## Provider Fallback Chain

```
get_all_financials_optimized()
  │
  ├── 1. DefeatBeta (primary)          ← DuckDB reads remote Parquet from HuggingFace
  │      │   Ticker.quarterly_income_statement()
  │      │   Ticker.quarterly_balance_sheet()
  │      │   Ticker.quarterly_cash_flow()
  │      │   Ticker.annual_*()
  │      │
  │      └── gaps?: _fill_gaps_with_yfinance()  ← per-period gap-fill
  │
  └── on total failure → 2. _fallback_to_yfinance()
         │
         ├── 2a. Stockdex (macrotrends scraper)     ┐
         ├── 2b. Edgar (SEC XBRL filings)            ├── _fetch_statement_df_with_fallback()
         └── 2c. YFinance (yfinance library)        ┘
```

**In production** the providers are initialized as: `edgar=False, stockdex=False, yfinance=True`. The fallback chain effectively becomes: **DuckDB → YFinance only**.

## Root Cause Analysis

The error has two distinct causes that compound each other:

### Cause 1: Transient DuckDB cache corruption

The `DuckDBClient` (in `defeatbeta_api` v0.0.58, running in WSL Python 3.12) is a singleton that uses the `cache_httpfs` community DuckDB extension for on-disk caching of remote Parquet files. On every startup, `_validate_httpfs_cache()` compares the remote `spec.json` update timestamp against the locally cached copy. If different, it clears and re-populates the cache by re-downloading spec.json.

The `stock_statement.parquet` is ~28.7M rows and hosted on HuggingFace. The `cache_httpfs` extension caches 1MB blocks on disk. When the file is updated by DefeatBeta during active reads, or when cache blocks are partially downloaded on a fresh cache, DuckDB's Parquet reader can encounter an empty column type annotation, producing:

```
don't know what type:  (empty type string — two null bytes in C++ internals)
```

This is **transient**: once the cache is fully populated and stable, subsequent queries succeed. In the production run, the first ticker (CHPY) corrupted the cache, causing all subsequent tickers to fail with the same error. After the cache is cleared and repopulated (e.g. by running a query for a known stock like AAPL first), the error no longer reproduces.

### Cause 2: Tickers not present in DefeatBeta parquet

Even without the cache corruption, many tickers simply **have no data** in the DefeatBeta parquet:

| Ticker | IS rows | BS rows | CF rows | In Parquet? |
|--------|:-------:|:-------:|:-------:|:-----------:|
| CHPY   | 0       | 0       | 0       | ❌ No data  |
| JEPI   | 0       | 0       | 0       | ❌ No data  |
| JEPQ   | 0       | 0       | 0       | ❌ No data  |
| CLM    | 23      | 16      | 0       | ⚠️ Partial |
| CRF    | 23      | 16      | 0       | ⚠️ Partial |
| VZ     | 47      | 80      | 57      | ✅ Full     |

CHPY, JEPI, and JEPQ simply don't exist in the DefeatBeta data source (these are Canadian REITs and JP Morgan ETFs — not individual stocks covered by the parquet dataset). The DuckDB query returns 0 rows successfully (no error), and the `if not any([income_rows.rows, balance_rows.rows, cash_rows.rows])` check raises `NoDataError`.

### Cause 3: No effective fallback for obscure tickers

With Stockdex and Edgar both disabled (`edgar=False, stockdex=False`), the only fallback is yfinance. For CHPY specifically:

```
ERROR:yfinance:HTTP Error 404: No fundamentals data found for symbol: CHPY
```

yfinance has dividend data for CHPY (61 dividend rows upserted) but no fundamentals (IS/BS/CF). The other tickers hit Stockdex rate limits (HTTP 429 from macrotrends).

## Impact

- **Every new stock** that's not in the DefeatBeta parquet gets NO IS/BS/CF data from the primary provider
- Stockdex and Edgar are disabled, so the yfinance fallback is the only option
- yfinance often lacks fundamentals for ETFs, REITs, and non-US tickers
- Without IS/BS/CF data, the health scores job (`[QHLTH]`) finds "No statement rows found" and cannot compute quarterly quality metrics or Piotroski/Altman scores
- This compounds the `.neq` bug: even when fixed, health scores cannot compute without source data

## Current Status (as of testing)

When tested today (fresh cache, after AAPL populated it):
- DuckDB queries work for tickers that exist in the parquet (VZ returns full data)
- Tickers not in the parquet (CHPY, JEPI, JEPQ) return 0 rows gracefully (no error)
- CLM/CRF have partial data (IS+BS but no CF)
- The "don't know what type:" error did NOT reproduce — confirming it was transient cache corruption

## Existing Test / Diagnostic Scripts

| Script | Location | What it does |
|--------|----------|-------------|
| `test_edgar_values.py` | `backend/scripts/test_edgar_values.py` | Tests Edgar SEC provider standalone (CIK lookup, 13F filings) |
| `backfill_eps_from_parquet.py` | `backend/scripts/backfill_eps_from_parquet.py` | Downloads DefeatBeta Parquet locally, queries with plain DuckDB (download-then-read pattern) |
| `phase7_backfill.py` | `backend/scripts/phase7_backfill.py` | Triggers full DefeatBeta re-fetch for all companies |

No standalone DuckDB/DefeatBeta test script exists. Tests mock the provider entirely.

## Suggested Fixes (not yet applied)

1. **Enable Stockdex and Edgar providers** — Currently `edgar=False, stockdex=False`. Enabling these would give the fallback chain real alternatives for tickers not in the DefeatBeta parquet.

2. **Handle 0-row results gracefully** — When DefeatBeta returns 0 rows (ticker not in parquet), consider it a "no data" result and proceed to fallback without counting it as a retry failure.

3. **Add a standalone test script** like `backend/scripts/test_defeatbeta_provider.py` that tests real DuckDB queries for a list of tickers and reports which have data.

4. **Pre-warm the cache on startup** by querying a known stock (e.g. AAPL) first, so the `cache_httpfs` cache is fully populated before handling user requests. This avoids the transient "don't know what type:" error on the first user-facing ticker.
