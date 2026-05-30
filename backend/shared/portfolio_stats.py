from __future__ import annotations

import logging
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

TRADING_DAYS: int = 252


def compute_daily_returns(values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return np.array([], dtype=np.float64)
    return (values[1:] - values[:-1]) / values[:-1]


def compute_annualized_return(daily_returns: np.ndarray) -> float:
    if len(daily_returns) < 1:
        return 0.0
    total_return = np.prod(1 + daily_returns) - 1
    return float(total_return)


def _safe_metric(value: float, default: float = 0.0) -> float:
    if value is None or value != value or np.isinf(value):
        return default
    return value


def _sanity_bounds(metric_name: str, value: float, lo: float, hi: float) -> float:
    if value < lo or value > hi:
        logger.warning(f"{metric_name}={value:.4f} outside sane range [{lo}, {hi}]")
    return max(lo, min(hi, value))


def compute_annualized_volatility(daily_returns: np.ndarray) -> float:
    if len(daily_returns) < 2:
        return 0.0
    vol = float(np.std(daily_returns, ddof=1)) * np.sqrt(TRADING_DAYS)
    return _sanity_bounds("annualized_volatility", vol, 0.0, 2.0)


def compute_sharpe_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean_return = float(np.mean(daily_returns)) * TRADING_DAYS
    annual_vol = compute_annualized_volatility(daily_returns)
    if annual_vol < 1e-12:
        return 0.0
    sharpe = (mean_return - risk_free_rate) / annual_vol
    return _sanity_bounds("sharpe_ratio", sharpe, -3.0, 5.0)


def compute_downside_deviation(daily_returns: np.ndarray) -> float:
    if len(daily_returns) < 2:
        return 0.0
    negative = daily_returns[daily_returns < 0]
    if len(negative) < 2:
        return float(np.std(daily_returns, ddof=1)) * np.sqrt(TRADING_DAYS)
    dd = float(np.std(negative, ddof=1)) * np.sqrt(TRADING_DAYS)
    return _sanity_bounds("downside_deviation", dd, 0.0, 2.0)


def compute_sortino_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean_return = float(np.mean(daily_returns)) * TRADING_DAYS
    dd = compute_downside_deviation(daily_returns)
    if dd < 1e-12:
        return 0.0
    sortino = (mean_return - risk_free_rate) / dd
    return _sanity_bounds("sortino_ratio", sortino, -3.0, 10.0)


def compute_max_drawdown(values: np.ndarray) -> Tuple[float, float, int, int]:
    if len(values) < 2:
        return 0.0, 0.0, 0, 0
    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max
    trough_idx = int(np.argmin(drawdown))
    dd_pct = float(drawdown[trough_idx])
    peak_idx = int(np.argmax(running_max[:trough_idx + 1])) if trough_idx > 0 else 0
    dd_value = float(values[trough_idx] - values[peak_idx])
    dd_pct = _sanity_bounds("max_drawdown_pct", dd_pct, -1.0, 0.0)
    return dd_value, dd_pct, peak_idx, trough_idx


def compute_drawdown_series(values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return np.zeros_like(values)
    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max
    return np.minimum(drawdown, 0.0)


def compute_value_at_risk(
    daily_returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    from scipy.stats import norm
    z = norm.ppf(1 - confidence)
    mean = float(np.mean(daily_returns))
    std = float(np.std(daily_returns, ddof=1))
    var = mean - z * std
    return _sanity_bounds(f"VaR_{int(confidence*100)}", var, -0.5, 0.0)


def compute_historical_var(
    daily_returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    var = float(np.percentile(daily_returns, (1 - confidence) * 100))
    return _sanity_bounds(f"historical_VaR_{int(confidence*100)}", var, -0.5, 0.0)


def compute_conditional_var(
    daily_returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    threshold = float(np.percentile(daily_returns, (1 - confidence) * 100))
    tail = daily_returns[daily_returns <= threshold]
    if len(tail) == 0:
        return threshold
    cvar = float(np.mean(tail))
    return _sanity_bounds(f"CVaR_{int(confidence*100)}", cvar, -0.5, 0.0)


def compute_beta(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
) -> float:
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    cov = np.cov(portfolio_returns, benchmark_returns, ddof=1)
    var_b = cov[1, 1]
    if var_b < 1e-12:
        return 0.0
    beta_val = float(cov[0, 1] / var_b)
    return _sanity_bounds("beta", beta_val, -5.0, 5.0)


def compute_alpha(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    risk_free_rate: float = 0.02,
) -> float:
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    b = compute_beta(portfolio_returns, benchmark_returns)
    port_mean = float(np.mean(portfolio_returns)) * TRADING_DAYS
    bench_mean = float(np.mean(benchmark_returns)) * TRADING_DAYS
    alpha_val = port_mean - (risk_free_rate + b * (bench_mean - risk_free_rate))
    return _sanity_bounds("alpha", alpha_val, -1.0, 1.0)


def compute_tracking_error(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
) -> float:
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    diff = portfolio_returns - benchmark_returns
    te = float(np.std(diff, ddof=1)) * np.sqrt(TRADING_DAYS)
    return _sanity_bounds("tracking_error", te, 0.0, 2.0)


def compute_information_ratio(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
) -> float:
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        return 0.0
    port_mean = float(np.mean(portfolio_returns)) * TRADING_DAYS
    bench_mean = float(np.mean(benchmark_returns)) * TRADING_DAYS
    te = compute_tracking_error(portfolio_returns, benchmark_returns)
    if te < 1e-12:
        return 0.0
    ir = (port_mean - bench_mean) / te
    return _sanity_bounds("information_ratio", ir, -5.0, 5.0)


def compute_rolling_sharpe(
    daily_returns: np.ndarray,
    window: int = 252,
    risk_free_rate: float = 0.02,
) -> np.ndarray:
    if len(daily_returns) < window:
        return np.array([])
    means = np.zeros(len(daily_returns) - window + 1)
    stds = np.zeros(len(daily_returns) - window + 1)
    for i in range(len(means)):
        chunk = daily_returns[i:i + window]
        means[i] = float(np.mean(chunk)) * TRADING_DAYS
        s = float(np.std(chunk, ddof=1)) * np.sqrt(TRADING_DAYS)
        stds[i] = s if s > 1e-12 else 1.0
    sharpe = (means - risk_free_rate) / stds
    return np.clip(sharpe, -3.0, 5.0)


def compute_correlation_matrix(returns_matrix: np.ndarray) -> np.ndarray:
    corr = np.corrcoef(returns_matrix)
    assert np.allclose(corr, corr.T), "Correlation matrix not symmetric"
    assert np.allclose(np.diag(corr), 1.0), "Correlation diagonal not 1.0"
    assert np.all(np.abs(corr) <= 1.0 + 1e-10), "Correlation outside [-1, 1]"
    return corr
