from __future__ import annotations

import numpy as np
import pytest

from shared.portfolio_stats import (
    TRADING_DAYS,
    compute_alpha,
    compute_annualized_volatility,
    compute_beta,
    compute_conditional_var,
    compute_correlation_matrix,
    compute_drawdown_series,
    compute_downside_deviation,
    compute_historical_var,
    compute_information_ratio,
    compute_max_drawdown,
    compute_rolling_sharpe,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_tracking_error,
    compute_value_at_risk,
)


def _constant_returns(n: int = 252, val: float = 0.001) -> np.ndarray:
    return np.full(n, val)


def _random_returns(n: int = 252, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0005, 0.015, n)


class TestSharpeRatio:
    def test_constant_positive_returns(self):
        r = _constant_returns(252, 0.001)
        sr = compute_sharpe_ratio(r, risk_free_rate=0.02)
        assert sr == 0.0

    def test_positive_sharpe(self):
        r = _random_returns(252)
        sr = compute_sharpe_ratio(r, risk_free_rate=0.02)
        assert -3.0 <= sr <= 5.0

    def test_insufficient_data(self):
        assert compute_sharpe_ratio(np.array([0.001])) == 0.0
        assert compute_sharpe_ratio(np.array([])) == 0.0


class TestSortinoRatio:
    def test_positive_sortino(self):
        r = _random_returns(5000)
        sortino = compute_sortino_ratio(r, risk_free_rate=0.02)
        sharpe = compute_sharpe_ratio(r, risk_free_rate=0.02)
        assert sortino >= sharpe - 0.01

    def test_insufficient_data(self):
        assert compute_sortino_ratio(np.array([0.001])) == 0.0
        assert compute_sortino_ratio(np.array([])) == 0.0

    def test_all_positive_returns(self):
        r = np.full(252, 0.001)
        sortino = compute_sortino_ratio(r, risk_free_rate=0.02)
        sr = compute_sharpe_ratio(r, risk_free_rate=0.02)
        assert sortino >= sr


class TestMaxDrawdown:
    def test_no_drawdown(self):
        values = np.linspace(100, 200, 252)
        dd_val, dd_pct, peak, trough = compute_max_drawdown(values)
        assert dd_pct == 0.0
        assert dd_val == 0.0

    def test_single_drawdown(self):
        values = np.array([100, 110, 90, 95, 105])
        dd_val, dd_pct, peak, trough = compute_max_drawdown(values)
        assert dd_pct == pytest.approx(-0.1818, rel=0.01)
        assert peak == 1
        assert trough == 2

    def test_insufficient_data(self):
        assert compute_max_drawdown(np.array([100])) == (0.0, 0.0, 0, 0)
        assert compute_max_drawdown(np.array([])) == (0.0, 0.0, 0, 0)

    def test_strictly_increasing_is_zero(self):
        values = np.array([1, 2, 3, 4, 5])
        _, dd_pct, _, _ = compute_max_drawdown(values)
        assert dd_pct == 0.0

    def test_drawdown_series(self):
        values = np.array([100, 110, 90, 95, 105])
        dd = compute_drawdown_series(values)
        assert len(dd) == len(values)
        assert np.all(dd <= 0)
        assert dd[2] == pytest.approx(-0.1818, rel=0.01)

    def test_drawdown_series_insufficient(self):
        assert len(compute_drawdown_series(np.array([100]))) == 1
        assert len(compute_drawdown_series(np.array([]))) == 0


class TestValueAtRisk:
    def test_normal_returns(self):
        r = _random_returns(1000)
        var95 = compute_value_at_risk(r, 0.95)
        var99 = compute_value_at_risk(r, 0.99)
        assert var95 <= 0.0
        assert var99 <= var95

    def test_historical_var(self):
        r = _random_returns(1000)
        hv95 = compute_historical_var(r, 0.95)
        assert hv95 <= 0.0

    def test_conditional_var(self):
        r = _random_returns(1000)
        cvar95 = compute_conditional_var(r, 0.95)
        var95 = compute_historical_var(r, 0.95)
        assert cvar95 <= var95

    def test_insufficient_data(self):
        assert compute_value_at_risk(np.array([0.001])) == 0.0
        assert compute_historical_var(np.array([0.001])) == 0.0
        assert compute_conditional_var(np.array([0.001])) == 0.0


class TestDownsideDeviation:
    def test_all_positive(self):
        r = np.full(252, 0.001)
        dd = compute_downside_deviation(r)
        assert dd >= 0.0

    def test_mixed_returns(self):
        r = _random_returns(252)
        dd = compute_downside_deviation(r)
        vol = compute_annualized_volatility(r)
        assert dd <= vol + 1e-10

    def test_insufficient_data(self):
        assert compute_downside_deviation(np.array([0.001])) == 0.0


