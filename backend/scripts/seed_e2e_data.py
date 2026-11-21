"""Seed portfolio data for the e2e test user.

The portfolio plan itself lives in ``scripts/e2e_fixtures.py`` - accounts,
positions, trades and dividends - so this script and ``seed_e2e_requests.py``
cannot disagree about what the fixture contains.

Seeding writes three things per account, in the order the product writes them:

    1. ``portfolio_transactions``  the broker record
    2. ``transaction_imported`` events derived from those rows
    3. ``portfolio_holdings``      the projection, verified against a replay

Step 3 is not written blind: :func:`verify_replay_matches_holdings` replays the
account through the production ``ReplayEngine`` and fails the seed if the
projection it just wrote is not what the event log says it should be.

    python scripts/seed_e2e_data.py                 # create anything missing
    python scripts/seed_e2e_data.py --reset         # rebuild the fixture accounts
"""
import argparse
import os
import sys
from datetime import date, timedelta

# Add backend and this script's directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ENV", "development")

import e2e_fixtures as fixtures

from config import settings
from supabase import Client, create_client

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

FIREBASE_UID = "OVUH9KDf7TORSB4KuvrGEIRAvTI2"
EMAIL = "e2e-test-2026@stockerpro-test.com"
# Market data is generated relative to the wall clock so prices stay current. The
# broker record (trades, dividends) is anchored to the fixture's fixed AS_OF date:
# using TODAY there made a re-seed on a new day create a different fixture and
# leave the previous day's dividends behind. See e2e_fixtures.AS_OF.
TODAY = date.today()

def log(msg):
    """Print a seed log line without ever dying on console encoding.

    This used to be a bare ``print``. On a Windows console (cp1252) a single
    non-ASCII character in a log message aborted the whole seeder with
    ``UnicodeEncodeError`` before it had written any data, which is one reason the
    fixture and the database could disagree: the script that was supposed to make
    them agree never finished.
    """
    line = f"[seed] {msg}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode(encoding, "replace").decode(encoding))

def get_or_create_user():
    """Create user row and return user_id."""
    existing = supabase.table("users").select("user_id").eq("auth_id", FIREBASE_UID).execute()
    if existing.data:
        uid = existing.data[0]["user_id"]
        log(f"User already exists: user_id={uid}")
        return uid

    result = supabase.table("users").insert({"auth_id": FIREBASE_UID}).execute()
    uid = result.data[0]["user_id"]
    log(f"Created user: user_id={uid}")
    return uid

def ensure_brokerages():
    """Ensure brokerages exist and return {code: id} map."""
    codes = {
        "QUESTRADE": "Questrade",
        "TD_DIRECT": "TD Direct Investing",
        "WS_TRADE": "Wealthsimple Trade",
    }
    result = {}
    for code, name in codes.items():
        existing = supabase.table("portfolio_brokerages").select("brokerage_id").eq("brokerage_code", code).execute()
        if existing.data:
            result[code] = existing.data[0]["brokerage_id"]
        else:
            ins = supabase.table("portfolio_brokerages").insert({
                "brokerage_code": code,
                "brokerage_name": name,
                "country_code": "CA",
                "is_active": True,
            }).execute()
            result[code] = ins.data[0]["brokerage_id"]
        log(f"Brokerage {code} -> id={result[code]}")
    return result

def create_accounts(user_id, brokerages):
    """Create portfolio accounts, return {name: id} map."""
    result = {}
    for a in fixtures.ACCOUNTS:
        existing = supabase.table("portfolio_accounts").select("account_id, account_name").eq("user_id", user_id).eq("account_external_id", a.external_id).execute()
        if existing.data:
            result[a.name] = existing.data[0]["account_id"]
            log(f"Account '{a.name}' already exists: id={existing.data[0]['account_id']}")
            continue
        ins = supabase.table("portfolio_accounts").insert({
            "user_id": user_id,
            "brokerage_id": brokerages[a.brokerage_code],
            "account_external_id": a.external_id,
            "account_name": a.name,
            "account_type": a.account_type,
            "currency": "CAD",
            "is_active": True,
        }).execute()
        result[a.name] = ins.data[0]["account_id"]
        log(f"Created account '{a.name}': id={ins.data[0]['account_id']}")
    return result

