"""
Historical backfill script for portfolio_snapshots.

Usage:
    python -m scripts.backfill_portfolio_snapshots [--account-id N] [--force] [--validate-only]

Event-driven strategy: Only compute FIFO snapshots on dates where something
changes (trade, money movement, dividend, month-end).

WARNING: In production, the daily snapshot job handles gap-filling automatically.
This script should only be used for initial setup or one-time repairs in dev/staging.
"""

import os
import argparse
import logging

_env = os.environ.get("ENVIRONMENT", "development").lower()
if _env == "production":
    print("ERROR: backfill_portfolio_snapshots.py should NOT be run in production.")
    print("The daily snapshot job handles gap-filling automatically.")
    print("Set ENVIRONMENT=development to override (not recommended).")
    import sys
    sys.exit(1)
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from shared.time_utils import now_utc
from shared.snapshot_builder import (
    build_snapshot_row, _classify_lot_action, resolve_price_forward_filled
)
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger = logging.getLogger("stockerpro.portfolio.backfill")


def reconstruct_holdings_at_date(
    account_ids: List[int],
    target_date: date,
    all_txns: List[Dict[str, Any]],
    price_map: Dict[int, List[tuple]],
) -> List[Dict[str, Any]]:
    lots: Dict[tuple, list] = defaultdict(list)

    relevant = [
        t for t in all_txns
        if _classify_lot_action(t) is not None
        and t["transaction_date"] <= target_date
    ]
    relevant.sort(key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))

    for t in relevant:
        cid = t.get("company_id")
        if not cid:
            continue
        key = (t.get("account_id"), cid)
        action = _classify_lot_action(t)

        if action == "BUY":
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            cost_per_share = price + (commission / qty) if qty else price
            lots[key].append({
                "quantity": float(qty),
                "cost_per_share": float(cost_per_share),
                "date": t["transaction_date"].isoformat(),
                "symbol": t.get("symbol"),
                "company_id": cid,
            })

        elif action == "SELL":
            qty = abs(float(t.get("quantity") or 0))
            remaining = qty
            while remaining > 0 and lots[key]:
                lot = lots[key][0]
                lot_qty = float(lot["quantity"])
                if lot_qty <= remaining:
                    remaining -= lot_qty
                    lots[key].pop(0)
                else:
                    lot["quantity"] -= remaining
                    remaining = 0

    holdings_state = []
    for (_, cid), lot_list in lots.items():
        qty_held = sum(l["quantity"] for l in lot_list)
        if qty_held <= 0.001:
            continue
        avg_cost = sum(l["quantity"] * l["cost_per_share"] for l in lot_list) / qty_held
        total_cost = qty_held * avg_cost
        symbol = lot_list[0].get("symbol", "?")

        holdings_state.append({
            "company_id": cid,
            "symbol": symbol,
            "quantity": qty_held,
            "total_cost": total_cost,
            "average_cost": avg_cost,
        })

    return holdings_state


def find_corrupted_snapshots() -> List[Dict[str, Any]]:
    """Detect snapshots where cost_basis=0 but holdings_json shows non-zero quantities.
    
    These were created by the snapshot job before the key-name fix
    (cost_basis→total_cost, avg_cost→average_cost).
    """
    repo = PortfolioRepository()
    accounts = repo.get_user_accounts_all()
    snapshots_repo = PortfolioSnapshotsRepository()
    corrupt: List[Dict[str, Any]] = []
    
    for acct in accounts:
        all_snaps = snapshots_repo.get_account_snapshots(acct["account_id"])
        for s in all_snaps:
            if s.get("cost_basis", 0) != 0:
                continue
            hj = s.get("holdings_json")
            if not hj:
                continue
            has_nonzero_qty = any(
                isinstance(h, dict) and h.get("quantity", 0) > 0
                for h in hj
            )
            if has_nonzero_qty:
                corrupt.append(s)
    
    return corrupt


