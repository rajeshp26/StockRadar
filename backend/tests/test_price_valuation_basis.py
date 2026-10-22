"""Valuation price basis for the portfolio value series (see the 2026-10-18
amendment in docs/price-history-professional-model.md).

`PortfolioRepository.get_all_prices_historical` feeds portfolio VALUATION. The
replay engine applies splits to SHARE counts at their effective dates, so the
share count on date d is the as-traded count; the price it is multiplied by must
therefore be the as-traded (true raw) `close_price`.

`adj_close` is the split-RESTATED series on the current share scale -- a
single-security continuity device for charts/indicators. Pairing it with
as-traded shares double-counts every later split:

    AAPL 2020-08-28  close_price 499.23   (as traded, before the 2020-08-31 4:1)
                     adj_close   124.8075 (x1/4)
    XELA 2022-07-25  close_price 0.1455   (as traded)
                     adj_close   582.0    (x4000: 1:20 + 1:200 reverse splits)
                     -> 60 shares valued 34,920 USD instead of 8.73 USD

Legacy rows written before the refetch carry no `adj_close`; `close_price` is
then the only column, exactly as before the amendment.
"""

from datetime import date
from unittest.mock import MagicMock

from infrastructure.repositories.portfolio_repository import PortfolioRepository


def _repo_with_pages(pages: list[list[dict]]) -> PortfolioRepository:
    """PortfolioRepository wired to a mock client serving `pages` in order."""
    client = MagicMock()
    remaining = list(pages)

    def _execute():
        result = MagicMock()
        result.data = remaining.pop(0) if remaining else []
        return result

    (
        client.table.return_value.select.return_value
        .in_.return_value.lte.return_value
        .order.return_value.order.return_value
        .range.return_value
    ).execute.side_effect = _execute
    return PortfolioRepository(client=client)


def _row(company_id: int, price_date: str, close_price, adj_close) -> dict:
    return {
        "company_id": company_id,
        "price_date": price_date,
        "close_price": close_price,
        "adj_close": adj_close,
    }


class TestValuationPriceBasis:
    """As-traded close is the valuation basis; adj_close is not."""

    def test_uses_as_traded_close_when_both_columns_present(self):
        """XELA 2022-07-25/26 - the real artifact (60 sh valued 34,920 USD)."""
        repo = _repo_with_pages([[
            _row(3124, "2022-07-25", 0.1455, 582.0),
            _row(3124, "2022-07-26", 1.85, 370.0),
        ]])

        series = repo.get_all_prices_historical([3124], date(2022, 7, 26))

        assert series[3124] == [
            (date(2022, 7, 25), 0.1455),
            (date(2022, 7, 26), 1.85),
        ]
        # 60 as-traded shares on 2022-07-25 were worth 8.73 USD, not 34,920 USD.
        assert round(60 * series[3124][0][1], 2) == 8.73

    def test_forward_split_row_uses_as_traded_close(self):
        """AAPL 2020-08-28 closed at 499.23 as traded (adj_close 124.8075)."""
        repo = _repo_with_pages([[_row(69, "2020-08-28", 499.23, 124.8075)]])

        series = repo.get_all_prices_historical([69], date(2020, 8, 28))

        assert series[69] == [(date(2020, 8, 28), 499.23)]

    def test_value_is_continuous_across_a_split_date(self):
        """As-traded prices make the 4:1 split a ~4x inverse move in the price.

        A holding of 1 pre-split share becomes 4 post-split shares. With the
        as-traded basis the position value is continuous (the price divides by
        ~4 while the share count multiplies by 4). With the restated basis the
        pre-split price already sits on the post-split scale, so the same
        position shows a 4x jump in value at the split date.
        """
        repo = _repo_with_pages([[
            _row(69, "2020-08-28", 499.23, 124.8075),
            _row(69, "2020-08-31", 129.04, 129.04),
        ]])

        series = repo.get_all_prices_historical([69], date(2020, 8, 31))
        pre_px = series[69][0][1]
        post_px = series[69][1][1]

        assert pre_px == 499.23
        assert post_px == 129.04
        # 1 share x pre_px  ~=  4 shares x post_px  (a market move, not a 4x jump)
        assert 3.0 < (pre_px / post_px) < 5.0

    def test_legacy_row_without_adj_close_uses_close_price(self):
        """Pre-refetch rows have no adj_close; close_price is the only column."""
        repo = _repo_with_pages([[_row(1, "2015-03-02", 12.5, None)]])

        series = repo.get_all_prices_historical([1], date(2015, 3, 2))

        assert series[1] == [(date(2015, 3, 2), 12.5)]

    def test_null_close_price_falls_back_to_adj_close(self):
        """Defensive: a row with no close_price still yields a usable price."""
        repo = _repo_with_pages([[_row(1, "2015-03-02", None, 12.5)]])

        series = repo.get_all_prices_historical([1], date(2015, 3, 2))

        assert series[1] == [(date(2015, 3, 2), 12.5)]
