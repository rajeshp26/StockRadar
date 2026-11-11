"""System tests for AC-1: the portfolio performance series served by the real stack.

AC-1 (verification_output/fixtures/AC7-REAL-PLAN.md) is tagged [browser], which routes two
gates: g6 proves the chart renders the payload, and g17 proves the payload itself is a real
series from the real database. These tests are the g17 half. They are black-box -- they log in
through Supabase Auth over HTTP and call the backend's public endpoints -- so they cannot share
the implementation's assumptions.

The data they run against is the live Supabase data behind the running backend. What was
profiled from it, and when, is recorded in data/MANIFEST.json; the monetary values are
deliberately not reproduced in the repository, only the structural facts the assertions were
derived from.
"""
from datetime import date

import requests

from test_support import _base, get, series

# Money is served as JSON floats, so equality is asserted at a cent, not at 1e-15.
CENT = 0.01


def _days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def test_performance_all_series_is_a_consistent_time_series():
    """AC-1 kind:positive shape:multi_account shape:monthly_snapshots the ALL series is one ordered, positive, two-decimal time series"""
    body = series("ALL")
    snaps = body["snapshots"]

    assert len(snaps) >= 12, "ALL returned only %d snapshot(s)" % len(snaps)
    dates = [s["date"] for s in snaps]
    assert dates == sorted(dates), "snapshots are not ordered by date"
    assert len(set(dates)) == len(dates), "the series repeats a date"

    for s in snaps:
        assert s["value"] > 0, "snapshot %s has a non-positive value" % s["date"]
        for field in ("value", "net_deposits", "cost_basis", "cash_balance"):
            amount = float(s[field])
            assert abs(round(amount, 2) - amount) < 1e-6, (
                "%s is not a two-decimal amount: %r" % (field, amount))

    # Deposits accumulate: a snapshot can never report fewer net deposits than the one before it.
    deposits = [float(s["net_deposits"]) for s in snaps]
    for earlier, later in zip(deposits, deposits[1:]):
        assert later >= earlier - CENT, (
            "net_deposits fell from %.2f to %.2f" % (earlier, later))


def test_performance_all_covers_the_full_history():
    """AC-1 kind:positive shape:long_history the ALL window spans the recorded history and ends at the latest valuation"""
    snaps = series("ALL")["snapshots"]

    first, last = snaps[0]["date"], snaps[-1]["date"]
    assert _days_between(first, last) >= 365, "ALL spans only %s..%s" % (first, last)
    # A stale terminal point would make every period view stale with it.
    assert (date.today() - date.fromisoformat(last)).days <= 120, (
        "the series ends at %s, which is not the latest valuation" % last)


def test_period_window_agrees_with_all_on_shared_dates():
    """AC-1 kind:boundary the YTD and 1Y windows agree with ALL on every shared date and on the terminal value"""
    all_snaps = series("ALL")["snapshots"]
    by_date = {s["date"]: float(s["value"]) for s in all_snaps}

    for period in ("YTD", "1Y"):
        snaps = series(period)["snapshots"]
        assert snaps, "period=%s returned no snapshots" % period

        shared = [s for s in snaps if s["date"] in by_date]
        assert shared, "period=%s shares no date with ALL" % period
        for s in shared:
            assert abs(float(s["value"]) - by_date[s["date"]]) <= CENT, (
                "period=%s reports %.2f on %s, ALL reports %.2f"
                % (period, float(s["value"]), s["date"], by_date[s["date"]]))

        # The window is a view of the same series, so the terminal valuation must be identical.
        assert abs(float(snaps[-1]["value"]) - float(all_snaps[-1]["value"])) <= CENT, (
            "period=%s ends at %.2f, ALL ends at %.2f"
            % (period, float(snaps[-1]["value"]), float(all_snaps[-1]["value"])))


def test_performance_requires_a_bearer_token():
    """AC-1 kind:abuse an unauthenticated or forged request never returns a portfolio series"""
    for label, headers in (
        ("no header", {}),
        ("forged token", {"Authorization": "Bearer not-a-jwt"}),
    ):
        resp = requests.get(_base() + "/portfolio/performance",
                            params={"period": "ALL"}, headers=headers, timeout=60)
        assert resp.status_code == 401, (
            "%s answered %d instead of 401" % (label, resp.status_code))
        assert "snapshots" not in resp.text, "%s returned series data" % label


def test_unknown_account_filter_returns_no_snapshots():
    """AC-1 kind:negative an account id that is not the user's yields an empty series, never the whole portfolio"""
    whole = series("ALL")["snapshots"]
    assert whole, "the unfiltered series is empty; this test would prove nothing"

    resp = get("/portfolio/performance", period="ALL", account_ids="999999")
    assert resp.status_code in (200, 403, 404), (
        "an unknown account answered %d" % resp.status_code)
    if resp.status_code == 200:
        assert resp.json()["snapshots"] == [], (
            "an unknown account id returned %d snapshot(s)"
            % len(resp.json()["snapshots"]))


def test_repeated_request_returns_the_same_series():
    """AC-1 kind:idempotency two identical reads return the same series; reading does not mutate the portfolio"""
    first = series("ALL")["snapshots"]
    second = series("ALL")["snapshots"]

    assert len(first) == len(second), (
        "the same request returned %d then %d snapshot(s)" % (len(first), len(second)))
    assert first == second, "the same request returned different values"