class TestAnnualizedVolatility:
    def test_constant_returns(self):
        vol = compute_annualized_volatility(np.full(252, 0.001))
        assert vol == pytest.approx(0.0, abs=1e-15)

    def test_random_returns(self):
        r = _random_returns(252)
        vol = compute_annualized_volatility(r)
        assert 0.0 < vol < 1.0

    def test_insufficient_data(self):
        assert compute_annualized_volatility(np.array([0.001])) == 0.0


class TestBetaAlpha:
    def test_self_beta(self):
        r = _random_returns(252)
        b = compute_beta(r, r)
        assert b == pytest.approx(1.0, abs=0.01)

    def test_unrelated_beta(self):
        r1 = _random_returns(252, seed=1)
        r2 = _random_returns(252, seed=2)
        b = compute_beta(r1, r2)
        assert -5.0 <= b <= 5.0

    def test_alpha(self):
        r = _random_returns(252)
        bm = _random_returns(252, seed=1)
        a = compute_alpha(r, bm, risk_free_rate=0.02)
        assert -1.0 <= a <= 1.0

    def test_insufficient_data(self):
        assert compute_beta(np.array([0.001]), np.array([0.001])) == 0.0
        assert compute_beta(np.array([]), np.array([])) == 0.0
        assert compute_alpha(np.array([0.001]), np.array([0.001])) == 0.0


class TestTrackingError:
    def test_identical(self):
        r = _random_returns(252)
        te = compute_tracking_error(r, r)
        assert te == pytest.approx(0.0, abs=0.01)

    def test_different(self):
        r1 = _random_returns(252, seed=1)
        r2 = _random_returns(252, seed=2)
        te = compute_tracking_error(r1, r2)
        assert te >= 0.0

    def test_insufficient_data(self):
        assert compute_tracking_error(np.array([0.001]), np.array([0.001])) == 0.0


class TestInformationRatio:
    def test_identical(self):
        r = _random_returns(252)
        ir = compute_information_ratio(r, r)
        assert ir == pytest.approx(0.0, abs=0.01)

    def test_insufficient_data(self):
        assert compute_information_ratio(np.array([0.001]), np.array([0.001])) == 0.0


class TestRollingSharpe:
    def test_length(self):
        r = _random_returns(300)
        rs = compute_rolling_sharpe(r, window=252)
        assert len(rs) == 300 - 252 + 1

    def test_empty_when_too_short(self):
        r = _random_returns(100)
        rs = compute_rolling_sharpe(r, window=252)
        assert len(rs) == 0

    def test_bounds(self):
        r = _random_returns(500)
        rs = compute_rolling_sharpe(r, window=252)
        assert np.all(rs >= -3.0)
        assert np.all(rs <= 5.0)

    def test_constant_returns(self):
        r = np.full(300, 0.001)
        rs = compute_rolling_sharpe(r, window=252)
        assert len(rs) > 0
        assert np.allclose(rs, rs[0])


class TestCorrelationMatrix:
    def test_identity(self):
        r = np.random.randn(3, 100)
        corr = compute_correlation_matrix(r)
        assert corr.shape == (3, 3)

    def test_symmetric(self):
        r = np.random.randn(5, 100)
        corr = compute_correlation_matrix(r)
        assert np.allclose(corr, corr.T)

    def test_diagonal(self):
        r = np.random.randn(3, 100)
        corr = compute_correlation_matrix(r)
        assert np.allclose(np.diag(corr), 1.0)

    def test_range(self):
        r = np.random.randn(4, 200)
        corr = compute_correlation_matrix(r)
        assert np.all(np.abs(corr) <= 1.0 + 1e-10)


class TestSanityBounds:
    def test_sharpe_sortino_invariant(self):
        r = _random_returns(5000)
        sortino = compute_sortino_ratio(r, risk_free_rate=0.02)
        sharpe = compute_sharpe_ratio(r, risk_free_rate=0.02)
        assert sortino >= sharpe - 0.01

    def test_var_cvar_invariant(self):
        r = _random_returns(1000)
        var95 = compute_historical_var(r, confidence=0.95)
        var99 = compute_historical_var(r, confidence=0.99)
        cvar95 = compute_conditional_var(r, confidence=0.95)
        assert var99 <= var95
        assert cvar95 <= var95

    def test_downside_vol_invariant(self):
        r = _random_returns(1000)
        dd = compute_downside_deviation(r)
        vol = compute_annualized_volatility(r)
        assert dd <= vol + 1e-10

    def test_drawdown_non_positive(self):
        r = np.cumprod(1 + _random_returns(500))
        _, dd_pct, _, _ = compute_max_drawdown(r)
        assert dd_pct <= 0.0

    def test_drawdown_series_non_positive(self):
        r = np.cumprod(1 + _random_returns(500))
        dd = compute_drawdown_series(r)
        assert np.all(dd <= 0.0)
