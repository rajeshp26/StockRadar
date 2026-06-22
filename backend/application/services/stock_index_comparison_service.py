"""
Stock vs Index Outperformance Service

Analyzes whether a stock is likely to outperform a benchmark index using:
- Historical price performance (alpha, beta, Sharpe ratio)
- Fundamental growth metrics (revenue, EPS, FCF CAGR)
- Valuation efficiency (PEG ratio)
- Visual chart patterns (relative strength, drawdown, outperformance rate)

Stateless service — no caching in valuation_runs (results change daily with price).
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from shared.time_utils import now_utc
from typing import Any, Dict, List, Optional

import numpy as np

from infrastructure.repositories.analysis_repository import AnalysisRepository
from shared.finance_math import safe_float

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.045  # 4.5% — update periodically or fetch from ^TNX


class StockIndexComparisonService:
    def __init__(self, repo: AnalysisRepository):
        self.repo = repo

    async def evaluate_outperformance(
        self,
        symbol: str,
        benchmark_symbols: Optional[List[str]] = None,
        years: int = 3,
    ) -> Dict[str, Any]:
        """
        Full outperformance evaluation against one or more benchmarks.

        The first benchmark in the list drives quantitative/visual scoring.
        All benchmarks are included in chart data for visual comparison.

        Args:
            symbol: Stock ticker to analyze.
            benchmark_symbols: Benchmark tickers (e.g. ["SPY", "QQQ"]).
                              Defaults to ["SPY"].
            years: Historical years to analyze.

        Returns:
            {
                "symbol": str,
                "primary_index": str,
                "benchmarks": [{symbol, name}],
                "period_years": int,
                "quantitative": {...},
                "visual": {...},
                "combined_score": float,
                "recommendation": str,
                "charts": {...}
            }
        """
        if not benchmark_symbols:
            benchmark_symbols = ["SPY"]

        benchmark_symbols = [s.upper() for s in benchmark_symbols]

        ctx = await self.repo._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found")

        company_id = ctx["company_id"]

        # Resolve all benchmark symbols to configs
        benchmarks = []
        for bsym in benchmark_symbols:
            cfg = await self.repo.get_benchmark_by_symbol(bsym)
            if cfg:
                benchmarks.append(cfg)

        if not benchmarks:
            raise ValueError(
                f"None of the requested benchmark symbols are configured: {benchmark_symbols}"
            )

        primary = benchmarks[0]
        index_company_id = primary["company_id"]
        primary_index_symbol = primary["symbol"]

        end_date = now_utc().date()
        start_date = end_date - timedelta(days=years * 365 + 30)

        # Fetch stock price data
        stock_prices = await self.repo.get_price_history_range(
            company_id, start_date, end_date
        )
        if not stock_prices:
            raise ValueError("Insufficient price history for analysis")

        # Fetch price data for primary benchmark (required for scoring)
        primary_prices = await self.repo.get_price_history_range(
            index_company_id, start_date, end_date
        )
        if not primary_prices:
            raise ValueError("Insufficient benchmark price history for analysis")

        # Fetch price data for all other benchmarks
        all_benchmark_prices: Dict[str, List[Dict]] = {}
        all_benchmark_prices[primary["symbol"]] = primary_prices
        for bm in benchmarks[1:]:
            bm_prices = await self.repo.get_price_history_range(
                bm["company_id"], start_date, end_date
            )
            if bm_prices:
                all_benchmark_prices[bm["symbol"]] = bm_prices

        # Quantitative + visual scoring against PRIMARY benchmark
        quant = await self._quantitative_analysis(
            company_id, stock_prices, primary_prices, years
        )
        visual = self._visual_analysis(stock_prices, primary_prices)

        combined_score = (quant["score"] * 0.6) + (visual["score"] * 0.4)
        recommendation = self._get_recommendation(combined_score)

        # Chart data with all benchmarks
        charts = self._prepare_chart_data(
            stock_prices, all_benchmark_prices, symbol.upper()
        )

        benchmark_list = [
            {"symbol": bm["symbol"], "name": bm.get("name") or bm["symbol"]}
            for bm in benchmarks
        ]

        return {
            "symbol": symbol.upper(),
            "primary_index": primary_index_symbol,
            "benchmarks": benchmark_list,
            "period_years": years,
            "quantitative": quant,
            "visual": visual,
            "combined_score": round(combined_score, 3),
            "recommendation": recommendation,
            "charts": charts,
        }

    async def _quantitative_analysis(
        self,
        company_id: int,
        stock_prices: List[Dict],
        index_prices: List[Dict],
        years: int,
    ) -> Dict[str, Any]:
        stock_closes = [float(p["close_price"]) for p in stock_prices]
        index_closes = [float(p["close_price"]) for p in index_prices]

        stock_returns = self._calculate_returns(stock_closes)
        index_returns = self._calculate_returns(index_closes)

        stock_returns, index_returns = self._align_returns(
            stock_returns, index_returns
        )

        beta = self._calculate_beta(stock_returns, index_returns)

        stock_annual_return = self._annualized_return(stock_prices)
        index_annual_return = self._annualized_return(index_prices)
        expected_return = RISK_FREE_RATE + beta * (
            index_annual_return - RISK_FREE_RATE
        )
        alpha = stock_annual_return - expected_return

        stock_sharpe = self._sharpe_ratio(stock_returns, stock_annual_return)
        index_sharpe = self._sharpe_ratio(index_returns, index_annual_return)

        growth_data = await self.repo.get_revenue_and_eps_growth(company_id, years=3)
        fcf_data = await self.repo._repo.get_fcf_history(company_id, years=4)

        revenue_growth = growth_data.get("revenue_cagr")
        eps_growth = growth_data.get("eps_cagr")
        fcf_growth = self._calculate_fcf_growth(fcf_data)

        index_avg_growth = 0.08
        growth_score = 0
        if revenue_growth and revenue_growth > index_avg_growth * 1.5:
            growth_score += 1
        if eps_growth and eps_growth > index_avg_growth * 1.5:
            growth_score += 1
        if fcf_growth and fcf_growth > index_avg_growth * 1.5:
            growth_score += 1

        summary = await self.repo._repo.get_company_summary_latest(company_id)
        peg_ratio = None
        if summary and summary.get("trailing_pe") and eps_growth and eps_growth > 0:
            pe = float(summary["trailing_pe"])
            peg_ratio = pe / (eps_growth * 100)

        score = (
            (1 if alpha > 0 else 0) * 0.3
            + (1 if stock_sharpe > index_sharpe else 0) * 0.25
            + (1 if 0.8 <= beta <= 1.2 else 0) * 0.15
            + (growth_score / 3) * 0.2
            + (1 if peg_ratio and peg_ratio < 1.5 else 0) * 0.1
        )

        return {
            "beta": round(beta, 3),
            "alpha": round(alpha, 4),
            "stock_sharpe": round(stock_sharpe, 3),
            "index_sharpe": round(index_sharpe, 3),
            "growth_score": growth_score,
            "revenue_cagr": round(revenue_growth, 4) if revenue_growth else None,
            "eps_cagr": round(eps_growth, 4) if eps_growth else None,
            "fcf_cagr": round(fcf_growth, 4) if fcf_growth else None,
            "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
            "score": round(score, 3),
        }

    def _visual_analysis(
        self, stock_prices: List[Dict], index_prices: List[Dict]
    ) -> Dict[str, Any]:
        min_len = min(len(stock_prices), len(index_prices))
        stock_prices = stock_prices[:min_len]
        index_prices = index_prices[:min_len]
        stock_closes = [float(p["close_price"]) for p in stock_prices]
        index_closes = [float(p["close_price"]) for p in index_prices]

        stock_norm = self._normalize_prices(stock_closes)
        index_norm = self._normalize_prices(index_closes)

        rs_values = [s / i * 100 for s, i in zip(stock_norm, index_norm)]
        rs_trend = (rs_values[-1] - rs_values[0]) / rs_values[0]

        months_outperformed = self._count_outperformance_months(
            stock_prices, index_prices
        )
        total_months = min(len(stock_prices), len(index_prices))
        outperform_rate = (
            months_outperformed / total_months if total_months > 0 else 0
        )

        stock_dd = self._max_drawdown(stock_closes)
        index_dd = self._max_drawdown(index_closes)
        dd_ratio = stock_dd / index_dd if index_dd != 0 else 1.0

        score = (
            (1 if outperform_rate > 0.6 else 0) * 0.4
            + (1 if rs_trend > 0.15 else 0) * 0.3
            + (1 if 0.7 < dd_ratio < 1.0 else 0) * 0.3
        )

        return {
            "rs_trend": round(rs_trend, 4),
            "outperform_rate": round(outperform_rate, 3),
            "stock_max_drawdown": round(stock_dd, 4),
            "index_max_drawdown": round(index_dd, 4),
            "dd_ratio": round(dd_ratio, 3),
            "score": round(score, 3),
        }

    def _prepare_chart_data(
        self,
        stock_prices: List[Dict],
        benchmark_prices: Dict[str, List[Dict]],
        stock_symbol: str,
    ) -> Dict[str, Any]:
        dates = [p["price_date"] for p in stock_prices]
        stock_closes = [float(p["close_price"]) for p in stock_prices]
        stock_norm = self._normalize_prices(stock_closes)
        stock_rolling = self._rolling_returns(stock_closes, 12)
        stock_dd = self._drawdown_series(stock_closes)

        normalized_prices: Dict[str, List[float]] = {stock_symbol: stock_norm}
        relative_strength: Dict[str, List[float]] = {}
        rolling_12m_returns: Dict[str, List[Optional[float]]] = {stock_symbol: stock_rolling}
        drawdowns: Dict[str, List[float]] = {stock_symbol: stock_dd}

        for bm_symbol, bm_prices in benchmark_prices.items():
            min_len = min(len(stock_closes), len(bm_prices))
            bm_closes = [float(p["close_price"]) for p in bm_prices[:min_len]]
            bm_norm = self._normalize_prices(bm_closes)

            normalized_prices[bm_symbol] = bm_norm

            rs_line = [
                s / i * 100
                for s, i in zip(stock_norm[:min_len], bm_norm)
            ]
            relative_strength[bm_symbol] = rs_line

            rolling_12m_returns[bm_symbol] = self._rolling_returns(bm_closes, 12)
            drawdowns[bm_symbol] = self._drawdown_series(bm_closes)

        return {
            "dates": dates,
            "normalized_prices": normalized_prices,
            "relative_strength": relative_strength,
            "rolling_12m_returns": rolling_12m_returns,
            "drawdowns": drawdowns,
        }

    def _calculate_returns(self, prices: List[float]) -> List[float]:
        return [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
        ]

    def _align_returns(
        self, stock_returns: List[float], index_returns: List[float]
    ) -> tuple:
        min_len = min(len(stock_returns), len(index_returns))
        return stock_returns[:min_len], index_returns[:min_len]

    def _calculate_beta(
        self, stock_returns: List[float], index_returns: List[float]
    ) -> float:
        if len(stock_returns) < 2 or len(index_returns) < 2:
            return 1.0

        stock_arr = np.array(stock_returns)
        index_arr = np.array(index_returns)

        covariance = np.cov(stock_arr, index_arr)[0, 1]
        variance = np.var(index_arr)

        return covariance / variance if variance != 0 else 1.0

    def _annualized_return(self, prices: List[Dict]) -> float:
        if len(prices) < 2:
            return 0.0

        start_price = float(prices[0]["close_price"])
        end_price = float(prices[-1]["close_price"])

        start_date = date.fromisoformat(prices[0]["price_date"])
        end_date = date.fromisoformat(prices[-1]["price_date"])
        years = (end_date - start_date).days / 365.25

        if start_price <= 0 or years <= 0:
            return 0.0

        return (end_price / start_price) ** (1 / years) - 1

    def _sharpe_ratio(self, returns: List[float], annual_return: float) -> float:
        if not returns:
            return 0.0

        std_dev = np.std(returns) * math.sqrt(252)
        if std_dev == 0:
            return 0.0

        return (annual_return - RISK_FREE_RATE) / std_dev

    def _calculate_fcf_growth(self, fcf_data: List[Dict]) -> Optional[float]:
        if len(fcf_data) < 2:
            return None

        fcf_data = sorted(fcf_data, key=lambda x: x.get("fiscal_year", 0))
        fcf_start = safe_float(fcf_data[0].get("fcf"))
        fcf_end = safe_float(fcf_data[-1].get("fcf"))

        if not fcf_start or not fcf_end or fcf_start <= 0:
            return None

        years = fcf_data[-1]["fiscal_year"] - fcf_data[0]["fiscal_year"]
        if years <= 0:
            return None

        return (fcf_end / fcf_start) ** (1 / years) - 1

    def _normalize_prices(self, prices: List[float]) -> List[float]:
        if not prices or prices[0] == 0:
            return prices
        return [p / prices[0] * 100 for p in prices]

    def _count_outperformance_months(
        self, stock_prices: List[Dict], index_prices: List[Dict]
    ) -> int:
        stock_closes = [float(p["close_price"]) for p in stock_prices]
        index_closes = [float(p["close_price"]) for p in index_prices]

        if len(stock_closes) < 12 or len(index_closes) < 12:
            return 0

        count = 0
        for i in range(12, len(stock_closes)):
            stock_ret = (stock_closes[i] - stock_closes[i - 12]) / stock_closes[i - 12]
            index_ret = (index_closes[i] - index_closes[i - 12]) / index_closes[i - 12]
            if stock_ret > index_ret:
                count += 1

        return count

    def _max_drawdown(self, prices: List[float]) -> float:
        if not prices:
            return 0.0

        peak = prices[0]
        max_dd = 0.0

        for price in prices:
            if price > peak:
                peak = price
            dd = (price - peak) / peak
            if dd < max_dd:
                max_dd = dd

        return abs(max_dd)

    def _rolling_returns(
        self, prices: List[float], window: int
    ) -> List[Optional[float]]:
        if len(prices) < window:
            return [None] * len(prices)

        returns = [None] * (window - 1)
        for i in range(window, len(prices) + 1):
            ret = (prices[i - 1] - prices[i - window]) / prices[i - window]
            returns.append(ret)

        return returns

    def _drawdown_series(self, prices: List[float]) -> List[float]:
        peak = prices[0]
        drawdowns = []

        for price in prices:
            if price > peak:
                peak = price
            dd = ((price - peak) / peak) * 100
            drawdowns.append(dd)

        return drawdowns

    async def list_benchmarks(self) -> List[Dict[str, Any]]:
        """Returns all active benchmarks. Delegates to repository (shared source of truth)."""
        return await self.repo.list_active_benchmarks()

    def _get_recommendation(self, score: float) -> str:
        if score >= 0.80:
            return "Strong Outperformance Signal"
        elif score >= 0.65:
            return "Likely Outperforms"
        elif score >= 0.50:
            return "Neutral / Mixed Signals"
        else:
            return "Unlikely to Outperform"