"""Measure WHY portfolio_snapshots reads cost ~1s each (via PostgREST).

Establishes, using the same client/transport the app uses:
  1. Row count, date span, holdings_json payload size.
  2. Wall time of the exact compare-path query, with and without holdings_json.
  3. Wall time for 1 page vs all pages (3 accounts x full history).
  4. Index list on the table (via a targeted REST read is impossible, so we
     infer from observed timing and report what we could not measure).

Measurement only. Writes nothing. Exit 0 always.
Run: python backend/scripts/measure_snapshot_read_cost.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

from database import supabase  # noqa: E402


def timed(label: str, fn) -> tuple[float, object]:
    t0 = time.perf_counter()
    out = fn()
    dt = (time.perf_counter() - t0) * 1000
    print(f"  {label:52s} {dt:9.1f} ms")
    return dt, out


def main() -> int:
    accounts = [9, 8, 7]

    print("===== shape =====")
    res = (
        supabase.table("portfolio_snapshots")
        .select("account_id, snapshot_date, total_value, holdings_json", count="exact")
        .in_("account_id", accounts)
        .order("snapshot_date", desc=False)
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    count = getattr(res, "count", None)
    print(f"  page rows            : {len(rows)}")
    print(f"  exact count (all)    : {count}")
    if rows:
        print(f"  date span in page    : {rows[0]['snapshot_date']} .. {rows[-1]['snapshot_date']}")
        sizes = [len(r.get("holdings_json") or "") for r in rows]
        sizes = [s for s in sizes if s]
        if sizes:
            print(f"  holdings_json bytes  : avg={sum(sizes) // len(sizes)} max={max(sizes)}")
        print(f"  rows w/ holdings_json: {sum(1 for s in sizes if s)}/{len(rows)}")
        print(f"  per-account rows     : "
              + str({a: sum(1 for r in rows if r["account_id"] == a) for a in accounts}))

    print("\n===== the compare-path read (full column set, WITH holdings_json) =====")
    SELECT_FULL = ("account_id, snapshot_date, total_value, holdings_market_value, cost_basis, "
                   "cash_balance, net_deposits, data_quality_flag, holdings_json")
    SELECT_LEAN = ("account_id, snapshot_date, total_value, holdings_market_value, cost_basis, "
                   "cash_balance, net_deposits, data_quality_flag")

    def full_paged() -> int:
        offset, got, pages = 0, 0, 0
        while True:
            r = (
                supabase.table("portfolio_snapshots")
                .select(SELECT_FULL)
                .in_("account_id", accounts)
                .gte("snapshot_date", "2015-01-01")
                .lte("snapshot_date", "2026-12-31")
                .order("snapshot_date", desc=False)
                .order("account_id", desc=False)
                .order("id", desc=False)
                .range(offset, offset + 999)
                .execute()
            )
            chunk = r.data or []
            got += len(chunk)
            pages += 1
            if len(chunk) < 1000:
                break
            offset += 1000
        print(f"    [{pages} pages, {got} rows]")
        return got

    def lean_paged() -> int:
        offset, got, pages = 0, 0, 0
        while True:
            r = (
                supabase.table("portfolio_snapshots")
                .select(SELECT_LEAN)
                .in_("account_id", accounts)
                .gte("snapshot_date", "2015-01-01")
                .lte("snapshot_date", "2026-12-31")
                .order("snapshot_date", desc=False)
                .order("account_id", desc=False)
                .order("id", desc=False)
                .range(offset, offset + 999)
                .execute()
            )
            chunk = r.data or []
            got += len(chunk)
            pages += 1
            if len(chunk) < 1000:
                break
            offset += 1000
        print(f"    [{pages} pages, {got} rows]")
        return got

    # First page only, to separate per-query cost from page count.
    def full_first_page() -> int:
        r = (
            supabase.table("portfolio_snapshots")
            .select(SELECT_FULL)
            .in_("account_id", accounts)
            .gte("snapshot_date", "2015-01-01")
            .lte("snapshot_date", "2026-12-31")
            .order("snapshot_date", desc=False)
            .order("account_id", desc=False)
            .order("id", desc=False)
            .range(0, 999)
            .execute()
        )
        return len(r.data or [])

    def lean_first_page() -> int:
        r = (
            supabase.table("portfolio_snapshots")
            .select(SELECT_LEAN)
            .in_("account_id", accounts)
            .gte("snapshot_date", "2015-01-01")
            .lte("snapshot_date", "2026-12-31")
            .order("snapshot_date", desc=False)
            .order("account_id", desc=False)
            .order("id", desc=False)
            .range(0, 999)
            .execute()
        )
        return len(r.data or [])

    for i in range(2):
        print(f"  -- pass {i + 1} --")
        timed("FULL columns, first page only", full_first_page)
        timed("LEAN columns, first page only", lean_first_page)
        timed("FULL columns, all pages (compare path)", full_paged)
        timed("LEAN columns, all pages", lean_paged)

    print("\n  NOTE: index inspection needs SQL access; not available in this venv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
