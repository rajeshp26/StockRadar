"""Read-only reconciliation of stored snapshots against a fresh in-memory recompute.

Nothing is written. For each account every snapshot date is rebuilt in memory
and diffed against the stored row at three levels: row totals, each holding
inside holdings_json, and the CDR ratio that was actually applied.

The CDR defect priced a 1/10-scale position as a full US share, so a holding
whose stored value is ~10x its recomputed value is the signature of an
unrepaired row. A ratio near 1.0 instead means an ordinary valuation drift
(missing or revised price), which is a different defect and must not be
confused with the CDR repair.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

FIELDS = (
    "snapshot_date,total_value,holdings_market_value,cash_balance,"
    "holdings_json,data_quality_flag"
)


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _by_company(row: dict) -> dict:
    out: dict[int, dict] = {}
    for holding in row.get("holdings_json") or []:
        cid = holding.get("company_id")
        if cid is not None:
            out[int(cid)] = holding
    return out


def load_stored(aid: int) -> dict:
    from rebuild_account_snapshots import fetch_all_rows

    rows = fetch_all_rows(
        "portfolio_snapshots", FIELDS, eq_col="account_id", eq_val=aid,
        order_col="snapshot_date",
    )
    return {r["snapshot_date"]: r for r in rows}


def reconcile_account(aid: int, tolerance: Decimal) -> dict:
    from rebuild_account_snapshots import build_snapshots

    recomputed = {r["snapshot_date"]: r for r in build_snapshots(aid)}
    stored = load_stored(aid)

    row_diffs: list[dict] = []
    holding_diffs: list[dict] = []

    for iso in sorted(set(recomputed) | set(stored)):
        new, old = recomputed.get(iso), stored.get(iso)
        if new is None or old is None:
            row_diffs.append({
                "date": iso,
                "kind": "missing_recomputed" if old else "missing_stored",
                "stored_total": float(_dec(old.get("total_value"))) if old else None,
                "recomputed_total": float(_dec(new.get("total_value"))) if new else None,
            })
            continue

        new_total, old_total = _dec(new.get("total_value")), _dec(old.get("total_value"))
        delta = new_total - old_total
        if abs(delta) > tolerance:
            row_diffs.append({
                "date": iso,
                "kind": "total_mismatch",
                "stored_total": float(old_total),
                "recomputed_total": float(new_total),
                "delta": float(delta),
            })

        new_h, old_h = _by_company(new), _by_company(old)
        for cid in sorted(set(new_h) | set(old_h)):
            n, o = new_h.get(cid), old_h.get(cid)
            nv = _dec(n.get("current_value")) if n else Decimal(0)
            ov = _dec(o.get("current_value")) if o else Decimal(0)
            if abs(nv - ov) <= tolerance:
                continue
            holding_diffs.append({
                "date": iso,
                "company_id": cid,
                "symbol": (n or o or {}).get("symbol"),
                "stored_value": float(ov),
                "recomputed_value": float(nv),
                "delta": float(nv - ov),
                "stored_over_recomputed": float(ov / nv) if nv else None,
                "stored_qty": (o or {}).get("quantity"),
                "recomputed_qty": (n or {}).get("quantity"),
                "stored_price": (o or {}).get("current_price"),
                "recomputed_price": (n or {}).get("current_price"),
                "recomputed_cdr_ratio": (n or {}).get("cdr_ratio"),
                "recomputed_cdr_source": (n or {}).get("cdr_ratio_source"),
                "stored_exchange_override": (o or {}).get("exchange_override"),
            })

    def is_cdr_sig(d: dict) -> bool:
        ratio = d.get("stored_over_recomputed")
        return ratio is not None and 9.0 <= ratio <= 11.0

    cdr_dates = sorted({d["date"] for d in holding_diffs if is_cdr_sig(d)})
    other = [d for d in holding_diffs if not is_cdr_sig(d)]
    abs_delta = sum(abs(d["delta"]) for d in row_diffs if d["kind"] == "total_mismatch")

    return {
        "account_id": aid,
        "stored_rows": len(stored),
        "recomputed_rows": len(recomputed),
        "row_diffs": row_diffs,
        "holding_diffs": holding_diffs,
        "cdr_10x_holding_diffs": [d for d in holding_diffs if is_cdr_sig(d)],
        "non_cdr_holding_diffs": other,
        "cdr_affected_dates": cdr_dates,
        "cdr_affected_date_count": len(cdr_dates),
        "total_abs_row_delta": float(abs_delta),
    }


def dump_case(aid: int, iso: str, cid: int) -> None:
    """Print the full stored vs recomputed holding record for one date+company."""
    from rebuild_account_snapshots import build_snapshots

    recomputed = {r["snapshot_date"]: r for r in build_snapshots(aid)}
    stored = load_stored(aid)
    new, old = recomputed.get(iso), stored.get(iso)
    if new is None or old is None:
        print(f"missing side: recomputed={new is not None} stored={old is not None}")
        return
    print(f"\n{'=' * 72}\nACCOUNT {aid} {iso} company_id={cid}\n{'=' * 72}")
    for label, row in (("STORED", old), ("RECOMPUTED", new)):
        holding = _by_company(row).get(cid, {})
        print(f"\n--- {label} ---")
        print(json.dumps(holding, indent=2, sort_keys=True, default=str))
        print(f"  row total_value      : {row.get('total_value')}")
        print(f"  row cash_balance     : {row.get('cash_balance')}")
        print(f"  row data_quality_flag: {row.get('data_quality_flag')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", default="7,8,9")
    parser.add_argument("--tolerance", default="0.01")
    parser.add_argument("--sample", type=int, default=8, help="holding diffs to print per account")
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--dump", help="ISO_DATE,COMPANY_ID - print one full holding record")
    args = parser.parse_args()

    if args.dump:
        iso, cid = args.dump.split(",")
        dump_case(int(args.accounts.split(",")[0]), iso, int(cid))
        return 0

    accounts = [int(a) for a in args.accounts.split(",") if a.strip()]
    tolerance = Decimal(args.tolerance)
    reports = [reconcile_account(aid, tolerance) for aid in accounts]

    if args.as_json:
        print(json.dumps(reports, indent=2, default=str))
        return 0

    grand_cdr_dates: set[str] = set()
    for rep in reports:
        print(f"\n{'=' * 72}\nACCOUNT {rep['account_id']}  "
              f"stored={rep['stored_rows']}  recomputed={rep['recomputed_rows']}")
        print(f"  total_mismatch rows      : {len(rep['row_diffs'])}")
        print(f"  holding diffs            : {len(rep['holding_diffs'])}")
        print(f"  CDR 10x signature diffs  : {len(rep['cdr_10x_holding_diffs'])}")
        print(f"  non-CDR holding diffs    : {len(rep['non_cdr_holding_diffs'])}")
        print(f"  CDR-affected dates       : {rep['cdr_affected_date_count']}")
        print(f"  summed |row delta|       : {rep['total_abs_row_delta']:,.2f}")
        grand_cdr_dates.update(rep["cdr_affected_dates"])

        for d in rep["cdr_10x_holding_diffs"][: args.sample]:
            print(f"    {d['date']} cid={d['company_id']:<4} {str(d['symbol']):<6} "
                  f"stored={d['stored_value']:>12,.2f} "
                  f"recomputed={d['recomputed_value']:>11,.2f} "
                  f"ratio={d['stored_over_recomputed']:.2f} "
                  f"-> {d['recomputed_cdr_source']}")
        if len(rep["cdr_10x_holding_diffs"]) > args.sample:
            print(f"    ... and {len(rep['cdr_10x_holding_diffs']) - args.sample} more")
        for d in rep["non_cdr_holding_diffs"][: args.sample]:
            ratio = d["stored_over_recomputed"]
            ratio_s = f"{ratio:.2f}" if ratio is not None else "n/a"
            print(f"    [non-cdr] {d['date']} cid={d['company_id']:<4} "
                  f"{str(d['symbol']):<6} stored={d['stored_value']:>12,.2f} "
                  f"recomputed={d['recomputed_value']:>11,.2f} ratio={ratio_s} "
                  f"qty {d['stored_qty']}->{d['recomputed_qty']} "
                  f"px {d['stored_price']}->{d['recomputed_price']}")

    print(f"\n{'=' * 72}\nTOTAL CDR-affected dates across accounts: {len(grand_cdr_dates)}")
    print("READ-ONLY: no rows were modified. Repair requires explicit approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
