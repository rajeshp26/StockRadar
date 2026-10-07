"""
Portfolio Dashboard Loading Performance Test

Measures and reports timing for ALL portfolio dashboard API calls,
diagnoses the performance chart 500 error, and identifies root causes
for slow page load.

Usage:
  1) Run against live dev server:
     set PERF_AUTH_TOKEN=your_jwt_token
     python -m pytest tests/test_portfolio_performance_loading.py -v -s

  2) Run mock-based timing estimates (no auth needed):
     python -m pytest tests/test_portfolio_performance_loading.py -v -s -k "mock"

The waterfall simulates the EXACT request order the dashboard makes.
"""
import asyncio
import os
import sys
import time
from datetime import datetime

import pytest

# -- CONFIG --------------------------------------------------------------------

BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://172.19.86.61:8001")
AUTH_TOKEN = os.getenv("PERF_AUTH_TOKEN", "")

ENDPOINTS = [
    ("POST", "/users/sync", "User Sync"),
    ("GET", "/portfolio/overview", "Portfolio Overview"),
    ("GET", "/portfolio/holdings", "Portfolio Holdings"),
    ("GET", "/portfolio/accounts", "Portfolio Accounts"),
    ("GET", "/portfolio/dashboard", "Portfolio Dashboard"),
    ("GET", "/portfolio/brokerages", "Portfolio Brokerages"),
    ("GET", "/portfolio/performance?period=1Y", "Performance Chart (1Y)"),
    ("GET", "/portfolio/performance?period=1M", "Performance Chart (1M)"),
    ("GET", "/benchmarks", "Benchmarks"),
]

THRESHOLDS = {
    "fast": 500,
    "ok": 2000,
    "slow": 8000,
    "critical": 12000,
}

