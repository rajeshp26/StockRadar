"""Maintenance job: keep the materialised benchmark series fresh.

Why a job and not a request hook
────────────────────────────────
The benchmark store is an append-only read model (migration 015). Its tail
advances once a day, when the portfolio snapshot job lands a new date and the
price ingestion lands the matching close. Refreshing on the first page view of
the day works but makes one user pay for everyone; refreshing in the daily job
that already exists makes the page view a pure slice-read.

The job is a maintenance pass, not a gate: it exercises the SAME reuse helper
the read path uses, so the guard decides what to rebuild and the cost is one
tail day per symbol per account set, not a full re-simulation.

Failure policy
──────────────
A failure here must never fail the daily snapshot job that owns it, and must
never make the store *worse* than empty. Each account set and symbol is
refreshed independently, failures are counted and returned, and the request
path still simulates live for anything the pass could not refresh.

shortcut: one account-set composition per user (all active accounts), no
per-account-subset precompute. Upgrade when a user is observed routinely
comparing a subset of accounts on a cold cache.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from application.services.portfolio_service import PortfolioService
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.portfolio.benchmark_series")

# Benchmarks to precompute. Kept explicit rather than "every benchmark_config
# row" so adding an index to the comparison UI does not silently add a daily
# simulation for every account set.
DEFAULT_BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ")


@dataclass
class RefreshResult:
    account_sets: int = 0
    symbols_ok: int = 0
    failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "account_sets": self.account_sets,
            "symbols_refreshed": self.symbols_ok,
            "failures": self.failures,
        }


async def refresh_benchmark_series(
    symbols: tuple[str, ...] = DEFAULT_BENCHMARK_SYMBOLS,
    as_of: date | None = None,
) -> RefreshResult:
    """Refresh the stored benchmark series for every user's active account set.

    Returns counts, never raises: this runs inside the daily snapshot job and a
    benchmark read-model failure is not a reason to fail snapshot generation.
    """
    result = RefreshResult()
    target_end = as_of or now_utc().date()

    try:
        portfolio_repo = PortfolioRepository()
        service = PortfolioService(portfolio_repo=portfolio_repo)
        users = _active_user_ids(portfolio_repo)
    except Exception as e:
        logger.warning("benchmark_series refresh: cannot enumerate users: %s", e)
        result.failures += 1
        return result

    for user_id in users:
        try:
            accounts = portfolio_repo.get_user_accounts(user_id)
            account_ids = [a["account_id"] for a in accounts]
            if not account_ids:
                continue

            account_key = ",".join(str(a) for a in sorted(account_ids))

            # Inception and seed come from the same service calls the read path
            # uses, so the job and the request agree on what a valid series is.
            snapshots_repo = _snapshots_repo()
            inception_dates = [
                d for d in (snapshots_repo.get_first_snapshot_date(a) for a in account_ids)
                if d is not None
            ]
            if not inception_dates:
                continue
            inception_date = min(inception_dates)

            perf = await service.get_portfolio_performance(user_id, "ALL", account_ids)
            first_nonzero = next(
                (s for s in (perf.get("snapshots") or []) if s["value"] > 0), None
            )
            if first_nonzero is None:
                continue
            initial_value = first_nonzero["value"]
            anchor_dt = date.fromisoformat(first_nonzero["date"])

            cashflows = [
                cf for cf in service._get_cashflow_deltas(account_ids)
                if not (cf["date"] == anchor_dt
                        and abs(cf["amount"] - initial_value) < 1e-6)
            ]

            window_dates = _monthly_grid(inception_date, target_end)
            result.account_sets += 1

            for sym in symbols:
                try:
                    company = await service.financial_repo.get_company_by_symbol(sym)
                    if not company:
                        logger.info("benchmark_series refresh: %s not in companies — skip", sym)
                        continue
                    series = await service._benchmark_series_with_reuse(
                        account_key=account_key,
                        symbol=sym,
                        benchmark_company_id=company["company_id"],
                        inception_date=inception_date,
                        end_date=target_end,
                        initial_value=initial_value,
                        cashflows=cashflows,
                        window_dates=window_dates,
                    )
                    if series:
                        result.symbols_ok += 1
                except Exception as e:
                    logger.warning(
                        "benchmark_series refresh failed for user=%s %s/%s: %s",
                        user_id, account_key, sym, e,
                    )
                    result.failures += 1
        except Exception as e:
            logger.warning("benchmark_series refresh failed for user=%s: %s", user_id, e)
            result.failures += 1

    logger.info(
        "benchmark_series refresh complete: %s",
        result.as_dict(),
    )
    return result


def _snapshots_repo():
    from infrastructure.repositories.portfolio_snapshots_repository import (
        PortfolioSnapshotsRepository,
    )
    return PortfolioSnapshotsRepository()


def _monthly_grid(start: date, end: date) -> list[str]:
    """Coarse grid for the maintenance pass.

    The pass exists to ADVANCE the tail, not to redraw the window: points
    already stored are frozen, and the only date that must be present is the
    new end date. Monthly steps keep the grid bounded over a multi-year span.
    """
    dates: list[str] = []
    d = start
    while d <= end:
        dates.append(d.isoformat())
        d = _add_month(d)
    if not dates or dates[-1] != end.isoformat():
        dates.append(end.isoformat())
    return dates


def _add_month(d: date) -> date:
    month = d.month + 1
    year = d.year + (1 if month > 12 else 0)
    month = 1 if month > 12 else month
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _active_user_ids(portfolio_repo: PortfolioRepository) -> list[int]:
    """Distinct user ids that own at least one account."""
    accounts = portfolio_repo.get_user_accounts_all()
    return sorted({a["user_id"] for a in accounts if a.get("user_id") is not None})


async def handle_benchmark_series_refresh(job: dict[str, Any]) -> dict[str, Any]:
    """Handler registered with JobEngine."""
    payload = job.get("payload") or {}
    as_of_raw = payload.get("date")
    as_of = date.fromisoformat(as_of_raw) if as_of_raw else None
    result = await refresh_benchmark_series(as_of=as_of)
    return {"status": "completed", **result.as_dict()}
