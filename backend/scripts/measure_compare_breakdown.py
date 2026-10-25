"""Diagnostic: time the pieces of /portfolio/performance/compare on live data.

Read-only (the materialised stores are already warm). Prints milliseconds per
stage so a timeframe-switch budget can be reasoned about from measurements
rather than guesses.

Run: backend/venv/Scripts/python.exe backend/scripts/measure_compare_breakdown.py
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

from application.services.portfolio_service import PortfolioService  # noqa: E402


def _ms(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, (time.perf_counter() - t0) * 1000.0


async def _ams(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = await fn(*args, **kwargs)
    return out, (time.perf_counter() - t0) * 1000.0


async def main() -> int:
    svc = PortfolioService()
    user_id = 1
    accounts = svc.portfolio_repo.get_user_accounts(user_id)
    account_ids = [a["account_id"] for a in accounts]
    print(f"user={user_id} accounts={account_ids}")

    company = await svc.financial_repo.get_company_by_symbol("SPY")
    company_id = company["company_id"] if company else None

    for period in ("1Y", "YTD", "ALL"):
        print(f"\n=== {period} ===")
        # Warm the caches for this period, then measure three repeats.
        await svc.get_portfolio_performance(user_id, period, account_ids)
        await svc.get_performance_compare(user_id, period, ["SPY", "QQQ"], account_ids)

        perf_t, all_t, cmp_t = [], [], []
        for _ in range(3):
            _, t = await _ams(svc.get_portfolio_performance, user_id, period, account_ids)
            perf_t.append(t)
            _, t = await _ams(svc.get_portfolio_performance, user_id, "ALL", account_ids)
            all_t.append(t)
            res, t = await _ams(
                svc.get_performance_compare, user_id, period, ["SPY", "QQQ"], account_ids
            )
            cmp_t.append(t)
        print(f"  performance({period})      median {statistics.median(perf_t):7.1f} ms")
        print(f"  performance(ALL)          median {statistics.median(all_t):7.1f} ms")
        print(f"  compare({period})          median {statistics.median(cmp_t):7.1f} ms")
        print(
            f"  compare spends            ~{statistics.median(cmp_t) - statistics.median(all_t) - statistics.median(perf_t):7.1f} ms "
            f"outside the two performance reads"
        )
        spy = next((b for b in res.get("benchmarks", []) if b["symbol"] == "SPY"), None)
        print(f"  payload: portfolio={len(res.get('portfolio', []))} spy={len(spy['data']) if spy else 0}")

    if company_id:
        print("\n=== benchmark price read (inception -> end) ===")
        for _ in range(3):
            rows, t = _ms(
                svc._fetch_benchmark_price_rows,
                benchmark_company_id=company_id,
                inception_date=__import__("datetime").date(2021, 1, 7),
                end_date=__import__("datetime").date(2026, 10, 23),
            )
            print(f"  price rows={len(rows):>5}  {t:7.1f} ms")

    print("\n=== accounts read ===")
    for _ in range(3):
        _, t = _ms(svc.portfolio_repo.get_user_accounts, user_id)
        print(f"  get_user_accounts {t:7.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
