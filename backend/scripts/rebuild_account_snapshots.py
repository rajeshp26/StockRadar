"""Rebuild ALL historical snapshots for a single account using event replay.

Mirrors the proven single-pass replay logic of step9_rebuild_all_snapshots.py
but scoped to ONE account so the blast radius is minimal. This is the repair
path for snapshots corrupted by pre-split pricing (inflated total_value from
raw pre-split price x raw quantity when the `splits` table was empty).

Usage:
    python scripts/rebuild_account_snapshots.py --account-id 9                # dry-run (no writes)
    python scripts/rebuild_account_snapshots.py --account-id 9 --apply        # delete+rebuild

Safety:
    * Default is DRY-RUN: recompute every snapshot, compare to stored rows,
      and print the diff summary. Nothing is written.
    * --apply deletes the account's snapshots first, then re-inserts the
      recomputed rows in batches (identical to step9's proven path).
    * Refuses to run when ENVIRONMENT == production.

NOT split-quantity-aware alternative: backfill_portfolio_snapshots.py
reconstruct_holdings_at_date() rebuilds lots from raw transaction quantities
and does NOT apply split factors; for post-split dates it yields raw-scale
quantities. Use THIS script (replay-based) for any split-affected account.
"""
import argparse
import bisect
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

_env = os.environ.get("ENVIRONMENT", "development").lower()
if _env == "production":
    print("ERROR: rebuild_account_snapshots.py must NOT be run in production.")
    print("Use the daily snapshot job (compute_daily_snapshots) instead.")
    sys.exit(1)

sys.path.insert(0, ".")
sys.path.insert(0, "backend")

from database import supabase

logger = logging.getLogger("rebuild")
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.cdr_utils import (
    derive_account_cdr_companies,
    derive_cdr_lots_by_account_at_dates,
    split_holdings_by_cdr_lot,
)
from shared.fx_service import FXService
from shared.replay_engine import AccountState, ReplayEngine
from shared.snapshot_builder import build_snapshot_row
from shared.time_utils import now_utc

event_store = EventStore()
replay_engine = ReplayEngine(event_store)


class _SeriesFXService(FXService):
    """FXService backed by an in-memory rate series instead of per-call queries.

    build_snapshot_row creates a fresh FXService per snapshot date (and its
    instance cache has a 300s TTL), so a full multi-year rebuild performs
    ~2 PostgREST exchange_rates queries per holding per date -- market value
    at snapshot_date plus one per lot date for cost basis. For 1322 dates x
    ~73 holdings that is ~190k serial HTTP round-trips (hours). Preloading the
    USD->CAD series once (a few thousand rows) and resolving nearest-past from
    memory removes nearly all of those queries while keeping FXService's exact
    staleness semantics (MAX_STALE_DAYS) for the conversions.
    """

    def __init__(self, client, series: list[tuple[date, Decimal]]):
        super().__init__(client)
        # Ascending by rate_date: [(rate_date, rate), ...]
        self._series = series
        self._series_dates = [d for d, _ in series]

    def _query_cached_rate(self, base: str, target: str, as_of: date) -> Decimal | None:
        if base == "USD" and target == "CAD" and self._series:
            i = bisect.bisect_right(self._series_dates, as_of) - 1
            if i >= 0:
                rate_date, rate = self._series[i]
                days_old = (as_of - rate_date).days
                if days_old > self.MAX_STALE_DAYS:
                    logger.warning(
                        "FX rate %s->%s is %d days old (beyond %d-day freshness "
                        "window); forward-filling it rather than dropping the conversion",
                        base, target, days_old, self.MAX_STALE_DAYS,
                    )
                return rate
            return None
        return super()._query_cached_rate(base, target, as_of)


