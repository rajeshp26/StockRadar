"""Split adjustment for the transaction-derived lot replay (I2).

Two independent derivations claim to answer "how many shares are held":

  - the replay engine, which applies `split` events to the position, and
  - cdr_utils._accumulate_lots, which summed raw transaction quantities.

They disagreed for every split company, and the disagreement is exact split factors
(SPCE 30 vs 1.5, NFLX 73 vs 730, NYCB 30 vs 9.9999). classify_lot_legs() therefore
refused to split those holdings and logged "Replay lot split declined", silently
falling back to the company-keyed CDR verdict -- which misprices a mixed CDR/direct
position.

Three defects are specified here, because fixing only the first leaves the other two:

1. No split adjustment. Raw quantities are pre-split; stored quantities are post-split.
2. The wrong activity filter. Everything except Dividend was summed as a share move,
   but `quantity` carries a CASH amount for every other non-trade type. Live evidence:
   account 7 / ETHY holds 80 shares and summed to 90.616.
3. Same-date ordering. Replay sorted by date only, so whether a split applied to a
   movement on its own effective date depended on insertion order. The live data settles
   it: a -0.3 SELL on the split date at the POST-split unit price.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Cases copied verbatim from the live dataset these bugs were found on.
# ---------------------------------------------------------------------------

# account 7 / company 3157 (ETHY): 80 real shares, 90.616 when cash rows are summed.
ETHY_TRADE = ("2022-10-04", "Trade", "80")
ETHY_CASH_ROWS = [
    ("2022-11-07", "Dividend", "2.16"),
    ("2022-11-07", "ReturnOfCapital", "-2.16"),
    ("2023-12-07", "Dividend", "1.68"),
    ("2023-12-07", "ReturnOfCapital", "-1.68"),
    ("2024-12-23", "NonCashDistribution", "29.84"),
]

# account 9 / company 3110 (IVR): 85 + 108 held, 1:10 reverse split on 2022-06-06,
# and a -0.3 fractional-share SELL booked on that same date at the post-split price.
IVR_ROWS = [
    ("2022-04-07", "Trade", "85"),
    ("2022-04-26", "Trade", "108"),
    ("2022-06-06", "Trade", "-0.3"),
]
IVR_SPLIT = (date(2022, 6, 6), Decimal("0.1"))


def _row(cid, on, activity, qty, account=9, cdr=False):
    return {
        "account_id": account,
        "company_id": cid,
        "transaction_date": on,
        "activity_type": activity,
        "quantity": qty,
        "security_name": "META CDR (CAD Hedged)" if cdr else "META",
        "raw_data": None,
    }


class _TableClient:
    """Table-aware Supabase stand-in: transactions and splits come from separate lists.

    The lot derivation reads both, so a fake that serves one list for every table would
    hide exactly the bug this file specifies (the schedule being ignored).
    """

    def __init__(self, tables):
        self.tables = tables
        self._name = None
        self._filters = {}
        self._range = (0, 999)

    def table(self, name):
        self._name = name
        self._filters = {}
        self._range = (0, 999)
        return self

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def in_(self, col, vals):
        self._filters[col] = set(vals)
        return self

    def order(self, _col):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = list(self.tables.get(self._name, []))
        for col, val in self._filters.items():
            if isinstance(val, set):
                rows = [r for r in rows if r.get(col) in val]
            else:
                rows = [r for r in rows if r.get(col) == val]
        start, end = self._range
        return SimpleNamespace(data=rows[start : end + 1])


class TestSplitScheduleParsing:
    def test_two_column_factor_is_exact_decimal(self):
        from shared.split_utils import parse_split_factor_decimal

        assert parse_split_factor_decimal("1:10") == Decimal("0.1")
        assert parse_split_factor_decimal("10:1") == Decimal("10")
        assert parse_split_factor_decimal("16:100") == Decimal("0.16")

    def test_unparseable_is_a_no_op_not_an_error(self):
        from shared.split_utils import parse_split_factor_decimal

        for raw in (None, "", "3", "x:y", "1:-5"):
            assert parse_split_factor_decimal(raw) == Decimal(1), raw
        # A zero multiplier is faithful to the input, not silently turned into a no-op;
        # split_schedule_from_rows() is where degenerate rows are dropped.
        assert parse_split_factor_decimal("0:1") == Decimal(0)

    def test_schedule_drops_a_degenerate_multiplier(self):
        from shared.split_utils import split_schedule_from_rows

        schedule = split_schedule_from_rows(
            [
                {"company_id": 1, "report_date": "2022-06-06", "split_factor": "0:1"},
                {"company_id": 1, "report_date": "2023-06-06", "split_factor": "1:10"},
            ]
        )
        assert schedule[1] == [(date(2023, 6, 6), Decimal("0.1"))]

    def test_schedule_is_sorted_and_keyed_by_company(self):
        from shared.split_utils import split_schedule_from_rows

        schedule = split_schedule_from_rows(
            [
                {"company_id": 2, "report_date": "2023-01-02", "split_factor": "1:5"},
                {"company_id": 1, "report_date": "2022-06-06", "split_factor": "1:10"},
                {"company_id": 1, "report_date": "2020-01-01", "split_factor": "10:1"},
                {"company_id": None, "report_date": "2020-01-01", "split_factor": "2:1"},
                {"company_id": 3, "report_date": None, "split_factor": "2:1"},
            ]
        )
        assert [d for d, _ in schedule[1]] == [date(2020, 1, 1), date(2022, 6, 6)]
        assert schedule[2] == [(date(2023, 1, 2), Decimal("0.2"))]
        assert None not in schedule
        assert 3 not in schedule


class TestBoundaryRule:
    """A split rescales at the start of its effective date; that day's trades are post-split."""

    def test_movement_on_the_split_date_is_not_adjusted(self):
        from shared.split_utils import split_adjustment_factor

        assert (
            split_adjustment_factor([IVR_SPLIT], date(2022, 6, 6), date(2022, 6, 6))
            == Decimal(1)
        )

    def test_movement_before_the_split_date_is_adjusted(self):
        from shared.split_utils import split_adjustment_factor

        assert split_adjustment_factor(
            [IVR_SPLIT], date(2022, 4, 26), date(2022, 6, 6)
        ) == Decimal("0.1")

    def test_a_split_after_the_as_of_date_has_not_happened(self):
        from shared.split_utils import split_adjustment_factor

        assert (
            split_adjustment_factor([IVR_SPLIT], date(2022, 4, 26), date(2022, 5, 31))
            == Decimal(1)
        )

    def test_multiple_splits_multiply(self):
        from shared.split_utils import split_adjustment_factor

        splits = [
            (date(2022, 6, 6), Decimal("0.1")),
            (date(2023, 5, 10), Decimal("0.16")),
        ]
        factor = split_adjustment_factor(splits, date(2022, 4, 26), date(2023, 12, 31))
        assert factor == Decimal("0.016")
        # ... but only the ones that precede the as-of date.
        factor = split_adjustment_factor(splits, date(2022, 4, 26), date(2022, 12, 31))
        assert factor == Decimal("0.1")

    def test_undated_movement_is_treated_as_the_earliest(self):
        from shared.split_utils import split_adjustment_factor

        assert split_adjustment_factor(
            [IVR_SPLIT], None, date(2022, 6, 6)
        ) == Decimal("0.1")

    def test_no_schedule_is_the_identity(self):
        from shared.split_utils import split_adjustment_factor

        assert split_adjustment_factor(None, date(2020, 1, 1), date(2024, 1, 1)) == 1
        assert split_adjustment_factor([], date(2020, 1, 1), date(2024, 1, 1)) == 1

    def test_awkward_ratio_keeps_precision(self):
        """Real split rows are not all integers: 10000:9033 appears in the table."""
        from shared.split_utils import parse_split_factor_decimal, split_adjustment_factor

        splits = [(date(2022, 6, 6), parse_split_factor_decimal("10000:9033"))]
        adjusted = Decimal("870") * split_adjustment_factor(
            splits, date(2022, 1, 1), date(2022, 12, 31)
        )
        expected = Decimal("870") * Decimal(10000) / Decimal(9033)
        assert abs(adjusted - expected) < Decimal("0.000001")


