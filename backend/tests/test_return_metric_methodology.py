"""Regression: the headline return metric must be cash-flow aware.

ROOT CAUSE (verified against real data, 2026-09-26)
----------------------------------------------------
The ALL window opens on a newly-created account holding a deposit and ZERO
positions, flat for weeks. `total_return_pct` is naive simple return:

    (V_n - V_0) / V_0

Against a $500 base, a real $201,506 gain renders as 40301.23%. The arithmetic is
correct; the metric is not applicable. Simple return is only valid when net
deposits are constant over the window, which is false for every real window here.

The API already computes TWR and MWR and already declares
`return_methodology="twr"` (portfolio_service.py:1659-1677, 1894) -- the correct
metric was computed, shipped in the payload, and then not surfaced. RiskPanel
rendered `total_return_pct` instead.

These tests pin the property that actually distinguishes the two metrics. Both
assertions are arithmetic identities, not tolerances, so they fail loudly if
simple return is ever promoted back to the headline:

  1. When net deposits are constant, TWR == simple return exactly (they are the
     same function; the chained ratios telescope to V_n/V_0 - 1).
  2. Extending a leading cash-only period leaves TWR bit-identical, because
     each flat sub-period contributes a growth factor of exactly 1.0. Simple
     return is NOT invariant -- this is the 40301% mechanism.
"""
from datetime import date, timedelta

import pytest

from shared.portfolio_stats import (
    annualize_return,
    compute_portfolio_mwr,
    compute_portfolio_twr,
)


def _cash_only_lead_in(days: int) -> list[dict]:
    """A real lead-in: deposit arrives, nothing is bought, value sits flat.

    Mirrors user 1's 2021-01-07 start (value=500.00, net_deposits=500.00).
    """
    snaps = []
    d = date(2021, 1, 7)
    for i in range(days):
        snaps.append({"date": d + timedelta(days=i), "value": 500.0, "net_deposits": 500.0})
    return snaps


def _realistic_series(lead_in_days: int = 35) -> list[dict]:
    """Reproduces the real user-1 ALL series: flat cash lead-in, modest compounding,
    then a large contribution supplying most of the final balance."""
    deployment_deposit = 1_000.0
    daily_growth = 1.0007
    compounding_days = 1_000
    largest_contribution = 150_000.0
    post_contribution_days = 300

    snaps = _cash_only_lead_in(lead_in_days)
    deploy_day = date(2021, 1, 7) + timedelta(days=lead_in_days)

    value = nd = 500.0 + deployment_deposit
    for i in range(compounding_days):
        if i:
            value *= daily_growth
        snaps.append({"date": deploy_day + timedelta(days=i), "value": round(value, 2),
                      "net_deposits": nd})

    post_day = deploy_day + timedelta(days=compounding_days)
    for i in range(post_contribution_days):
        if i == 0:
            value += largest_contribution
            nd += largest_contribution
        else:
            value *= daily_growth
        snaps.append({"date": post_day + timedelta(days=i), "value": round(value, 2),
                      "net_deposits": nd})
    return snaps


def _simple_return_pct(snaps: list[dict]) -> float:
    v0, vn = snaps[0]["value"], snaps[-1]["value"]
    return (vn - v0) / v0 * 100 if v0 > 0 else 0.0


class TestSimpleReturnIsInvalidWithCashFlows:
    """The 40301% mechanism, reproduced deterministically."""

    def test_reproduces_absurd_simple_return(self):
        snaps = _realistic_series()
        simple = _simple_return_pct(snaps)
        assert simple > 10_000, (
            f"fixture no longer reproduces the defect: simple={simple:.2f}%. "
            "If this fails the series shape changed -- re-derive before editing."
        )

    def test_twr_stays_plausible_on_the_same_series(self):
        snaps = _realistic_series()
        twr = compute_portfolio_twr(snaps) * 100
        assert 0 < twr < 1_000, f"TWR should be implausible-free, got {twr:.2f}%"
        # TWR must be orders of magnitude below simple return, not merely lower.
        assert twr < _simple_return_pct(snaps) / 100

    def test_twr_is_invariant_to_cash_only_lead_in_length(self):
        """The property that makes TWR correct here.

        Adding 30 more days of untouched cash before deployment cannot change
        investment performance: every added sub-period has zero growth.
        """
        short = compute_portfolio_twr(_realistic_series(lead_in_days=35))
        long = compute_portfolio_twr(_realistic_series(lead_in_days=65))
        assert short == pytest.approx(long, abs=1e-12), (
            f"TWR moved when only the cash-only lead-in changed: {short} -> {long}. "
            "A leading period with no growth must contribute a factor of exactly 1.0."
        )

    def test_large_contribution_dominates_simple_return_but_not_twr(self):
        """The discriminator: a contribution moves simple return ~60x, TWR barely.

        This is why TWR is the defensible headline and simple return is not.
        """
        with_deposit = _realistic_series()
        without = _realistic_series()[: 35 + 1_000]

        simple_delta = _simple_return_pct(with_deposit) / max(
            _simple_return_pct(without), 1e-9
        )
        twr_with = compute_portfolio_twr(with_deposit)
        twr_without = compute_portfolio_twr(without)
        twr_delta = twr_with / max(twr_without, 1e-9)

        assert simple_delta > 10, f"simple return only moved {simple_delta:.1f}x"
        assert twr_delta < 2.0, f"TWR moved {twr_delta:.2f}x on a pure contribution"


