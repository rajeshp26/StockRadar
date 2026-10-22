"""Read-only fleet scan for the BLK-026 lookahead signature.

BLK-026 defines the signature as a stored snapshot holding whose
price_age_days is NEGATIVE, i.e. the price used to value it is dated AFTER
the snapshot date. BLK-026's declared repair is to rebuild the affected
batches with the lookahead-guarded writer, so this scan is the executable
completion test for that blocker.

It scans every row (not a sample), because the claim being tested is
fleet-wide. Read-only. Exit 0 when no negative age exists, 1 when any does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

PAGE = 1000
COLS = "account_id,snapshot_date,total_value,data_quality_flag,holdings_json"


def fetch_snapshots() -> list[dict]:
    from database import supabase

    rows: list[dict] = []
    start = 0
    while True:
        batch = (
            supabase.table("portfolio_snapshots")
            .select(COLS)
            .order("account_id")
            .order("snapshot_date")
            .range(start, start + PAGE - 1)
            .execute()
        ).data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def parse_holdings(raw) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if isinstance(raw, dict):
        for key in ("holdings", "positions", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return [h for h in val if isinstance(h, dict)]
        return []
    if isinstance(raw, list):
        return [h for h in raw if isinstance(h, dict)]
    return []


def main() -> int:
    rows = fetch_snapshots()

    neg_rows = 0
    neg_entries = 0
    worst = 0
    per_account: dict[int, dict] = {}
    month_counts: dict[str, int] = {}
    samples: list[tuple[int, str, int, int]] = []

    for r in rows:
        aid = int(r["account_id"])
        snap_date = str(r["snapshot_date"])[:10]
        st = per_account.setdefault(aid, {"rows": 0, "neg_rows": 0, "entries": 0, "worst": 0})
        st["rows"] += 1

        bad = 0
        worst_here = 0
        for h in parse_holdings(r.get("holdings_json")):
            age = h.get("price_age_days")
            if age is None:
                continue
            try:
                age_i = int(age)
            except (TypeError, ValueError):
                continue
            if age_i < 0:
                bad += 1
                worst_here = min(worst_here, age_i)

        if bad:
            neg_rows += 1
            neg_entries += bad
            worst = min(worst, worst_here)
            st["neg_rows"] += 1
            st["entries"] += bad
            st["worst"] = min(st["worst"], worst_here)
            month = snap_date[:7]
            month_counts[month] = month_counts.get(month, 0) + 1
            if len(samples) < 10:
                samples.append((aid, snap_date, bad, worst_here))

    print(f"portfolio_snapshots rows scanned            : {len(rows)}")
    print(f"rows containing a negative price_age_days   : {neg_rows}")
    print(f"individual holdings entries with negative age: {neg_entries}")
    print(f"worst (most negative) price_age_days        : {worst}")

    if neg_rows:
        affected = sorted(a for a, s in per_account.items() if s["neg_rows"])
        print(f"accounts affected                           : {affected}")
        print("\nper-account (only affected):")
        for a in affected:
            s = per_account[a]
            print(f"  account {a:>3}: rows={s['rows']:>5} neg_rows={s['neg_rows']:>5} "
                  f"entries={s['entries']:>6} worst_age={s['worst']}")
        print("\nfirst contaminated rows (account, date, neg_entries, worst_age):")
        for a, d, n, w in samples:
            print(f"  acct={a} date={d} neg_entries={n} worst_age={w}")
        print("\nby snapshot month:")
        for m in sorted(month_counts):
            print(f"  {m}: {month_counts[m]}")
    else:
        print("accounts affected                           : none")

    print("\nREAD-ONLY: nothing was modified.")
    return 1 if neg_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
