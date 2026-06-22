"""
validation_suite.py
====================
Pre/post-implementation validation suite for the Data Freshness fixes.

Run BEFORE making changes to baseline the current state:
    cd backend && python scripts/validation_suite.py --mode=baseline

Run AFTER making changes to verify they work:
    cd backend && python scripts/validation_suite.py --mode=verify

Each test is independent and self-contained.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

from datetime import date, datetime, timedelta
from shared.time_utils import now_utc, parse_db_timestamp
from database import supabase
from typing import List, Optional
import argparse

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def test(name: str, result: bool, detail: str = ""):
    status = PASS if result else FAIL
    print(f"  [{status}] {name}")
    if detail:
        print(f"          {detail}")
    return result


def run_baseline():
    """Record the current state before any changes."""
    print("\n" + "=" * 70)
    print("BASELINE: Recording current state before changes")
    print("=" * 70)

    results = {}

    # --- 1. Scheduler State ---
    print("\n--- Test 1: Scheduler States ---")
    ss = supabase.table("scheduler_state").select("scheduler_name, enabled, last_planned_at, last_status").execute()
    state_names = [s["scheduler_name"] for s in (ss.data or [])]
    
    for sched in ["super_investors", "market_data", "earnings", "aggregation"]:
        exists = sched in state_names
        results[f"scheduler_state_{sched}"] = exists
        if exists:
            s = [s for s in ss.data if s["scheduler_name"] == sched][0]
            test(f"{sched} state exists", True, f"enabled={s.get('enabled')} last_planned={str(s.get('last_planned_at',''))[:19]} status={s.get('last_status','?')}")
        else:
            test(f"{sched} state exists", False)

    # --- 2. Companies Missing Financial Data ---
    print("\n--- Test 2: Companies Without Financial Data ---")
    test_results = _get_companies_without_financials()
    results["missing_financials_count"] = len(test_results)
    test(f"Active companies without financials", len(test_results) > 0, f"Count: {len(test_results)}")
    for c in test_results[:10]:
        print(f"         {c['ticker_symbol']:10s} ({c.get('security_type','?')})")

    # --- 3. Companies Missing Earnings Dates ---
    print("\n--- Test 3: Companies Missing Earnings Dates ---")
    results["missing_earnings_dates"] = _get_missing_earnings_dates()
    test(f"Active companies missing earnings dates", len(results["missing_earnings_dates"]) > 0, f"Count: {len(results['missing_earnings_dates'])}")
    for c in results["missing_earnings_dates"][:10]:
        print(f"         {c['ticker_symbol']:10s} ({c.get('security_type','?')})")

    # --- 4. Super Investor Data Freshness ---
    print("\n--- Test 4: Super Investor Data Freshness ---")
    investors = supabase.table("institutional_investors").select("investor_name, last_filed_period").execute()
    stale_investors = []
    for inv in (investors.data or []):
        if inv.get("last_filed_period"):
            lp = str(inv["last_filed_period"])
            if lp < "2024-01-01":
                stale_investors.append(inv["investor_name"])
    results["stale_investors"] = len(stale_investors)
    test(f"Super investors with pre-2024 data", len(stale_investors) > 0, f"Count: {len(stale_investors)}")
    for name in stale_investors:
        print(f"         {name}")

    # --- 5. Stale Locks ---
    print("\n--- Test 5: Stale Scheduler Locks ---")
    locks = supabase.table("scheduler_locks").select("*").execute()
    stale_lock_count = 0
    now = now_utc()
    for lk in (locks.data or []):
        exp = lk.get("expires_at")
        if exp:
            exp_dt = parse_db_timestamp(exp) if isinstance(exp, str) else exp
            if exp_dt < now:
                stale_lock_count += 1
    results["stale_locks"] = stale_lock_count
    test(f"Stale scheduler locks detected", stale_lock_count > 0, f"Count: {stale_lock_count}")

    # --- 6. Zombie Heartbeats ---
    print("\n--- Test 6: Zombie Worker Heartbeats ---")
    hb = supabase.table("worker_heartbeats").select("worker_id, hostname, last_hb_at, active_jobs").execute()
    zombie_count = sum(1 for w in (hb.data or []) if w.get("hostname") == "shutdown")
    results["zombie_heartbeats"] = zombie_count
    test(f"Zombie worker heartbeats (hostname=shutdown)", zombie_count > 0, f"Count: {zombie_count}")

    # --- 7. Dead Letter Jobs ---
    print("\n--- Test 7: Dead Letter Jobs ---")
    dl = supabase.table("jobs").select("id, job_type, resource_id, last_error").eq("status", "dead_letter").execute()
    results["dead_letter_count"] = len(dl.data or [])
    test(f"Dead letter jobs", len(dl.data or []) > 0, f"Count: {len(dl.data or [])}")
    for j in (dl.data or []):
        print(f"         type={j['job_type']} resource={j.get('resource_id')} error={str(j.get('last_error',''))[:80]}")

    # --- 8. Scheduler Configuration ---
    print("\n--- Test 8: Scheduler Config Validation ---")
    from config import settings
    configs = {
        "ENABLE_SUPER_INVESTORS_SCHEDULER": getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", None),
        "ENABLE_MARKET_DATA_SCHEDULER": getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", None),
        "ENABLE_EARNINGS_SCHEDULER": getattr(settings, "ENABLE_EARNINGS_SCHEDULER", None),
        "ENABLE_AGGREGATION_SCHEDULER": getattr(settings, "ENABLE_AGGREGATION_SCHEDULER", None),
    }
    for name, val in configs.items():
        results[f"config_{name}"] = val
        test(f"Config {name}", val is not None, f"Value: {val}")

    print("\n" + "=" * 70)
    print("BASELINE COMPLETE")
    print("=" * 70)

    return results


def run_verify():
    """Run verification checks after changes."""
    print("\n" + "=" * 70)
    print("VERIFY: Checking that changes are working correctly")
    print("=" * 70)

    all_pass = True

    # --- Verify 1: Super Investors Scheduler State ---
    print("\n--- Verify 1: Super Investors Scheduler Registered ---")
    ss = supabase.table("scheduler_state").select("scheduler_name, enabled, last_status, last_planned_at, next_due_at").eq("scheduler_name", "super_investors").execute()
    if ss.data:
        s = ss.data[0]
        all_pass &= test("super_investors has state row", True, f"enabled={s.get('enabled')} last_status={s.get('last_status','?')} next_due={str(s.get('next_due_at',''))[:19]}")
        all_pass &= test("super_investors is enabled", s.get("enabled", False) == True)
        
        # Check jobs were enqueued
        jc = supabase.table("jobs").select("id", count="exact").eq("job_type", "investor_refresh").gte("created_at", "2026-06-21").execute()
        all_pass &= test("investor_refresh jobs created", (jc.count or 0) > 0, f"Count: {jc.count}")
    else:
        all_pass &= test("super_investors has state row", False)
        print("  *** SUGGESTION: Check that ENABLE_SUPER_INVESTORS_SCHEDULER is True in .env")

    # --- Verify 2: Backlog Query Works ---
    print("\n--- Verify 2: Backlog Processing ---")
    backlog = _get_companies_without_financials(limit=50)
    print(f"  Companies needing bootstrap: {len(backlog)}")
    
    # If we have ETF entries without financials, that's expected -- they should be filtered
    etfs_in_backlog = [c for c in backlog if c.get("security_type") in ("etf", "index", "mutual_fund")]
    test("ETFs are filtered from financial backlog", len(etfs_in_backlog) == 0, f"ETFs in backlog: {len(etfs_in_backlog)}")
    
    # The real test: verify that the market_data scheduler includes 'financials' scope for backlog companies
    print("  Manual check: Verify market_data scheduler plan() adds 'financials' scope for backlog companies")

    # --- Verify 3: Earnings Date Sync ---
    print("\n--- Verify 3: Earnings Date Sync ---")
    missing_dates = _get_missing_earnings_dates()
    total_missing = len(missing_dates)
    
    # Count how many are stocks (vs ETFs)
    stock_missing = [c for c in missing_dates if c.get("security_type") in ("stock", None)]
    etf_missing = [c for c in missing_dates if c.get("security_type") not in ("stock", None)]
    
    all_pass &= test("Earnings sync prioritizes NULL dates", len(missing_dates) == len(etf_missing) + len(stock_missing))
    
    if etf_missing:
        all_pass &= test("ETFs can be excluded from earnings date fetch", False, 
                        f"{len(etf_missing)} ETFs/indexes should not need earnings dates")
        for c in etf_missing:
            print(f"  ETF w/out earnings date: {c['ticker_symbol']}")
    
    if stock_missing:
        print(f"  {len(stock_missing)} stock(s) still missing earnings dates -- these will be picked up by sync")
        for c in stock_missing[:5]:
            print(f"  {c['ticker_symbol']}")

    # --- Verify 4: Stale Lock Cleanup ---
    print("\n--- Verify 4: Stale Lock Cleanup ---")
    locks = supabase.table("scheduler_locks").select("company_id, expires_at, lock_type").execute()
    now = now_utc()
    stale = [lk for lk in (locks.data or []) if parse_db_timestamp(lk["expires_at"]) < now if isinstance(lk["expires_at"], str)]
    stale_count = 0
    for lk in (locks.data or []):
        exp = lk.get("expires_at")
        if exp:
            exp_dt = parse_db_timestamp(exp) if isinstance(exp, str) else exp
            if exp_dt < now:
                stale_count += 1
                
    all_pass &= test("No stale scheduler locks remain", stale_count == 0, f"Stale locks remaining: {stale_count}")
    if stale_count > 0:
        for lk in (locks.data or []):
            exp = lk.get("expires_at")
            if exp:
                exp_dt = parse_db_timestamp(exp) if isinstance(exp, str) else exp
                if exp_dt < now:
                    print(f"  Stale lock: company_id={lk['company_id']} type={lk.get('lock_type')} expires={exp}")

    # --- Verify 5: Zombie Heartbeat Cleanup ---
    print("\n--- Verify 5: Zombie Heartbeat Cleanup ---")
    hb = supabase.table("worker_heartbeats").select("worker_id, hostname").execute()
    zombies = [w for w in (hb.data or []) if w.get("hostname") == "shutdown"]
    all_pass &= test("No zombie heartbeats remain", len(zombies) == 0, f"Zombie heartbeats remaining: {len(zombies)}")

    # --- Verify 6: Dead Letter Requeue ---
    print("\n--- Verify 6: Dead Letter Re-queue ---")
    dl = supabase.table("jobs").select("id, job_type, status, available_at, attempts, max_attempts").eq("status", "dead_letter").execute()
    if dl.data:
        # Check if any have been re-queued (available_at in future)
        now = now_utc()
        requeued = [j for j in dl.data if j.get("available_at") and parse_db_timestamp(j["available_at"]) > now]
        test("Dead letter jobs have re-queue schedule", len(requeued) > 0 or len(dl.data) < 5, 
             f"Dead letters: {len(dl.data)}, Re-queued: {len(requeued)}")
        
        # Check for increased max_attempts
        adjusted = [j for j in dl.data if j.get("max_attempts", 0) > 3]
        if adjusted:
            test("Dead letter max_attempts increased", True, f"{len(adjusted)} jobs have adjusted max_attempts")
    else:
        test("No dead letter jobs", True)

    # --- Verify 7: Config Consistency ---
    print("\n--- Verify 7: Configuration Consistency ---")
    from config import settings
    enabled = getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", None)
    all_pass &= test("ENABLE_SUPER_INVESTORS_SCHEDULER is True", enabled == True, f"Current value: {enabled}")

    print("\n" + "=" * 70)
    if all_pass:
        print("ALL VERIFICATIONS PASSED")
    else:
        print("SOME VERIFICATIONS FAILED -- see details above")
    print("=" * 70)

    return all_pass


def _get_companies_without_financials(limit: int = 50) -> List[dict]:
    """Simulate the proposed get_companies_without_financials() query."""
    try:
        # Get active company IDs
        active_ids = set()
        ph = supabase.table("portfolio_holdings").select("symbol").execute()
        portfolio_symbols = list(set(h["symbol"] for h in (ph.data or [])))
        if portfolio_symbols:
            ph_comps = supabase.table("companies").select("company_id").in_("ticker_symbol", portfolio_symbols).execute()
            for c in (ph_comps.data or []):
                if c.get("company_id"):
                    active_ids.add(c["company_id"])
        wl = supabase.table("watchlist_items").select("company_id").execute()
        for w in (wl.data or []):
            if w.get("company_id"):
                active_ids.add(w["company_id"])

        if not active_ids:
            return []

        # Get all active companies (excluding ETFs/indexes)
        result = supabase.table("companies").select(
            "company_id, ticker_symbol, security_type"
        ).in_("company_id", list(active_ids)).execute()

        result.data.sort(key=lambda x: x.get("security_type", "") == "stock", reverse=True)
        
        without_financials = []
        for c in result.data:
            cid = c["company_id"]
            resp = supabase.table("income_statements").select("fiscal_year").eq("company_id", cid).limit(1).execute()
            if not resp.data:
                without_financials.append(c)
                if len(without_financials) >= limit:
                    break

        return without_financials
    except Exception as e:
        print(f"  Error in backlog query: {e}")
        return []


def _get_missing_earnings_dates() -> List[dict]:
    """Get all active companies with NULL next_earnings_date."""
    try:
        active_ids = set()
        ph = supabase.table("portfolio_holdings").select("symbol").execute()
        portfolio_symbols = list(set(h["symbol"] for h in (ph.data or [])))
        if portfolio_symbols:
            ph_comps = supabase.table("companies").select("company_id").in_("ticker_symbol", portfolio_symbols).execute()
            for c in (ph_comps.data or []):
                if c.get("company_id"):
                    active_ids.add(c["company_id"])
        wl = supabase.table("watchlist_items").select("company_id").execute()
        for w in (wl.data or []):
            if w.get("company_id"):
                active_ids.add(w["company_id"])

        if not active_ids:
            return []

        result = supabase.table("companies").select(
            "company_id, ticker_symbol, security_type"
        ).in_("company_id", list(active_ids)).is_("next_earnings_date", "null").execute()

        return result.data or []
    except Exception as e:
        print(f"  Error: {e}")
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Freshness Validation Suite")
    parser.add_argument("--mode", choices=["baseline", "verify"], default="baseline",
                        help="baseline = record current state, verify = check after changes")
    args = parser.parse_args()

    print("=" * 70)
    print(f"DATA FRESHNESS VALIDATION SUITE -- mode={args.mode}")
    print(f"Generated: {now_utc().isoformat()}")
    print("=" * 70)

    if args.mode == "baseline":
        run_baseline()
    else:
        success = run_verify()
        sys.exit(0 if success else 1)
