"""Shared utilities for stock split handling."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple


def parse_split_factor(split_factor_str: str) -> float:
    """Parse a split factor string like '3:1' or '1:5' into a numeric multiplier.

    Returns the adjustment factor (split_to / split_from).
    For a 3:1 split, returns 3.0.
    For a 1:5 reverse split, returns 0.2.
    Returns 1.0 for unparseable or no-op factors.
    """
    if not split_factor_str or ":" not in split_factor_str:
        return 1.0
    try:
        parts = split_factor_str.split(":")
        to_val = float(parts[0].strip())
        from_val = float(parts[1].strip())
        if from_val > 0:
            return to_val / from_val
    except (ValueError, ZeroDivisionError, InvalidOperation):
        pass
    return 1.0


def parse_split_date(raw) -> date:
    """Parse a date from various formats into a date object."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return date.fromisoformat(raw)
    raise ValueError(f"Cannot parse date: {raw!r}")


def get_split_factors_from_rows(
    rows: List[dict],
) -> Dict[int, List[Tuple[date, float]]]:
    """Parse split rows from the splits table into {company_id: [(split_date, adjustment_factor)]}.

    Rows should have keys: company_id, report_date, split_factor.
    Returns sorted by date ascending.
    """
    factors: Dict[int, List[Tuple[date, float]]] = {}
    for row in rows:
        cid = row.get("company_id")
        if not cid:
            continue
        try:
            sd = parse_split_date(row["report_date"])
        except (ValueError, KeyError):
            continue
        sf = row.get("split_factor") or "1:1"
        adj = parse_split_factor(sf)
        if adj != 1.0:
            factors.setdefault(cid, []).append((sd, adj))
    for cid in factors:
        factors[cid].sort(key=lambda x: x[0])
    return factors
