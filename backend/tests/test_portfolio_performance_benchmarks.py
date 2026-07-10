"""
Portfolio Performance Benchmarks

Measures execution time of critical portfolio service functions
to detect regressions and validate optimizations.

Usage:
    python -m pytest tests/test_portfolio_performance_benchmarks.py -v -s
    python -m pytest tests/test_portfolio_performance_benchmarks.py -v -s -k "twr"
"""

import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

import numpy as np
import pytest

from shared.portfolio_stats import (
    annualize_return,
    compute_annualized_volatility,
    compute_beta,
    compute_conditional_var,
    compute_correlation_matrix,
    compute_daily_returns,
    compute_drawdown_series,
    compute_historical_var,
    compute_max_drawdown,
    compute_portfolio_mwr,
    compute_portfolio_twr,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_value_at_risk,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade(elapsed_ms: float, thresholds: Dict[str, float]) -> str:
    if elapsed_ms < thresholds.get("fast", 5):
        return "PASS"
    if elapsed_ms < thresholds.get("ok", 50):
        return "OK"
    if elapsed_ms < thresholds.get("slow", 200):
        return "SLOW"
    return "CRITICAL"


def _print_result(
    label: str, elapsed_ms: float, detail: str = "",
    thresholds: Dict[str, float] = None,
):
    if thresholds is None:
        thresholds = {"fast": 5, "ok": 50, "slow": 200}
    grade = _grade(elapsed_ms, thresholds)
    detail_str = f"  |  {detail}" if detail else ""
    print(f"  {grade:<8s} {elapsed_ms:>8.3f}ms  {label}{detail_str}")


def _make_snapshots(
    count: int,
    start_value: float = 100000.0,
    with_deposits: bool = True,
    noise_std: float = 0.02,
) -> List[Dict[str, Any]]:
    snapshots: List[Dict[str, Any]] = []
    value = start_value
    cum_deposits = 0.0
    for i in range(count):
        d = date(2024, 1, 1) + timedelta(days=i * 7)
        if i > 0:
            deposit = np.random.normal(0, 500) if with_deposits else 0.0
            cum_deposits += max(deposit, -value * 0.1)
        snapshots.append({
            "date": d,
            "value": value + cum_deposits,
            "net_deposits": cum_deposits,
        })
        if i < count - 1:
            ret = np.random.normal(0.002, noise_std)
            value = value * (1 + ret)
    return snapshots


def _make_price_data(
    num_companies: int,
    num_days: int,
    with_unit_mismatch: bool = False,
) -> Dict[int, List]:
    price_map: Dict[int, List] = {}
    base_price = 100.0
    for cid in range(1, num_companies + 1):
        prices: List[tuple] = []
        price = base_price * (1 + cid * 0.1)
        for i in range(num_days):
            d = date(2024, 1, 1) + timedelta(days=i)
            if with_unit_mismatch and i < num_days // 2:
                p = price * 0.05
            else:
                p = price
            price *= 1 + np.random.normal(0.0005, 0.02)
            prices.append((d, p))
        price_map[cid] = prices
    return price_map


def _benchmark(fn, *args, **kwargs) -> float:
    start = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - start) * 1000


def _benchmark_async(fn, *args, **kwargs) -> float:
    import asyncio
    start = time.perf_counter()
    asyncio.run(fn(*args, **kwargs))
    return (time.perf_counter() - start) * 1000


# ── 1. TWR / MWR Calculation Performance ─────────────────────────────────────

