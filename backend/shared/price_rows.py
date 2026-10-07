"""Canonical daily price_history row construction.

Single source of truth for building ``price_history`` rows from provider output.

Why this module exists
----------------------
Four independent copies of ``_compress_daily_to_monthly_eom`` drifted across the
codebase (market_data_scheduler, portfolio_service, watchlist_service,
backfill_benchmark_prices). One of them -- ``backfill_holding_prices`` -- had
already been corrected to write daily rows, and the others silently kept
compressing. Measured on the local database, that left 61 of 193 companies
(one third of the universe) storing exactly one price per month.

Root cause of that state, not a special case: monthly compression is wrong for
``price_history`` because a mid-month day has no price of its own at
month-end resolution, and synthesising one picks a stale or future quote. The
grain the table is meant to hold is one row per provider-reported trading day.

Monthly *readers* are unaffected. ``get_price_history_monthly`` downsamples, and
every month-end date is a subset of the daily set, so densifying preserves the
values those queries return.

This module deliberately does not invent rows. Absent a provider bar, no row is
emitted -- weekends, holidays and suspended sessions stay absent rather than
being interpolated, because a fabricated trading day is indistinguishable from a
real one once stored.
"""
from __future__ import annotations

import datetime
from typing import Any


def safe_num(v: Any) -> float | None:
    """Coerce to float, mapping None / NaN / unparseable to None.

    Mirrors the historical behaviour of the per-module ``_safe_num`` helpers so
    that migrating a call site cannot change the values it writes.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    # NaN is the only value that is not equal to itself.
    return f if f == f else None


def sanitize_daily_price_rows(
    daily_rows: list[dict[str, Any]] | None,
    *,
    default_source: str = "defeatbeta",
) -> list[dict[str, Any]]:
    """Normalise provider rows to daily ``price_history`` rows.

    Drops rows with no ``price_date`` or no ``close_price`` (close_price is NOT
    NULL in the table; delisted and suspended days legitimately report nulls).
    Preserves every surviving trading day -- no monthly grouping.
    """
    if not daily_rows:
        return []

    out: list[dict[str, Any]] = []
    for r in daily_rows:
        if not isinstance(r, dict):
            continue
        company_id = r.get("company_id")
        if company_id is None:
            continue

        raw_date = r.get("price_date")
        if raw_date is None:
            continue
        if isinstance(raw_date, datetime.datetime):
            # datetime.datetime is a subclass of datetime.date, so it must be
            # checked first; pandas.Timestamp is a datetime subclass too.
            raw_date = raw_date.date()
        elif isinstance(raw_date, datetime.date):
            pass
        elif isinstance(raw_date, str):
            try:
                raw_date = datetime.date.fromisoformat(raw_date[:10])
            except ValueError:
                continue
        else:
            continue

        close = safe_num(r.get("close_price"))
        if close is None:
            continue

        volume = safe_num(r.get("volume"))
        out.append(
            {
                "company_id": int(r["company_id"]),
                "price_date": raw_date,
                "open_price": safe_num(r.get("open_price")),
                "close_price": close,
                "high_price": safe_num(r.get("high_price")),
                "low_price": safe_num(r.get("low_price")),
                "volume": int(volume) if volume is not None else None,
                "data_source": str(r.get("data_source") or default_source),
            }
        )

    out.sort(key=lambda x: x["price_date"])
    return out
