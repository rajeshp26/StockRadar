"""The lot split itself: turning one row per company into one row per CDR lot.

Complements test_cdr_mixed_lot_valuation.py, which specifies the BUILDER's lot
mode (two rows must be priced on different scales). That file assumes the caller
has already produced correctly-classified rows. This file specifies the step that
decides the classification -- split_holdings_by_cdr_lot() -- plus the batched
derivation it consumes, and proves the two compose into the right money.

The three failure modes this guards, each of which would misprice real money:

  - Splitting without checking that the replayed lots reconcile with the stored
    quantity silently invents share counts. 18 of 151 live pairs disagree (the
    NFLX 10:1 split, nine crypto pairs whose transaction and holding units
    differ), so this path is taken constantly and must refuse.
  - Treating absent lot evidence as "not a CDR" strips the TOR override and
    overvalues by 10x -- the original defect, re-entered through a different door.
  - A batched derivation that disagrees with the per-account one makes the
    account a factor of correctness. This file's as_of regression test exists
    because that bug shipped once already (the cutoff was hardcoded to
    9999-12-31, silently ignoring the requested date).
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

CID = 145  # META -- account 9 holds 25 CDR + 2 direct, reconciling to 27.0
QTY = Decimal("27.0")
COST = Decimal("1455.06")


class _TxClient:
    """Stand-in for the query builder iter_transactions drives.

    Unlike the fake in test_cdr_mixed_lot_valuation.py this HONOURS the
    account_id filter, because batching over several accounts is exactly what
    derive_cdr_lots_by_account_as_of() has to get right.
    """

    def __init__(self, rows):
        self.rows = rows
        self._account = None

    def table(self, _name):
        return self

    def select(self, _cols):
        return self

    def eq(self, col, val):
        if col == "account_id":
            self._account = val
        return self

    def order(self, _col):
        return self

    def range(self, _start, _end):
        return self

    def execute(self):
        rows = self.rows
        if self._account is not None:
            rows = [r for r in rows if r.get("account_id") == self._account]
        return SimpleNamespace(data=rows)


def _tx(cid, on, qty, cdr, activity="Trade", account=9):
    return {
        "account_id": account,
        "company_id": cid,
        "transaction_date": on,
        "activity_type": activity,
        "quantity": qty,
        "security_name": "META CDR (CAD Hedged)" if cdr else "META",
        "raw_data": None,
    }


def _holding(qty=QTY, cost=COST, override=None, cid=CID, symbol="META"):
    return {
        "company_id": cid,
        "symbol": symbol,
        "quantity": Decimal(str(qty)),
        "total_cost": Decimal(str(cost)),
        "average_cost": Decimal("53.89"),
        "price_currency": "USD",
        "exchange_override": override,
    }


class TestBatchedDerivation:
    """derive_cdr_lots_by_account_as_of must be the batched twin, not a variant."""

    def test_batched_matches_per_account_for_every_account(self):
        from shared.cdr_utils import (
            derive_account_cdr_lots_as_of,
            derive_cdr_lots_by_account_as_of,
        )

        rows = [
            _tx(145, "2022-02-17", 2.0, cdr=False, account=9),
            _tx(145, "2022-11-01", 25.0, cdr=True, account=9),
            _tx(200, "2023-05-04", 10.0, cdr=False, account=11),
            _tx(200, "2023-09-09", 4.0, cdr=True, account=11),
        ]
        batched = derive_cdr_lots_by_account_as_of(_TxClient(rows), "2026-10-04")
        for aid in (9, 11):
            single = derive_account_cdr_lots_as_of(
                _TxClient(rows), aid, "2026-10-04"
            )
            assert batched.get(aid) == single, (
                f"acct {aid}: batched {batched.get(aid)} != per-account {single}"
            )

    def test_batched_honours_the_as_of_cutoff(self):
        """Regression: the cutoff was hardcoded to 9999-12-31, so the batched
        form ignored as_of and returned future lots. Per-account honoured it, so
        the two disagreed and nothing noticed."""
        from shared.cdr_utils import derive_cdr_lots_by_account_as_of

        rows = [
            _tx(145, "2022-02-17", 2.0, cdr=False),
            _tx(145, "2022-11-01", 25.0, cdr=True),
        ]
        lots = derive_cdr_lots_by_account_as_of(_TxClient(rows), "2022-06-01")
        assert lots[9][145] == {"direct": Decimal("2.0")}, (
            "a transaction dated after as_of must not appear in the lot map"
        )

    def test_batched_keeps_accounts_separate(self):
        """AAPL can be CDR in one account and direct in another; conflating them
        would misprice one of the two."""
        from shared.cdr_utils import derive_cdr_lots_by_account_as_of

        rows = [
            _tx(300, "2024-01-05", 10.0, cdr=True, account=7),
            _tx(300, "2024-01-05", 10.0, cdr=False, account=10),
        ]
        lots = derive_cdr_lots_by_account_as_of(_TxClient(rows), "2026-10-04")
        assert lots[7][300] == {"cdr": Decimal("10.0")}
        assert lots[10][300] == {"direct": Decimal("10.0")}


class TestSplitUniformIsIdentical:
    """The 147 uniform pairs must be byte-identical to today's company-keyed row."""

    def test_uniform_cdr_position_stays_one_row(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"cdr": Decimal("27.0")}},
            {CID},
        )
        assert len(rows) == 1
        assert rows[0]["quantity"] == Decimal("27.0")
        assert rows[0]["total_cost"] == COST
        assert rows[0]["exchange_override"] == "TOR"
        assert notes == []

    def test_uniform_direct_position_stays_one_row(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot(
            [_holding()], {CID: {"direct": Decimal("27.0")}}, set()
        )
        assert len(rows) == 1
        assert rows[0]["exchange_override"] is None
        assert notes == []


class TestSplitMixed:
    """25 CDR + 2 direct -> two legs, cost and quantity conserved exactly."""

    def _split(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        return split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"cdr": Decimal("25.0"), "direct": Decimal("2.0")}},
            {CID},
        )

    def test_produces_one_leg_per_lot(self):
        rows, notes = self._split()
        assert len(rows) == 2
        assert notes == []
        assert sorted(r["quantity"] for r in rows) == [Decimal("2.0"), Decimal("25.0")]

    def test_each_leg_carries_its_own_verdict(self):
        rows, _ = self._split()
        by_qty = {r["quantity"]: r for r in rows}
        assert by_qty[Decimal("25.0")]["exchange_override"] == "TOR"
        assert by_qty[Decimal("2.0")]["exchange_override"] is None

    def test_quantity_and_cost_are_conserved_exactly(self):
        """sum(legs) must equal the stored row, or the holdings_market_value
        validator in portfolio_snapshots_repository nullifies the whole snapshot."""
        rows, _ = self._split()
        assert sum(r["quantity"] for r in rows) == QTY
        assert sum(r["total_cost"] for r in rows) == COST

    def test_legs_do_not_alias_the_input(self):
        rows, _ = self._split()
        assert len({id(r) for r in rows}) == 2
        assert all("symbol" in r for r in rows)