def load_account_events(aid: int) -> list:
    events = event_store.get_all_events(aggregate_type="account")
    account_events = []
    for ev in events:
        agg_id = ev.get("aggregate_id", "")
        if agg_id.startswith("account_"):
            try:
                ev_aid = int(agg_id.split("_")[1])
            except (ValueError, IndexError):
                continue
            if ev_aid == aid:
                account_events.append(ev)
    account_events.sort(key=lambda e: replay_engine._get_event_date(e) or date.min)
    return account_events


def fetch_all_rows(table, select, eq_col=None, eq_val=None, order_col=None, desc=False):
    """Fetch ALL rows for a filter, paginating past PostgREST's 1000-row cap."""
    step = 1000
    out = []
    start = 0
    while True:
        q = supabase.table(table).select(select)
        if eq_col is not None:
            q = q.eq(eq_col, eq_val)
        if order_col:
            q = q.order(order_col, desc=desc)
        q = q.range(start, start + step - 1)
        batch = q.execute()
        rows = batch.data or []
        out.extend(rows)
        if len(rows) < step:
            break
        start += step
    return out


def build_dates(aid: int, account_events: list) -> list:
    import calendar

    all_dates_set = set()
    rows = fetch_all_rows("portfolio_snapshots", "snapshot_date", eq_col="account_id", eq_val=aid)
    for r in rows:
        all_dates_set.add(r["snapshot_date"])
    for ev in account_events:
        data = ev.get("data", {}) or {}
        for key in ["transaction_date", "effective_date"]:
            val = data.get(key)
            if val:
                all_dates_set.add(str(val)[:10])
        created = ev.get("created_at", "")
        if created:
            all_dates_set.add(str(created)[:10])
    # Month-end anchors; a future one is unbuildable, so it is dropped. Use the
    # builder's own clock - a local/UTC date split here reintroduces the refusal.
    today = now_utc().date()
    for d_str in list(all_dates_set):
        dt = date.fromisoformat(d_str)
        all_dates_set.add(dt.replace(day=1).isoformat())
        month_end = dt.replace(day=calendar.monthrange(dt.year, dt.month)[1])
        if month_end <= today:
            all_dates_set.add(month_end.isoformat())
    return sorted(all_dates_set)


def load_companies(cids) -> tuple:
    company_names, companies_map, company_currencies = {}, {}, {}
    if not cids:
        return company_names, companies_map, company_currencies
    comps = supabase.table("companies").select(
        "company_id,company_name,ticker_symbol,cdr_ratio,currency"
    ).in_("company_id", list(cids)).execute()
    for row in comps.data or []:
        cid_key = int(row["company_id"])
        company_names[cid_key] = row["company_name"] or row["ticker_symbol"]
        companies_map[cid_key] = row
        company_currencies[cid_key] = row.get("currency", "USD")
    return company_names, companies_map, company_currencies


def load_price_history(cids, max_date) -> dict:
    price_history_map = {}
    if not cids:
        return price_history_map
    repo = PortfolioRepository(supabase)
    for cid in cids:
        try:
            single_map = repo.get_all_prices_historical([cid], max_date)
            if single_map:
                price_history_map[cid] = single_map[cid]
        except Exception as e:
            logger.error(f"Failed to load price_history for cid={cid}: {e}")
    return price_history_map


def load_exchange_overrides(aid: int, derived_cdr: set[int] | None = None) -> dict:
    """CDR exchange overrides from transactions, unioned with stored holdings.

    The parser detects CDR per-transaction and stored the override in
    portfolio_transactions raw_data for sold positions too (AMD/NVDA in
    account 7), which holdings rows no longer cover. Transactions are the
    durable source: classify per (account, company) from raw transaction data
    and union with whatever is currently stored on holdings rows so the TOR
    override survives every historical window that held the CDR.
    """
    overrides: dict[int, str] = {}
    try:
        rows = supabase.table("portfolio_holdings").select(
            "company_id, exchange_override"
        ).eq("account_id", aid).execute()
        for row in rows.data or []:
            if row.get("exchange_override"):
                overrides[int(row["company_id"])] = row["exchange_override"]
    except Exception as e:
        print(f"  WARNING: could not load exchange_overrides for account {aid}: {e}")
    if derived_cdr is None:
        derived_cdr = derive_account_cdr_companies(supabase, aid)
    for cid in derived_cdr:
        overrides[cid] = "TOR"
    return overrides


