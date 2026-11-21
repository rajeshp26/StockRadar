"""Shared utilities for stock split handling."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

ONE = Decimal(1)


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


def parse_split_factor_decimal(split_factor_str: str | None) -> Decimal:
    """Parse a split factor string like '3:1' or '1:10' into an exact Decimal.

    The float twin above is retained for its existing callers, but a float cannot
    carry a quantity through a split: 1/20 has no exact binary representation, and
    `Decimal("193.0") * 0.05` is not `Decimal("9.65")`. The lot reconciliation
    compares share totals against a 1e-6 tolerance, so float drift is indistinguishable
    from a real disagreement. Share arithmetic uses this form.
    """
    if not split_factor_str or ":" not in str(split_factor_str):
        return ONE
    parts = str(split_factor_str).split(":")
    if len(parts) < 2:
        return ONE
    try:
        to_val = Decimal(parts[0].strip())
        from_val = Decimal(parts[1].strip())
    except (InvalidOperation, ValueError, TypeError):
        return ONE
    if from_val <= 0:
        return ONE
    return to_val / from_val


def split_schedule_from_rows(rows: Iterable[dict]) -> dict[int, list[tuple[date, Decimal]]]:
    """``{company_id: [(split_date, multiplier)]}``, exact and sorted ascending.

    Same input contract as :func:`get_split_factors_from_rows` (a row per split with
    ``company_id``, ``report_date``, ``split_factor``), but Decimal-valued and without
    the float no-op filter, so a row whose factor is 1:1 stays visible as evidence
    rather than disappearing.
    """
    schedule: dict[int, list[tuple[date, Decimal]]] = {}
    for row in rows:
        cid = row.get("company_id")
        if cid is None:
            continue
        try:
            split_date = parse_split_date(row["report_date"])
        except (ValueError, KeyError, TypeError):
            continue
        factor = parse_split_factor_decimal(row.get("split_factor"))
        if factor <= 0:
            continue
        schedule.setdefault(int(cid), []).append((split_date, factor))
    for splits in schedule.values():
        splits.sort(key=lambda entry: entry[0])
    return schedule


def split_adjustment_factor(
    splits: Sequence[tuple[date, Decimal]] | None,
    transaction_date: date | None,
    as_of: date,
) -> Decimal:
    """Multiplier that restates one share movement into ``as_of`` units.

    A split changes the share scale at the *start* of its effective date, so every
    share movement dated on that day is already denominated in post-split shares and
    must NOT be multiplied by the split's factor. The boundary is therefore strict:
    a split applies to movements dated ``transaction_date < split_date``.

    This is not a style preference, and it is not inferred from the data's insertion
    order. In the live dataset exactly one share movement shares a date with a split:
    account 9 / IVR, a -0.3 SELL on 2022-06-06, the day of a 1:10 reverse split. The
    broker row records unit_price 21.42491904 and net_cash_amount 6.43 (0.3 x 21.42),
    which is the POST-split price of a ~$214 pre-split share: the 0.3 is the fractional
    remainder of 193/10 = 19.3, sold for cash. Applying the split to it would double-
    count the consolidation and leave a phantom 0.27 shares.

    A movement dated after ``as_of`` never exists here (the caller cuts them off), and
    a split dated after ``as_of`` has not happened yet, hence ``split_date <= as_of``.
    An undated movement is treated as the earliest possible date, which is the same
    assumption the as-of cutoff already makes for it.
    """
    if not splits:
        return ONE
    movement = transaction_date or date.min
    factor = ONE
    for split_date, split_factor in splits:
        if movement < split_date <= as_of:
            factor *= split_factor
    return factor