class TestTWRCaclulationPerformance:
    """Time-Weighted Return computation for increasing snapshot counts."""

    SIZES = [10, 52, 252, 504, 1000]

    @pytest.mark.anyio
    async def test_twr_small(self):
        snaps = _make_snapshots(10)
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result(f"TWR small (10 snapshots)", elapsed, f"result={compute_portfolio_twr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_twr_medium(self):
        snaps = _make_snapshots(52)
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result(f"TWR medium (52 snapshots)", elapsed, f"result={compute_portfolio_twr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_twr_large(self):
        snaps = _make_snapshots(252)
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result(f"TWR large (252 snapshots)", elapsed, f"result={compute_portfolio_twr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_twr_very_large(self):
        snaps = _make_snapshots(504)
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result(f"TWR very large (504 snapshots)", elapsed, f"result={compute_portfolio_twr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_twr_max(self):
        snaps = _make_snapshots(1000)
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result(f"TWR max (1000 snapshots)", elapsed, f"result={compute_portfolio_twr(snaps):.4f}")


class TestMWRCalculationPerformance:
    """Money-Weighted Return computation for increasing snapshot counts."""

    @pytest.mark.anyio
    async def test_mwr_small(self):
        snaps = _make_snapshots(10, with_deposits=True)
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result(f"MWR small (10 snapshots)", elapsed, f"result={compute_portfolio_mwr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_mwr_medium(self):
        snaps = _make_snapshots(52, with_deposits=True)
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result(f"MWR medium (52 snapshots)", elapsed, f"result={compute_portfolio_mwr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_mwr_large(self):
        snaps = _make_snapshots(252, with_deposits=True)
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result(f"MWR large (252 snapshots)", elapsed, f"result={compute_portfolio_mwr(snaps):.4f}")

    @pytest.mark.anyio
    async def test_mwr_very_large(self):
        snaps = _make_snapshots(504, with_deposits=True)
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result(f"MWR very large (504 snapshots)", elapsed, f"result={compute_portfolio_mwr(snaps):.4f}")


class TestAnnualizedReturnPerformance:
    """Annualize return (CAGR) computation edge cases."""

    @pytest.mark.anyio
    async def test_annualize_1y(self):
        elapsed = _benchmark(annualize_return, 0.15, 365)
        _print_result("CAGR 1 year (15% return)", elapsed)

    @pytest.mark.anyio
    async def test_annualize_5y(self):
        elapsed = _benchmark(annualize_return, 0.75, 1825)
        _print_result("CAGR 5 years (75% return)", elapsed)

    @pytest.mark.anyio
    async def test_annualize_10y(self):
        elapsed = _benchmark(annualize_return, 2.50, 3650)
        _print_result("CAGR 10 years (250% return)", elapsed)

    @pytest.mark.anyio
    async def test_annualize_negative(self):
        elapsed = _benchmark(annualize_return, -0.30, 365)
        _print_result("CAGR negative (-30% return)", elapsed)

    @pytest.mark.anyio
    async def test_annualize_edge(self):
        elapsed = _benchmark(annualize_return, -1.0, 365)
        _print_result("CAGR edge (-100% return)", elapsed)


# ── 2. Risk Metric Computation Performance ────────────────────────────────────

class TestRiskMetricsPerformance:
    """Compute all risk metrics at various scales."""

    SIZES = [63, 252, 504, 756, 1008]

    @staticmethod
    def _make_returns(n: int, seed: int = 42) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.normal(0.0008, 0.015, size=n)

    @pytest.mark.anyio
    async def test_daily_returns(self):
        vals = np.cumprod(1 + self._make_returns(253)) * 100000
        elapsed = _benchmark(compute_daily_returns, vals)
        _print_result("Daily returns (252 values)", elapsed)

    @pytest.mark.anyio
    async def test_max_drawdown(self):
        vals = np.cumprod(1 + self._make_returns(253)) * 100000
        elapsed = _benchmark(compute_max_drawdown, vals)
        _print_result("Max drawdown (252 values)", elapsed)

    @pytest.mark.anyio
    async def test_drawdown_series(self):
        vals = np.cumprod(1 + self._make_returns(253)) * 100000
        elapsed = _benchmark(compute_drawdown_series, vals)
        _print_result("Drawdown series (252 values)", elapsed)

    @pytest.mark.anyio
    async def test_annualized_volatility(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_annualized_volatility, rets)
        _print_result("Annualized volatility (252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_sharpe_ratio(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_sharpe_ratio, rets)
        _print_result("Sharpe ratio (252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_sortino_ratio(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_sortino_ratio, rets)
        _print_result("Sortino ratio (252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_value_at_risk(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_value_at_risk, rets)
        _print_result("VaR (95%, 252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_historical_var(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_historical_var, rets)
        _print_result("Historical VaR (95%, 252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_conditional_var(self):
        rets = self._make_returns(252)
        elapsed = _benchmark(compute_conditional_var, rets)
        _print_result("CVaR (95%, 252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_beta(self):
        port_rets = self._make_returns(252, seed=1)
        bench_rets = self._make_returns(252, seed=2)
        elapsed = _benchmark(compute_beta, port_rets, bench_rets)
        _print_result("Beta (252 returns)", elapsed)

    @pytest.mark.anyio
    async def test_correlation_matrix(self):
        rng = np.random.default_rng(99)
        matrix = rng.normal(0.0008, 0.02, size=(10, 252))
        elapsed = _benchmark(compute_correlation_matrix, matrix)
        _print_result("Correlation matrix (10 assets, 252 periods)", elapsed)

    @pytest.mark.anyio
    async def test_risk_all_metrics_252(self):
        """Run ALL risk metrics for 252 days (typical 1Y)."""
        vals = np.cumprod(1 + self._make_returns(253)) * 100000
        rets = self._make_returns(252)
        bench = self._make_returns(252, seed=5)

        start = time.perf_counter()
        compute_daily_returns(vals)
        compute_max_drawdown(vals)
        compute_drawdown_series(vals)
        compute_annualized_volatility(rets)
        compute_sharpe_ratio(rets)
        compute_sortino_ratio(rets)
        compute_value_at_risk(rets)
        compute_historical_var(rets)
        compute_conditional_var(rets)
        compute_beta(rets, bench)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "All 10 risk metrics (252 days)",
            elapsed,
            thresholds={"fast": 20, "ok": 100, "slow": 300},
        )

    @pytest.mark.anyio
    async def test_risk_all_metrics_1008(self):
        """Run ALL risk metrics for 1008 days (typical 4Y)."""
        vals = np.cumprod(1 + self._make_returns(1009)) * 100000
        rets = self._make_returns(1008)
        bench = self._make_returns(1008, seed=5)

        start = time.perf_counter()
        compute_daily_returns(vals)
        compute_max_drawdown(vals)
        compute_drawdown_series(vals)
        compute_annualized_volatility(rets)
        compute_sharpe_ratio(rets)
        compute_sortino_ratio(rets)
        compute_value_at_risk(rets)
        compute_historical_var(rets)
        compute_conditional_var(rets)
        compute_beta(rets, bench)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "All 10 risk metrics (1008 days)",
            elapsed,
            thresholds={"fast": 20, "ok": 100, "slow": 300},
        )


# ── 3. Snapshot Merge (LOCF) Performance ─────────────────────────────────────

class TestSnapshotMergePerformance:
    """Last-Observation-Carried-Forward merge used in portfolio_service.py."""

    @staticmethod
    def _run_locf_merge(snapshots: List[Dict], num_accounts: int):
        by_account = defaultdict(list)
        for s in snapshots:
            by_account[s["account_id"]].append(s)

        accounts_with_data = list(by_account.keys())
        all_dates = sorted({s["snapshot_date"] for s in snapshots})
        account_iters = {}
        current_snap = {}
        for aid in accounts_with_data:
            it = iter(by_account[aid])
            account_iters[aid] = it
            try:
                current_snap[aid] = next(it)
            except StopIteration:
                current_snap[aid] = None

        merged = []
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
            merged.append({"date": d, "value": total_value})
        return merged

    @pytest.mark.anyio
    async def test_locf_3_accounts_52_weeks(self):
        snapshots = []
        for w in range(52):
            d = date(2025, 1, 1) + timedelta(weeks=w)
            for a in range(1, 4):
                snapshots.append({
                    "account_id": a,
                    "snapshot_date": d,
                    "total_value": 10000.0 + a * 1000 + w * 100,
                    "cost_basis": 8000.0,
                    "cash_balance": 500.0,
                    "net_deposits": 0.0,
                    "data_quality_flag": "OK",
                })
        elapsed = _benchmark(self._run_locf_merge, snapshots, 3)
        _print_result(
            "LOCF merge 3A x 52W (156 snapshots)",
            elapsed,
            thresholds={"fast": 2, "ok": 10, "slow": 50},
        )

    @pytest.mark.anyio
    async def test_locf_5_accounts_252_weeks(self):
        snapshots = []
        for w in range(252):
            d = date(2024, 1, 1) + timedelta(weeks=w)
            for a in range(1, 6):
                snapshots.append({
                    "account_id": a,
                    "snapshot_date": d,
                    "total_value": 10000.0 + a * 2000 + w * 50,
                    "cost_basis": 8000.0,
                    "cash_balance": 500.0,
                    "net_deposits": 0.0,
                    "data_quality_flag": "OK",
                })
        elapsed = _benchmark(self._run_locf_merge, snapshots, 5)
        _print_result(
            "LOCF merge 5A x 252W (1260 snapshots)",
            elapsed,
            thresholds={"fast": 5, "ok": 20, "slow": 100},
        )

    @pytest.mark.anyio
    async def test_locf_10_accounts_504_weeks(self):
        snapshots = []
        for w in range(504):
            d = date(2023, 1, 1) + timedelta(weeks=w)
            for a in range(1, 11):
                snapshots.append({
                    "account_id": a,
                    "snapshot_date": d,
                    "total_value": 10000.0 + a * 1000 + w * 25,
                    "cost_basis": 8000.0,
                    "cash_balance": 500.0,
                    "net_deposits": 0.0,
                    "data_quality_flag": "OK",
                })
        elapsed = _benchmark(self._run_locf_merge, snapshots, 10)
        _print_result(
            "LOCF merge 10A x 504W (5040 snapshots)",
            elapsed,
            thresholds={"fast": 10, "ok": 50, "slow": 200},
        )


# ── 4. Price Normalization Performance ────────────────────────────────────────

class TestPriceNormalizationPerformance:
    """Benchmark the price unit mismatch detection/normalization."""

    @staticmethod
    def _run_normalization(price_map: Dict[int, List], max_ratio: float = 5.0, min_days: int = 60):
        for cid, prices in price_map.items():
            if len(prices) < 2:
                continue
            prices.sort(key=lambda x: x[0])
            fix_up_to = 0
            for i in range(len(prices) - 1, 0, -1):
                newer = prices[i]
                older = prices[i - 1]
                days = (newer[0] - older[0]).days
                if days > min_days:
                    break
                if older[1] > 0 and newer[1] / older[1] > max_ratio:
                    fix_up_to = i
            if fix_up_to > 0:
                anchor = prices[fix_up_to]
                scale = anchor[1] / prices[fix_up_to - 1][1] if prices[fix_up_to - 1][1] > 0 else 1.0
                fixed = []
                for j, (pd_, pr_) in enumerate(prices):
                    if j < fix_up_to:
                        fixed.append((pd_, pr_ * scale))
                    else:
                        fixed.append((pd_, pr_))
                price_map[cid] = fixed

    @pytest.mark.anyio
    async def test_normalization_no_anomaly_1_company(self):
        data = _make_price_data(1, 252, with_unit_mismatch=False)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 1 co, no anomaly, 252 days", elapsed, thresholds={"fast": 1, "ok": 5, "slow": 20})

    @pytest.mark.anyio
    async def test_normalization_with_anomaly_1_company(self):
        data = _make_price_data(1, 252, with_unit_mismatch=True)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 1 co, WITH anomaly, 252 days", elapsed, thresholds={"fast": 1, "ok": 5, "slow": 20})

    @pytest.mark.anyio
    async def test_normalization_20_companies_no_anomaly(self):
        data = _make_price_data(20, 504, with_unit_mismatch=False)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 20 co, no anomaly, 504 days", elapsed, thresholds={"fast": 5, "ok": 20, "slow": 50})

    @pytest.mark.anyio
    async def test_normalization_20_companies_with_anomaly(self):
        data = _make_price_data(20, 504, with_unit_mismatch=True)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 20 co, WITH anomaly, 504 days", elapsed, thresholds={"fast": 5, "ok": 20, "slow": 50})

    @pytest.mark.anyio
    async def test_normalization_50_companies_no_anomaly(self):
        data = _make_price_data(50, 1008, with_unit_mismatch=False)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 50 co, no anomaly, 1008 days", elapsed, thresholds={"fast": 10, "ok": 50, "slow": 100})

    @pytest.mark.anyio
    async def test_normalization_50_companies_with_anomaly(self):
        data = _make_price_data(50, 1008, with_unit_mismatch=True)
        elapsed = _benchmark(self._run_normalization, data)
        _print_result("Normalization 50 co, WITH anomaly, 1008 days", elapsed, thresholds={"fast": 10, "ok": 50, "slow": 100})


# ── 5. Batch vs Individual Query Performance ──────────────────────────────────

class TestBatchVsIndividualPerformance:
    """Measure overhead of batch helpers used in portfolio_repository.py."""

    @pytest.mark.anyio
    async def test_batch_execute_overhead_small(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        repo = PortfolioRepository()

        calls_batch = []
        calls_single = []

        def batch_fn(chunk):
            calls_batch.append(list(chunk))
            return [{"account_id": aid} for aid in chunk]

        def single_fn(aid):
            calls_single.append(aid)
            return [{"account_id": aid}]

        account_ids = list(range(1, 11))
        elapsed = _benchmark(
            repo.get_accounts_dividends_by_year,
            account_ids, 2025,
        )
        # Actually call the right method...
        from infrastructure.repositories.portfolio_repository import _batch_execute
        elapsed = _benchmark(_batch_execute, account_ids, batch_fn, single_fn, 500)
        _print_result(
            "batch_execute 10 ids, 1 chunk",
            elapsed,
            thresholds={"fast": 0.1, "ok": 0.5, "slow": 2},
        )

    @pytest.mark.anyio
    async def test_batch_execute_overhead_100(self):
        from infrastructure.repositories.portfolio_repository import _batch_execute

        def batch_fn(chunk):
            return [{"account_id": aid} for aid in chunk]

        def single_fn(aid):
            return [{"account_id": aid}]

        account_ids = list(range(1, 101))
        elapsed = _benchmark(_batch_execute, account_ids, batch_fn, single_fn, 500)
        _print_result(
            "batch_execute 100 ids, 1 chunk",
            elapsed,
            thresholds={"fast": 0.1, "ok": 0.5, "slow": 2},
        )

    @pytest.mark.anyio
    async def test_batch_execute_overhead_5000(self):
        from infrastructure.repositories.portfolio_repository import _batch_execute

        def batch_fn(chunk):
            return [{"account_id": aid} for aid in chunk]

        def single_fn(aid):
            return [{"account_id": aid}]

        account_ids = list(range(1, 5001))
        elapsed = _benchmark(_batch_execute, account_ids, batch_fn, single_fn, 500)
        _print_result(
            "batch_execute 5000 ids, 10 chunks",
            elapsed,
            thresholds={"fast": 1, "ok": 5, "slow": 20},
        )

    @pytest.mark.anyio
    async def test_batch_execute_with_fallback(self):
        from infrastructure.repositories.portfolio_repository import _batch_execute

        call_count = {"batch": 0, "single": 0}

        def batch_fn(chunk):
            call_count["batch"] += 1
            raise Exception("Simulated batch failure")

        def single_fn(aid):
            call_count["single"] += 1
            return [{"account_id": aid}]

        account_ids = list(range(1, 11))
        start = time.perf_counter()
        result = _batch_execute(account_ids, batch_fn, single_fn, 500)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "batch_execute 10 ids WITH fallback",
            elapsed,
            f"batch_calls={call_count['batch']} single_calls={call_count['single']} results={len(result)}",
            thresholds={"fast": 1, "ok": 5, "slow": 20},
        )


# ── 6. Combined TWR + MWR + CAGR Full Pipeline ───────────────────────────────

class TestFullReturnPipelinePerformance:
    """End-to-end return computation as done in the API response."""

    @pytest.mark.anyio
    async def test_full_pipeline_1y(self):
        snaps = _make_snapshots(52, with_deposits=True)
        start = time.perf_counter()
        twr = compute_portfolio_twr(snaps)
        mwr = compute_portfolio_mwr(snaps)
        cagr = annualize_return(twr, 365)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "Full pipeline TWR+MWR+CAGR (52 snapshots, 1Y)",
            elapsed,
            f"twr={twr:.4f} mwr={mwr:.4f} cagr={cagr:.4f}",
            thresholds={"fast": 2, "ok": 10, "slow": 50},
        )

    @pytest.mark.anyio
    async def test_full_pipeline_3y(self):
        snaps = _make_snapshots(156, with_deposits=True)
        start = time.perf_counter()
        twr = compute_portfolio_twr(snaps)
        mwr = compute_portfolio_mwr(snaps)
        cagr = annualize_return(twr, 1095)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "Full pipeline TWR+MWR+CAGR (156 snapshots, 3Y)",
            elapsed,
            f"twr={twr:.4f} mwr={mwr:.4f} cagr={cagr:.4f}",
            thresholds={"fast": 5, "ok": 20, "slow": 100},
        )

    @pytest.mark.anyio
    async def test_full_pipeline_5y(self):
        snaps = _make_snapshots(260, with_deposits=True)
        start = time.perf_counter()
        twr = compute_portfolio_twr(snaps)
        mwr = compute_portfolio_mwr(snaps)
        cagr = annualize_return(twr, 1825)
        elapsed = (time.perf_counter() - start) * 1000
        _print_result(
            "Full pipeline TWR+MWR+CAGR (260 snapshots, 5Y)",
            elapsed,
            f"twr={twr:.4f} mwr={mwr:.4f} cagr={cagr:.4f}",
            thresholds={"fast": 5, "ok": 20, "slow": 100},
        )


# ── 7. Price History Data Structure Overhead ──────────────────────────────────

class TestPriceDataStructurePerformance:
    """Benchmark the Dict[int, List[tuple]] data structure used by FIFO engine."""

    @pytest.mark.anyio
    async def test_dict_insert_10x252(self):
        elapsed = _benchmark(_make_price_data, 10, 252)
        _print_result("Build price dict 10 co x 252 days", elapsed, thresholds={"fast": 2, "ok": 10, "slow": 50})

    @pytest.mark.anyio
    async def test_dict_insert_50x1008(self):
        elapsed = _benchmark(_make_price_data, 50, 1008)
        _print_result("Build price dict 50 co x 1008 days", elapsed, thresholds={"fast": 5, "ok": 20, "slow": 100})

    @pytest.mark.anyio
    async def test_dict_lookup_all(self):
        data = _make_price_data(20, 504)
        elapsed = _benchmark(
            lambda d: {cid: prices for cid, prices in d.items()},
            data,
        )
        _print_result("Iterate all 20 companies' prices", elapsed, thresholds={"fast": 1, "ok": 5, "slow": 10})

    @pytest.mark.anyio
    async def test_dict_sort_prices(self):
        data = _make_price_data(20, 504)
        elapsed = _benchmark(
            lambda d: {cid: sorted(prices, key=lambda x: x[0]) for cid, prices in d.items()},
            data,
        )
        _print_result("Sort all 20 companies' prices by date", elapsed, thresholds={"fast": 2, "ok": 10, "slow": 20})


# ── 8. Edge Cases and Stress Tests ────────────────────────────────────────────

class TestEdgeCasePerformance:
    """Performance for pathological inputs."""

    @pytest.mark.anyio
    async def test_twr_single_snapshot(self):
        snaps = [{"date": date(2025, 1, 1), "value": 100000, "net_deposits": 0}]
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result("TWR single snapshot (edge case)", elapsed)

    @pytest.mark.anyio
    async def test_twr_all_zero_values(self):
        snaps = [{"date": date(2025, 1, 1) + timedelta(days=i * 7), "value": 0, "net_deposits": 0} for i in range(52)]
        elapsed = _benchmark(compute_portfolio_twr, snaps)
        _print_result("TWR all zero values (edge case)", elapsed)

    @pytest.mark.anyio
    async def test_mwr_single_snapshot(self):
        snaps = [{"date": date(2025, 1, 1), "value": 100000, "net_deposits": 0}]
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result("MWR single snapshot (edge case)", elapsed)

    @pytest.mark.anyio
    async def test_mwr_all_zero_values(self):
        snaps = [{"date": date(2025, 1, 1) + timedelta(days=i * 7), "value": 0, "net_deposits": 0} for i in range(52)]
        elapsed = _benchmark(compute_portfolio_mwr, snaps)
        _print_result("MWR all zero values (edge case)", elapsed)

    @pytest.mark.anyio
    async def test_normalization_empty(self):
        elapsed = _benchmark(
            TestPriceNormalizationPerformance._run_normalization, {}
        )
        _print_result("Normalization empty dict", elapsed, thresholds={"fast": 0.1, "ok": 1, "slow": 5})

    @pytest.mark.anyio
    async def test_normalization_single_price(self):
        data = {1: [(date(2025, 1, 1), 100.0)]}
        elapsed = _benchmark(
            TestPriceNormalizationPerformance._run_normalization, data,
        )
        _print_result("Normalization single price entry", elapsed, thresholds={"fast": 0.1, "ok": 1, "slow": 5})