def repair_corrupted_snapshots(dry_run: bool = False) -> int:
    """Re-compute and upsert corrupted snapshots using corrected builder."""
    corrupt = find_corrupted_snapshots()
    if not corrupt:
        logger.info("No corrupted snapshots found")
        return 0
    
    logger.warning(f"Found {len(corrupt)} corrupted snapshots to repair")
    portfolio_repo = PortfolioRepository()
    snapshots_repo = PortfolioSnapshotsRepository()
    
    repaired = 0
    for s in corrupt:
        account_id = s["account_id"]
        snapshot_date = s["snapshot_date"]
        if isinstance(snapshot_date, str):
            sd = date.fromisoformat(snapshot_date)
        else:
            sd = snapshot_date
        
        logger.info(f"Repairing account {account_id} snapshot on {sd}")
        
        company_ids = [
            h["company_id"] for h in (s.get("holdings_json") or [])
            if h.get("company_id")
        ]
        price_map = portfolio_repo.get_all_prices_historical(company_ids, sd)
        
        all_txns = portfolio_repo.get_accounts_transactions(
            [account_id], activity_types=["Trade"]
        )
        for t in all_txns:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()
        
        holdings_state = reconstruct_holdings_at_date(
            [account_id], sd, all_txns, price_map
        )
        cash_balance = portfolio_repo.get_cash_balance(account_id, sd)
        net_deposits = portfolio_repo.get_net_deposits(account_id, sd)
        
        prices_by_company: Dict[int, Dict] = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, sd, price_map)
            if result:
                prices_by_company[cid] = result
        
        account_info = portfolio_repo.get_account_by_id(account_id)
        account_currency = (account_info or {}).get("currency", "CAD")
        
        corrected = build_snapshot_row(
            account_id=account_id,
            snapshot_date=sd,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id=f"repair_{now_utc().isoformat()}",
            account_currency=account_currency,
        )
        if not dry_run:
            snapshots_repo.upsert_snapshot(corrected)
        repaired += 1
    
    logger.info(f"Repaired {repaired} corrupted snapshots" +
                (" (dry run)" if dry_run else ""))
    return repaired


def _compute_symbol_company_map(account_ids: List[int]) -> Tuple[set, List[int]]:
    repo = PortfolioRepository()
    symbols_seen: set = set()
    company_ids: set = set()

    txns = repo.get_accounts_transactions(account_ids, activity_types=["Trade"])
    for t in txns:
        sym = t.get("symbol")
        cid = t.get("company_id")
        if sym:
            symbols_seen.add(sym)
        if cid:
            company_ids.add(cid)

    return symbols_seen, list(company_ids)


def backfill_account(account_id: int, force: bool = False, validate_only: bool = False):
    portfolio_repo = PortfolioRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    if not force and snapshots_repo.has_snapshots(account_id):
        logger.info(f"Account {account_id} already backfilled")
        return

    event_dates = portfolio_repo.get_event_dates(account_id)
    if not event_dates:
        logger.info(f"No events for account {account_id}, skipping")
        return

    today = now_utc().date()
    earliest = event_dates[0]

    symbols_seen, company_ids = _compute_symbol_company_map([account_id])
    price_map = portfolio_repo.get_all_prices_historical(company_ids, today)
    all_txns = portfolio_repo.get_accounts_transactions([account_id], activity_types=["Trade"])

    for t in all_txns:
        d = t.get("transaction_date")
        if isinstance(d, str):
            t["transaction_date"] = date.fromisoformat(d)
        elif isinstance(d, datetime):
            t["transaction_date"] = d.date()

    logger.info(f"Backfilling account {account_id}: {len(event_dates)} event dates")

    # Resolve account currency for FX conversion
    account_info = portfolio_repo.get_account_by_id(account_id)
    account_currency = (account_info or {}).get("currency", "CAD")

    written = 0
    for d in event_dates:
        holdings_state = reconstruct_holdings_at_date([account_id], d, all_txns, price_map)
        cash_balance = portfolio_repo.get_cash_balance(account_id, d)
        net_deposits = portfolio_repo.get_net_deposits(account_id, d)

        prices_by_company: Dict[int, Dict] = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, d, price_map)
            if result:
                prices_by_company[cid] = result

        snapshot_row = build_snapshot_row(
            account_id=account_id,
            snapshot_date=d,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id="backfill_20260622",
            account_currency=account_currency,
        )

        if not validate_only:
            snapshots_repo.upsert_snapshot(snapshot_row)
        written += 1

    if event_dates[-1] < today:
        holdings_state = reconstruct_holdings_at_date([account_id], today, all_txns, price_map)
        cash_balance = portfolio_repo.get_cash_balance(account_id, today)
        net_deposits = portfolio_repo.get_net_deposits(account_id, today)
        prices_by_company = {}
        for cid in company_ids:
            result = resolve_price_forward_filled(cid, today, price_map)
            if result:
                prices_by_company[cid] = result

        snapshot_row = build_snapshot_row(
            account_id=account_id,
            snapshot_date=today,
            holdings_state=holdings_state,
            cash_balance=cash_balance,
            net_deposits=net_deposits,
            prices_by_company=prices_by_company,
            job_id="backfill_20260622",
            account_currency=account_currency,
        )

        if not validate_only:
            snapshots_repo.upsert_snapshot(snapshot_row)
        written += 1

    if validate_only:
        errors = snapshots_repo.validate_snapshot_invariants(account_id)
        if errors:
            for e in errors:
                logger.warning(f"Validation issue: {e}")
        else:
            logger.info(f"Account {account_id}: all invariants passed")

    logger.info(f"Backfilled account {account_id}: {written} snapshots from {earliest} to {today}")


