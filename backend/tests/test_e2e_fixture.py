"""The E2E fixture must be reproducible from its own history (I2b).

The fixture used to assert two different truths about the same position:

  * ``portfolio_holdings`` said RY 100 and TD 200, and
  * ``portfolio_transactions`` netted to RY 110 and TD 210, because the Sell rows
    carried POSITIVE quantities.

Nothing compared them, so the disagreement only surfaced as a warning on every
snapshot run: ``Replay lot split declined: ... lot replay totals 110.00000000 but
stored quantity is 100.00000000``. ``classify_lot_legs`` then silently fell back to
the company-keyed CDR verdict for those positions.

These tests prove the fixture is now internally consistent, and they prove it the
strong way: by replaying the declared trades through the production
``ReplayEngine`` and comparing the result to the declared positions. A fixture
literal and a fixture history agreeing by construction would prove nothing, so
the comparison runs the real engine over real event payloads.

They also pin the single-definition rule: both seeders import
``scripts/e2e_fixtures.py`` and carry no plan literal of their own. The plan had
three copies, and two of them had already drifted.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import e2e_fixtures as fixtures

BACKEND = Path(__file__).resolve().parents[1]

# Company and account ids are the live ones the fixture lands on, so the replay
# here exercises the same identities the seeded database carries.
COMPANY_IDS = {"AAPL": 69, "RY": 2808, "SHOP": 1117, "TD": 2225, "ENB": 1341}
ACCOUNT_IDS = {"Main TFSA": 10, "Retirement RRSP": 11, "Margin Account": 12}

# One anchor, owned by the fixture module. A second literal here would let the
# test drift away from the seeders by exactly the kind of copy this module exists
# to prevent.
TODAY = fixtures.AS_OF


class _Store:
    """ReplayEngine only needs get_all_events; the engine filters by account."""

    def __init__(self, events):
        self.events = events

    def get_all_events(self, **_kwargs):
        return self.events


def _events(trades):
    events = []
    for i, t in enumerate(trades):
        tx_date = t.trade_date(TODAY)
        events.append(
            {
                "id": f"ev-{i:03d}",
                "event_type": "transaction_imported",
                "event_version": 1,
                "aggregate_id": f"account_{ACCOUNT_IDS[t.account]}",
                "aggregate_type": "account",
                "created_at": f"{tx_date.isoformat()}T00:00:00+00:00",
                "data": {
                    "account_id": ACCOUNT_IDS[t.account],
                    "company_id": COMPANY_IDS[t.symbol],
                    "transaction_date": tx_date.isoformat(),
                    "activity_type": "Trade",
                    "activity_sub_type": t.direction,
                    "direction": t.direction,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "unit_price": t.unit_price,
                    "net_cash_amount": t.net_cash_amount,
                    "currency": "CAD",
                },
            }
        )
    return events


def _replay(trades, account):
    from shared.replay_engine import ReplayEngine

    return ReplayEngine(_Store(_events(trades))).replay_to_date(
        ACCOUNT_IDS[account], TODAY
    )


# ---------------------------------------------------------------------------
# The declared plan is coherent
# ---------------------------------------------------------------------------

def test_fixture_invariants_hold():
    fixtures.verify_invariants()


def test_every_sale_carries_a_negative_quantity():
    sells = [t for t in fixtures.TRADES if t.direction == "Sell"]
    assert sells, "the fixture must exercise a sale"
    for t in sells:
        assert t.quantity < 0, f"{t.account}/{t.symbol} sale is not negative"
        assert t.net_cash_amount > 0, "selling shares must bring cash in"


def test_buys_include_the_shares_later_sold():
    """RY buys 110 and sells 10 to hold 100 - not buys 100 and sells +10."""
    for held in fixtures.POSITIONS:
        sold = sum(
            (
                -t.quantity
                for t in fixtures.TRADES
                if t.account == held.account
                and t.symbol == held.symbol
                and t.quantity < 0
            ),
            Decimal("0"),
        )
        bought = sum(
            (
                t.quantity
                for t in fixtures.TRADES
                if t.account == held.account
                and t.symbol == held.symbol
                and t.quantity > 0
            ),
            Decimal("0"),
        )
        assert bought - sold == held.quantity, held


# ---------------------------------------------------------------------------
# The production replay engine reproduces the declared positions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("account", fixtures.account_names())
def test_replay_of_the_fixture_reproduces_its_declared_positions(account):
    state = _replay(fixtures.TRADES, account)

    expected = [p for p in fixtures.POSITIONS if p.account == account]
    assert len(state.holdings) == len(expected), (
        f"{account}: replay produced {sorted(h.symbol for h in state.holdings.values())}"
    )

    for p in expected:
        cid = COMPANY_IDS[p.symbol]
        holding = state.holdings[cid]
        assert holding.quantity == p.quantity, f"{p.symbol} quantity"
        assert holding.average_cost == p.average_cost, f"{p.symbol} average cost"
        assert holding.total_cost == p.total_cost, f"{p.symbol} total cost"
        assert holding.realized_gain_loss == fixtures.realized_gain_loss(
            p.account, p.symbol
        ), f"{p.symbol} realized gain"


def test_replay_derives_the_cash_the_history_implies():
    for account in fixtures.account_names():
        state = _replay(fixtures.TRADES, account)
        expected = sum(
            (
                t.net_cash_amount
                for t in fixtures.TRADES
                if t.account == account
            ),
            Decimal("0"),
        )
        assert state.cash_balance == expected, account


def test_the_old_shape_would_replay_to_110_shares():
    """Non-vacuity: the defect this replaces produced a specific, wrong number.

    If this test ever stops producing 110, the replay path changed and the whole
    file's assumptions need re-checking.
    """
    from scripts.e2e_fixtures import TradeSpec

    old_shape = [
        TradeSpec("Main TFSA", "RY", 150, Decimal("100"), Decimal("93.50"), "Buy"),
        # a Sell written with a POSITIVE quantity, as the old seeders did
        TradeSpec("Main TFSA", "RY", 30, Decimal("10"), Decimal("105.00"), "Sell"),
    ]
    state = _replay(old_shape, "Main TFSA")
    assert state.holdings[COMPANY_IDS["RY"]].quantity == Decimal("110")


# ---------------------------------------------------------------------------
# One definition, three entry points
# ---------------------------------------------------------------------------

SEEDERS = ("scripts/seed_e2e_data.py", "scripts/seed_e2e_requests.py")


def test_fixture_history_is_anchored_to_a_fixed_date():
    """Re-running the seed on a different day must not create a different fixture.

    ``days_ago`` used to be measured from ``date.today()``, so the 2026-11-16 seed
    declared RY dividends on 09-17/06-19 and a 2026-11-17 seed declared 09-18/06-20.
    Neither the declaration nor any verification result survived a day rollover,
    and a reset that only inserted rows kept both sets. The anchor is now a literal
    in the shared fixture; market data is still generated relative to today, which
    is why only the trade and dividend writers are checked here.
    """
    assert fixtures.AS_OF.isoformat() == "2026-11-16"
    fixture_source = (BACKEND / "scripts" / "e2e_fixtures.py").read_text(encoding="utf-8")
    assert "AS_OF = date(2026, 11, 16)" in fixture_source

    for relative in SEEDERS:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        assert "trade_date(TODAY)" not in source, f"{relative} anchors trades to the clock"
        assert "pay_date = TODAY" not in source, f"{relative} anchors dividends to the clock"
        assert "trade_date(fixtures.AS_OF)" in source
        assert "pay_date = fixtures.AS_OF" in source


@pytest.mark.parametrize("relative", SEEDERS)
def test_seeder_uses_the_shared_fixture_and_keeps_no_plan_of_its_own(relative):
    source = (BACKEND / relative).read_text(encoding="utf-8")
    assert "import e2e_fixtures" in source, f"{relative} does not import the fixture"
    for literal in ("holdings_plan", "tx_plan", "account_data"):
        assert literal not in source, (
            f"{relative} still carries its own plan ({literal!r}); a second copy "
            "of the fixture is how the two seeders drifted apart"
        )


def test_powershell_entry_point_forwards_to_the_python_seeder():
    source = (BACKEND / "scripts" / "seed_e2e_data.ps1").read_text(encoding="utf-8")
    assert "seed_e2e_data.py" in source
    for literal in ("holdingsPlan", "txPlan", "accountData", "companyData"):
        assert literal not in source, f"the .ps1 still carries its own {literal}"


def test_every_seeded_transaction_gets_an_event():
    """A transaction row with no event is invisible to replay.

    ``backfill_initial_holdings.py`` selects accounts 'with holdings but no events',
    so history-less rows cause a ``position_state_checkpoint`` to be captured from
    the projection - freezing the contradiction instead of fixing it.
    """
    for relative in SEEDERS:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        assert "transaction_imported" in source, (
            f"{relative} writes transactions without an event"
        )


def test_no_seeder_writes_the_deprecated_performance_table():
    """The fixture must not invent a valuation series.

    ``portfolio_performance`` is deprecated: ``get_portfolio_performance`` reads
    ``portfolio_snapshots`` (5,015 rows), ``get_account_performance_history`` and
    ``upsert_performance_snapshot`` have no callers, no frontend or mobile query
    touches it, and the production baseline records 0 rows. The seeders used to
    write twelve months of ``50000 - i*500 + i*200`` per account so a chart would
    have something to draw - the same class of defect as the positive-sale rows,
    which is a fixture asserting a state the product cannot produce.

    The insert could never succeed either: ``total_cost`` is NOT NULL with no
    default and was never sent, so it raised 23502 on the first row. Removing the
    writer removes a claim, not data.

    Prose may name the table (the reset clears legacy rows); a *write* may not.
    """
    write_patterns = (
        (re.compile(r'portfolio_performance"\)\s*\.\s*(insert|upsert)'), "supabase-py write"),
        (re.compile(r'post\(\s*"portfolio_performance"'), "REST write"),
    )
    for relative in SEEDERS:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        for pattern, label in write_patterns:
            match = pattern.search(source)
            assert match is None, (
                f"{relative} still performs a {label}: {match.group(0)!r}. The "
                "fixture must not fabricate a performance series - that table is "
                "deprecated and the real curve comes from the snapshot job"
            )

        # Comments legitimately quote the old curve to explain why it went; only
        # executable lines matter. The seeders are plain scripts, so a
        # comment-line filter is exact here.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "50000" not in code, (
            f"{relative} still carries the invented value curve in executable code"
        )


def test_reset_clears_fixture_owned_and_derived_rows():
    """A reset must not leave rows that disagree with the history it replaced.

    Three tables were each a stale answer sitting next to the rebuilt one:

    ``portfolio_snapshots``
        Derived: every ``total_value`` is a replay of the transactions as they
        stood at build time. The fixture's rows were produced by
        ``rebuild_account_snapshots.py`` against the pre-split, wrong-sign
        history. Measured consequence: the snapshot job's gap repair reported
        account 10 as a 72.4% unexplained cliff ($42,165.07 -> $11,641.90) because
        the stored 2026-11-15 row disagreed with the 2026-11-16 replay.

    ``portfolio_dividends``
        Used to be dated from ``date.today()``, so each seed day declared a new
        set and kept the old one. Measured: the plan declares 6 rows, the database
        held 12, the extra six dated 2026-03-31 and 2025-12-31. Dates now come from
        the fixture's fixed ``AS_OF``; the delete removes rows written by older
        revisions.

    This is a source-level assertion on purpose: the deletions are DB calls and a
    unit test cannot run them. The behavioural proof is
    ``scripts/scratch/probe_i2b_verify.py``, which compares every declared
    dividend and every stored snapshot's cash against a replay at that date.
    """
    source = (BACKEND / "scripts" / "seed_e2e_data.py").read_text(encoding="utf-8")
    for table in ("portfolio_snapshots", "portfolio_dividends"):
        assert re.search(
            rf'table\("{table}"\)\s*\n?\s*\.delete\(\)\s*\n?\s*\.eq\(\s*"account_id"',
            source,
        ), (
            f"the reset does not delete {table}, so the fixture keeps a stale "
            "answer next to the rebuilt one"
        )


def test_seeder_source_stays_ascii():
    """The seeder prints to a Windows console (cp1252).

    One '->' written as a unicode arrow aborted the whole run with
    ``UnicodeEncodeError`` before it wrote anything, which is part of why the
    fixture and the database could disagree. ``log()`` now degrades instead of
    raising, but the source staying ASCII keeps the common case clean.
    """
    source = (BACKEND / "scripts" / "seed_e2e_data.py").read_bytes()
    offenders = [
        (number, line)
        for number, line in enumerate(source.splitlines(), 1)
        if any(byte > 0x7F for byte in line)
    ]
    assert offenders == [], f"non-ASCII bytes at {offenders}"