class TestTwrEqualsSimpleReturnWithoutCashFlows:
    """Identity: with constant net deposits the two metrics are the same thing."""

    def test_identity_holds(self):
        snaps = []
        value = 100_000.0
        d = date(2024, 1, 1)
        for i in range(365):
            if i:
                value *= 1.001
            snaps.append({"date": d + timedelta(days=i), "value": round(value, 2),
                          "net_deposits": 0.0})
        twr = compute_portfolio_twr(snaps) * 100
        assert twr == pytest.approx(_simple_return_pct(snaps), abs=1e-9)

    def test_mwr_also_reduces_to_simple_without_cash_flows(self):
        snaps = []
        value = 100_000.0
        d = date(2024, 1, 1)
        for i in range(365):
            if i:
                value *= 1.001
            snaps.append({"date": d + timedelta(days=i), "value": round(value, 2),
                          "net_deposits": 0.0})
        mwr = compute_portfolio_mwr(snaps) * 100
        assert mwr == pytest.approx(_simple_return_pct(snaps), abs=1e-6)

    def test_zero_deposits_and_flat_value_is_zero_not_error(self):
        snaps = [{"date": date(2024, 1, 1) + timedelta(days=i),
                  "value": 1000.0, "net_deposits": 0.0} for i in range(10)]
        assert compute_portfolio_twr(snaps) == 0.0
        assert compute_portfolio_mwr(snaps) == 0.0


class TestMwrRemovesCashFlows:
    def test_deposit_is_not_counted_as_gain(self):
        """A deposit must not read as performance."""
        base = [
            {"date": date(2024, 1, 1), "value": 1000.0, "net_deposits": 1000.0},
            {"date": date(2024, 7, 1), "value": 1000.0, "net_deposits": 1000.0},
        ]
        with_deposit = [
            *base,
            {"date": date(2025, 1, 1), "value": 2000.0, "net_deposits": 2000.0},
        ]
        # Value doubled, but the extra 1000 was deposited, not earned.
        assert compute_portfolio_twr(with_deposit) == pytest.approx(0.0, abs=1e-12)
        assert compute_portfolio_mwr(with_deposit) == pytest.approx(0.0, abs=1e-6)
        # Simple return would report +100% here.
        assert _simple_return_pct(with_deposit) == pytest.approx(100.0)


class TestCagrIsNotDisplayableForShortWindows:
    """Second defect from the same dump: annualizing a week returns ~100%.

    Real values (verified 2026-09-26, user 1): 1W cagr%=99.9, 1M cagr%=52.47,
    3M cagr%=32.97, 1Y cagr%=9.97, ALL cagr%=17.22. The arithmetic is correct at
    every point and the sub-annual figures are useless. CAGR is only meaningful
    once the window approaches a year, so the consumer must gate it.
    """

    @pytest.mark.parametrize(
        "label,twr_pct,days,expected_cagr_pct",
        [
            ("1W", 1.34, 7, 99.9),
            ("1M", 3.17, 27, 52.47),
            ("3M", 7.03, 87, 32.97),
        ],
    )
    def test_sub_annual_cagr_is_absurd(self, label, twr_pct, days, expected_cagr_pct):
        cagr = annualize_return(twr_pct / 100.0, days) * 100
        assert cagr == pytest.approx(expected_cagr_pct, abs=0.5), (
            f"{label} CAGR drifted from the real observed value: {cagr:.2f}%"
        )
        assert cagr > 25.0, f"{label} CAGR={cagr:.1f}% must not be user-facing"

    def test_one_year_cagr_equals_twr(self):
        cagr = annualize_return(0.0997, 365) * 100
        assert cagr == pytest.approx(9.97, abs=0.05)

    def test_all_window_cagr_is_the_plausible_annual_figure(self):
        cagr = annualize_return(1.4811, 2073) * 100
        assert cagr == pytest.approx(17.22, abs=0.5)
        assert 0 < cagr < 50