class TestSplitRefusesToGuess:
    """The paths where evidence is absent or contradictory."""

    def test_absent_evidence_keeps_the_company_keyed_verdict(self):
        """No transactions at or before the date -> one row. A CDR company keeps
        TOR; falling back to the holding's own flag would treat it as direct and
        overvalue 10x."""
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot([_holding()], {}, {CID})
        assert len(rows) == 1
        assert rows[0]["exchange_override"] == "TOR"
        assert notes == []

    def test_absent_evidence_on_a_direct_company_stays_direct(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, _ = split_holdings_by_cdr_lot([_holding()], {}, set())
        assert len(rows) == 1
        assert rows[0]["exchange_override"] is None

    def test_mismatch_refuses_to_split_and_says_why(self):
        """18 of 151 live pairs mismatch. Reconciling them by inventing shares
        would fabricate a position."""
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"cdr": Decimal("73.0")}},  # stored is 27.0
            {CID},
        )
        assert len(rows) == 1
        assert rows[0]["quantity"] == QTY
        assert len(notes) == 1
        assert "73" in notes[0] and "27" in notes[0]

    def test_floating_point_noise_within_tolerance_still_splits(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot(
            [_holding()],
            {CID: {"cdr": Decimal("25.0000000001"), "direct": Decimal("2.0")}},
            {CID},
        )
        assert len(rows) == 2
        assert notes == []

    def test_stale_tor_on_a_direct_leg_is_stripped(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, _ = split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"direct": Decimal("27.0")}},
            set(),
        )
        assert rows[0]["exchange_override"] is None

    def test_non_tor_override_survives(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, _ = split_holdings_by_cdr_lot(
            [_holding(override="NYSE")],
            {CID: {"direct": Decimal("27.0")}},
            set(),
        )
        assert rows[0]["exchange_override"] == "NYSE"

    def test_derived_cdr_companies_is_required(self):
        """Defaulting it would make every holding look direct and strip TOR from
        every leg -- the 10x overvaluation, re-entered through a missing argument.
        Locked here so nobody re-adds a default."""
        from shared.cdr_utils import split_holdings_by_cdr_lot

        try:
            split_holdings_by_cdr_lot([_holding()], {}, None)
        except TypeError:
            return
        raise AssertionError(
            "derived_cdr_companies must be required; a None default strips TOR "
            "from every leg and overvalues CDR holdings 10x"
        )

    def test_zero_quantity_passes_through_untouched(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        rows, notes = split_holdings_by_cdr_lot(
            [_holding(qty=0, override="TOR")], {CID: {"cdr": Decimal("27.0")}}, {CID}
        )
        assert len(rows) == 1
        assert rows[0]["exchange_override"] == "TOR"
        assert notes == []


class TestSplitComposesWithBuilder:
    """End of the chain: the legs must actually price on different scales."""

    def _row(self, legs):
        from shared.snapshot_builder import build_snapshot_row

        prices = {
            CID: {"price": 500.0, "price_date": date(2024, 6, 1), "source": "yfinance_tor"}
        }
        with patch("config.settings") as mock_settings:
            mock_settings.ENABLE_FX_CONVERSION = False
            return build_snapshot_row(
                account_id=9,
                snapshot_date=date(2024, 6, 1),
                holdings_state=legs,
                cash_balance=Decimal("0"),
                net_deposits=Decimal("1000"),
                prices_by_company=prices,
                job_id="test",
                account_currency="CAD",
                price_history={},
                exchange_overrides={CID: "TOR"},
                derived_cdr_companies={CID},
                lot_cdr_authoritative=True,
            )

    def test_mixed_position_values_each_lot_at_its_own_scale(self):
        from shared.cdr_utils import split_holdings_by_cdr_lot

        legs, _ = split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"cdr": Decimal("25.0"), "direct": Decimal("2.0")}},
            {CID},
        )
        row = self._row(legs)

        by_qty = {h["quantity"]: h for h in row["holdings_json"]}
        assert by_qty[25.0]["current_price"] == 50.0    # 500 / 10
        assert by_qty[2.0]["current_price"] == 500.0   # untouched
        assert sum(h["current_value"] for h in row["holdings_json"]) == 2250.0

    def test_would_be_1350_under_the_company_keyed_verdict(self):
        """The number the fix exists to change. If this stops holding, the split
        is not reaching the builder."""
        from shared.cdr_utils import split_holdings_by_cdr_lot

        legs, _ = split_holdings_by_cdr_lot(
            [_holding(override="TOR")],
            {CID: {"cdr": Decimal("25.0"), "direct": Decimal("2.0")}},
            {CID},
        )
        naive = self._row([_holding(override="TOR")])
        fixed = self._row(legs)
        assert sum(h["current_value"] for h in naive["holdings_json"]) == 1350.0
        assert sum(h["current_value"] for h in fixed["holdings_json"]) == 2250.0