from __future__ import annotations

import logging
from datetime import timedelta
from shared.time_utils import now_utc, now_iso, parse_db_timestamp
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from application.services.portfolio_service import PortfolioService
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.portfolio_stats import (
    TRADING_DAYS,
    compute_alpha,
    compute_annualized_return,
    compute_annualized_volatility,
    compute_beta,
    compute_conditional_var,
    compute_daily_returns,
    compute_drawdown_series,
    compute_downside_deviation,
    compute_information_ratio,
    compute_max_drawdown,
    compute_rolling_sharpe as _rolling_sharpe,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_tracking_error,
    compute_value_at_risk,
    _safe_metric,
)
from shared.price_data_provider import PriceDataProvider
from schemas_portfolio import (
    CovarianceResponse,
    DrawdownResponse,
    EfficientFrontierResponse,
    FactorExposureResponse,
    RiskContributionItem,
    RiskContributionResponse,
    RiskMetricsResponse,
    RollingSharpeResponse,
)

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.02

_PERIOD_MAP: Dict[str, int] = {
    "1M": 30, "3M": 90, "6M": 180, "1Y": 365,
    "2Y": 730, "3Y": 1095, "5Y": 1825, "MAX": 9999,
}


def _parse_period(period: str) -> int:
    return _PERIOD_MAP.get(period.upper(), 365)