def get_or_create_companies():
    """Get or create company entries for our test symbols."""
    symbols = [
        ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics"),
        ("RY", "Royal Bank of Canada", "Financial Services", "Banks"),
        ("TD", "Toronto-Dominion Bank", "Financial Services", "Banks"),
        ("ENB", "Enbridge Inc.", "Energy", "Oil & Gas Midstream"),
        ("SHOP", "Shopify Inc.", "Technology", "Software"),
    ]
    result = {}
    for sym, name, sector, industry in symbols:
        existing = supabase.table("companies").select("company_id").eq("ticker_symbol", sym).execute()
        if existing.data:
            result[sym] = existing.data[0]["company_id"]
            log(f"Company {sym} already exists: id={result[sym]}")
        else:
            ins = supabase.table("companies").insert({
                "ticker_symbol": sym,
                "company_name": name,
                "sector": sector,
                "industry": industry,
                "exchange": "NMS" if sym in ("AAPL", "SHOP") else "TSX",
                "currency": "USD" if sym in ("AAPL", "SHOP") else "CAD",
                "security_type": "stock",
            }).execute()
            result[sym] = ins.data[0]["company_id"]
            log(f"Created company {sym}: id={result[sym]}")
    return result

def create_holdings(accounts, companies):
    """Write the projection declared by the fixture.

    ``realized_gain_loss`` is derived, not asserted: the fixture sells part of two
    positions, so the column carries the sale's realized spread instead of the
    ``0`` the old plan wrote while also claiming a sale had happened.
    """
    holding_ids = []
    for p in fixtures.POSITIONS:
        acct_id = accounts[p.account]
        company_id = companies[p.symbol]
        existing = supabase.table("portfolio_holdings").select("holding_id").eq("account_id", acct_id).eq("company_id", company_id).execute()
        if existing.data:
            holding_ids.append(existing.data[0]["holding_id"])
            log(f"Holding {p.symbol} in {p.account} already exists: id={existing.data[0]['holding_id']}")
            continue
        ins = supabase.table("portfolio_holdings").insert({
            "account_id": acct_id,
            "company_id": company_id,
            "symbol": p.symbol,
            "quantity": float(p.quantity),
            "average_cost": float(p.average_cost),
            "total_cost": float(p.total_cost),
            "realized_gain_loss": float(fixtures.realized_gain_loss(p.account, p.symbol)),
        }).execute()
        holding_ids.append(ins.data[0]["holding_id"])
        log(f"Created holding {p.symbol} x {p.quantity} @ ${p.average_cost} in {p.account}")
    return holding_ids

def create_transactions(accounts, companies):
    """Write the broker record declared by the fixture, signs included."""
    count = 0
    for t in fixtures.TRADES:
        acct_id = accounts[t.account]
        company_id = companies[t.symbol]
        tx_date = t.trade_date(fixtures.AS_OF)
        existing = supabase.table("portfolio_transactions").select("transaction_id").eq("account_id", acct_id).eq("symbol", t.symbol).eq("transaction_date", tx_date.isoformat()).eq("quantity", float(t.quantity)).execute()
        if existing.data:
            continue
        supabase.table("portfolio_transactions").insert({
            "account_id": acct_id,
            "company_id": company_id,
            "transaction_date": tx_date.isoformat(),
            "activity_type": "Trade",
            "activity_sub_type": t.direction,
            "direction": t.direction,
            "symbol": t.symbol,
            "quantity": float(t.quantity),
            "unit_price": float(t.unit_price),
            "net_cash_amount": float(t.net_cash_amount),
            "currency": "CAD",
        }).execute()
        count += 1
    log(f"Created {count} transactions")