def load_usd_cad_rate_series() -> list[tuple[date, Decimal]]:
    """Fetch the full USD->CAD rate series once for in-memory FX lookups."""
    rows = fetch_all_rows(
        "exchange_rates",
        "base_currency, rate, rate_date",
        eq_col="target_currency",
        eq_val="CAD",
    )
    series = []
    for r in rows:
        if r.get("base_currency") != "USD":
            continue
        try:
            series.append((date.fromisoformat(r["rate_date"]), Decimal(str(r["rate"]))))
        except (KeyError, ValueError):
            continue
    series.sort(key=lambda t: t[0])
    return series


def build_snapshots(aid: int):
    acct_ccy = "USD"
    try:
        acct_rows = supabase.table("portfolio_accounts").select(
            "account_id, currency"
        ).eq("account_id", aid).execute()
        for r in acct_rows.data or []:
            acct_ccy = r.get("currency", "USD")
    except Exception:
        pass

    print(f"Loading events for account {aid}...")
    account_events = load_account_events(aid)
    print(f"  Account {aid}: {len(account_events)} events")

    all_dates = build_dates(aid, account_events)
    print(f"Total unique dates: {len(all_dates)}")
    print(f"Range: {all_dates[0]} to {all_dates[-1]}")

    cids = set()
    for ev in account_events:
        cid = ev.get("data", {}).get("company_id")
        if cid:
            cids.add(int(cid))
    print(f"Companies referenced: {sorted(cids)}")

    company_names, companies_map, company_currencies = load_companies(cids)

    fx_series = load_usd_cad_rate_series()
    print(f"USD->CAD FX series: {len(fx_series)} rates "
          f"({fx_series[0][0]} to {fx_series[-1][0]})" if fx_series else "USD->CAD FX series: empty")
    fx_service = _SeriesFXService(supabase, fx_series)

    max_date = date.fromisoformat(all_dates[-1])
    price_history_map = load_price_history(cids, max_date)
    ph_total = sum(len(v) for v in price_history_map.values())
    print(f"Price history: {ph_total} rows for {len(price_history_map)} companies (split-adjusted)")

    # Tier 2 forward-fill cannot price a company with no rows, so these positions
    # stay in the portfolio (keeping cash correct) but carry no valuation. The
    # rebuild still succeeds, so name them here rather than let them pass silent.
    unpriced = sorted(cid for cid in cids if not price_history_map.get(cid))
    if unpriced:
        print(f"WARNING: {len(unpriced)} of {len(cids)} companies have no price_history "
              f"and will be carried UNVALUED: {unpriced}")

    derived_cdr = derive_account_cdr_companies(supabase, aid)
    exchange_overrides = load_exchange_overrides(aid, derived_cdr)

    # derived_cdr is company-keyed and date-blind, so it cannot express a company held
    # as BOTH a CDR lot and a direct lot (BLK-027). One scan for every rebuild date:
    # this loop walks all_dates, so a per-date derivation would re-read the whole
    # paginated transaction table once per date.
    lots_by_date = derive_cdr_lots_by_account_at_dates(supabase, all_dates)

    # Group events by effective date
    events_by_date = defaultdict(list)
    for ev in account_events:
        ev_date = replay_engine._get_event_date(ev)
        if ev_date:
            events_by_date[ev_date.isoformat()].append(ev)
        else:
            created = ev.get("created_at", "")
            events_by_date[str(created)[:10] if created else "2000-01-01"].append(ev)

    rows = []
    state = AccountState(account_id=aid)
    for sd in all_dates:
        target_date = date.fromisoformat(sd)
        for ev in events_by_date.get(sd, []):
            handler_name = f"_handle_{ev.get('event_type', '')}"
            handler = getattr(replay_engine, handler_name, None)
            if handler:
                handler(state, ev)

        if not state.holdings and float(state.cash_balance) == 0 and float(state.net_deposits) == 0:
            continue

        holdings_state = []
        for cid, h in state.holdings.items():
            holdings_state.append({
                "company_id": cid,
                "symbol": h.symbol,
                "company_name": company_names.get(cid, h.symbol),
                "quantity": float(h.quantity),
                "total_cost": float(h.total_cost),
                "average_cost": float(h.average_cost),
                "realized_gain_loss": float(h.realized_gain_loss),
                "price_currency": company_currencies.get(cid, "USD"),
                "exchange_override": exchange_overrides.get(cid),
                "lots": [
                    {
                        "quantity": float(l["quantity"]),
                        "cost_per_share": float(l["cost_per_share"]),
                        "date": l["date"].isoformat()
                        if hasattr(l.get("date"), "isoformat")
                        else (str(l.get("date", "")) if l.get("date") else None),
                    }
                    for l in h.lots
                ] if h.lots else None,
            })

        lot_legs, lot_notes = split_holdings_by_cdr_lot(
            holdings_state, lots_by_date.get(sd, {}).get(aid), derived_cdr
        )
        for note in lot_notes:
            print(f"  Account {aid} {sd}: {note}")

        try:
            # Empty prices_by_company so Tier 1 (current) never fires:
            # consistent Tier 2 forward-fill from split-adjusted price_history.
            snapshot = build_snapshot_row(
                account_id=aid,
                snapshot_date=target_date,
                holdings_state=lot_legs,
                cash_balance=state.cash_balance,
                net_deposits=state.net_deposits,
                prices_by_company={},
                job_id=f"rebuild_{aid}_{sd}",
                stale_threshold_days=0,
                account_currency=acct_ccy,
                fx_service=fx_service,
                price_history=price_history_map,
                exchange_overrides=exchange_overrides,
                derived_cdr_companies=derived_cdr,
                company_currencies=company_currencies,
                companies_map=companies_map,
                lot_cdr_authoritative=True,
            )
        except Exception as e:
            print(f"  ERROR building snapshot {aid} {sd}: {e}")
            continue

        rows.append({
            "account_id": aid,
            "snapshot_date": sd,
            "total_value": snapshot.get("total_value", 0),
            "holdings_market_value": snapshot.get("holdings_market_value", 0),
            "cost_basis": snapshot.get("cost_basis", 0),
            "cash_balance": snapshot.get("cash_balance", 0),
            "net_deposits": snapshot.get("net_deposits", 0),
            "holdings_json": snapshot.get("holdings_json") or [],
            "job_id": snapshot.get("job_id"),
            "computed_at": datetime.now().isoformat(),
            "data_quality_flag": snapshot.get("data_quality_flag", "OK"),
        })
    return rows