def _safe_date_add_years(d: date, years: int) -> date:
    """Add years safely, handling Feb 29 gracefully."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=d.day - 1)


def _error_dict(error: str, error_code: str, **extra: Any) -> Dict[str, Any]:
    return {"success": False, "error": error, "error_code": error_code, **extra}


class PortfolioRiskService:
    def __init__(
        self,
        portfolio_repo: Optional[PortfolioRepository] = None,
        portfolio_service: Optional[PortfolioService] = None,
        price_provider: Optional[PriceDataProvider] = None,
    ):
        self.portfolio_repo = portfolio_repo or PortfolioRepository()
        self.portfolio_service = portfolio_service or PortfolioService(
            portfolio_repo=self.portfolio_repo
        )
        self.price_provider = price_provider or PriceDataProvider()

    async def _get_snapshot_series(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> Tuple[List[Dict[str, Any]], str, Optional[str], Optional[str]]:
        try:
            perf = await self.portfolio_service.get_portfolio_performance(
                user_id, period=period, account_ids=account_ids
            )
        except Exception as e:
            logger.error(f"Failed to get portfolio performance: {e}")
            return [], "", "Failed to fetch portfolio data", "data_integrity"
        if not perf.get("success"):
            return [], "", perf.get("error", "Unknown error"), "data_integrity"
        snapshots = perf.get("snapshots", [])
        if len(snapshots) < 2:
            return [], perf.get("period", period), "insufficient_data", "insufficient_data"
        return snapshots, perf.get("period", period), None, None

    def _returns_from_snapshots(
        self, snapshots: List[Dict[str, Any]]
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        values = np.array([s["value"] for s in snapshots], dtype=np.float64)
        dates = [s["date"] for s in snapshots]
        daily_returns = compute_daily_returns(values)
        return values, daily_returns, dates

    def _periods_per_year(self, snapshots: List[Dict[str, Any]]) -> int:
        """Compute periods per year from snapshot date intervals."""
        if len(snapshots) < 2:
            return TRADING_DAYS
        start = date.fromisoformat(snapshots[0]["date"])
        end = date.fromisoformat(snapshots[-1]["date"])
        total_days = (end - start).days
        n_returns = len(snapshots) - 1
        if total_days <= 0 or n_returns <= 0:
            return TRADING_DAYS
        avg_interval = total_days / n_returns
        if avg_interval <= 1:
            return TRADING_DAYS
        return max(1, min(TRADING_DAYS, round(365 / avg_interval)))

    async def _get_aligned_benchmark_returns(
        self, snapshots: List[Dict[str, Any]]
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Fetch SPY prices aligned to portfolio snapshot dates.

        Returns (portfolio_returns, benchmark_returns) as equal-length arrays.
        Returns None if benchmark data is unavailable.
        """
        if len(snapshots) < 2:
            return None

        dates = [s["date"] for s in snapshots]
        values = np.array([s["value"] for s in snapshots], dtype=np.float64)
        port_returns = compute_daily_returns(values)
        if len(port_returns) < 2:
            return None

        start = date.fromisoformat(dates[0])
        end = date.fromisoformat(dates[-1])

        try:
            spy = self.price_provider.fetch_prices(
                ["SPY"], start=start, end=end, min_periods=2,
            )
            if spy.empty or spy.shape[1] < 1:
                return None

            spy_col = spy.iloc[:, 0]
            spy_prices = []
            for d in dates:
                dt = pd.Timestamp(d) if isinstance(d, str) else pd.Timestamp(d.isoformat())
                mask = spy_col.index <= dt
                if not mask.any():
                    return None
                spy_prices.append(float(spy_col[mask].iloc[-1]))

            spy_arr = np.array(spy_prices, dtype=np.float64)
            spy_returns = compute_daily_returns(spy_arr)

            min_len = min(len(port_returns), len(spy_returns))
            if min_len < 2:
                return None

            return port_returns[:min_len], spy_returns[:min_len]
        except Exception:
            return None

    async def compute_risk_metrics(
        self,
        user_id: int,
        period: str,
        account_ids: Optional[List[int]] = None,
    ) -> RiskMetricsResponse:
        snapshots, resolved_period, error, error_code = await self._get_snapshot_series(
            user_id, period, account_ids
        )
        if error:
            return RiskMetricsResponse(
                success=False, period=resolved_period,
                error=error, error_code=error_code,
            )

        values_arr = np.array([s["value"] for s in snapshots], dtype=np.float64)
        _, daily_returns, _ = self._returns_from_snapshots(snapshots)
        if len(daily_returns) < 5:
            return RiskMetricsResponse(
                success=False, period=resolved_period,
                error="insufficient_data", error_code="insufficient_data",
            )

        ppy = self._periods_per_year(snapshots)
        vol = compute_annualized_volatility(daily_returns, ppy)
        sharpe = compute_sharpe_ratio(daily_returns, risk_free_rate=RISK_FREE_RATE, periods_per_year=ppy)
        sortino = compute_sortino_ratio(daily_returns, risk_free_rate=RISK_FREE_RATE, periods_per_year=ppy)
        dd_val, dd_pct, _, _ = compute_max_drawdown(values_arr)
        var95 = compute_value_at_risk(daily_returns, confidence=0.95)
        var99 = compute_value_at_risk(daily_returns, confidence=0.99)
        cvar95 = compute_conditional_var(daily_returns, confidence=0.95)
        downside = compute_downside_deviation(daily_returns, ppy)
        total_ret = compute_annualized_return(daily_returns)

        result = RiskMetricsResponse(
            success=True,
            period=resolved_period,
            variance=_safe_metric(vol * vol),
            std_deviation=_safe_metric(vol),
            sharpe_ratio=_safe_metric(sharpe),
            sortino_ratio=_safe_metric(sortino),
            max_drawdown=_safe_metric(dd_val),
            max_drawdown_pct=_safe_metric(dd_pct),
            value_at_risk_95=_safe_metric(var95),
            value_at_risk_99=_safe_metric(var99),
            conditional_var_95=_safe_metric(cvar95),
            downside_deviation=_safe_metric(downside),
            total_return_pct=_safe_metric(total_ret),
        )

        aligned = await self._get_aligned_benchmark_returns(snapshots)
        if aligned is not None:
            port_ret, bench_ret = aligned
            result.beta = _safe_metric(compute_beta(port_ret, bench_ret))
            result.alpha = _safe_metric(
                compute_alpha(port_ret, bench_ret, risk_free_rate=RISK_FREE_RATE, periods_per_year=ppy)
            )
            result.tracking_error = _safe_metric(
                compute_tracking_error(port_ret, bench_ret, periods_per_year=ppy)
            )
            result.information_ratio = _safe_metric(
                compute_information_ratio(port_ret, bench_ret, periods_per_year=ppy)
            )

        return _validate_risk_metrics_response(result)

    async def compute_drawdown(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> DrawdownResponse:
        snapshots, resolved_period, error, error_code = await self._get_snapshot_series(
            user_id, period, account_ids
        )
        if error:
            return DrawdownResponse(
                success=False, period=resolved_period, drawdowns=[],
                error=error, error_code=error_code,
            )

        values, _, dates = self._returns_from_snapshots(snapshots)
        dd_series = compute_drawdown_series(values)
        _, dd_pct, peak_idx, trough_idx = compute_max_drawdown(values)

        points = [
            {"date": dates[i], "value": float(values[i]), "drawdown_pct": float(dd_series[i])}
            for i in range(len(dates))
        ]

        result = DrawdownResponse(
            success=True,
            period=resolved_period,
            drawdowns=points,
            max_drawdown=_safe_metric(dd_series.min()),
            max_drawdown_pct=_safe_metric(dd_pct),
            max_drawdown_start=dates[peak_idx] if 0 <= peak_idx < len(dates) else None,
            max_drawdown_end=dates[trough_idx] if 0 <= trough_idx < len(dates) else None,
            avg_drawdown=_safe_metric(float(np.mean(dd_series))),
        )

        if peak_idx < trough_idx and trough_idx + 1 < len(dates):
            recovery = [
                i for i in range(trough_idx + 1, len(dates))
                if dd_series[i] >= dd_pct * 0.95
            ]
            if recovery:
                result.max_drawdown_recovery = dates[recovery[0]]

        return result

    async def _get_holdings_symbols(
        self, user_id: int, account_ids: Optional[List[int]] = None
    ) -> Tuple[List[str], Optional[str], Optional[str]]:
        try:
            holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            return [], "Failed to fetch holdings", "no_holdings"
        if not holdings:
            return [], "no_holdings", "no_holdings"
        symbols = list(dict.fromkeys(h["symbol"] for h in holdings if h.get("symbol")))
        if len(symbols) < 2:
            return symbols, "single_holding", "single_holding"
        return symbols, None, None

    async def _fetch_holding_prices(
        self, symbols: List[str], period: str,
    ) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
        end = now_utc().date()
        n_days = _parse_period(period)
        start = end - timedelta(days=n_days * 2)
        try:
            prices = self.price_provider.fetch_prices(symbols, start, end)
            if prices.shape[1] < 2:
                return None, "single_holding after price fetch", "single_holding"
            if prices.shape[0] < 30:
                return None, "insufficient_data", "insufficient_data"
            return prices, None, None
        except ImportError:
            return None, "yfinance not available", "computation_failed"
        except Exception as e:
            logger.error(f"Price fetch failed: {e}")
            return None, str(e), "computation_failed"

    async def compute_covariance_matrix(
        self, user_id: int, period: str, account_ids: Optional[List[int]] = None
    ) -> CovarianceResponse:
        symbols, error, error_code = await self._get_holdings_symbols(user_id, account_ids)
        if error:
            return CovarianceResponse(
                success=False, period=period, holdings=symbols,
                covariance_matrix=[], correlation_matrix=[],
                error=error, error_code=error_code,
            )

        prices, error, error_code = await self._fetch_holding_prices(symbols, period)
        if error:
            return CovarianceResponse(
                success=False, period=period, holdings=symbols,
                covariance_matrix=[], correlation_matrix=[],
                error=error, error_code=error_code,
            )

        from pypfopt import risk_models

        cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        cov_arr = cov.values.tolist()
        cov_symbols = list(cov.columns)
        D = np.sqrt(np.diag(cov.values))
        corr_arr = (cov.values / np.outer(D, D)).tolist()

        return CovarianceResponse(
            success=True, period=period, holdings=cov_symbols,
            covariance_matrix=cov_arr, correlation_matrix=corr_arr,
        )

    async def compute_efficient_frontier(
        self, user_id: int, account_ids: Optional[List[int]] = None, points: int = 50,
    ) -> EfficientFrontierResponse:
        symbols, error, error_code = await self._get_holdings_symbols(user_id, account_ids)
        if error:
            return EfficientFrontierResponse(
                success=False, frontier=[],
                error="Efficient Frontier requires 2+ holdings" if error_code == "single_holding" else error,
                error_code=error_code,
            )

        end = now_utc().date()
        start = _safe_date_add_years(end, -3)
        try:
            prices = self.price_provider.fetch_prices(symbols, start, end)
            if prices.shape[1] < 2:
                return EfficientFrontierResponse(
                    success=False, frontier=[],
                    error="single_holding after price fetch", error_code="single_holding",
                )
            if prices.shape[0] < 30:
                return EfficientFrontierResponse(
                    success=False, frontier=[],
                    error="insufficient_data", error_code="insufficient_data",
                )
        except ImportError:
            return EfficientFrontierResponse(
                success=False, frontier=[],
                error="Required libraries not available", error_code="computation_failed",
            )
        except Exception as e:
            logger.error(f"Price fetch for frontier failed: {e}")
            return EfficientFrontierResponse(
                success=False, frontier=[],
                error=str(e), error_code="computation_failed",
            )

        from pypfopt import EfficientFrontier, expected_returns, risk_models

        mu = expected_returns.mean_historical_return(prices)
        S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()

        ef = EfficientFrontier(mu, S)
        ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
        max_sharpe_perf = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)
        max_sharpe_weights = dict(ef.clean_weights())

        ef_min = EfficientFrontier(mu, S)
        ef_min.min_volatility()
        min_var_perf = ef_min.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)
        min_var_weights = dict(ef_min.clean_weights())

        target_returns = np.linspace(mu.min(), mu.max(), points)
        frontier = []
        for target_ret in target_returns:
            ef_pt = EfficientFrontier(mu, S)
            try:
                ef_pt.efficient_return(target_return=float(target_ret))
            except Exception:
                continue
            pt_perf = ef_pt.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)
            frontier.append({
                "volatility": float(pt_perf[1]),
                "expected_return": float(pt_perf[0]),
                "weights": dict(ef_pt.clean_weights()),
                "sharpe_ratio": float(pt_perf[2]),
            })

        if not frontier:
            return EfficientFrontierResponse(
                success=False, frontier=[],
                error="No feasible frontier points", error_code="computation_failed",
            )

        return EfficientFrontierResponse(
            success=True,
            frontier=frontier,
            max_sharpe={
                "volatility": float(max_sharpe_perf[1]),
                "expected_return": float(max_sharpe_perf[0]),
                "weights": max_sharpe_weights,
                "sharpe_ratio": float(max_sharpe_perf[2]),
            },
            min_variance={
                "volatility": float(min_var_perf[1]),
                "expected_return": float(min_var_perf[0]),
                "weights": min_var_weights,
                "sharpe_ratio": float(min_var_perf[2]),
            },
        )

    async def compute_rolling_sharpe(
        self, user_id: int, window: int = 252, account_ids: Optional[List[int]] = None,
    ) -> RollingSharpeResponse:
        snapshots, resolved_period, error, error_code = await self._get_snapshot_series(
            user_id, "MAX", account_ids
        )
        if error:
            return RollingSharpeResponse(
                success=False, period=resolved_period, window=window, series=[],
                error=error, error_code=error_code,
            )

        _, daily_returns, dates = self._returns_from_snapshots(snapshots)
        if len(daily_returns) < window:
            return RollingSharpeResponse(
                success=False, period=resolved_period, window=window, series=[],
                error="insufficient_data", error_code="insufficient_data",
            )

        ppy = self._periods_per_year(snapshots)
        rs = _rolling_sharpe(daily_returns, window=window, risk_free_rate=RISK_FREE_RATE, periods_per_year=ppy)
        if len(rs) == 0:
            return RollingSharpeResponse(
                success=False, period=resolved_period, window=window, series=[],
                error="insufficient_data", error_code="insufficient_data",
            )

        series = [
            {"date": dates[i + window], "sharpe_ratio": float(rs[i])}
            for i in range(len(rs))
            if i + window < len(dates)
        ]

        return RollingSharpeResponse(
            success=True, period=resolved_period, window=window, series=series,
        )

    async def compute_risk_contribution(
        self, user_id: int, account_ids: Optional[List[int]] = None,
    ) -> RiskContributionResponse:
        try:
            holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error="Failed to fetch holdings", error_code="no_holdings",
            )
        if not holdings:
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error="no_holdings", error_code="no_holdings",
            )

        symbols: List[str] = []
        raw_weights: List[float] = []
        for h in holdings:
            sym = h.get("symbol")
            w = float(h.get("current_value") or 0)
            if sym:
                symbols.append(sym)
                raw_weights.append(w)

        if not symbols:
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error="no_holdings", error_code="no_holdings",
            )

        total_value = sum(raw_weights)
        if total_value <= 0:
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error="Zero portfolio value", error_code="data_integrity",
            )

        weights_arr = np.array(raw_weights, dtype=np.float64) / total_value

        from pypfopt import risk_models

        end = now_utc().date()
        start = _safe_date_add_years(end, -1)
        try:
            prices = self.price_provider.fetch_prices(symbols, start, end)
        except Exception as e:
            logger.error(f"Risk contribution price fetch failed: {e}")
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error=str(e), error_code="computation_failed",
            )

        if prices.shape[1] < 2:
            return RiskContributionResponse(
                success=False, contributions=[], total_risk=0.0,
                error="single_holding", error_code="single_holding",
            )

        S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        index_order = list(S.index)
        w_ordered = np.array(
            [weights_arr[symbols.index(s)] if s in symbols else 0.0 for s in index_order],
            dtype=np.float64,
        )
        ws = w_ordered.sum()
        if ws > 0:
            w_ordered = w_ordered / ws

        S_arr = S.values
        port_var = float(w_ordered.T @ S_arr @ w_ordered)
        port_vol = np.sqrt(port_var) if port_var > 0 else 1e-10
        mcr = (S_arr @ w_ordered) / port_vol
        ccr = w_ordered * mcr
        ccr_pct = ccr / port_vol

        contributions = [
            RiskContributionItem(
                symbol=sym,
                weight=float(w_ordered[i]),
                marginal_risk=float(mcr[i]),
                component_risk=float(ccr[i]),
                risk_pct=float(ccr_pct[i]),
            )
            for i, sym in enumerate(index_order)
            if i < len(w_ordered)
        ]

        return RiskContributionResponse(
            success=True, contributions=contributions, total_risk=float(port_vol),
        )

    async def compute_market_exposure(
        self, user_id: int, account_ids: Optional[List[int]] = None,
    ) -> FactorExposureResponse:
        snapshots, _, error, error_code = await self._get_snapshot_series(
            user_id, "1Y", account_ids
        )
        if error:
            return FactorExposureResponse(
                success=False, exposures={}, r_squared=0.0,
                error=error, error_code=error_code,
            )

        if len(snapshots) < 2:
            return FactorExposureResponse(
                success=False, exposures={}, r_squared=0.0,
                error="insufficient_data", error_code="insufficient_data",
            )

        aligned = await self._get_aligned_benchmark_returns(snapshots)
        if aligned is None:
            return FactorExposureResponse(
                success=False, exposures={}, r_squared=0.0,
                error="no_benchmark_data", error_code="no_benchmark_data",
            )

        port_ret, bench_ret = aligned
        if len(port_ret) < 5:
            return FactorExposureResponse(
                success=False, exposures={}, r_squared=0.0,
                error="insufficient_data", error_code="insufficient_data",
            )

        ppy = self._periods_per_year(snapshots)

        try:
            n = len(port_ret)
            X = np.vstack([np.ones(n), bench_ret]).T
            coeffs, residuals, _, _ = np.linalg.lstsq(X, port_ret, rcond=None)
            alpha_hat, beta_hat = float(coeffs[0]), float(coeffs[1])

            ss_res = float(np.sum((port_ret - X @ coeffs) ** 2))
            ss_tot = float(np.sum((port_ret - np.mean(port_ret)) ** 2))
            r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            return FactorExposureResponse(
                success=True,
                exposures={
                    "market": _safe_metric(beta_hat),
                    "alpha": _safe_metric(alpha_hat * ppy),
                },
                r_squared=_safe_metric(r_squared),
            )
        except Exception as e:
            logger.error(f"Market exposure computation failed: {e}")
            return FactorExposureResponse(
                success=False, exposures={}, r_squared=0.0,
                error=str(e), error_code="computation_failed",
            )


