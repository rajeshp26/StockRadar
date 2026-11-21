"""
Holdings Reconciliation Script

Compares the corrected backfill final holdings state against portfolio_holdings.
Cutover is BLOCKED if any position is missing/extra or quantity delta exceeds tolerance.

Usage:
    python -m scripts.reconcile_holdings [--account-id N] [--quantity-tolerance 0.00000001]

I3 -- why the tolerance is 1e-8, not 0.0001
-------------------------------------------
The old default (0.0001) was a *float* tolerance chosen to absorb binary-float
noise. It is larger than a real, stored position: account 9 / company 3112 holds
0.00005625 shares. A missing holding of that size reconciled as PASS because
abs(float(0.00005625) - 0.0) <= 0.0001, so the check could not distinguish
"correct" from "position silently dropped" -- its tolerance was unfalsifiable.

Share quantities are Decimal all the way through the reconciliation now: the DB
columns are numeric(20,8), and the replay/lot code parses with Decimal(str(...)).
Binary-float noise is therefore not something the tolerance has to absorb. The
tolerance is set to the declared storage scale (1e-8), so any difference that is
representable in the database is detectable. On the live dataset this tighter
tolerance changes no verdict across 151 positions (verified by
scripts/scratch/probe_i3_tolerance_impact.py): it only makes the check able to
fail when a sub-0.0001 share position goes missing.
"""

import argparse
import logging
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from shared.time_utils import now_utc

logger = logging.getLogger("stockerpro.portfolio.reconciliation")

#: portfolio_holdings.quantity / total_cost are numeric(20,8). A larger tolerance
#: is unfalsifiable for the smallest real positions (I3).
QUANTITY_TOLERANCE = Decimal("0.00000001")
PCT_TOLERANCE = Decimal("0.1")


def _decimal(value: object) -> Decimal:
    """Convert a DB/JSON scalar to Decimal via its decimal string.

    Going through str() is deliberate: Decimal(float) preserves the exact binary
    expansion (0.00005625 -> 0.00005624999999999999...), which is the float noise
    I3 exists to keep out of financial comparisons. str() yields the intended
    decimal value written by the producer.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a decimal quantity: {value!r}") from exc


def reconcile_holdings(
    account_id: int,
    quantity_tolerance: Decimal | float | str = QUANTITY_TOLERANCE,
    pct_tolerance: Decimal | float | str = PCT_TOLERANCE,
) -> tuple[bool, list[str]]:
    tol = _decimal(quantity_tolerance)
    if tol < 0:
        raise ValueError("quantity_tolerance must be non-negative")
    pct_tol = _decimal(pct_tolerance)

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

    corrected = {
        int(h["company_id"]): _decimal(h["quantity"])
        for h in latest_snapshot.get("holdings_json") or []
    }
    symbols = {
        int(h["company_id"]): h.get("symbol", "?")
        for h in latest_snapshot.get("holdings_json") or []
    }
    current_rows = portfolio_repo.get_holdings(account_id)
    current = {int(h["company_id"]): _decimal(h["quantity"]) for h in current_rows}
    for h in current_rows:
        symbols.setdefault(int(h["company_id"]), h.get("symbol", "?"))

    all_ids = set(corrected) | set(current)
    issues: list[str] = []
    passes = True

    for cid in all_ids:
        corr = corrected.get(cid)
        curr = current.get(cid)
        sym = symbols.get(cid, "?")

        if corr is not None and curr is None:
            issues.append(f"MISSING in holdings: company_id={cid} ({sym}) qty={corr}")
            passes = False
        elif curr is not None and corr is None:
            issues.append(f"EXTRA in holdings: company_id={cid} ({sym}) qty={curr}")
            passes = False
        elif corr is not None and curr is not None:
            qty_diff = abs(corr - curr)
            base = max(abs(corr), abs(curr), tol)
            if qty_diff > tol and base > 0:
                pct = qty_diff / base * 100
                if pct > pct_tol:
                    issues.append(
                        f"MISMATCH: company_id={cid} ({sym}): "
                        f"backfill qty={corr}, holdings qty={curr} "
                        f"(diff={qty_diff:.8f}, {pct:.2f}%)"
                    )
                    passes = False

    if issues:
        for i in issues:
            logger.warning("Reconciliation %s: %s", account_id, i)
    else:
        logger.info("Account %s: holdings table is consistent with corrected FIFO", account_id)

    return passes, issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile holdings with backfill snapshots")
    parser.add_argument("--account-id", type=int, help="Specific account to reconcile")
    parser.add_argument(
        "--quantity-tolerance",
        type=str,
        default=str(QUANTITY_TOLERANCE),
        help="absolute share-quantity tolerance as a decimal string (default: numeric(20,8) scale)",
    )
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
        passes, _issues = reconcile_holdings(
            acct["account_id"],
            quantity_tolerance=args.quantity_tolerance,
        )
        if not passes:
            all_pass = False
            logger.warning("Account %s: RECONCILIATION FAILED", acct["account_id"])
        else:
            logger.info("Account %s: PASSED", acct["account_id"])

    if all_pass:
        logger.info("All accounts passed reconciliation")
    else:
        logger.warning("Some accounts FAILED reconciliation \u2014 block cutover")
        sys.exit(1)


if __name__ == "__main__":
    main()