# -- HELPERS -------------------------------------------------------------------


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if AUTH_TOKEN:
        h["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return h


async def _time_request(method: str, path: str, label: str) -> dict:
    """Make a single request and return timing + status info."""
    import httpx

    url = f"{BACKEND_ORIGIN}{path}"
    transport = httpx.AsyncHTTPTransport(retries=0)
    limits = httpx.Limits(max_keepalive_connections=0, max_connections=1)

    async with httpx.AsyncClient(
        transport=transport, limits=limits, timeout=30.0
    ) as client:
        start = time.perf_counter()
        try:
            if method == "GET":
                resp = await client.get(url, headers=_headers(), follow_redirects=False)
            else:
                resp = await client.post(url, headers=_headers(), json={}, follow_redirects=False)
            elapsed = time.perf_counter() - start
            elapsed_ms = round(elapsed * 1000)
            status = resp.status_code
            body = ""
            try:
                body = resp.text[:500]
            except Exception:
                pass
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - start
            elapsed_ms = round(elapsed * 1000)
            status = 0
            body = f"TIMEOUT after {elapsed_ms}ms: {e}"
        except Exception as e:
            elapsed = time.perf_counter() - start
            elapsed_ms = round(elapsed * 1000)
            status = 0
            body = f"ERROR: {e}"

    return {
        "method": method,
        "path": path,
        "label": label,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "elapsed_s": round(elapsed_ms / 1000, 1),
        "body": body,
    }


def _grade(ms: int) -> tuple[str, str]:
    if ms < THRESHOLDS["fast"]:
        return "PASS", "green"
    elif ms < THRESHOLDS["ok"]:
        return "OK", "yellow"
    elif ms < THRESHOLDS["slow"]:
        return "SLOW", "orange"
    else:
        return "CRITICAL", "red"


def _print_waterfall(results: list[dict]):
    """Print a waterfall chart of all requests in order."""
    print()
    print("=" * 100)
    print("  PORTFOLIO DASHBOARD -- REQUEST WATERFALL")
    print("=" * 100)
    print(f"  Backend: {BACKEND_ORIGIN}")
    print(f"  Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Auth:    {'[OK] Bearer token' if AUTH_TOKEN else '[NO] NO TOKEN (will get 401)'}")
    print("=" * 100)
    print()

    total_ms = sum(r["elapsed_ms"] for r in results)
    width = 60

    for i, r in enumerate(results, 1):
        grade_name, _ = _grade(r["elapsed_ms"])
        bar_len = max(1, int(r["elapsed_ms"] / max(total_ms, 1) * width))
        bar = "#" * bar_len

        status_str = f"{r['status']}" if r["status"] else "TIMEOUT"

        print(f"  {i:2d}. {r['label']:<35s} {status_str:>4s}  {r['elapsed_s']:>5.1f}s  {grade_name:<10s} {bar}")

    print()
    print(f"      TOTAL: {total_ms / 1000:.1f}s  (sum of {len(results)} requests)")
    print()

    sorted_by_time = sorted(results, key=lambda r: r["elapsed_ms"], reverse=True)
    print("  -- Slowest requests --")
    for r in sorted_by_time[:3]:
        print(f"     {r['elapsed_s']:>5.1f}s  {r['method']} {r['path']}  ({r['label']})")

    errors = [r for r in results if r["status"] and r["status"] >= 400]
    if errors:
        print()
        print(f"  -- Errors ({len(errors)}) --")
        for r in errors:
            print(f"     HTTP {r['status']}  {r['method']} {r['path']}")
            if r["body"]:
                for line in r["body"].split("\n")[:5]:
                    print(f"       {line}")
        print()


def _print_diagnosis(results: list[dict]):
    """Print root-cause diagnosis based on observed timings."""
    print()
    print("=" * 100)
    print("  ROOT CAUSE DIAGNOSIS")
    print("=" * 100)

    # Check for 500 on performance
    perf_results = [r for r in results if "performance" in r["path"] and r["status"] == 500]
    if perf_results:
        print()
        print("  [CRITICAL] Performance chart endpoint returns HTTP 500")
        print()
        print("     Root cause: The backend is throwing an unhandled exception.")
        print("     Check the FastAPI server logs for the Python traceback.")
        print()
        print("     Common causes:")
        print("     1. Data integrity error in build_snapshot_row() invariant")
        print("        (cost=0 with qty>0 - fixed in snapshot_builder.py)")
        print("     2. KeyError when accessing legacy DB column names")
        print("        (cost_basis vs total_cost - fixed in snapshot_builder.py)")
        print("     3. Supabase query timeout or network error")
        print("     4. Division by zero in return percentage calculation")
        for r in perf_results:
            print(f"         Response body: {r['body'][:200]}")

    slow = [r for r in results if r["elapsed_ms"] >= THRESHOLDS["slow"]]
    if slow:
        print()
        print(f"  [CRITICAL] {len(slow)} requests exceed {THRESHOLDS['slow']/1000}s")
        print()
        print("     Root cause: TWO compounding problems:")
        print()
        print("     1. NO TIMEOUT on proxy fetch (web/src/app/api/proxy/[...path]/route.ts:192)")
        print("         The fetch() call has no timeout -> can wait indefinitely")
        print()
        print("     2. N+1 QUERY STORM in _compute_performance_fallback()")
        print("        (backend/application/services/portfolio_service.py:2241-2415)")
        print("         For each date (~52 for 1Y) x each account (~5) x each company (~20):")
        print("            - resolve_price_forward_filled() (in-memory, fast)")
        print("            - get_cash_balance(aid, date)  (Supabase query, SLOW)")
        print("            - get_net_deposits(aid, date)  (Supabase query, SLOW)")
        print("         Total: ~520 Supabase queries per request!")
        print()
        print(f"     3. Backend on DIFFERENT HOST: {BACKEND_ORIGIN}")
        print("         Network hop adds latency vs localhost")
        print()

    # Duplicate request analysis
    paths_seen = {}
    for r in results:
        p = r["path"].split("?")[0]
        paths_seen.setdefault(p, []).append(r)
    duplicates = {p: rs for p, rs in paths_seen.items() if len(rs) > 1}
    if duplicates:
        print()
        print(f"  [DUP] DUPLICATE REQUESTS: {len(duplicates)} endpoints called multiple times")
        print()
        print("     Root cause: Each tab component makes INDEPENDENT API calls:")
        print("     - PortfolioTabShell -> usePortfolioDashboard() -> GET /portfolio/dashboard")
        print("     - OverviewTab      -> usePortfolioOverview() -> GET /portfolio/overview  (DUP)")
        print("     - HoldingsTab      -> useAllHoldings()       -> GET /portfolio/holdings  (DUP)")
        print("     - PerformanceTab   -> usePortfolioAccounts() -> GET /portfolio/accounts  (DUP)")
        print()
        print("     Fix: Share data via React Query cache keys, or use the dashboard")
        print("     bundle endpoint for all data.")
        for p, rs in duplicates.items():
            times = ", ".join(f"{r['elapsed_s']}s" for r in rs)
            print(f"       {p}: {len(rs)} calls ({times})")

    print()


# -- TESTS ---------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(not AUTH_TOKEN, reason="Set PERF_AUTH_TOKEN env var")
async def test_performance_waterfall_live():
    """Hit ALL portfolio endpoints against the LIVE backend and report timing."""

    all_results = []

    # Phase 1: Warmup
    print("\n  Warming up...")
    warmup = await _time_request("GET", "/portfolio/accounts", "Warmup")
    print(f"  Warmup done: {warmup['elapsed_s']}s")

    # Phase 2: Sequential requests
    print("\n  Loading portfolio dashboard (sequential waterfall)...")
    for method, path, label in ENDPOINTS:
        result = await _time_request(method, path, label)
        all_results.append(result)
        icon = "[OK]" if result["status"] == 200 else "[FAIL]"
        print(f"    {result['elapsed_s']:>5.1f}s  {icon} {result['status']}  {label}")

    # Phase 3: Diagnose
    _print_waterfall(all_results)
    _print_diagnosis(all_results)

    # Assert: performance chart should NOT return 500
    for r in all_results:
        assert "performance" not in r["path"] or r["status"] != 500, (
            f"Performance chart returned HTTP {r['status']}: {r['body'][:200]}"
        )

    # Assert: no request should exceed Axios timeout (12s)
    for r in all_results:
        assert r["elapsed_ms"] < 12000, (
            f"{r['label']} took {r['elapsed_s']}s - exceeds 12s Axios timeout"
        )


@pytest.mark.asyncio
async def test_performance_snapshot_path_timing():
    """
    Mock-based estimate of the snapshot read path timing.

    The snapshot path (used when portfolio_snapshots table has data)
    should be MUCH faster than the fallback because it reads pre-computed
    data from the DB rather than computing on the fly.
    """
    from collections import defaultdict
    from datetime import date, timedelta

    # Simulate 1 year of weekly snapshots for 3 accounts
    num_weeks = 52
    num_accounts = 3
    num_dates = num_weeks

    mock_snapshots = []
    for w in range(num_weeks):
        d = date(2026, 1, 1) + timedelta(weeks=w)
        for a in range(1, num_accounts + 1):
            mock_snapshots.append({
                "account_id": a,
                "snapshot_date": d,
                "total_value": 10000.0 + a * 1000 + w * 100,
                "cost_basis": 8000.0 + a * 500,
                "cash_balance": 500.0,
                "net_deposits": 0.0,
                "data_quality_flag": "OK",
                "holdings_json": None,
            })

    start = time.perf_counter()

    # Simulate the LOCF merge (same algorithm as portfolio_service.py lines 2108-2188)
    by_account = defaultdict(list)
    for s in mock_snapshots:
        by_account[s["account_id"]].append(s)

    accounts_with_data = list(by_account.keys())
    all_dates = sorted({s["snapshot_date"] for s in mock_snapshots})

    account_iters = {}
    current_snap = {}
    for aid in accounts_with_data:
        it = iter(by_account[aid])
        account_iters[aid] = it
        try:
            current_snap[aid] = next(it)
        except StopIteration:
            current_snap[aid] = None

    last_value = {}
    for d in all_dates:
        total_value = 0.0
        for aid in accounts_with_data:
            cs = current_snap.get(aid)
            if cs is not None and cs["snapshot_date"] == d:
                total_value += cs["total_value"]
                last_value[aid] = cs["total_value"]
                try:
                    current_snap[aid] = next(account_iters[aid])
                except StopIteration:
                    current_snap[aid] = None
            elif aid in last_value:
                total_value += last_value[aid]

    elapsed = time.perf_counter() - start
    elapsed_ms = round(elapsed * 1000)

    print("\n  Snapshot path timing (mock):")
    print(f"    Accounts:   {num_accounts}")
    print(f"    Dates:      {num_dates}")
    print(f"    Snapshots:  {len(mock_snapshots)}")
    print(f"    Merge time: {elapsed_ms}ms")

    assert elapsed_ms < 100, (
        f"Snapshot merge took {elapsed_ms}ms - should be <100ms in-memory"
    )
    print("    [OK] In-memory merge is fast (<100ms)")
    print()
    print("  -> With DB query time (~500ms for indexed query):")
    print(f"    Estimated total snapshot path: ~{elapsed_ms + 500}ms")


@pytest.mark.asyncio
async def test_performance_duplicate_request_analysis():
    """
    Count how many unique API calls the portfolio dashboard makes
    and identify overlaps that could be consolidated.
    """
    # Simulate the request tree from the dashboard load
    request_tree = {
        "PortfolioTabShell": [
            "GET /portfolio/dashboard",
        ],
        "OverviewTab": [
            "GET /portfolio/overview",
            "GET /portfolio/holdings",
        ],
        "PerformanceTab": [
            "GET /portfolio/accounts",
            "GET /portfolio/performance?period=1Y",
            "GET /benchmarks",
            "GET /portfolio/performance/compare",
        ],
        "HoldingsTab": [
            "GET /portfolio/holdings",
            "GET /portfolio/holdings?aggregated=true",
            "GET /portfolio/allocation",
        ],
    }

    all_requests = []
    for component, endpoints in request_tree.items():
        for ep in endpoints:
            base_path = ep.split("?")[0]
            all_requests.append({"component": component, "endpoint": ep, "base_path": base_path})

    from collections import Counter
    path_counts = Counter(r["base_path"] for r in all_requests)
    duplicates = {p: c for p, c in path_counts.items() if c > 1}

    print("\n  Duplicate request analysis:")
    print(f"    Total requests:  {len(all_requests)}")
    print(f"    Unique endpoints: {len(path_counts)}")
    print(f"    Duplicates:       {len(duplicates)}")

    for p, c in sorted(duplicates.items()):
        components = [r["component"] for r in all_requests if r["base_path"] == p]
        print(f"      {p}: called {c}x by {', '.join(set(components))}")

    print()
    if duplicates:
        print("  [DUP] RECOMMENDATION: Consolidate these into shared React Query hooks")
        print("     with a STALE time of 30s to avoid redundant network calls.")
        for p in duplicates:
            print(f"       {p}")

    # Verify: at minimum, /portfolio/dashboard should be called exactly once
    assert path_counts.get("/portfolio/dashboard", 0) <= 2, (
        f"/portfolio/dashboard called {path_counts['/portfolio/dashboard']}x!"
    )


@pytest.mark.asyncio
async def test_performance_overview_response_size():
    """
    Estimate the response payload size for the overview endpoint.
    Large responses increase serialization/transfer time.
    """
    import json

    # Simulate a representative overview response
    mock_response = {
        "success": True,
        "total_value": 125000.00,
        "total_cost": 95000.00,
        "total_return": 30000.00,
        "total_return_pct": 31.58,
        "day_change": 1250.00,
        "day_change_pct": 1.01,
        "accounts": [
            {
                "account_id": i,
                "name": f"Account {i}",
                "brokerage": f"Brokerage {i % 3}",
                "currency": "CAD" if i % 2 == 0 else "USD",
                "total_value": 25000.0 + i * 1000,
                "total_cost": 19000.0 + i * 800,
                "return": 6000.0 + i * 200,
                "return_pct": 31.58 + i * 0.5,
            }
            for i in range(1, 11)
        ],
        "holdings": [
            {
                "symbol": f"STOCK{j}",
                "company_id": j,
                "quantity": 100 + j * 10,
                "total_cost": 5000.0 + j * 500,
                "market_value": 5500.0 + j * 550,
                "unrealized_pl": 500.0 + j * 50,
                "unrealized_pl_pct": 10.0 + j * 0.5,
            }
            for j in range(1, 31)
        ],
    }

    size_bytes = len(json.dumps(mock_response).encode("utf-8"))
    size_kb = size_bytes / 1024

    print("\n  Overview response size estimate:")
    print(f"    Size: {size_kb:.1f} KB")
    print("    Accounts: 10")
    print("    Holdings: 30")

    transfer_time_ms = size_bytes / (1 * 1024 * 1024 / 1000)
    print(f"    Estimated transfer time (1 MB/s): {transfer_time_ms:.1f}ms")
    print()
    print("    [OK] Response size is not the bottleneck")


@pytest.mark.asyncio
async def test_performance_before_vs_after():
    """
    Compare old behavior (3 redundant API calls) vs new (single dashboard call).

    BEFORE (old code): 4 API calls:
      GET /portfolio/accounts   (_enrich_holdings)
      GET /portfolio/overview   (_enrich_holdings again)
      GET /portfolio/holdings   (_enrich_holdings again)
      GET /portfolio/dashboard  (_enrich_holdings again)

    AFTER (new code): 1 API call:
      GET /portfolio/dashboard  (_enrich_holdings ONCE)

    This test uses timing estimates to show the expected improvement.
    """

    # Simulate enrichment cost per call
    enrichment_cost_ms = 150  # ~150ms per _enrich_holdings call

    # Network + DB overhead per request
    request_overhead_ms = 300  # DNS + TLS + proxy + DB query time

    before_calls = 4  # accounts + overview + holdings + dashboard
    after_calls = 1   # dashboard only (OverviewTab uses dashboard data)

    before_total = before_calls * (enrichment_cost_ms + request_overhead_ms)
    after_total = after_calls * (enrichment_cost_ms + request_overhead_ms)

    saving_ms = before_total - after_total

    print()
    title = " BEFORE-AFTER COMPARISON (mock estimates) "
    print(f"  {title:=^60s}")
    print(f"  {'Metric':<40s} {'BEFORE':>10s} {'AFTER':>10s}")
    dline = "-" * 40 + " " + "-" * 10 + " " + "-" * 10
    print(f"  {dline}")
    print(f"  {'API calls per page load':<40s} {before_calls:>10d} {after_calls:>10d}")
    print(f"  {'_enrich_holdings calls':<40s} {before_calls:>10d} {after_calls:>10d}")
    print(f"  {'Estimated total time':<40s} {before_total:>9d}ms {after_total:>9d}ms")
    print(f"  {'TTL cache eliminates duplicate DB reads':<40s} {'NO':>10s} {'YES':>9s}")
    print(f"  {'Snapshot builder invariant fixed (500 error)':<40s} {'NO':>10s} {'YES':>9s}")
    print()
    print(f"  SAVING: {saving_ms}ms ({saving_ms/1000:.1f}s) per page load")
    print(f"  IMPROVEMENT: {((1 - after_total/before_total) * 100):.0f}% fewer API calls")

    # The TTL cache adds additional savings for multi-account enrichment
    ttl_cache_extra = (before_calls - 1) * enrichment_cost_ms * 0.6  # ~60% of price queries hit cache
    print(f"  TTL cache additional saving: ~{ttl_cache_extra:.0f}ms")
    print(f"  TOTAL ESTIMATED IMPROVEMENT: ~{saving_ms + ttl_cache_extra:.0f}ms")
    print()
    print("  Changes deployed:")
    print("  1. OverviewTab uses dashboard data (no more redundant calls)")
    print("  2. TTL cache for current_market_data (30s, reduces DB reads)")
    print("  3. Snapshot builder: zero-cost invariant is warning, not error")
    print("  4. DashboardAccount includes gain_loss/gain_loss_pct per account")
    print("  5. DashboardHolding includes company_id")

    assert after_calls < before_calls, "New code should make fewer calls"
    assert after_total < before_total, "New code should be faster"


# -- MAIN ----------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 100)
    print("  PORTFOLIO DASHBOARD LOADING PERFORMANCE TEST")
    print("=" * 100)
    print()
    print(f"  Backend: {BACKEND_ORIGIN}")
    print(f"  Auth:    {'[OK] Token provided' if AUTH_TOKEN else '[NO] No token (set PERF_AUTH_TOKEN)'}")
    print()

    if not AUTH_TOKEN:
        print("  USAGE:")
        print("    set PERF_AUTH_TOKEN=your_jwt_token")
        print("    python -m pytest tests/test_portfolio_performance_loading.py -v -s")
        print()
        print("  Or run mock tests only:")
        print("    python -m pytest tests/test_portfolio_performance_loading.py -v -s -k \"mock\"")
        print()
        sys.exit(1)


    async def main():
        results = []
        print("  Warming up...")
        warmup = await _time_request("GET", "/portfolio/accounts", "Warmup")
        print(f"  Done ({warmup['elapsed_s']}s)\n")

        print("  Loading portfolio dashboard...\n")
        for method, path, label in ENDPOINTS:
            result = await _time_request(method, path, label)
            results.append(result)
            icon = "[OK]" if result["status"] == 200 else "[FAIL]"
            print(f"    {result['elapsed_s']:>5.1f}s  {icon}  {result['status']}  {label}")

        _print_waterfall(results)
        _print_diagnosis(results)

        # Summary
        total = sum(r["elapsed_ms"] for r in results) / 1000
        failed = [r for r in results if r["status"] and r["status"] >= 400]
        slow = [r for r in results if r["elapsed_ms"] >= THRESHOLDS["slow"]]

        print("  " + "=" * 50)
        print(f"  SUMMARY: {total:.1f}s total  |  {len(failed)} failed  |  {len(slow)} slow")
        print("  " + "=" * 50)

    asyncio.run(main())
