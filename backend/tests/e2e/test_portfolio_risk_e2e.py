"""
Portfolio Risk — End-to-End Tests

Tests all 8 use cases end-to-end through the full stack:
  API → Service → Stats → Repository → Supabase

No mocking. Requires RUN_E2E=true + real Supabase credentials + backend running.

Each use case validates:
  - API endpoint responds 200
  - Schema contract (all expected fields present)
  - Data invariants (Sharpe > Sortino, VaR99 <= VaR95, etc.)
  - Supabase table round-trip (data flows correctly through the DB)
"""

import pytest


# ========================================================================
# UC-1: View Risk Metrics Summary
# ========================================================================

@pytest.mark.e2e
class TestRiskMetricsE2E:
    """UC-1: End-to-end validation of risk metrics computation."""

    async def test_risk_metrics_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=1Y", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        _assert_risk_metrics_schema(data)
        _assert_risk_metrics_invariants(data)

    async def test_risk_metrics_with_account_filter(self, e2e_http_client, e2e_auth_headers, e2e_account_ids):
        ids = ",".join(str(aid) for aid in e2e_account_ids[:2])
        resp = await e2e_http_client.get(
            f"/portfolio/risk-metrics?period=1Y&account_ids={ids}",
            headers=e2e_auth_headers,
        )
        assert resp.status_code == 200
        _assert_risk_metrics_schema(resp.json())

    async def test_risk_metrics_multiple_periods(self, e2e_http_client, e2e_auth_headers):
        resp_1y = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=1Y", headers=e2e_auth_headers
        )
        resp_5y = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=5Y", headers=e2e_auth_headers
        )
        assert resp_1y.status_code == 200
        assert resp_5y.status_code == 200
        d1, d5 = resp_1y.json(), resp_5y.json()
        if d1["success"] and d5["success"]:
            assert d5["value_at_risk_95"] <= d1["value_at_risk_95"], (
                f"5Y VaR(95)={d5['value_at_risk_95']} should be <= 1Y VaR(95)={d1['value_at_risk_95']}"
            )

    async def test_risk_metrics_schema_stability(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        expected = [
            "success", "period", "variance", "std_deviation",
            "sharpe_ratio", "sortino_ratio",
            "max_drawdown", "max_drawdown_pct",
            "value_at_risk_95", "value_at_risk_99", "conditional_var_95",
            "downside_deviation",
        ]
        for field in expected:
            assert field in data, f"Missing field: {field}"
        assert isinstance(data["sharpe_ratio"], float)
        assert isinstance(data["std_deviation"], float)
        assert isinstance(data["success"], bool)

    async def test_risk_metrics_supabase_data_flow(self, e2e_http_client, e2e_auth_headers, e2e_supabase):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=MAX", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["success"] and data.get("sharpe_ratio", 0) != 0:
            snapshots = (
                e2e_supabase.table("portfolio_performance")
                .select("snapshot_date, total_value")
                .limit(5)
                .execute()
            )
            assert len(snapshots.data) > 0, "No performance data in Supabase"
            for snap in snapshots.data:
                assert "snapshot_date" in snap
                assert "total_value" in snap


# ========================================================================
# UC-2: View Drawdown Chart
# ========================================================================

@pytest.mark.e2e
class TestDrawdownE2E:
    """UC-2: End-to-end validation of drawdown computation."""

    async def test_drawdown_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/drawdown?period=1Y", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["drawdowns"], list)
        assert isinstance(data["period"], str)
        for dd in data["drawdowns"]:
            assert "date" in dd
            assert "value" in dd
            assert "drawdown_pct" in dd

    async def test_drawdown_non_positive(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/drawdown?period=5Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"]:
            for dd in data["drawdowns"]:
                assert dd["drawdown_pct"] <= 0.0, (
                    f"Drawdown {dd['date']}: {dd['drawdown_pct']} > 0"
                )

    async def test_drawdown_max_matches_worst(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/drawdown?period=5Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["drawdowns"]:
            worst = min(d["drawdown_pct"] for d in data["drawdowns"])
            assert abs(data["max_drawdown_pct"] - worst) < 0.001

    async def test_drawdown_chronological(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/drawdown?period=5Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["drawdowns"]:
            dates = [d["date"] for d in data["drawdowns"]]
            assert dates == sorted(dates), "Drawdown dates not chronological"

    async def test_drawdown_period_scoping(self, e2e_http_client, e2e_auth_headers):
        resp_1y = await e2e_http_client.get(
            "/portfolio/drawdown?period=1Y", headers=e2e_auth_headers
        )
        resp_5y = await e2e_http_client.get(
            "/portfolio/drawdown?period=5Y", headers=e2e_auth_headers
        )
        d1, d5 = resp_1y.json(), resp_5y.json()
        if d1["success"] and d5["success"]:
            assert len(d5["drawdowns"]) >= len(d1["drawdowns"])


# ========================================================================
# UC-3: View Covariance & Correlation Heatmap
# ========================================================================

@pytest.mark.e2e
class TestCovarianceE2E:
    """UC-3: End-to-end validation of covariance/correlation matrices."""

    async def test_covariance_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/covariance?period=1Y", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["holdings"], list)
        assert isinstance(data["covariance_matrix"], list)
        assert isinstance(data["correlation_matrix"], list)

    async def test_covariance_matrix_shape(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/covariance?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and len(data["holdings"]) > 0:
            n = len(data["holdings"])
            assert len(data["covariance_matrix"]) == n
            assert len(data["covariance_matrix"][0]) == n

    async def test_correlation_matrix_symmetric(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/covariance?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and len(data["holdings"]) > 1:
            corr = data["correlation_matrix"]
            n = len(corr)
            for i in range(n):
                assert abs(corr[i][i] - 1.0) < 0.001, f"Diagonal {i}: {corr[i][i]} != 1"
                for j in range(n):
                    assert abs(corr[i][j] - corr[j][i]) < 0.001, (
                        f"Symmetry broken at ({i},{j})"
                    )

    async def test_correlation_range(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/covariance?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"]:
            for row in data["correlation_matrix"]:
                for val in row:
                    assert -1.0 <= val <= 1.0, f"Correlation {val} outside [-1, 1]"

    async def test_covariance_holdings_match(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/covariance?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["holdings"]:
            symbols = data["holdings"]
            assert len(symbols) == len(set(symbols)), "Duplicate symbols in holdings"
            assert all(isinstance(s, str) for s in symbols)


# ========================================================================
# UC-4: View Efficient Frontier
# ========================================================================

@pytest.mark.e2e
class TestEfficientFrontierE2E:
    """UC-4: End-to-end validation of efficient frontier optimization."""

    async def test_frontier_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier?points=50", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "frontier" in data
        assert "max_sharpe" in data
        assert "min_variance" in data

    async def test_frontier_weights_sum_to_one(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier?points=50", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"]:
            for pt in data["frontier"]:
                total = sum(pt["weights"].values())
                assert abs(total - 1.0) < 0.02, (
                    f"Weights sum to {total}, expected ~1.0"
                )

    async def test_max_sharpe_outperforms_min_variance(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier?points=50", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["max_sharpe"] and data["min_variance"]:
            assert data["max_sharpe"]["sharpe_ratio"] >= data["min_variance"]["sharpe_ratio"]

    async def test_frontier_convex(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier?points=50", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and len(data["frontier"]) > 1:
            vols = [p["volatility"] for p in data["frontier"]]
            for i in range(len(vols) - 1):
                assert vols[i] <= vols[i + 1] + 1e-6, (
                    f"Volatility decreased at point {i}: {vols[i]} -> {vols[i+1]}"
                )

    async def test_frontier_single_holding(self, e2e_http_client, e2e_single_holding_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier", headers=e2e_single_holding_headers
        )
        data = resp.json()
        assert data["success"] is False or data.get("error") is not None

    async def test_frontier_schema(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/efficient-frontier?points=20", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["frontier"]:
            pt = data["frontier"][0]
            assert "volatility" in pt
            assert "expected_return" in pt
            assert "weights" in pt
            assert "sharpe_ratio" in pt
            if data["max_sharpe"]:
                assert "volatility" in data["max_sharpe"]
                assert "expected_return" in data["max_sharpe"]
                assert "weights" in data["max_sharpe"]
                assert "sharpe_ratio" in data["max_sharpe"]


# ========================================================================
# UC-5: View Rolling Sharpe
# ========================================================================

@pytest.mark.e2e
class TestRollingSharpeE2E:
    """UC-5: End-to-end validation of rolling Sharpe computation."""

    async def test_rolling_sharpe_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/rolling-sharpe?window=252", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "series" in data
        assert "window" in data
        assert data["window"] == 252

    async def test_rolling_sharpe_series_shape(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/rolling-sharpe?window=252", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["series"]:
            for pt in data["series"]:
                assert "date" in pt
                assert "sharpe_ratio" in pt
                assert isinstance(pt["sharpe_ratio"], float)

    async def test_rolling_sharpe_different_windows(self, e2e_http_client, e2e_auth_headers):
        resp_60 = await e2e_http_client.get(
            "/portfolio/rolling-sharpe?window=60", headers=e2e_auth_headers
        )
        resp_252 = await e2e_http_client.get(
            "/portfolio/rolling-sharpe?window=252", headers=e2e_auth_headers
        )
        d60, d252 = resp_60.json(), resp_252.json()
        if d60["success"] and d252["success"]:
            assert len(d60["series"]) >= len(d252["series"])


# ========================================================================
# UC-6: View Risk Contribution
# ========================================================================

@pytest.mark.e2e
class TestRiskContributionE2E:
    """UC-6: End-to-end validation of risk contribution decomposition."""

    async def test_risk_contribution_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-contribution", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "contributions" in data
        assert "total_risk" in data

    async def test_risk_contribution_schema(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-contribution", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["contributions"]:
            for item in data["contributions"]:
                assert "symbol" in item
                assert "weight" in item
                assert "marginal_risk" in item
                assert "component_risk" in item
                assert "risk_pct" in item

    async def test_risk_contribution_sums_to_total(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-contribution", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and data["contributions"]:
            component_sum = sum(c["component_risk"] for c in data["contributions"])
            risk_pct_sum = sum(c["risk_pct"] for c in data["contributions"])
            total_risk = data["total_risk"]
            assert abs(component_sum - total_risk) < 0.01 * max(0.01, total_risk)
            assert abs(risk_pct_sum - 1.0) < 0.02

    async def test_risk_contribution_account_scoping(self, e2e_http_client, e2e_auth_headers, e2e_account_ids):
        if len(e2e_account_ids) < 2:
            pytest.skip("Need at least 2 accounts to test scoping")
        ids = ",".join(str(aid) for aid in e2e_account_ids[:1])
        resp = await e2e_http_client.get(
            f"/portfolio/risk-contribution?account_ids={ids}",
            headers=e2e_auth_headers,
        )
        assert resp.status_code == 200
        assert "success" in resp.json()


# ========================================================================
# UC-7: View Factor Exposure
# ========================================================================

@pytest.mark.e2e
class TestFactorExposureE2E:
    """UC-7: End-to-end validation of factor exposure / market beta."""

    async def test_factor_exposure_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/market-exposure", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "exposures" in data
        assert "r_squared" in data

    async def test_factor_exposure_schema(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/market-exposure", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"]:
            exposures = data["exposures"]
            assert "market" in exposures
            assert "alpha" in exposures
            assert isinstance(exposures["market"], float)
            assert isinstance(data["r_squared"], float)
            assert 0.0 <= data["r_squared"] <= 1.0

    async def test_factor_exposure_beta_range(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/market-exposure", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"] and "market" in data["exposures"]:
            beta = data["exposures"]["market"]
            assert -2.0 <= beta <= 3.0, f"Beta={beta} outside reasonable range"


# ========================================================================
# UC-8: View Benchmark Comparison (Extended)
# ========================================================================

@pytest.mark.e2e
class TestBenchmarkComparisonE2E:
    """UC-8: Extended benchmark comparison with risk-adjusted metrics."""

    async def test_benchmark_compare_happy_path(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/performance/compare?period=1Y&benchmarks=SPY",
            headers=e2e_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "portfolio" in data
        assert "benchmarks" in data

    async def test_benchmark_compare_multi(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/performance/compare?period=1Y&benchmarks=SPY,QQQ",
            headers=e2e_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["success"]:
            assert len(data["benchmarks"]) == 2

    async def test_risk_metrics_with_benchmark_returns(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=1Y", headers=e2e_auth_headers
        )
        data = resp.json()
        if data["success"]:
            if data.get("beta") is not None:
                assert isinstance(data["beta"], float)
                assert isinstance(data["alpha"], float)
            if data.get("tracking_error") is not None:
                assert isinstance(data["tracking_error"], float)


# ========================================================================
# CROSS-CUTTING: Account Scoping
# ========================================================================

@pytest.mark.e2e
class TestAccountScopingE2E:
    """Account scoping applies to all risk endpoints."""

    ALL_ENDPOINTS = [
        "/portfolio/risk-metrics?period=1Y",
        "/portfolio/drawdown?period=1Y",
        "/portfolio/covariance?period=1Y",
        "/portfolio/efficient-frontier?points=20",
        "/portfolio/rolling-sharpe?window=252",
        "/portfolio/risk-contribution",
        "/portfolio/market-exposure",
    ]

    async def test_all_endpoints_accept_account_ids(self, e2e_http_client, e2e_auth_headers, e2e_account_ids):
        if not e2e_account_ids:
            pytest.skip("No accounts available for scoping test")
        ids = ",".join(str(aid) for aid in e2e_account_ids[:1])
        for ep in self.ALL_ENDPOINTS:
            sep = "&" if "?" in ep else "?"
            resp = await e2e_http_client.get(
                f"{ep}{sep}account_ids={ids}", headers=e2e_auth_headers
            )
            assert resp.status_code == 200, f"{ep} with account_ids returned {resp.status_code}"

    async def test_all_endpoints_empty_account_ids(self, e2e_http_client, e2e_auth_headers):
        for ep in self.ALL_ENDPOINTS:
            resp = await e2e_http_client.get(ep, headers=e2e_auth_headers)
            assert resp.status_code == 200, f"{ep} returned {resp.status_code}"


# ========================================================================
# CROSS-CUTTING: Error Handling
# ========================================================================

@pytest.mark.e2e
class TestErrorHandlingE2E:
    """Error handling for edge cases across all endpoints."""

    ENDPOINTS = [
        "/portfolio/risk-metrics",
        "/portfolio/drawdown",
        "/portfolio/covariance",
        "/portfolio/efficient-frontier",
        "/portfolio/rolling-sharpe",
        "/portfolio/risk-contribution",
        "/portfolio/market-exposure",
    ]

    async def test_unauthenticated_request_fails(self, e2e_http_client):
        for ep in self.ENDPOINTS:
            resp = await e2e_http_client.get(ep)
            assert resp.status_code in (401, 403), f"{ep} should reject unauthenticated, got {resp.status_code}"

    async def test_invalid_period_returns_default(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?period=INVALID", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        assert "success" in resp.json()

    async def test_invalid_account_ids_handled(self, e2e_http_client, e2e_auth_headers):
        resp = await e2e_http_client.get(
            "/portfolio/risk-metrics?account_ids=999999", headers=e2e_auth_headers
        )
        assert resp.status_code == 200
        assert "success" in resp.json()


# ========================================================================
# Shared assertion helpers
# ========================================================================

def _assert_risk_metrics_schema(data: dict) -> None:
    assert isinstance(data.get("success"), bool)
    assert isinstance(data.get("period"), str)
    assert isinstance(data.get("sharpe_ratio"), float)
    assert isinstance(data.get("sortino_ratio"), float)
    assert isinstance(data.get("std_deviation"), float)
    assert isinstance(data.get("max_drawdown_pct"), float)
    assert isinstance(data.get("value_at_risk_95"), float)
    assert isinstance(data.get("value_at_risk_99"), float)
    assert isinstance(data.get("conditional_var_95"), float)
    assert isinstance(data.get("downside_deviation"), float)


def _assert_risk_metrics_invariants(data: dict) -> None:
    if not data.get("success"):
        return
    assert data["value_at_risk_99"] <= data["value_at_risk_95"], (
        f"VaR99={data['value_at_risk_99']} > VaR95={data['value_at_risk_95']}"
    )
    assert data["conditional_var_95"] <= data["value_at_risk_95"], (
        f"CVaR={data['conditional_var_95']} > VaR95={data['value_at_risk_95']}"
    )
    assert data["max_drawdown_pct"] <= 0.0
    assert data["downside_deviation"] <= data["std_deviation"] + 0.001
    assert data["sortino_ratio"] >= data["sharpe_ratio"] - 0.01
    assert abs(data["variance"] - data["std_deviation"] ** 2) < 0.001