def _detect_bug_types(stored: dict, recomputed: dict) -> List[str]:
    """Compare stored vs recomputed snapshot. Returns list of bug type labels."""
    bugs: List[str] = []

    # Type 1: cost_basis=0 with non-zero holdings
    if (stored.get("cost_basis", 0) == 0
            and recomputed.get("cost_basis", 0) > 0):
        bugs.append("COST_BASIS_ZERO")

    # Type 2: cash gap from missing whitelist types
    stored_cash = Decimal(str(stored.get("cash_balance", 0)))
    recomputed_cash = Decimal(str(recomputed.get("cash_balance", 0)))
    if abs(stored_cash - recomputed_cash) > Decimal("0.01"):
        bugs.append("CASH_GAP")

    # Type 3: negative total with OK quality flag
    total = Decimal(str(stored.get("total_value", 0)))
    if total < 0 and stored.get("data_quality_flag") == "OK":
        bugs.append("NEGATIVE_TOTAL_NO_FLAG")

    # Type 4: holdings_market_value differs due to avg_cost vs average_cost key
    stored_mv = Decimal(str(stored.get("holdings_market_value", 0)))
    recomputed_mv = Decimal(str(recomputed.get("holdings_market_value", 0)))
    if stored_mv != recomputed_mv and "CASH_GAP" not in bugs:
        bugs.append("PRICE_KEY_MISMATCH")

    return bugs