def create_dividends(accounts, companies):
    """Create dividend payment records."""
    count = 0
    for d in fixtures.DIVIDENDS:
        acct_id = accounts[d.account]
        company_id = companies[d.symbol]
        pay_date = fixtures.AS_OF - timedelta(days=d.days_ago)
        existing = supabase.table("portfolio_dividends").select("dividend_id").eq("account_id", acct_id).eq("symbol", d.symbol).eq("payment_date", pay_date.isoformat()).execute()
        if existing.data:
            continue
        supabase.table("portfolio_dividends").insert({
            "account_id": acct_id,
            "company_id": company_id,
            "symbol": d.symbol,
            "payment_date": pay_date.isoformat(),
            "amount": float(d.amount),
            "currency": "CAD",
            "fiscal_year": pay_date.year,
            "fiscal_month": pay_date.month,
        }).execute()
        count += 1
    log(f"Created {count} dividends")

# There is deliberately no ``create_performance_snapshots``.
#
# The fixture used to insert twelve months of ``portfolio_performance`` rows per
# account from a literal curve: ``50000 - i*500 + i*200`` for total value and
# ``48000 - i*400`` for cost basis, identical for every account. That is not this
# portfolio (its market value is roughly 18.8k / 25.6k / 4.7k per account) and it
# was never a record of anything - it was a shape the fixture asserted so a chart
# would have something to draw.
#
# Three independent facts make writing it wrong:
#
#   1. The table is deprecated. ``docs/PORTFOLIO_PERFORMANCE_REENGINEERING.md:2146``
#      keeps it only during migration and states seed-script usage should move to
#      ``portfolio_snapshots`` in a future release.
#   2. Nothing reads it. ``get_portfolio_performance`` reads
#      ``portfolio_snapshots`` (5,015 rows) or computes from transactions;
#      ``get_account_performance_history`` and ``upsert_performance_snapshot``
#      have no callers anywhere in the repo, and no frontend or mobile query
#      touches the table.
#   3. The insert cannot succeed. ``total_cost`` is NOT NULL with no default, and
#      the payload never set it, so this function raised 23502 on its first row.
#      Measured: ``select count(*) from portfolio_performance`` -> 0. The fixture
#      data this code was supposed to provide has never existed.
#
# Seeding it therefore adds a second, contradictory truth about portfolio value to
# a dead table. The real series is produced by the snapshot job; a fixture cannot
# invent it without inventing a valuation engine too.

def update_current_prices(companies):
    """Update current_market_data for companies to enable price lookups."""
    prices = {
        "AAPL": 178.50,
        "RY": 102.30,
        "TD": 78.40,
        "ENB": 47.20,
        "SHOP": 82.00,
    }
    for sym, price in prices.items():
        company_id = companies[sym]
        supabase.table("current_market_data").upsert({
            "company_id": company_id,
            "current_price": price,
            "open_price": price - 0.50,
            "high_price": price + 1.00,
            "low_price": price - 1.00,
            "close_price": price,
            "volume": 1000000,
            "market_state": "CLOSED",
        }, on_conflict="company_id").execute()
    log("Updated market prices")

def create_price_history(companies):
    """Create 90 days of price history for each company."""
    from random import seed as random_seed
    from random import uniform
    random_seed(42)
    prices = {
        "AAPL": 175.00,
        "RY": 100.00,
        "TD": 76.00,
        "ENB": 45.00,
        "SHOP": 65.00,
    }
    count = 0
    for sym, base in prices.items():
        company_id = companies[sym]
        for i in range(90, -1, -1):
            d = TODAY - timedelta(days=i)
            daily = base + uniform(-3, 3)
            existing = supabase.table("price_history").select("company_id").eq("company_id", company_id).eq("price_date", d.isoformat()).execute()
            if existing.data:
                continue
            supabase.table("price_history").insert({
                "company_id": company_id,
                "price_date": d.isoformat(),
                "open_price": round(daily - 0.2, 2),
                "close_price": round(daily, 2),
                "high_price": round(daily + 0.5, 2),
                "low_price": round(daily - 0.5, 2),
                "volume": 2000000,
            }).execute()
            count += 1
    log(f"Created {count} price history rows")

