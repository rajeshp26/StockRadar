"""Shared utilities for stock split handling."""

from datetime import date, datetime
from decimal import InvalidOperation


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


def extract_event_date(event: dict) -> date | None:
    """Extract the relevant date from an event.

    Priority:
    1. data.effective_date — explicit override
    2. data.transaction_date — for trade/dividend events
    3. data.report_date — for split/corporate-action events (historical date)
    4. event.created_at — fallback (insertion timestamp)

    This is the canonical implementation shared by the replay engine and the
    split reconciler so ordering decisions never diverge between the two.
    """
    data = event.get("data", {}) or {}

    def _parse_field(value) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None

    for key in ("effective_date", "transaction_date", "report_date"):
        parsed = _parse_field(data.get(key))
        if parsed is not None:
            return parsed

    created_str = event.get("created_at", "")
    if created_str:
        try:
            return datetime.fromisoformat(created_str.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            return None
    return None


def get_split_factors_from_rows(
    rows: list[dict],
) -> dict[int, list[tuple[date, float]]]:
    """Parse split rows from the splits table into {company_id: [(split_date, adjustment_factor)]}.

    Rows should have keys: company_id, report_date, split_factor.
    Returns sorted by date ascending.
    """
    factors: dict[int, list[tuple[date, float]]] = {}
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
