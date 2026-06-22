"""Unit tests for _compute_overview_from_holdings helper."""

import sys
from unittest import mock

# Mock broken import chain BEFORE importing api.portfolio.
# These are pre-existing project-wide issues (unused/dead imports in
# portfolio_service.py and broken class name references).
sys.modules["domain.model_types"] = mock.MagicMock()

# Now import — the chain (api.portfolio -> portfolio_service -> ...) is clean
from api.portfolio import _compute_overview_from_holdings


def test_overview_from_single_holding():
    """$1000 value, $800 cost -> $200 gain, 25%."""
    holdings = [
        {"current_value": 1000.0, "total_cost": 800.0}
    ]
    result = _compute_overview_from_holdings(holdings, [], 1, 0.0)
    assert result["total_value"] == 1000.0
    assert result["total_cost_basis"] == 800.0
    assert result["total_gain_loss"] == 200.0
    assert result["total_gain_loss_pct"] == 25.0
    assert result["holdings_count"] == 1
    assert result["accounts_count"] == 0


def test_overview_from_multiple_holdings():
    """Sum across 5 holdings matches expected totals."""
    holdings = [
        {"current_value": 1000.0, "total_cost": 800.0},
        {"current_value": 2000.0, "total_cost": 1500.0},
        {"current_value": 500.0, "total_cost": 600.0},
        {"current_value": 3000.0, "total_cost": 2500.0},
        {"current_value": 1500.0, "total_cost": 1200.0},
    ]
    result = _compute_overview_from_holdings(holdings, [], 1, 0.0)
    assert result["total_value"] == 8000.0
    assert result["total_cost_basis"] == 6600.0
    assert result["total_gain_loss"] == 1400.0
    assert result["holdings_count"] == 5


def test_overview_no_holdings():
    """Empty list -> $0 total, 0 count."""
    result = _compute_overview_from_holdings([], [], 1, 0.0)
    assert result["total_value"] == 0.0
    assert result["total_cost_basis"] == 0.0
    assert result["total_gain_loss"] == 0.0
    assert result["total_gain_loss_pct"] == 0.0
    assert result["holdings_count"] == 0


def test_overview_zero_cost_basis():
    """Total gain=0, cost=0 -> gain_pct=0 (no div-by-zero)."""
    result = _compute_overview_from_holdings([], [], 1, 0.0)
    assert result["total_gain_loss_pct"] == 0.0
    assert result["total_value"] == 0.0


def test_overview_includes_ytd_dividends():
    """$50 ytd_dividends appears in output."""
    holdings = [
        {"current_value": 1000.0, "total_cost": 800.0}
    ]
    result = _compute_overview_from_holdings(holdings, [], 1, 50.0)
    assert result["ytd_dividends"] == 50.0


def test_overview_negative_gain():
    """Negative gain correctly reflected."""
    holdings = [
        {"current_value": 500.0, "total_cost": 1000.0}
    ]
    result = _compute_overview_from_holdings(holdings, [], 1, 0.0)
    assert result["total_gain_loss"] == -500.0
    assert result["total_gain_loss_pct"] == -50.0


def test_overview_with_accounts():
    """accounts_count reflects number of accounts."""
    accounts = [{"account_id": 1}, {"account_id": 2}, {"account_id": 3}]
    result = _compute_overview_from_holdings([], accounts, 1, 0.0)
    assert result["accounts_count"] == 3