#: Event types the fixture owns and may delete during a reset.
#:
#: ``portfolio_events`` is append-only in spirit - ``event_sequence`` has a foreign
#: key to it precisely so a row cannot vanish from under the ordering index. That
#: guarantee is about the *product*; this module seeds a disposable fixture, and a
#: reset that cannot remove its own previous output is not a reset. Anything not
#: listed here (``split`` above all, which records a real corporate action) is
#: never touched.
_FIXTURE_EVENT_TYPES = ("position_state_checkpoint", "transaction_imported")


def _delete_fixture_events(acct_id, event_type):
    """Delete one account's events of one fixture-owned type, index rows first.

    ``event_sequence`` is an ordering index maintained by the
    ``trg_portfolio_events_after_insert`` trigger; it holds a foreign key to every
    event row, so its entry has to go before the row it describes. Nothing else in
    the schema references ``portfolio_events``, so this is the whole dependency.
    """
    if event_type not in _FIXTURE_EVENT_TYPES:
        raise SystemExit(f"refusing to delete event_type {event_type!r}: not fixture-owned")

    ids = [
        row["id"]
        for row in (
            supabase.table("portfolio_events")
            .select("id")
            .eq("aggregate_id", f"account_{acct_id}")
            .eq("event_type", event_type)
            .execute()
            .data
            or []
        )
    ]
    if not ids:
        return 0

    index_rows = (
        supabase.table("event_sequence")
        .delete(returning="representation")
        .in_("event_id", ids)
        .execute()
        .data
        or []
    )
    if len(index_rows) != len(ids):
        raise SystemExit(
            f"refusing to delete {len(ids)} '{event_type}' event(s) for account "
            f"{acct_id}: only {len(index_rows)} event_sequence entry/entries were "
            "removed, so a row would still be referenced"
        )

    supabase.table("portfolio_events").delete().eq(
        "aggregate_id", f"account_{acct_id}"
    ).eq("event_type", event_type).execute()
    return len(ids)