def _validate_risk_metrics_response(response: RiskMetricsResponse) -> RiskMetricsResponse:
    checks: List[str] = []

    if response.value_at_risk_99 is not None and response.value_at_risk_95 is not None:
        if response.value_at_risk_99 > response.value_at_risk_95:
            response.value_at_risk_99 = response.value_at_risk_95
            checks.append("clamped VaR99 <= VaR95")

    if response.conditional_var_95 is not None and response.value_at_risk_95 is not None:
        if response.conditional_var_95 > response.value_at_risk_95:
            response.conditional_var_95 = response.value_at_risk_95
            checks.append("clamped CVaR <= VaR95")

    if response.downside_deviation is not None and response.std_deviation is not None:
        if response.downside_deviation > response.std_deviation:
            response.downside_deviation = response.std_deviation
            checks.append("clamped downside_deviation <= std_deviation")

    if response.sortino_ratio is not None and response.sharpe_ratio is not None:
        if response.sortino_ratio + 0.01 < response.sharpe_ratio:
            logger.warning(
                f"sortino_ratio={response.sortino_ratio} < sharpe_ratio={response.sharpe_ratio}"
            )

    if response.max_drawdown_pct is not None and response.max_drawdown_pct > 0:
        response.max_drawdown_pct = 0.0
        checks.append("clamped max_drawdown_pct <= 0")

    if checks:
        logger.warning(f"Cross-metric invariant corrections: {', '.join(checks)}")

    return response
