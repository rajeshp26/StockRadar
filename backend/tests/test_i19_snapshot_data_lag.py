"""I19 -- snapshot date may lead the provider data date by one day; stay honest.

Observed in the 2026-11-14 worker log: a snapshot labelled 2026-11-15 was built
while the SDK's dataset update time was 2026-11-14T05:08:50Z. That is the normal
daily-publish lag (EOD prices are published the next morning), not a future-date
bug: the future-date guard already rejects a snapshot_date later than today.

What must hold is that the snapshot is priced with the *last knowable* prices and
discloses their true date -- it must never stamp a one-day-old price as if it
were dated on the snapshot. `build_snapshot_row` already records per-position
`price_date` / `price_age_days` from the resolved price; these tests lock that in
for the exact I19 scenario.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from shared.snapshot_builder import PriceTier, build_snapshot_row
from shared.time_utils import now_utc

COMPANY = 69  # AAPL fixture
SNAPSHOT = now_utc().date()  # "today" -- the date the job would pick
DATA_DATE = SNAPSHOT - timedelta(days=1)  # 2026-11-14-style one-day publish lag


def _row():
    return build_snapshot_row(
        account_id=7,
        snapshot_date=SNAPSHOT,
        holdings_state=[{
            "company_id": COMPANY,
            "symbol": "AAPL",
            "company_name": "Apple",
            "quantity": 100,
            "total_cost": Decimal("50000"),
            "average_cost": Decimal("500"),
            "price_currency": "USD",
        }],
        cash_balance=Decimal("1000"),
        net_deposits=Decimal("51000"),
        # The provider's "latest" price is dated a day before the snapshot.
        prices_by_company={COMPANY: {"price": 210.0, "price_date": DATA_DATE}},
        job_id="i19",
        stale_threshold_days=30,
    )


def test_snapshot_date_leads_data_date_is_accepted():
    row = _row()
    assert row["snapshot_date"] == SNAPSHOT.isoformat()


def test_position_discloses_the_true_data_date_not_the_snapshot_date():
    pos = _row()["holdings_json"][0]
    assert pos["price_date"] == DATA_DATE.isoformat()
    assert pos["price_age_days"] == 1


def test_one_day_old_data_is_current_tier_not_mislabelled():
    pos = _row()["holdings_json"][0]
    # Within the staleness threshold, the last knowable price is legitimately
    # CURRENT; the age/date fields are what keep that honest.
    assert pos["price_tier"] == PriceTier.CURRENT.value
    assert pos["price_data_quality"] == "OK"


def test_snapshot_total_uses_the_disclosed_price():
    row = _row()
    # 100 * 210 = 21,000 market value + 1,000 cash; cost 50,000.
    assert row["holdings_market_value"] == 21000.0
    assert row["total_value"] == 22000.0


def test_future_snapshot_date_still_rejected():
    """I19's one-day lead is data lag, not a future snapshot -- that stays illegal."""
    import pytest

    with pytest.raises(ValueError, match="future"):
        build_snapshot_row(
            account_id=7,
            snapshot_date=SNAPSHOT + timedelta(days=1),
            holdings_state=[],
            cash_balance=Decimal("0"),
            net_deposits=Decimal("0"),
            prices_by_company={},
            job_id="i19",
        )
