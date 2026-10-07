"""Tier 1 of the price cascade must not price history with future information.

The cascade's contract is "the most recent price that was knowable on
snapshot_date". A price dated after snapshot_date is lookahead: it makes
historical rows unreproducible, because the same snapshot_date re-priced after
a newer quote lands yields a different total. That is what put a 449-day-old
negative price age and a +5.7% single-day jump into account 7's 2025-06-30 row
while the quality flag still read OK.

The guard also has to bound age in BOTH directions. A price older than
stale_threshold_days is stale and must reach Tier 2, otherwise Tier 2 is
unreachable and every row is stamped OK.
"""
from datetime import date, timedelta

from shared.time_utils import now_utc
from decimal import Decimal

import pytest

from shared.snapshot_builder import PriceTier, _resolve_holding_price

SNAPSHOT = date(2025, 6, 30)
SYMBOL = "META"
COMPANY = 145


def _resolve(prices, history=None, snapshot_date=SNAPSHOT, threshold=30):
    return _resolve_holding_price(
        company_id=COMPANY,
        symbol=SYMBOL,
        avg_cost=None,
        latest_prices=prices,
        price_history=history if history is not None else {},
        snapshot_date=snapshot_date,
        stale_threshold_days=threshold,
    )


def test_price_dated_after_snapshot_is_never_current():
    price, tier, price_date = _resolve(
        {COMPANY: {"price": 735.68, "price_date": SNAPSHOT + timedelta(days=1)}}
    )
    assert tier != PriceTier.CURRENT


def test_lookahead_price_falls_through_to_forward_fill():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=1), 644.88)]}
    price, tier, price_date = _resolve(
        {COMPANY: {"price": 735.68, "price_date": SNAPSHOT + timedelta(days=449)}},
        history=history,
    )
    assert tier == PriceTier.FORWARD_FILL
    assert price == Decimal("644.88")
    assert price_date == SNAPSHOT - timedelta(days=1)


def test_undated_price_is_not_current():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=2), 640.0)]}
    price, tier, _ = _resolve({COMPANY: {"price": 735.68}}, history=history)
    assert tier == PriceTier.FORWARD_FILL
    assert price == Decimal("640.0")


def test_price_older_than_threshold_is_not_current():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=60), 500.0)]}
    price, tier, _ = _resolve(
        {COMPANY: {"price": 735.68, "price_date": SNAPSHOT - timedelta(days=90)}},
        history=history,
        threshold=30,
    )
    assert tier == PriceTier.FORWARD_FILL
    assert price == Decimal("500.0")


@pytest.mark.parametrize("days_before,threshold", [(0, 0), (0, 30), (5, 30), (30, 30)])
def test_price_knowable_on_snapshot_date_is_current(days_before, threshold):
    price_date = SNAPSHOT - timedelta(days=days_before)
    price, tier, returned_date = _resolve(
        {COMPANY: {"price": 644.88, "price_date": price_date}},
        snapshot_date=SNAPSHOT,
        threshold=threshold,
    )
    assert tier == PriceTier.CURRENT
    assert price == Decimal("644.88")
    assert returned_date == price_date


def test_future_quotes_do_not_influence_historical_pricing():
    """The property the defect violated: a later quote must not move history.

    Both calls carry the same knowable information (the history row); they differ
    only in whether a post-snapshot quote is also present, which is the sole
    variable lookahead could act through.
    """
    history = {COMPANY: [(SNAPSHOT - timedelta(days=1), 644.88)]}
    clean_price, clean_tier, _ = _resolve(
        {COMPANY: {"price": 644.88, "price_date": SNAPSHOT - timedelta(days=1)}},
        history=history,
    )
    contaminated_price, contaminated_tier, _ = _resolve(
        {COMPANY: {"price": 735.68, "price_date": SNAPSHOT + timedelta(days=400)}},
        history=history,
    )
    assert contaminated_price == clean_price == Decimal("644.88")
    assert clean_tier == PriceTier.CURRENT
    assert contaminated_tier != PriceTier.CURRENT


