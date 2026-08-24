"""
Backfill eps_basic, eps_diluted, and shares_outstanding for contaminated rows.

The DefeatBeta Parquet has correct EPS and shares data for the same periods
where revenue/net_income fields were NULL. This script re-fetches those
values directly from the Parquet and updates the DB.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
import urllib3

urllib3.disable_warnings()
import httpx

_orig_init = httpx.Client.__init__
def _patched_init(self, *args, **kwargs):
    kwargs["verify"] = False
    return _orig_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_init

logging.disable(logging.CRITICAL)
import tempfile

import duckdb
import requests

from database import supabase

PARQUET_URL = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/stock_statement.parquet"


def download_parquet() -> str:
    """Download parquet to a temp file and return the local path."""
    tmp = os.path.join(tempfile.gettempdir(), "stock_statement.parquet")
    if os.path.exists(tmp) and os.path.getsize(tmp) > 100_000_000:
        print(f"  Using cached parquet ({os.path.getsize(tmp):,} bytes)")
        return tmp
    print(f"  Downloading parquet ({PARQUET_URL})...")
    resp = requests.get(PARQUET_URL, verify=False, stream=True)
    resp.raise_for_status()
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"  Downloaded {os.path.getsize(tmp):,} bytes")
    return tmp


def get_affected_rows() -> list[dict]:
    """Return income_statements rows where eps_basic IS NULL for large-cap cos."""
    large = supabase.table("income_statements") \
        .select("company_id") \
        .gt("revenue", 10_000_000_000) \
        .not_.is_("revenue", "null") \
        .execute()
    large_ids = list(set(r["company_id"] for r in large.data))

    affected = []
    CHUNK = 50
    for i in range(0, len(large_ids), CHUNK):
        chunk = large_ids[i:i+CHUNK]
        resp = supabase.table("income_statements") \
            .select("is_id,company_id,fiscal_year,fiscal_quarter,period_end_date,eps_basic,eps_diluted,shares_outstanding_basic,shares_outstanding_diluted") \
            .in_("company_id", chunk) \
            .is_("eps_basic", "null") \
            .execute()
        affected.extend(resp.data)
    return affected


def get_ticker_map(company_ids: list[int]) -> dict:
    """Map company_id -> ticker_symbol."""
    resp = supabase.table("companies") \
        .select("company_id,ticker_symbol") \
        .in_("company_id", company_ids) \
        .execute()
    return {r["company_id"]: r["ticker_symbol"] for r in resp.data}


def query_parquet(parquet_path: str, ticker: str, dates: list[str]) -> dict:
    """Query local parquet for EPS and shares data at given dates."""
    if not dates:
        return {}
    date_list = ", ".join(f"'{d}'" for d in sorted(set(dates)))

    sql = f"""
        SELECT report_date,
               MAX(CASE WHEN item_name = 'basic_eps' THEN item_value END) as basic_eps,
               MAX(CASE WHEN item_name = 'diluted_eps' THEN item_value END) as diluted_eps,
               MAX(CASE WHEN item_name = 'basic_average_shares' THEN item_value END) as basic_shares,
               MAX(CASE WHEN item_name = 'diluted_average_shares' THEN item_value END) as diluted_shares
        FROM read_parquet('{parquet_path}')
        WHERE symbol = '{ticker}'
          AND finance_type = 'income_statement'
          AND period_type = 'quarterly'
          AND report_date IN ({date_list})
        GROUP BY report_date
        ORDER BY report_date
    """
    try:
        con = duckdb.connect()
        con.execute("SET threads=1")
        con.execute("SET memory_limit='512MB'")
        result = con.execute(sql).fetchdf()
        con.close()
        if result.empty:
            return {}
        out = {}
        for _, row in result.iterrows():
            dt = row["report_date"]
            if hasattr(dt, "strftime"):
                dt = dt.strftime("%Y-%m-%d")
            out[str(dt)] = {
                "basic_eps": row["basic_eps"],
                "diluted_eps": row["diluted_eps"],
                "basic_shares": row["basic_shares"],
                "diluted_shares": row["diluted_shares"],
            }
        return out
    except Exception as e:
        print(f"  [WARN] DuckDB query failed for {ticker}: {e}")
        return {}


def main():
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("[DRY RUN] No changes. Pass --apply to commit.")
    else:
        print("[LIVE] Updating database.")

    print("Downloading parquet file (one-time)...")
    parquet_path = download_parquet()

    print("\nFinding affected rows (large-cap, eps_basic IS NULL)...")
    affected = get_affected_rows()
    print(f"Found {len(affected)} rows with missing EPS data.")

    company_ids = list(set(r["company_id"] for r in affected))
    ticker_map = get_ticker_map(company_ids)
    print(f"Affects {len(ticker_map)} unique tickers.\n")

    by_ticker: dict = {}
    for row in affected:
        cid = row["company_id"]
        ticker = ticker_map.get(cid)
        if not ticker:
            continue
        dt = row["period_end_date"]
        if hasattr(dt, "strftime"):
            dt = dt.strftime("%Y-%m-%d")
        by_ticker.setdefault(ticker, []).append({**row, "date_str": dt})

    total_updated = 0
    total_skipped = 0

    for ticker, rows in sorted(by_ticker.items()):
        dates = list(set(r["date_str"] for r in rows))
        print(f"[{ticker}] {len(rows)} rows, {len(dates)} dates...")

        parquet_data = query_parquet(parquet_path, ticker, dates)

        for row in rows:
            dt = row["date_str"]
            pd_data = parquet_data.get(dt)
            if not pd_data:
                print(f"  [SKIP] {ticker} {dt} — no Parquet EPS data")
                total_skipped += 1
                continue

            eps_basic = pd_data["basic_eps"]
            eps_diluted = pd_data["diluted_eps"]
            shares_basic = pd_data["basic_shares"]
            shares_diluted = pd_data["diluted_shares"]

            update = {}
            if eps_basic is not None and not (isinstance(eps_basic, float) and eps_basic != eps_basic):
                update["eps_basic"] = float(eps_basic)
            if eps_diluted is not None and not (isinstance(eps_diluted, float) and eps_diluted != eps_diluted):
                update["eps_diluted"] = float(eps_diluted)
            if shares_basic is not None and not (isinstance(shares_basic, float) and shares_basic != shares_basic):
                update["shares_outstanding_basic"] = int(float(shares_basic))
            if shares_diluted is not None and not (isinstance(shares_diluted, float) and shares_diluted != shares_diluted):
                update["shares_outstanding_diluted"] = int(float(shares_diluted))

            if not update:
                print(f"  [SKIP] {ticker} {dt} — no valid EPS/shares in Parquet")
                total_skipped += 1
                continue

            rid = row["is_id"]
            fy = row["fiscal_year"]
            fq = row["fiscal_quarter"]

            if dry_run:
                print(f"  [DRY]  {ticker} Q{fq} {fy} (is_id={rid}, date={dt})")
                for k, v in update.items():
                    print(f"         {k} = {v}")
            else:
                supabase.table("income_statements") \
                    .update(update) \
                    .eq("is_id", rid) \
                    .execute()
                print(f"  [OK]   {ticker} Q{fq} {fy} — {len(update)} cols updated")

            total_updated += 1

    print(f"\n{'='*60}")
    print(f"Total: {total_updated} updated, {total_skipped} skipped")
    if dry_run:
        print("Run with --apply to commit.")


if __name__ == "__main__":
    main()
