"""Forensic probe: does the dump use the SAME company_id mapping as the local DB?

The sampling verdict checked company_id 899 (LEG) and 3162 (RMAX), values taken
from the LOCAL database. If the cloud dump assigned different company_ids, those
counts were measuring an unrelated company and the "monthly sampled" conclusion
would be unfounded. This resolves identity from the dump's own companies table by
ticker_symbol, then re-counts price_history under those ids.

Also captures the splits rows for these tickers, since re-derivation of
adjustment_factor depends on the owned split calendar.

Read-only. Touches no database.

Usage:
    python backend/scripts/verify_dump_company_identity.py
"""
from __future__ import annotations

import gzip
import re
from collections import defaultdict
from pathlib import Path

DUMP = Path(r"C:\Documents\db_cluster-31-08-2026@19-49-47.backup.gz")
COPY_RE = re.compile(r"^COPY\s+([\w.]+)\s*(?:\((.*?)\))?\s+FROM\s+stdin;")
LOCAL_IDS = {"LEG": 899, "RMAX": 3162}
NULL = r"\N"


def main() -> int:
    if not DUMP.exists():
        print(f"FATAL: dump not found: {DUMP}")
        return 1

    companies_cols: list[str] = []
    companies: dict[str, str] = {}          # ticker_symbol -> company_id
    names: dict[str, str] = {}              # ticker_symbol -> company_name
    all_tickers: dict[str, str] = {}        # company_id -> ticker
    splits_cols: list[str] = []
    ph_rows: dict[str, list[str]] = defaultdict(list)
    splits_rows: list[list[str]] = []
    current = None

    with gzip.open(DUMP, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if current is not None:
                if line.startswith("\\."):
                    current = None
                    continue
                parts = line.rstrip("\n").split("\t")
                if current.endswith("companies"):
                    d = dict(zip(companies_cols, parts, strict=False))
                    sym = (d.get("ticker_symbol") or "").strip().upper()
                    cid = d.get("company_id", "")
                    if sym and cid:
                        companies[sym] = cid
                        names[sym] = d.get("company_name") or ""
                        all_tickers[cid] = sym
                elif current.endswith("price_history"):
                    ph_rows[parts[0]].append(parts[1][:10] if len(parts) > 1 else NULL)
                elif current.endswith("splits"):
                    splits_rows.append(parts)
                continue

            m = COPY_RE.match(line)
            if m:
                current = m.group(1)
                cols = [c.strip() for c in (m.group(2) or "").split(",")] if m.group(2) else []
                if current.endswith("companies"):
                    companies_cols = cols
                elif current.endswith("splits"):
                    splits_cols = cols

    print(f"dump companies rows parsed: {len(companies)} tickers")
    print(f"price_history distinct company_ids present: {len(ph_rows)}")

    for sym, local_id in LOCAL_IDS.items():
        dump_id = companies.get(sym)
        print(f"\n{'=' * 72}")
        print(f"{sym}: local company_id={local_id}  dump company_id={dump_id}")
        if dump_id is None:
            print("  NOT PRESENT in dump companies table")
            continue
        if dump_id != str(local_id):
            print("  *** IDENTITY MISMATCH: dump id differs from local id ***")
        print(f"  company_name: {names.get(sym, '')}")

        rows = ph_rows.get(dump_id, [])
        dates = sorted(d for d in rows if d != NULL)
        print(f"  price_history rows under dump id: {len(rows)}")
        if dates:
            print(f"  range: {dates[0]} .. {dates[-1]}  distinct={len(set(dates))}")
            years = sorted({d[:4] for d in dates})
            print(f"  years present: {len(years)} ({years[0]}..{years[-1]})")
            per_year: dict[str, int] = defaultdict(int)
            for d in dates:
                per_year[d[:4]] += 1
            counts = sorted(set(per_year.values()))
            print(f"  distinct rows-per-year values: {counts[:12]}")
            tail = sorted(per_year.items())[-6:]
            print(f"  recent years: {tail}")

    print(f"\n{'=' * 72}\nsplits table: {len(splits_rows)} rows, cols={splits_cols}")
    if splits_cols and "company_id" in splits_cols:
        k = splits_cols.index("company_id")
        dump_ids = {sym: companies.get(sym) for sym in LOCAL_IDS}
        for cid in dump_ids.values():
            if cid is None:
                continue
            match = [r for r in splits_rows if len(r) > k and r[k] == cid]
            sym = next(s for s, v in dump_ids.items() if v == cid)
            print(f"  splits for {sym} (id={cid}): {len(match)}")
            for r in match[:10]:
                print("   ", dict(zip(splits_cols, r, strict=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