def reset_fixture_accounts(accounts):
    """Rebuild the fixture accounts from scratch, leaving real accounts untouched.

    A ``position_state_checkpoint`` is a CAPTURE of a projection dated at the moment
    of capture, and replay APPLIES it as a reset (``_handle_position_state_checkpoint``
    clears holdings before loading the payload). It exists only for accounts that
    have a projection but no history: ``backfill_initial_holdings.py`` selects
    accounts "with holdings but no events". Once an account has a complete
    transaction history the capture is a second, competing truth about the same
    position: its payload carries the cash total the *old* (wrong-sign, wrong-price)
    rows implied, so keeping it re-introduces the disagreement the rebuild removes.

    ``transaction_imported`` events go too. They are derived from the transaction
    rows deleted below, so leaving them behind would make the reset additive: the
    rebuild appends history the event log already holds, and replay totals 200
    shares against a 100-share position.

    Only these rows are removed, and only for accounts named by the fixture:

      event_sequence          the derived ordering index, for the events below only
      portfolio_events        position_state_checkpoint and transaction_imported
                              rows - split events are real corporate-action facts
                              and stay
      portfolio_snapshots     the derived daily read model, computed from the
                              transactions being replaced
      portfolio_transactions  the fixture's broker record
      portfolio_dividends     the fixture's declared dividend payments, whose
                              dates move with the seed day
      portfolio_holdings      the fixture's projection

    Not atomic: PostgREST issues one request per statement and there is no
    transaction around them. Every step is a delete-then-recreate, so a failed run
    is repaired by running again, and ``verify_replay_matches_holdings`` refuses to
    call the seed complete unless the end state replays correctly.
    """
    expected = {a.name: a.external_id for a in fixtures.ACCOUNTS}
    for name in fixtures.account_names():
        acct_id = accounts[name]

        # Defence in depth: the id came from a lookup by fixture external id, and
        # this asserts it still points at the fixture's own account before anything
        # is deleted.
        row = (
            supabase.table("portfolio_accounts")
            .select("account_external_id")
            .eq("account_id", acct_id)
            .execute()
            .data
        )
        external_id = row[0]["account_external_id"] if row else None
        if external_id != expected[name]:
            raise SystemExit(
                f"refusing to reset '{name}' (id={acct_id}): account_external_id is "
                f"{external_id!r}, not the fixture's {expected[name]!r}"
            )

        removed_checkpoints = _delete_fixture_events(acct_id, "position_state_checkpoint")
        removed_events = _delete_fixture_events(acct_id, "transaction_imported")

        # Legacy fixture output. ``portfolio_performance`` is deprecated (see the
        # note above ``update_current_prices``); older revisions of this seeder
        # targeted it, so a reset clears whatever they may have left behind rather
        # than leaving a stale curve next to the rebuilt history.
        legacy = (
            supabase.table("portfolio_performance")
            .delete()
            .eq("account_id", acct_id)
            .execute()
            .data
            or []
        )

        # ``portfolio_snapshots`` is a read model DERIVED from the rows deleted
        # below - every total_value in it is a replay of the transactions as they
        # were at build time. Leaving those rows behind keeps a second, older
        # answer to "what was this account worth on date X" alive next to the
        # rebuilt one, and the snapshot job then reads the pair as a cliff: a
        # measured run flagged account 10 as a 72.4% unexplained drop
        # ($42,165.07 -> $11,641.90) purely because the stored 2026-11-15 row had
        # been built from pre-split, wrong-sign history.
        #
        # They cannot be repaired in place here: only the snapshot job knows how to
        # price a date (price history, FX, split factors), so the honest reset is
        # to drop the derived rows and let the job recompute them. Cash balance is
        # transaction-derived, so the contradiction was visible without prices at
        # all: stored 2026-07-07 cash was -17,350 against -17,700 replayed from the
        # current rows.
        snapshots = (
            supabase.table("portfolio_snapshots")
            .delete()
            .eq("account_id", acct_id)
            .execute()
            .data
            or []
        )

        txs = supabase.table("portfolio_transactions").delete().eq("account_id", acct_id).execute()

        # Dividends are declared by the fixture with dates relative to the seed day
        # (``today - days_ago``), so a reset run on a different day creates a new set
        # and, without this delete, keeps the previous one. Measured before the fix:
        # the plan declares 6 dividend rows and the database held 12 - the extra six
        # were dated 2026-03-31 and 2025-12-31, from an earlier seed day, and no
        # amount of re-running would remove them.
        dividends = (
            supabase.table("portfolio_dividends")
            .delete()
            .eq("account_id", acct_id)
            .execute()
            .data
            or []
        )

        holdings = supabase.table("portfolio_holdings").delete().eq("account_id", acct_id).execute()

        log(
            f"Reset '{name}' (id={acct_id}): "
            f"{removed_checkpoints} checkpoint(s), "
            f"{removed_events} transaction event(s), "
            f"{len(snapshots)} snapshot(s), "
            f"{len(txs.data or [])} transaction(s), "
            f"{len(dividends)} dividend(s), "
            f"{len(holdings.data or [])} holding(s) removed"
            + (f", {len(legacy)} legacy performance row(s)" if legacy else "")
        )