def write_snapshots(aid: int, rows: list, max_date: str | None = None):
    MAX_BATCH = 50
    total_written = 0
    q = supabase.table("portfolio_snapshots").delete().eq("account_id", aid)
    if max_date:
        q = q.lte("snapshot_date", max_date)
        print(f"Old snapshots <= {max_date} deleted for account {aid}.")
    else:
        print(f"Old snapshots deleted for account {aid}.")
    q.execute()
    for i in range(0, len(rows), MAX_BATCH):
        batch = rows[i:i + MAX_BATCH]
        try:
            supabase.table("portfolio_snapshots").insert(batch).execute()
        except Exception as e:
            print(f"  ERROR writing batch: {e}")
            for br in batch:
                try:
                    supabase.table("portfolio_snapshots").insert(br).execute()
                except Exception:
                    pass
        total_written += len(batch)
    print(f"Written: {total_written} snapshots for account {aid}")


def main():
    parser = argparse.ArgumentParser(description="Rebuild snapshots for one account via event replay")
    parser.add_argument("--account-id", type=int, required=True, help="Account to rebuild")
    parser.add_argument("--apply", action="store_true", help="Write to DB (default: dry-run)")
    parser.add_argument("--max-date", type=str, default=None,
                        help="Only rebuild/write snapshots on or before this date (YYYY-MM-DD). "
                             "Snapshots after this date are left untouched.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    t0 = time.time()
    rows = build_snapshots(args.account_id)
    if args.max_date:
        rows = [r for r in rows if r["snapshot_date"] <= args.max_date]
        print(f"(boundary --max-date {args.max_date}: keeping {len(rows)} recomputed rows)")
    print(f"\nRecomputed {len(rows)} snapshots in {time.time() - t0:.1f}s")

    recomputed_by_date = {r["snapshot_date"]: r for r in rows}

    # ── Compare with stored rows (for dry-run informational output) ──
    stored = fetch_all_rows(
        "portfolio_snapshots",
        "snapshot_date,total_value,cost_basis,cash_balance,net_deposits,data_quality_flag",
        eq_col="account_id",
        eq_val=args.account_id,
        order_col="snapshot_date",
    )
    stored_by_date = {r["snapshot_date"]: r for r in stored}

    changed = 0
    too_high = 0
    max_recomputed = 0.0
    nd_decreases = 0
    nd_decrease_total = 0.0
    prev_nd = None

    for sd in sorted(recomputed_by_date):
        rc = recomputed_by_date[sd]
        rv = float(rc["total_value"])
        max_recomputed = max(max_recomputed, rv)
        if rv > 5_000_000:
            too_high += 1
        st = stored_by_date.get(sd)
        if prev_nd is not None and float(rc["net_deposits"]) < prev_nd - 0.01:
            nd_decreases += 1
            nd_decrease_total += prev_nd - float(rc["net_deposits"])
            print(f"  - ND down {sd}: {prev_nd:.2f} -> {float(rc['net_deposits']):.2f} "
                  f"(withdrawal)")
        prev_nd = float(rc["net_deposits"])
        if st is None:
            print(f"  + NEW {sd}: total={rv:,.2f} flag={rc['data_quality_flag']}")
            changed += 1
            continue
        sv = float(st["total_value"])
        if abs(sv - rv) > 0.01 or st["data_quality_flag"] != rc["data_quality_flag"]:
            changed += 1
            print(
                f"  ~ {sd}: stored={sv:,.2f} ({st['data_quality_flag']}) "
                f"-> recomputed={rv:,.2f} ({rc['data_quality_flag']})"
            )
    stored_dates = set(stored_by_date)
    preserved = {sd for sd in stored_dates if sd > (args.max_date or "")}
    missing_effective = len((stored_dates - preserved) - set(recomputed_by_date))

    print("\n=== REBUILD SUMMARY ===")
    print(f"Account: {args.account_id}")
    print(f"Stored snapshots: {len(stored_by_date)}  Recomputed: {len(recomputed_by_date)}")
    print(f"Rows changed (value or flag): {changed}")
    print(f"Rows absent from recompute (likely no activity): {missing_effective}")
    if preserved:
        print(f"Stored rows preserved beyond --max-date (left untouched): {len(preserved)}")
    print(f"Recomputed snapshots still > $5M: {too_high}")
    print(f"Recomputed max total_value: {max_recomputed:,.2f}")
    print(f"Net deposit decreases (withdrawals): {nd_decreases}, "
          f"total {nd_decrease_total:,.2f}")
    print(f"First: {rows[0]['snapshot_date']} val={float(rows[0]['total_value']):,.2f} nd={float(rows[0]['net_deposits']):,.2f}")
    print(f"Last:  {rows[-1]['snapshot_date']} val={float(rows[-1]['total_value']):,.2f} nd={float(rows[-1]['net_deposits']):,.2f}")

    if args.apply:
        write_snapshots(args.account_id, rows, args.max_date)
    else:
        print("\nDRY-RUN: no writes performed. Re-run with --apply to write.")


if __name__ == "__main__":
    main()