def test_no_tier_reports_a_price_date_after_the_snapshot():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=1), 644.88)]}
    for price_date in (
        SNAPSHOT + timedelta(days=1),
        SNAPSHOT + timedelta(days=449),
        SNAPSHOT - timedelta(days=500),
    ):
        _, _, returned = _resolve(
            {COMPANY: {"price": 735.68, "price_date": price_date}}, history=history
        )
        assert returned is None or returned <= SNAPSHOT


def _row(latest_price, snapshot_date=SNAPSHOT, stale_threshold_days=30):
    from shared.snapshot_builder import build_snapshot_row

    return build_snapshot_row(
        account_id=7,
        snapshot_date=snapshot_date,
        holdings_state=[{
            "company_id": COMPANY,
            "symbol": SYMBOL,
            "company_name": SYMBOL,
            "quantity": 100,
            "total_cost": Decimal("50000"),
            "average_cost": Decimal("500"),
            "price_currency": "CAD",
        }],
        cash_balance=Decimal("1000"),
        net_deposits=Decimal("51000"),
        prices_by_company={COMPANY: latest_price},
        job_id="test",
        stale_threshold_days=stale_threshold_days,
    )["holdings_json"][0]


def test_reported_price_age_is_never_negative():
    holding = _row({"price": 735.68, "price_date": SNAPSHOT + timedelta(days=449)})
    assert holding["price_age_days"] is None or holding["price_age_days"] >= 0


def test_reported_price_age_reflects_the_resolved_price_not_the_raw_latest():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=40), 500.0)]}
    from shared.snapshot_builder import build_snapshot_row

    row = build_snapshot_row(
        account_id=7,
        snapshot_date=SNAPSHOT,
        holdings_state=[{
            "company_id": COMPANY, "symbol": SYMBOL, "company_name": SYMBOL,
            "quantity": 100, "total_cost": Decimal("50000"),
            "average_cost": Decimal("500"), "price_currency": "CAD",
        }],
        cash_balance=Decimal("1000"),
        net_deposits=Decimal("51000"),
        prices_by_company={COMPANY: {"price": 735.68, "price_date": SNAPSHOT + timedelta(days=449)}},
        job_id="test",
        price_history=history,
    )["holdings_json"][0]
    assert row["current_price"] == 500.0
    assert row["price_age_days"] == 40


def test_lookahead_price_does_not_report_a_current_quality_flag():
    history = {COMPANY: [(SNAPSHOT - timedelta(days=400), 500.0)]}
    from shared.snapshot_builder import build_snapshot_row

    row = build_snapshot_row(
        account_id=7,
        snapshot_date=SNAPSHOT,
        holdings_state=[{
            "company_id": COMPANY, "symbol": SYMBOL, "company_name": SYMBOL,
            "quantity": 100, "total_cost": Decimal("50000"),
            "average_cost": Decimal("500"), "price_currency": "CAD",
        }],
        cash_balance=Decimal("1000"),
        net_deposits=Decimal("51000"),
        prices_by_company={COMPANY: {"price": 735.68, "price_date": SNAPSHOT + timedelta(days=449)}},
        job_id="test",
        stale_threshold_days=30,
        price_history=history,
    )["holdings_json"][0]
    assert row["price_data_quality"] == "STALE_PRICE"


def _bare_row(snapshot_date):
    from shared.snapshot_builder import build_snapshot_row

    return build_snapshot_row(
        account_id=7,
        snapshot_date=snapshot_date,
        holdings_state=[],
        cash_balance=Decimal("0"),
        net_deposits=Decimal("0"),
        prices_by_company={},
        job_id="test",
    )


@pytest.mark.parametrize("offset", [1, 4, 365])
def test_future_snapshot_date_is_rejected(offset):
    today = now_utc().date()
    with pytest.raises(ValueError, match="future"):
        _bare_row(today + timedelta(days=offset))


def test_today_and_past_snapshot_dates_are_accepted():
    today = now_utc().date()
    assert _bare_row(today)["snapshot_date"] == today.isoformat()
    assert _bare_row(today - timedelta(days=400))["snapshot_date"] == (today - timedelta(days=400)).isoformat()