class TestLotAccumulation:
    """_accumulate_lots must agree with the stored, split-adjusted position."""

    def test_cash_activity_types_are_not_share_movements(self):
        from shared.cdr_utils import _accumulate_lots

        rows = [_row(3157, *ETHY_TRADE)] + [
            _row(3157, *r) for r in ETHY_CASH_ROWS
        ]
        lots = _accumulate_lots(rows, "2026-10-01", {})
        assert lots[3157] == {"direct": Decimal("80")}, (
            "dividends, return of capital and non-cash distributions carry cash in "
            "`quantity`; summing them inflated ETHY from 80 to 90.616"
        )

    def test_internal_security_transfer_is_a_share_movement(self):
        from shared.cdr_utils import _accumulate_lots

        rows = [
            _row(3110, "2022-06-16", "Trade", "20"),
            _row(3110, "2024-12-23", "InternalSecurityTransfer", "-59"),
        ]
        assert _accumulate_lots(rows, "2026-10-01", {})[3110] == {
            "direct": Decimal("-39")
        }

    def test_split_is_applied_to_earlier_movements_only(self):
        from shared.cdr_utils import _accumulate_lots

        rows = [_row(3110, *r) for r in IVR_ROWS]
        lots = _accumulate_lots(rows, "2022-06-06", {3110: [IVR_SPLIT]})
        # (85 + 108) / 10 - 0.3, NOT (85 + 108 - 0.3) / 10.
        assert lots[3110] == {"direct": Decimal("19.0")}

    def test_the_whole_live_history_reconciles(self):
        """The full IVR history: 19.3 post-split, -0.3 cash-in-lieu, +20 +20, -59 out."""
        from shared.cdr_utils import _accumulate_lots

        rows = [
            _row(3110, "2022-04-07", "Trade", "85"),
            _row(3110, "2022-04-26", "Trade", "108"),
            _row(3110, "2022-06-06", "Trade", "-0.3"),
            _row(3110, "2022-06-16", "Trade", "20"),
            _row(3110, "2022-06-23", "Trade", "20"),
            _row(3110, "2024-12-23", "InternalSecurityTransfer", "-59"),
        ]
        lots = _accumulate_lots(rows, "2026-10-01", {3110: [IVR_SPLIT]})
        assert lots.get(3110, {}) == {}, (
            "19.3 - 0.3 + 20 + 20 - 59 is exactly zero; the account was fully "
            "transferred out"
        )

    def test_as_of_before_the_split_keeps_raw_units(self):
        from shared.cdr_utils import _accumulate_lots

        rows = [_row(3110, *r) for r in IVR_ROWS]
        lots = _accumulate_lots(rows, "2022-05-31", {3110: [IVR_SPLIT]})
        assert lots[3110] == {"direct": Decimal("193")}


