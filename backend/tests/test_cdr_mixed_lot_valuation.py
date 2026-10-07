"""A position holding BOTH CDR and direct lots must value each lot on its own scale.

BLK-027. Account 9 / META (cid 145) holds 25 CDR shares and 2 direct shares,
which reconcile exactly to portfolio_holdings.quantity 27.0. The CDR ratio is
applied to the PRICE, not the quantity: build_snapshot_row divides the resolved
price by CDR_RATIO whenever the holding is classified CDR, so a mixed position
cannot be valued correctly from a single per-company price and a single quantity.

The account-wide classification is the specific mechanism. snapshot_builder
resolves _is_cdr as `cid in derived_cdr_companies`, a flat set[int] keyed by
COMPANY, not by lot. So both rows of a mixed position inherit CDR-ness and both
are priced at 1/10 scale, understating the direct lot by 10x.

Correct valuation of 25 CDR + 2 direct at a $500 underlying:
    CDR leg    25 x ($500 / 10) = $1,250
    direct leg  2 x $500         = $1,000
    total                      = $2,250
Currently stored: 27 x ($500 / 10) = $1,350  -- short by $900.

These tests are the specification for the fix. They must fail today and pass
once CDR-ness is resolved per holding row rather than per company.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

UNDERLYING = 500.0
CID = 145  # META


def _holding(qty, override):
    return {
        "company_id": CID,
        "symbol": "META",
        "quantity": qty,
        "total_cost": Decimal("1455.06"),
        "average_cost": Decimal("53.89"),
        "price_currency": "USD",
        "exchange_override": override,
    }


def _build(holdings, derived=frozenset({CID}), lot_authoritative=False):
    from shared.snapshot_builder import build_snapshot_row

    prices = {
        CID: {
            "price": UNDERLYING,
            "price_date": date(2024, 6, 1),
            "source": "yfinance_tor",
        }
    }
    with patch("config.settings") as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False
        return build_snapshot_row(
            account_id=9,
            snapshot_date=date(2024, 6, 1),
            holdings_state=holdings,
            cash_balance=Decimal("0"),
            net_deposits=Decimal("1000"),
            prices_by_company=prices,
            job_id="test",
            account_currency="CAD",
            price_history={},
            exchange_overrides={CID: "TOR"},
            derived_cdr_companies=set(derived),
            lot_cdr_authoritative=lot_authoritative,
        )


class TestMixedLotValuation:
    """25 CDR + 2 direct must be valued as two legs, not one divided position."""

    def test_mixed_position_totals_both_legs_at_their_own_scale(self):
        row = _build([_holding(25, "TOR"), _holding(2, None)], lot_authoritative=True)

        by_qty = {h["quantity"]: h for h in row["holdings_json"]}
        assert set(by_qty) == {25.0, 2.0}, (
            f"both lots must survive as separate rows, got {sorted(by_qty)}"
        )

        # CDR leg is divided by the 10:1 ratio; the direct leg is not.
        assert by_qty[25.0]["current_price"] == 50.0
        assert by_qty[2.0]["current_price"] == 500.0

        assert by_qty[25.0]["current_value"] == 1250.0
        assert by_qty[2.0]["current_value"] == 1000.0

        total = sum(h["current_value"] for h in row["holdings_json"])
        assert total == 2250.0

    def test_direct_lot_in_a_cdr_account_is_not_divided(self):
        """The account-wide `cid in derived_cdr_companies` answer must not
        propagate CDR-ness onto a lot that was never a CDR."""
        row = _build([_holding(25, "TOR"), _holding(2, None)], lot_authoritative=True)

        direct = next(h for h in row["holdings_json"] if h["quantity"] == 2.0)
        assert direct.get("cdr_ratio") is None
        assert direct.get("exchange_override") is None


class TestUniformLotsUnaffected:
    """Control: the fix must not disturb the 188 uniform (account, company) pairs."""

    def test_cdr_only_position_still_divides_in_full(self):
        row = _build([_holding(25, "TOR")])
        h = row["holdings_json"][0]
        assert h["current_price"] == 50.0
        assert h["current_value"] == 1250.0
        assert h["cdr_ratio"] == 10.0
        assert h["cdr_ratio_source"] == "transactions"

    def test_direct_only_position_is_untouched(self):
        row = _build([_holding(2, None)], derived=set())
        h = row["holdings_json"][0]
        assert h["current_price"] == 500.0
        assert h["current_value"] == 1000.0
        assert h["cdr_ratio"] is None


class _TxClient:
    """Minimal stand-in for the query builder iter_transactions drives."""

    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return self

    def select(self, _cols):
        return self

    def eq(self, *_a):
        return self

    def order(self, _col):
        return self

    def range(self, _start, _end):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def _tx(cid, on, qty, cdr, activity="Trade"):
    return {
        "company_id": cid,
        "transaction_date": on,
        "activity_type": activity,
        "quantity": qty,
        "security_name": "META CDR (CAD Hedged)" if cdr else "META",
        "raw_data": None,
    }


class TestLotDerivationFromTransactions:
    """derive_account_cdr_lots_as_of is what makes the lot split possible."""

    def _lots(self, rows, as_of):
        from shared.cdr_utils import derive_account_cdr_lots_as_of

        return derive_account_cdr_lots_as_of(_TxClient(rows), 9, as_of)

    def test_mixed_position_splits_by_lot_kind(self):
        lots = self._lots(
            [_tx(145, "2022-02-17", 2.0, cdr=False), _tx(145, "2022-11-01", 25.0, cdr=True)],
            "2023-06-01",
        )
        assert lots == {145: {"direct": Decimal("2.0"), "cdr": Decimal("25.0")}}

    def test_lots_are_replayed_to_the_as_of_date(self):
        rows = [_tx(145, "2022-02-17", 2.0, cdr=False), _tx(145, "2022-11-01", 25.0, cdr=True)]
        assert self._lots(rows, "2022-06-01") == {145: {"direct": Decimal("2.0")}}

    def test_transfer_out_reduces_only_its_own_bucket(self):
        rows = [
            _tx(145, "2022-02-17", 2.0, cdr=False),
            _tx(145, "2022-11-01", 25.0, cdr=True),
            _tx(145, "2024-12-23", -2.0, cdr=False, activity="InternalSecurityTransfer"),
        ]
        assert self._lots(rows, "2025-01-15") == {145: {"cdr": Decimal("25.0")}}

    def test_dividend_quantity_never_enters_share_math(self):
        rows = [
            _tx(145, "2022-11-01", 25.0, cdr=True),
            _tx(145, "2024-03-26", 1.45, cdr=True, activity="Dividend"),
        ]
        assert self._lots(rows, "2024-06-01") == {145: {"cdr": Decimal("25.0")}}

    def test_company_netted_to_zero_is_omitted(self):
        rows = [
            _tx(145, "2022-02-17", 2.0, cdr=False),
            _tx(145, "2024-12-23", -2.0, cdr=False, activity="InternalSecurityTransfer"),
        ]
        assert self._lots(rows, "2025-01-15") == {}

    def test_a_null_quantity_row_is_skipped_not_fatal(self):
        rows = [_tx(145, "2022-11-01", None, cdr=True), _tx(145, "2022-11-02", 25.0, cdr=True)]
        assert self._lots(rows, "2023-06-01") == {145: {"cdr": Decimal("25.0")}}


# ---------------------------------------------------------------------------
# _compute_performance_fallback grouping
# ---------------------------------------------------------------------------
# All-CAD fixtures on purpose: _cached_cash_balance/_cached_net_deposits only
# reach FX when txn_ccy != account currency, so a single-currency fixture never
# constructs FXService and never touches DNS. A mixed-currency fixture here
# fails on getaddrinfo rather than on the logic under test.
#
# ENABLE_FX_CONVERSION is patched on the portfolio_service module, not on
# config.settings: the service did `from config import settings` at import and
# holds a direct reference that patching config would not reach.

_CDR_NAME = "META CDR (CAD Hedged)"
_DIRECT_NAME = "META"
_ACCT = 9
_AS_OF = date(2024, 6, 1)
_START = date(2024, 1, 1)


def _trade(txn_id, on, qty, price, security_name):
    return {
        "transaction_id": txn_id,
        "account_id": _ACCT,
        "company_id": CID,
        "symbol": "META",
        "transaction_date": on,
        "activity_type": "TRADE",
        "activity_sub_type": "BUY",
        "quantity": qty,
        "unit_price": price,
        "commission": 0,
        "currency": "CAD",
        "security_name": security_name,
        "raw_data": None,
    }


class _FallbackRepo:
    """Only the three repository calls the fallback actually makes."""

    def __init__(self, trades):
        self._trades = trades

    def get_accounts_transactions(self, account_ids, activity_types=None):
        # The ["Trade"] query feeds the lot engine; the unfiltered one feeds cash
        # and net deposits. Returning [] there keeps cash at 0 without depending
        # on CASH_ACTIVITY_TYPES membership.
        return list(self._trades) if activity_types == ["Trade"] else []

    def get_all_prices_historical(self, company_ids, end_date):
        return {CID: [(date(2024, 5, 1), UNDERLYING)]}

    def get_user_accounts(self, user_id):
        return [{"account_id": _ACCT, "account_name": "Margin", "currency": "CAD"}]


async def _run_fallback(trades):
    """Drive the real fallback and return the holdings_state it handed over."""
    from application.services import portfolio_service as svc

    captured = {}

    def _capture(**kwargs):
        captured["holdings_state"] = kwargs["holdings_state"]
        captured["lot_cdr_authoritative"] = kwargs.get("lot_cdr_authoritative")
        return {"total_value": Decimal("0"), "cost_basis": Decimal("0")}

    class _Harness:
        # Borrow the real method; everything else it touches is stubbed below.
        _compute_performance_fallback = svc.PortfolioService._compute_performance_fallback

        def __init__(self, repo):
            self.portfolio_repo = repo

        def _generate_snapshot_dates(self, period, start_date, end_date):
            return [end_date.isoformat()]

        def _compute_returns_from_snapshots(self, snapshots, period):
            return {}

    with patch.object(svc, "settings") as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False
        with patch.object(svc, "build_snapshot_row", _capture):
            await _Harness(_FallbackRepo(trades))._compute_performance_fallback(
                _ACCT, "1Y", [_ACCT], _START, _AS_OF
            )
    return captured


class TestFallbackMixedLotSplit:
    """The fallback must split a mixed position into one row per lot kind."""

    async def test_mixed_lots_reach_the_builder_as_two_rows(self):
        captured = await _run_fallback([
            _trade(1, date(2022, 11, 1), 25.0, 3.858, _CDR_NAME),
            _trade(2, date(2022, 2, 17), 2.0, 38.58, _DIRECT_NAME),
        ])

        rows = captured["holdings_state"]
        assert len(rows) == 2, f"mixed lots must not collapse into one row, got {rows}"

        by_qty = {r["quantity"]: r for r in rows}
        assert set(by_qty) == {25.0, 2.0}
        assert by_qty[25.0]["exchange_override"] == "TOR"
        assert by_qty[2.0]["exchange_override"] is None

    async def test_fallback_marks_lots_authoritative(self):
        """Company-keyed truth would misprice the direct leg 10x, so the
        fallback must opt out of it exactly as the writers do."""
        captured = await _run_fallback([_trade(1, date(2022, 11, 1), 25.0, 3.858, _CDR_NAME)])
        assert captured["lot_cdr_authoritative"] is True

    async def test_cdr_only_position_stays_a_single_row(self):
        """Control: uniform positions must not gain extra rows."""
        captured = await _run_fallback([_trade(1, date(2022, 11, 1), 25.0, 3.858, _CDR_NAME)])

        rows = captured["holdings_state"]
        assert len(rows) == 1
        assert rows[0]["quantity"] == 25.0
        assert rows[0]["exchange_override"] == "TOR"

    async def test_direct_only_position_carries_no_override(self):
        captured = await _run_fallback([_trade(1, date(2022, 2, 17), 2.0, 38.58, _DIRECT_NAME)])

        rows = captured["holdings_state"]
        assert len(rows) == 1
        assert rows[0]["quantity"] == 2.0
        assert rows[0]["exchange_override"] is None