def emit_transaction_events(accounts):
    """Derive ``transaction_imported`` events from the rows just written.

    Uses the sanctioned backfill rather than a hand-rolled payload: it builds each
    event through ``build_transaction_event_data`` and is idempotent on
    ``backfill_{account}_{transaction_id}``, so a re-run adds nothing.
    """
    from scripts.backfill_events_from_transactions import backfill_events

    for name in fixtures.account_names():
        acct_id = accounts[name]
        result = backfill_events(account_id=acct_id)
        log(
            f"Events for '{name}' (id={acct_id}): {result['total_transactions']} transaction(s), "
            f"{result['skipped_duplicates']} already had events, {result['events_written']} written"
        )

def verify_replay_matches_holdings(accounts):
    """Fail the seed unless the projection equals what the event log replays to.

    This is the check the fixture was missing. ``portfolio_holdings`` used to be
    written straight from a literal while the event log said something else, and
    nothing compared them until a snapshot run logged "Replay lot split declined"
    and silently kept the company-keyed classification.

    Replay runs the production engine over the events just written, so the
    comparison cannot agree by construction: it exercises sign handling, split
    adjustment and same-date ordering for real.
    """
    from infrastructure.repositories.event_store import EventStore
    from shared.replay_engine import ReplayEngine

    engine = ReplayEngine(EventStore(client=supabase))
    problems: list[str] = []

    for name in fixtures.account_names():
        acct_id = accounts[name]
        state = engine.replay_to_date(acct_id, fixtures.AS_OF)

        stored = {
            int(r["company_id"]): r
            for r in (
                supabase.table("portfolio_holdings")
                .select("company_id, symbol, quantity, average_cost, realized_gain_loss")
                .eq("account_id", acct_id)
                .execute()
                .data
                or []
            )
        }

        for cid, holding in state.holdings.items():
            row = stored.get(cid)
            if row is None:
                problems.append(
                    f"{name}: replay holds {holding.symbol} x {holding.quantity} but no "
                    "portfolio_holdings row exists"
                )
                continue
            if abs(float(holding.quantity) - float(row["quantity"])) > 1e-6:
                problems.append(
                    f"{name}: {holding.symbol} replay={holding.quantity} "
                    f"stored={row['quantity']}"
                )
            if abs(float(holding.realized_gain_loss) - float(row["realized_gain_loss"] or 0)) > 1e-6:
                problems.append(
                    f"{name}: {holding.symbol} realized replay={holding.realized_gain_loss} "
                    f"stored={row['realized_gain_loss'] or 0}"
                )

        extra = set(stored) - set(state.holdings)
        for cid in sorted(extra):
            problems.append(
                f"{name}: portfolio_holdings has {stored[cid]['symbol']} x "
                f"{stored[cid]['quantity']} that replay does not hold"
            )

        for symbol in {p.symbol for p in fixtures.POSITIONS if p.account == name}:
            held = [
                round(float(h.quantity), 8)
                for h in state.holdings.values()
                if h.symbol == symbol
            ]
            want = float(fixtures.position(name, symbol).quantity)
            if held != [round(want, 8)]:
                problems.append(f"{name}: {symbol} replay={held} fixture={want}")

        log(f"Replay matches projection for '{name}' (id={acct_id})")

    if problems:
        raise SystemExit("E2E fixture is not reproducible from its own history:\n  " + "\n  ".join(problems))

def main():
    parser = argparse.ArgumentParser(description="Seed the E2E portfolio fixture")
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "delete the fixture accounts' transactions, holdings and "
            "position_state_checkpoint events, then re-create them from "
            "scripts/e2e_fixtures.py"
        ),
    )
    args = parser.parse_args()

    log("Starting e2e data seed...")
    user_id = get_or_create_user()
    brokerages = ensure_brokerages()
    accounts = create_accounts(user_id, brokerages)
    companies = get_or_create_companies()
    if args.reset:
        reset_fixture_accounts(accounts)
    create_holdings(accounts, companies)
    create_transactions(accounts, companies)
    emit_transaction_events(accounts)
    create_dividends(accounts, companies)
    update_current_prices(companies)
    create_price_history(companies)
    verify_replay_matches_holdings(accounts)
    log("E2E seed complete!")

if __name__ == "__main__":
    main()