class TestPublicDerivationsApplyTheSchedule:
    """The schedule has to reach the public API, not just the private helper."""

    def test_per_account_derivation_uses_the_splits_table(self):
        from shared.cdr_utils import derive_account_cdr_lots_as_of

        client = _TableClient(
            {
                "portfolio_transactions": [_row(3110, *r) for r in IVR_ROWS],
                "splits": [
                    {
                        "company_id": 3110,
                        "report_date": "2022-06-06",
                        "split_factor": "1:10",
                    }
                ],
            }
        )
        lots = derive_account_cdr_lots_as_of(client, 9, "2022-06-06")
        assert lots[3110] == {"direct": Decimal("19.0")}

    def test_batched_and_per_account_agree_with_splits(self):
        from shared.cdr_utils import (
            derive_account_cdr_lots_as_of,
            derive_cdr_lots_by_account_as_of,
        )

        tables = {
            "portfolio_transactions": [
                _row(3110, *r, account=9) for r in IVR_ROWS
            ]
            + [_row(3110, "2022-04-07", "Trade", "50", account=7)],
            "splits": [
                {"company_id": 3110, "report_date": "2022-06-06", "split_factor": "1:10"}
            ],
        }
        batched = derive_cdr_lots_by_account_as_of(_TableClient(tables), "2022-12-31")
        for aid in (7, 9):
            single = derive_account_cdr_lots_as_of(
                _TableClient(tables), aid, "2022-12-31"
            )
            assert batched.get(aid) == single, aid

    def test_at_dates_honours_each_as_of_independently(self):
        from shared.cdr_utils import derive_cdr_lots_by_account_at_dates

        client = _TableClient(
            {
                "portfolio_transactions": [_row(3110, *r) for r in IVR_ROWS],
                "splits": [
                    {
                        "company_id": 3110,
                        "report_date": "2022-06-06",
                        "split_factor": "1:10",
                    }
                ],
            }
        )
        by_date = derive_cdr_lots_by_account_at_dates(
            client, ["2022-05-31", "2022-06-06"]
        )
        assert by_date["2022-05-31"][9][3110] == {"direct": Decimal("193")}
        assert by_date["2022-06-06"][9][3110] == {"direct": Decimal("19.0")}


class _Store:
    def __init__(self, events):
        self.events = events

    def get_all_events(self, **_kwargs):
        return self.events


