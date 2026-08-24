"""
Holdings Reconciliation Script

Compares the corrected backfill final holdings state against portfolio_holdings.
Cutover is BLOCKED if any position is missing/extra or quantity delta exceeds tolerance.

Usage:
    python -m scripts.reconcile_holdings [--account-id N] [--quantity-tolerance 0.0001]
"""

import argparse
import logging
import sys
from datetime import date

from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.portfolio.reconciliation")


def reconcile_holdings(
    account_id: int,
    quantity_tolerance: float = 0.0001,
    pct_tolerance: float = 0.1,
) -> tuple[bool, list[str]]:
    today = now_utc().date()
    snapshots_repo = PortfolioSnapshotsRepository()
    portfolio_repo = PortfolioRepository()

    latest_snapshot = snapshots_repo.get_latest_snapshot(account_id)
    if not latest_snapshot:
        return False, [f"No snapshots found for account {account_id}"]

    sd = latest_snapshot["snapshot_date"]
    if isinstance(sd, str):
        sd = date.fromisoformat(sd)
    if (today - sd).days > 1:
        return False, [f"Snapshot too old ({today - sd}d). Run backfill again."]

    corrected = {h["company_id"]: h for h in latest_snapshot.get("holdings_json") or []}
    current = {h["company_id"]: h for h in portfolio_repo.get_holdings(account_id)}

    all_ids = set(corrected.keys()) | set(current.keys())
    issues: list[str] = []
    passes = True

    for cid in all_ids:
        corr = corrected.get(cid)
        curr = current.get(cid)

        if corr and not curr:
            issues.append(f"MISSING in holdings: company_id={cid} ({corr['symbol']}) qty={corr['quantity']}")
            passes = False
        elif curr and not corr:
            issues.append(f"EXTRA in holdings: company_id={cid} ({curr['symbol']}) qty={curr['quantity']}")
            passes = False
        elif corr and curr:
            qty_diff = abs(float(corr['quantity']) - float(curr['quantity']))
            base = max(abs(float(corr['quantity'])), abs(float(curr['quantity'])), quantity_tolerance)
            if qty_diff > quantity_tolerance and base > 0:
                pct = qty_diff / base * 100
                if pct > pct_tolerance:
                    issues.append(
                        f"MISMATCH: company_id={cid} ({corr['symbol']}): "
                        f"backfill qty={corr['quantity']}, holdings qty={curr['quantity']} "
                        f"(diff={qty_diff:.4f}, {pct:.2f}%)"
                    )
                    passes = False

    if issues:
        for i in issues:
            logger.warning(f"Reconciliation {account_id}: {i}")
    else:
        logger.info(f"Account {account_id}: holdings table is consistent with corrected FIFO")

    return passes, issues


def main():
    parser = argparse.ArgumentParser(description="Reconcile holdings with backfill snapshots")
    parser.add_argument("--account-id", type=int, help="Specific account to reconcile")
    parser.add_argument("--quantity-tolerance", type=float, default=0.0001)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(message)s",
        stream=sys.stderr,
    )

    portfolio_repo = PortfolioRepository()

    if args.account_id:
        accounts = [{"account_id": args.account_id}]
    else:
        accounts = portfolio_repo.get_user_accounts_all()

    all_pass = True
    for acct in accounts:
        passes, issues = reconcile_holdings(
            acct["account_id"],
            quantity_tolerance=args.quantity_tolerance,
        )
        if not passes:
            all_pass = False
            logger.warning(f"Account {acct['account_id']}: RECONCILIATION FAILED")
        else:
            logger.info(f"Account {acct['account_id']}: PASSED")

    if all_pass:
        logger.info("All accounts passed reconciliation")
    else:
        logger.warning("Some accounts FAILED reconciliation — block cutover")
        sys.exit(1)


if __name__ == "__main__":
    main()
