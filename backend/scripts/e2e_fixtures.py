"""The single definition of the E2E portfolio fixture.

Both seeders import this module instead of carrying their own copy of the plan:

    scripts/seed_e2e_data.py       supabase-py client (needs the backend package)
    scripts/seed_e2e_requests.py   standalone REST client (stdlib + requests only)

The two copies had already drifted, and the drifted one still signed a ``Sell``
with a POSITIVE quantity. That is not cosmetic. Every other writer of
``portfolio_transactions`` signs share movements, ``cdr_utils._accumulate_lots``
sums the signed value directly, and ``ReplayEngine._handle_transaction_imported``
treats a positive quantity as a buy. A positive sale therefore *adds* the shares
it was meant to remove: the account's transaction history totalled 110 shares
where its position and ``position_state_checkpoint`` said 100, so
``classify_lot_legs`` refused to split those holdings on every snapshot with

    Replay lot split declined: company 2808 (RY): lot replay totals 110.00000000
    but stored quantity is 100.00000000

Rules this module enforces so the fixture cannot drift again:

1. **History is the source of truth.** ``POSITIONS`` is the readable statement of
   what the fixture is *supposed* to hold, but every number in it is derived from
   ``TRADES`` and checked against it by :func:`verify_invariants`, which runs at
   import time. A position and its history cannot disagree.
2. **Signed quantities.** A sell is negative, matching the broker export.
3. **Cost basis is derivable.** A buy's ``unit_price`` equals the declared
   ``average_cost``. The fixture has one buy lot per position, so a partial sale
   leaves the unsold shares at the buy price and the remaining position carries
   exactly the declared cost. Realized P&L then falls out as
   ``(sell price - average_cost) x shares sold``: +100 for RY, +60 for TD, which
   is real rather than the ``0`` the old fixture asserted while it also claimed a
   sale had happened.
4. **Sells are real.** Two positions are partially sold, so E2E data exercises
   realized P&L instead of acquisitions only.

Stdlib only, deliberately: ``seed_e2e_requests.py`` runs without the backend
package importable, so this module must load in both seeders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

D = Decimal

#: The fixture's as-of date. Every ``days_ago`` in TRADES and DIVIDENDS is measured
#: from THIS literal, never from ``date.today()``.
#:
#: An earlier revision used the wall clock as the anchor. The plan then had a
#: different identity on every run: a seed on 2026-11-16 wrote RY dividends on
#: 09-17/06-19, a seed on 2026-11-17 wrote 09-18/06-20, and a reset kept both
#: sets. Measured: the plan declares 6 dividends, the database held 12, and the
#: extra six were dated 2026-03-31 and 2025-12-31 from earlier seed days. Worse,
#: the account's transaction history moved with the clock, so a replay run on a
#: later day compared the fixture against a different set of dates than the ones
#: it had been verified with. A fixture that changes identity when you re-run it
#: is not a fixture.
#:
#: Market data is deliberately NOT anchored here: ``current_market_data`` and
#: ``price_history`` must stay current so the snapshot job can price the fixture
#: at today's date. Only the broker record (trades, dividends) is fixed.
AS_OF = date(2026, 11, 16)


class FixtureInvariantError(AssertionError):
    """The declared positions and the declared trades contradict each other."""


@dataclass(frozen=True)
class AccountSpec:
    name: str
    external_id: str
    account_type: str
    brokerage_code: str


@dataclass(frozen=True)
class PositionSpec:
    account: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal

    @property
    def total_cost(self) -> Decimal:
        return self.quantity * self.average_cost


@dataclass(frozen=True)
class TradeSpec:
    """One row of ``portfolio_transactions``, with the sign the column really means."""

    account: str
    symbol: str
    days_ago: int
    quantity: Decimal  # signed: > 0 buy, < 0 sell
    unit_price: Decimal
    direction: str  # "Buy" | "Sell"

    @property
    def net_cash_amount(self) -> Decimal:
        """Cash that leaves the account is negative, so this is the negated signed value."""
        return -(self.quantity * self.unit_price)

    def trade_date(self, today: date) -> date:
        return today - timedelta(days=self.days_ago)


@dataclass(frozen=True)
class DividendSpec:
    account: str
    symbol: str
    days_ago: int
    amount: Decimal


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

ACCOUNTS: tuple[AccountSpec, ...] = (
    AccountSpec("Main TFSA", "EXT-TFSA-001", "TFSA", "QUESTRADE"),
    AccountSpec("Retirement RRSP", "EXT-RRSP-001", "RRSP", "TD_DIRECT"),
    AccountSpec("Margin Account", "EXT-MRG-001", "Margin", "QUESTRADE"),
)

POSITIONS: tuple[PositionSpec, ...] = (
    PositionSpec("Main TFSA", "AAPL", D("50"), D("145.00")),
    PositionSpec("Main TFSA", "RY", D("100"), D("95.00")),
    PositionSpec("Main TFSA", "SHOP", D("30"), D("68.00")),
    PositionSpec("Retirement RRSP", "TD", D("200"), D("72.00")),
    PositionSpec("Retirement RRSP", "ENB", D("150"), D("45.00")),
    PositionSpec("Retirement RRSP", "AAPL", D("30"), D("148.00")),
    PositionSpec("Margin Account", "SHOP", D("20"), D("70.00")),
    PositionSpec("Margin Account", "ENB", D("75"), D("44.50")),
)

# When each acquisition happened, in days before the seed date.
_BUY_DAYS_AGO: dict[tuple[str, str], int] = {
    ("Main TFSA", "AAPL"): 180,
    ("Main TFSA", "RY"): 150,
    ("Main TFSA", "SHOP"): 90,
    ("Retirement RRSP", "TD"): 200,
    ("Retirement RRSP", "ENB"): 170,
    ("Retirement RRSP", "AAPL"): 120,
    ("Margin Account", "SHOP"): 100,
    ("Margin Account", "ENB"): 80,
}

# (shares sold, sell price, days before the seed date). Positive "shares sold"
# reads naturally; the sign is applied when building the trade rows.
_SELLS: dict[tuple[str, str], tuple[Decimal, Decimal, int]] = {
    ("Main TFSA", "RY"): (D("10"), D("105.00"), 30),
    ("Retirement RRSP", "TD"): (D("10"), D("78.00"), 45),
}


def _build_trades() -> tuple[TradeSpec, ...]:
    """Buys first, then the partial sales that draw on them.

    The buy quantity is the *held* quantity plus the shares later sold, so the
    signed history sums back to exactly the declared position. The buy price is
    the declared average cost, so the surviving shares keep that cost basis.
    """
    trades: list[TradeSpec] = []
    for position in POSITIONS:
        sold, _, _ = _SELLS.get((position.account, position.symbol), (D("0"), D("0"), 0))
        trades.append(
            TradeSpec(
                account=position.account,
                symbol=position.symbol,
                days_ago=_BUY_DAYS_AGO[(position.account, position.symbol)],
                quantity=position.quantity + sold,
                unit_price=position.average_cost,
                direction="Buy",
            )
        )
    for (account, symbol), (sold, price, days_ago) in _SELLS.items():
        trades.append(
            TradeSpec(
                account=account,
                symbol=symbol,
                days_ago=days_ago,
                quantity=-sold,
                unit_price=price,
                direction="Sell",
            )
        )
    return tuple(trades)


TRADES: tuple[TradeSpec, ...] = _build_trades()

DIVIDENDS: tuple[DividendSpec, ...] = (
    DividendSpec("Main TFSA", "RY", 60, D("42.00")),
    DividendSpec("Main TFSA", "RY", 150, D("40.00")),
    DividendSpec("Retirement RRSP", "TD", 60, D("76.00")),
    DividendSpec("Retirement RRSP", "TD", 150, D("72.00")),
    DividendSpec("Retirement RRSP", "ENB", 60, D("52.50")),
    DividendSpec("Margin Account", "ENB", 60, D("26.25")),
)


# --------------------------------------------------------------------------
# Derivations the writers and tests share
# --------------------------------------------------------------------------

def account_names() -> tuple[str, ...]:
    return tuple(a.name for a in ACCOUNTS)


def position(account: str, symbol: str) -> PositionSpec:
    for p in POSITIONS:
        if p.account == account and p.symbol == symbol:
            return p
    raise KeyError(f"no declared position for {account}/{symbol}")


def net_quantity(account: str, symbol: str) -> Decimal:
    """What the declared trade history says the position should be."""
    return sum(
        (t.quantity for t in TRADES if t.account == account and t.symbol == symbol),
        D("0"),
    )


def realized_gain_loss(account: str, symbol: str) -> Decimal:
    """Realized P&L implied by the declared sales, costed at the declared average cost.

    The fixture has one buy lot per position and sells draw on it, so the cost of
    the shares sold is ``average_cost`` and the gain is the sale spread.
    """
    avg = position(account, symbol).average_cost
    return sum(
        (
            (t.unit_price - avg) * abs(t.quantity)
            for t in TRADES
            if t.account == account and t.symbol == symbol and t.quantity < 0
        ),
        D("0"),
    )


def verify_invariants() -> None:
    """Raise :class:`FixtureInvariantError` when the plan contradicts itself.

    Called at import time: a fixture that cannot be reproduced by its own history
    must fail loudly in the seeder rather than silently seeding a state the
    product can never reach.
    """
    declared = {(p.account, p.symbol) for p in POSITIONS}
    traded = {(t.account, t.symbol) for t in TRADES}
    if declared != traded:
        raise FixtureInvariantError(
            "positions and trades name different securities: "
            f"positions-only={sorted(declared - traded)} trades-only={sorted(traded - declared)}"
        )

    for p in POSITIONS:
        net = net_quantity(p.account, p.symbol)
        if net != p.quantity:
            raise FixtureInvariantError(
                f"{p.account}/{p.symbol}: trade history nets {net} but the declared "
                f"position is {p.quantity}"
            )
        buys = [
            t for t in TRADES
            if t.account == p.account and t.symbol == p.symbol and t.quantity > 0
        ]
        if len(buys) != 1:
            raise FixtureInvariantError(
                f"{p.account}/{p.symbol}: expected exactly one acquisition, got {len(buys)}"
            )
        if buys[0].unit_price != p.average_cost:
            raise FixtureInvariantError(
                f"{p.account}/{p.symbol}: acquisition price {buys[0].unit_price} is not "
                f"the declared average cost {p.average_cost}, so the position's cost "
                "basis is not derivable from its history"
            )
        if buys[0].quantity <= 0:
            raise FixtureInvariantError(
                f"{p.account}/{p.symbol}: acquisition quantity must be positive"
            )

    for t in TRADES:
        if t.direction == "Sell" and t.quantity >= 0:
            raise FixtureInvariantError(
                f"{t.account}/{t.symbol}: a Sell must carry a negative quantity, got {t.quantity}"
            )
        if t.direction == "Buy" and t.quantity <= 0:
            raise FixtureInvariantError(
                f"{t.account}/{t.symbol}: a Buy must carry a positive quantity, got {t.quantity}"
            )
        if t.direction == "Sell":
            buy_days = _BUY_DAYS_AGO[(t.account, t.symbol)]
            if t.days_ago >= buy_days:
                raise FixtureInvariantError(
                    f"{t.account}/{t.symbol}: sell is {t.days_ago} days before the seed "
                    f"date but the acquisition is {buy_days} days before it - a sale "
                    "cannot precede the shares it sells"
                )


verify_invariants()