def _trade_event(qty, on, created):
    return {
        "event_type": "transaction_imported",
        "aggregate_id": "account_9",
        "aggregate_type": "account",
        "created_at": created,
        "data": {
            "account_id": 9,
            "company_id": 3110,
            "activity_type": "Trade",
            "symbol": "IVR",
            "quantity": qty,
            "unit_price": 21.42,
            "net_cash_amount": 0,
            "currency": "CAD",
            "transaction_date": on,
        },
    }


def _split_event(on, factor, created):
    return {
        "event_type": "split",
        "aggregate_id": "account_9",
        "aggregate_type": "account",
        "created_at": created,
        "data": {"company_id": 3110, "split_factor": factor, "report_date": on},
    }


class TestReplaySameDateOrdering:
    def test_split_applies_before_a_same_day_trade(self):
        """The split event is written AFTER the trades that it adjusts -- always, because
        split_sync emits it on a later run. Ordering by date alone made the split land
        last and every same-day trade look pre-split. A split rescales at the start of
        its effective date, so it must be applied first."""
        from shared.replay_engine import ReplayEngine

        events = [
            _trade_event("85", "2022-04-07", "2026-07-09T00:21:51"),
            _trade_event("108", "2022-04-26", "2026-07-09T00:21:51"),
            _trade_event("-0.3", "2022-06-06", "2026-07-09T00:21:51"),
            _split_event("2022-06-06", "0.1", "2026-08-05T22:46:26"),
        ]
        state = ReplayEngine(_Store(events)).replay_to_date(9, date(2022, 6, 6))
        assert state.holdings[3110].quantity == Decimal("19.0")

    def test_ordering_does_not_depend_on_insertion_order(self):
        """Same four events, split written first or last: the result must be identical."""
        from shared.replay_engine import ReplayEngine

        shared_events = [
            _trade_event("85", "2022-04-07", "2026-07-09T00:21:51"),
            _trade_event("108", "2022-04-26", "2026-07-09T00:21:51"),
            _trade_event("-0.3", "2022-06-06", "2026-07-09T00:21:51"),
        ]
        split = _split_event("2022-06-06", "0.1", "2026-08-05T22:46:26")
        written_last = ReplayEngine(_Store([*shared_events, split])).replay_to_date(
            9, date(2022, 6, 6)
        )
        written_first = ReplayEngine(_Store([split, *shared_events])).replay_to_date(
            9, date(2022, 6, 6)
        )
        assert (
            written_last.holdings[3110].quantity
            == written_first.holdings[3110].quantity
            == Decimal("19.0")
        )

    def test_a_split_rescales_the_position_held_before_it(self):
        from shared.replay_engine import ReplayEngine

        events = [
            _trade_event("100", "2022-01-01", "2026-07-09T00:21:51"),
            _split_event("2022-06-06", "2", "2026-08-05T22:46:26"),
        ]
        state = ReplayEngine(_Store(events)).replay_to_date(9, date(2022, 12, 31))
        assert state.holdings[3110].quantity == Decimal("200")

    def test_a_split_on_a_date_with_no_holding_yet_does_nothing(self):
        from shared.replay_engine import ReplayEngine

        events = [
            _split_event("2022-06-06", "2", "2026-08-05T22:46:26"),
            _trade_event("100", "2022-07-01", "2026-07-09T00:21:51"),
        ]
        state = ReplayEngine(_Store(events)).replay_to_date(9, date(2022, 12, 31))
        assert state.holdings[3110].quantity == Decimal("100")

    def test_lot_replay_and_replay_engine_agree(self):
        """The whole point: two derivations of the same fact must produce the same number."""
        from shared.cdr_utils import _accumulate_lots
        from shared.replay_engine import ReplayEngine

        events = [
            _trade_event("85", "2022-04-07", "2026-07-09T00:21:51"),
            _trade_event("108", "2022-04-26", "2026-07-09T00:21:51"),
            _trade_event("-0.3", "2022-06-06", "2026-07-09T00:21:51"),
            _split_event("2022-06-06", "0.1", "2026-08-05T22:46:26"),
        ]
        state = ReplayEngine(_Store(events)).replay_to_date(9, date(2022, 6, 6))
        lots = _accumulate_lots(
            [_row(3110, *r) for r in IVR_ROWS], "2022-06-06", {3110: [IVR_SPLIT]}
        )
        assert sum(lots[3110].values()) == state.holdings[3110].quantity