def repair_all_snapshots(
    dry_run: bool = False,
    max_accounts: Optional[int] = None,
) -> Dict[str, Any]:
    """Scan ALL historical snapshots, recompute with fixed builder, classify bugs, repair.

    Returns summary dict with counts per bug type.
    """
    portfolio_repo = PortfolioRepository()
    snapshots_repo = PortfolioSnapshotsRepository()
    accounts = portfolio_repo.get_user_accounts_all()

    if max_accounts is not None:
        accounts = accounts[:max_accounts]

    summary: Dict[str, Any] = {
        "accounts_scanned": 0,
        "snapshots_scanned": 0,
        "snapshots_repaired": 0,
        "bug_counts": {
            "COST_BASIS_ZERO": 0,
            "CASH_GAP": 0,
            "NEGATIVE_TOTAL_NO_FLAG": 0,
            "PRICE_KEY_MISMATCH": 0,
        },
        "errors": [],
    }

    today = now_utc().date()

    for acct in accounts:
        account_id = acct["account_id"]
        summary["accounts_scanned"] += 1

        all_snaps = snapshots_repo.get_account_snapshots(account_id)
        if not all_snaps:
            continue

        # Gather data needed for recompute
        company_ids: List[int] = []
        for s in all_snaps:
            hj = s.get("holdings_json") or []
            for h in hj:
                cid = h.get("company_id")
                if cid and cid not in company_ids:
                    company_ids.append(cid)

        price_map = portfolio_repo.get_all_prices_historical(company_ids, today)

        all_txns = portfolio_repo.get_accounts_transactions(
            [account_id], activity_types=["Trade"]
        )
        for t in all_txns:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()

        account_info = portfolio_repo.get_account_by_id(account_id)
        account_currency = (account_info or {}).get("currency", "CAD")

        for s in all_snaps:
            summary["snapshots_scanned"] += 1
            snapshot_date = s["snapshot_date"]
            if isinstance(snapshot_date, str):
                sd = date.fromisoformat(snapshot_date)
            else:
                sd = snapshot_date

            try:
                holdings_state = reconstruct_holdings_at_date(
                    [account_id], sd, all_txns, price_map
                )
                cash_balance = portfolio_repo.get_cash_balance(account_id, sd)
                net_deposits = portfolio_repo.get_net_deposits(account_id, sd)

                prices_by_company: Dict[int, Dict] = {}
                for cid in company_ids:
                    result = resolve_price_forward_filled(cid, sd, price_map)
                    if result:
                        prices_by_company[cid] = result

                recomputed = build_snapshot_row(
                    account_id=account_id,
                    snapshot_date=sd,
                    holdings_state=holdings_state,
                    cash_balance=cash_balance,
                    net_deposits=net_deposits,
                    prices_by_company=prices_by_company,
                    job_id=f"repair_all_{now_utc().isoformat()}",
                    account_currency=account_currency,
                    price_history=price_map,
                )


                bugs = _detect_bug_types(s, recomputed)

                if bugs:
                    for bug in bugs:
                        summary["bug_counts"][bug] = \
                            summary["bug_counts"].get(bug, 0) + 1

                    logger.info(
                        f"Account {account_id} snapshot {sd}: "
                        f"bugs={bugs} stored=({s.get('total_value')}, "
                        f"{s.get('cash_balance')}, {s.get('cost_basis')}, "
                        f"{s.get('data_quality_flag')}) → recomputed=("
                        f"{recomputed['total_value']}, "
                        f"{recomputed['cash_balance']}, "
                        f"{recomputed['cost_basis']}, "
                        f"{recomputed['data_quality_flag']})"
                    )

                    if not dry_run:
                        snapshots_repo.upsert_snapshot(recomputed)
                        summary["snapshots_repaired"] += 1

            except Exception as e:
                summary["errors"].append(
                    f"Account {account_id} snapshot {sd}: {e}"
                )
                logger.error(f"Failed to reprocess account {account_id} {sd}: {e}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Backfill portfolio snapshots")
    parser.add_argument("--account-id", type=int, help="Specific account to backfill")
    parser.add_argument("--force", action="store_true", help="Re-run backfill even if snapshots exist")
    parser.add_argument("--validate-only", action="store_true", help="Check invariants without writing")
    parser.add_argument("--repair", action="store_true", help="Detect and repair corrupted snapshots (cost_basis=0 only)")
    parser.add_argument("--repair-all", action="store_true", help="Full recompute of ALL snapshots; detects Types 1-4 (cost_basis=0, cash_gap, negative_total_no_flag, price_key_mismatch)")
    parser.add_argument("--max-accounts", type=int, help="With --repair-all, limit accounts processed (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="With --repair/--repair-all, only list issues without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(message)s",
        stream=sys.stderr,
    )

    if args.repair:
        count = repair_corrupted_snapshots(dry_run=args.dry_run)
        if count == 0:
            logger.info("No repair needed")
        return

    if args.repair_all:
        summary = repair_all_snapshots(
            dry_run=args.dry_run,
            max_accounts=args.max_accounts,
        )
        logger.info(
            f"Repair-all complete: {summary['accounts_scanned']} accounts, "
            f"{summary['snapshots_scanned']} snapshots scanned, "
            f"{summary['snapshots_repaired']} repaired, "
            f"errors={len(summary['errors'])}. "
            f"Bug counts: {summary['bug_counts']}"
        )
        return

    snapshots_repo = PortfolioSnapshotsRepository()
    portfolio_repo = PortfolioRepository()

    if args.account_id:
        backfill_account(args.account_id, force=args.force, validate_only=args.validate_only)
    else:
        all_accounts = portfolio_repo.get_user_accounts_all()
        for acct in all_accounts:
            backfill_account(acct["account_id"], force=args.force, validate_only=args.validate_only)

    logger.info("Backfill complete")


if __name__ == "__main__":
    main()
