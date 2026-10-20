"""Tests for the chart series integrity gate.

The gate is only worth having if it fails on the defect class it exists to catch. These tests
pin both directions: an unexplained value collapse must FAIL, and a drop that a securities
transfer accounts for must PASS. The net_deposits invariant is pinned the same way: a change
with no ledger event behind it FAILS, and a withdrawal or deposit that the ledger records
PASSES (net_deposits is net of withdrawals, so a fall is legitimate when it is real).

A gate that only ever passes is worse than no gate, because it reports safety it has not
checked.

The pure functions are tested without a database or a series dump.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
for p in (str(BACKEND), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from gate_chart_series_integrity import (  # noqa: E402
    MATERIAL_MOVE_PCT,
    classify_events,
    evaluate_series,
    scope_accounts,
    sum_deposit_flows,
)


def _snap(d: str, value: str, nd: str = "10000") -> dict:
    return {"date": d, "value": value, "net_deposits": nd, "cost_basis": value}


# --- the defect class: a drop nothing explains -------------------------------------------

def test_unexplained_collapse_fails():
    snaps = [_snap("2024-09-30", "71064.52"), _snap("2024-12-31", "48044.29")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert len(ivs) == 1
    assert abs(ivs[0].pct_change) > MATERIAL_MOVE_PCT
    assert ivs[0].explained == Decimal("0")
    assert ivs[0].residual_pct > 20.0
    assert ivs[0].violations, "an unexplained 32% drop must produce a violation"
    assert any("unexplained residual" in v for v in ivs[0].violations)


def test_transfer_explained_drop_passes():
    """The real 2024-12-31 case: transfers out exceed the drop, so it is explained."""
    snaps = [_snap("2024-09-30", "71064.52"), _snap("2024-12-31", "48044.29")]
    events = [("2024-11-15", "transfer_out", Decimal("27874.86"))]

    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert len(ivs) == 1
    assert ivs[0].transfer_out == Decimal("27874.86")
    assert ivs[0].explained == Decimal("27874.86")
    assert ivs[0].residual < 0, "transfers exceed the drop, so nothing is left unexplained"
    assert not [v for v in ivs[0].violations if "unexplained residual" in v]


def test_transfer_outside_window_does_not_explain():
    """Events outside the interval must not be allowed to explain it."""
    snaps = [_snap("2024-09-30", "71064.52"), _snap("2024-12-31", "48044.29")]
    events = [("2024-01-05", "transfer_out", Decimal("27874.86"))]

    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert ivs[0].explained == Decimal("0")
    assert any("unexplained residual" in v for v in ivs[0].violations)


def test_partial_transfer_leaves_residual_and_fails():
    """A transfer too small to cover the drop must not pass."""
    snaps = [_snap("2024-09-30", "71064.52"), _snap("2024-12-31", "48044.29")]
    events = [("2024-11-15", "transfer_out", Decimal("1000"))]

    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert any("unexplained residual" in v for v in ivs[0].violations)


def test_within_tolerance_drift_is_not_flagged():
    """A sub-material move is left alone; only material moves are attributed."""
    snaps = [_snap("2024-09-30", "100000"), _snap("2024-12-31", "85000")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert abs(ivs[0].pct_change) < MATERIAL_MOVE_PCT
    assert ivs[0].violations == []


def test_large_increase_is_reported_but_never_fails():
    """Appreciation is not a defect: only decreases are gated.

    Regression: gating both directions flagged a +1164% early-account build-out as an
    unexplained residual, when the rise was market drift the gate does not model.
    """
    snaps = [_snap("2021-01-07", "500.00"), _snap("2021-03-31", "6321.29")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert ivs[0].change > 0
    assert abs(ivs[0].pct_change) > MATERIAL_MOVE_PCT
    assert ivs[0].residual_pct > 20.0, "the residual is still measured for reporting"
    assert not [v for v in ivs[0].violations if "unexplained residual" in v]


def test_large_decrease_is_still_gated():
    """The drop direction must remain strict after narrowing to drops only."""
    snaps = [_snap("2021-01-07", "6321.29"), _snap("2021-03-31", "500.00")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert ivs[0].change < 0
    assert any("unexplained residual" in v for v in ivs[0].violations)


def test_usd_event_amounts_are_converted_to_cad():
    """Snapshots are CAD; a USD transfer must be converted before it can explain a CAD drop.

    Regression: the gate compared raw USD magnitudes against CAD values, understating every
    USD explanation by the FX rate and flagging correct data.
    """
    from datetime import date
    from decimal import Decimal
    import gate_chart_series_integrity as gate

    original = gate._FX_RATES
    gate._FX_RATES = [(date(2024, 12, 1), Decimal("1.35")),
                      (date(2024, 12, 31), Decimal("1.40"))]
    try:
        # as-of the event date, never the later rate
        assert gate.to_reporting_currency(Decimal("100"), "USD", date(2024, 12, 23)) \
            == Decimal("135.00")
        assert gate.to_reporting_currency(Decimal("100"), "USD", date(2024, 12, 31)) \
            == Decimal("140.00")
        assert gate.to_reporting_currency(Decimal("100"), "CAD", date(2024, 12, 23)) \
            == Decimal("100")
        assert gate.to_reporting_currency(Decimal("100"), "EUR", date(2024, 12, 23)) \
            == Decimal("100")
    finally:
        gate._FX_RATES = original


def test_over_explained_drop_passes():
    """Events covering MORE than the drop is not a defect.

    Regression: residual_pct was computed with abs(), so a window whose events over-explained
    the drop was reported as a violation. That is the 2024-12-31 case once event amounts are
    FX-converted - it failed with a -17,332.93 residual purely because it was over-explained.
    """
    snaps = [_snap("2024-09-30", "71064.52"), _snap("2024-12-31", "48044.29")]
    events = [("2024-12-23", "transfer_out", Decimal("40000"))]
    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert ivs[0].change < 0
    assert ivs[0].residual < 0, "events explain more than the drop"
    assert ivs[0].residual_pct < 0, "residual_pct is signed, not absolute"
    assert not any("unexplained residual" in v for v in ivs[0].violations)


# --- structural invariants --------------------------------------------------------------
#
# net_deposits is net of withdrawals. A truthful series changes it by exactly the
# deposit/withdrawal events in the window - no more (phantom deposit) and no less
# (dropped withdrawal). A withdrawal that matches the fall is correct data and must
# PASS; a change with no ledger event behind it is the defect.

def test_net_deposits_falling_is_a_violation():
    """An unexplained fall is still corruption, not a withdrawal."""
    snaps = [_snap("2024-09-30", "100000", nd="50000"),
             _snap("2024-12-31", "98000", nd="40000")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert any("net_deposits fell" in v for v in ivs[0].violations)


def test_net_deposits_rising_is_a_violation():
    """A rise must be a deposit event; a phantom deposit is corruption too.

    This direction is what the previous 'never falls' rule could not see.
    """
    snaps = [_snap("2024-09-30", "100000", nd="50000"),
             _snap("2024-12-31", "100000", nd="60000")]
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert any("net_deposits rose" in v for v in ivs[0].violations)


def test_withdrawal_matching_the_fall_passes():
    """Regression: the replay writer dropped outflows, so every legitimate
    withdrawal looked like an unexplained net_deposits fall. It is now explained
    by the ledger event, and a fall of exactly that size must not be flagged."""
    snaps = [_snap("2024-09-30", "100000", nd="50000"),
             _snap("2024-12-31", "95000", nd="49567")]
    events = [("2024-11-15", "deposit", Decimal("-433"))]
    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert ivs[0].deposit_flow == Decimal("-433")
    assert not any("net_deposits" in v for v in ivs[0].violations)


def test_deposit_matching_the_rise_passes():
    snaps = [_snap("2024-09-30", "100000", nd="50000"),
             _snap("2024-12-31", "102000", nd="52000")]
    events = [("2024-11-15", "deposit", Decimal("2000"))]
    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert not any("net_deposits" in v for v in ivs[0].violations)


def test_partial_withdrawal_explanation_is_a_violation():
    """Only part of the fall is on the ledger - still a violation."""
    snaps = [_snap("2024-09-30", "100000", nd="50000"),
             _snap("2024-12-31", "95000", nd="49000")]
    events = [("2024-11-15", "deposit", Decimal("-433"))]
    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert any("net_deposits fell" in v for v in ivs[0].violations)


def test_deposit_event_is_excluded_from_cash_kind():
    """The deposit kind is separate; cash/transfer classification is unchanged."""
    events = [("2024-11-15", "deposit", Decimal("-433")),
              ("2024-11-15", "cash", Decimal("-433"))]
    cash, in_v, out_v = classify_events(events, "2024-10-01", "2024-12-31")

    assert cash == Decimal("-433")
    assert in_v == Decimal("0")
    assert out_v == Decimal("0")
    assert sum_deposit_flows(events, "2024-10-01", "2024-12-31") == Decimal("-433")


def test_dates_out_of_order_are_flagged():
    snaps = [{"date": "2024-12-31", "value": "100", "net_deposits": "10"},
             {"date": "2024-09-30", "value": "90", "net_deposits": "10"}]
    ordered = sorted(snaps, key=lambda s: s["date"])
    ivs = evaluate_series(snaps, [], tolerance=0.20)

    assert [s["date"] for s in ordered] == ["2024-09-30", "2024-12-31"]
    assert ivs[0].start == "2024-09-30", "evaluation must sort before walking"


def test_short_series_yields_nothing():
    assert evaluate_series([], [], 0.20) == []
    assert evaluate_series([_snap("2024-09-30", "100")], [], 0.20) == []


# --- window boundaries -------------------------------------------------------------------

def test_classify_window_is_open_on_left_closed_on_right():
    events = [
        ("2024-09-30", "cash", Decimal("100")),      # exactly at lo -> excluded
        ("2024-10-01", "cash", Decimal("200")),      # inside -> included
        ("2024-12-31", "transfer_out", Decimal("300")),  # exactly at hi -> included
        ("2025-01-01", "cash", Decimal("400")),      # after hi -> excluded
    ]

    cash, in_v, out_v = classify_events(events, "2024-09-30", "2024-12-31")

    assert cash == Decimal("200")
    assert in_v == Decimal("0")
    assert out_v == Decimal("300")


def test_cash_movement_counts_as_explanation():
    snaps = [_snap("2024-09-30", "100000"), _snap("2024-12-31", "60000")]
    events = [("2024-11-01", "cash", Decimal("41000"))]

    ivs = evaluate_series(snaps, events, tolerance=0.20)

    assert ivs[0].explained == Decimal("41000")
    assert not any("unexplained residual" in v for v in ivs[0].violations)


# --- scope resolution --------------------------------------------------------------------

def test_numeric_scope_is_a_user_id():
    accounts = {1: [7, 8, 9], 49: [12]}
    assert scope_accounts("1", accounts) == {7, 8, 9}
    assert scope_accounts("49", accounts) == {12}


def test_user_acct_scope_is_a_single_account():
    accounts = {1: [7, 8, 9]}
    assert scope_accounts("user1_acct9", accounts) == {9}


def test_unknown_scope_resolves_to_empty_not_a_guess():
    assert scope_accounts("nonsense", {1: [7]}) == set()
    assert scope_accounts("999", {1: [7]}) == set()