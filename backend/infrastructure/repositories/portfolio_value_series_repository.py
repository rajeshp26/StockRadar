# infrastructure/repositories/portfolio_value_series_repository.py
"""
Repository for the materialised portfolio value series (migration 017).

The value curve served by ``/portfolio/performance`` is a deterministic,
append-only function of the snapshot rows: the value on date D moves only when a
snapshot for D is written or corrected, a backdated transaction changes an
earlier date, or the account set changes. Recomputing it on every period
selection is waste - the period selector only changes the visible slice.

This is the storage half of that read model. One row per (account_key,
series_date); a period read is a slice; a new date is an append. Correctness is
enforced by the fingerprint column, never by trust:

* ``get_series`` returns the stored points AND the build's own fingerprint, so
  the caller compares before trusting.
* ``upsert_points`` writes a full build (a rebuild replaces, never merges).
* ``delete_account_key`` drops an account set whose identity no longer exists.

Degradation mirrors ``BenchmarkSeriesRepository``: an absent or unreachable
table returns an empty result so the caller falls back to live computation; a
write failure logs and swallows, because failing a read request over a cache
write is never correct.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)

_BATCH = 500


@dataclass
class StoredPortfolioSeries:
    """One build of the portfolio value curve as stored."""

    fingerprint: str | None = None
    last_mark_date: date | None = None
    computed_at: Any | None = None
    points: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.points


class PortfolioValueSeriesRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_series(
        self, account_key: str,
        start_date: date | None = None, end_date: date | None = None,
    ) -> StoredPortfolioSeries:
        """Read a stored curve (optionally sliced) plus its build metadata.

        A partial read is never returned: if pagination stops short, the build's
        ``last_mark_date`` cannot be trusted for tail slicing, so the caller's
        fingerprint check could pass on an incomplete series. Any read error
        therefore discards everything read so far.
        """
        try:
            rows: list[dict[str, Any]] = []
            offset = 0
            while True:
                q = (
                    self.client.table("portfolio_value_series")
                    .select("series_date, total_value, holdings_market_value, cost_basis, "
                            "cash_balance, net_deposits, fx_unconverted_count, points_used, "
                            "locf_filled, spike_suppressed, "
                            "fingerprint, computed_at, last_mark_date")
                    .eq("account_key", account_key)
                )
                if start_date is not None:
                    q = q.gte("series_date", start_date.isoformat())
                if end_date is not None:
                    q = q.lte("series_date", end_date.isoformat())
                res = (
                    q.order("series_date", desc=False)
                    .range(offset, offset + _BATCH - 1)
                    .execute()
                )
                chunk = res.data or []
                rows.extend(chunk)
                if len(chunk) < _BATCH:
                    break
                offset += _BATCH
        except Exception as e:
            logger.info(
                "portfolio_value_series read unavailable for %s (%s) - "
                "falling back to live computation",
                account_key, e,
            )
            return StoredPortfolioSeries()

        if not rows:
            return StoredPortfolioSeries()

        def _as_date(v: Any) -> date | None:
            if v is None:
                return None
            if isinstance(v, str):
                return date.fromisoformat(v)
            if isinstance(v, date):
                return v
            return None

        # last_mark_date is the MAX across the slice, not the first row's value:
        # a windowed read excludes early rows and the tail marker must still
        # describe the whole stored build.
        last_mark = max(
            (d for d in (_as_date(r.get("last_mark_date")) for r in rows) if d),
            default=None,
        )
        return StoredPortfolioSeries(
            fingerprint=rows[0].get("fingerprint"),
            last_mark_date=last_mark,
            computed_at=rows[0].get("computed_at"),
            points=[
                {
                    "date": r["series_date"],
                    "value": float(r["total_value"]),
                    "holdings_market_value": float(r.get("holdings_market_value") or 0),
                    "cost_basis": float(r.get("cost_basis") or 0),
                    "cash_balance": float(r.get("cash_balance") or 0),
                    "net_deposits": float(r.get("net_deposits") or 0),
                    "fx_unconverted_count": int(r.get("fx_unconverted_count") or 0),
                    "points_used": int(r.get("points_used") or 0),
                    "locf_filled": int(r.get("locf_filled") or 0),
                    "spike_suppressed": int(r.get("spike_suppressed") or 0),
                }
                for r in rows
            ],
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_points(
        self,
        account_key: str,
        points: list[dict[str, Any]],
        fingerprint: str,
        last_mark_date: date,
    ) -> int:
        """Write a full build for ``account_key``.

        The build is authoritative for the dates it covers; rows for those dates
        are replaced. Dates the build does not cover are left alone, so a
        partial rebuild cannot silently truncate stored history.
        """
        if not points:
            return 0
        rows = [
            {
                "account_key": account_key,
                "series_date": (
                    p["date"].isoformat() if isinstance(p["date"], date) else str(p["date"])
                ),
                "total_value": float(p["value"]),
                "holdings_market_value": float(p.get("holdings_market_value") or 0),
                "cost_basis": float(p.get("cost_basis") or 0),
                "cash_balance": float(p.get("cash_balance") or 0),
                "net_deposits": float(p.get("net_deposits") or 0),
                "fx_unconverted_count": int(p.get("fx_unconverted_count") or 0),
                "points_used": int(p.get("points_used") or 0),
                "locf_filled": int(p.get("locf_filled") or 0),
                "spike_suppressed": int(p.get("spike_suppressed") or 0),
                "fingerprint": fingerprint,
                "last_mark_date": last_mark_date.isoformat(),
            }
            for p in points
        ]
        written = 0
        for i in range(0, len(rows), _BATCH):
            chunk = rows[i:i + _BATCH]
            try:
                res = (
                    self.client.table("portfolio_value_series")
                    .upsert(chunk, on_conflict="account_key,series_date")
                    .execute()
                )
                written += len(res.data or chunk)
            except Exception as e:
                logger.warning(
                    "portfolio_value_series upsert failed for %s chunk %d: %s",
                    account_key, i, e,
                )
        return written

    def delete_account_key(self, account_key: str) -> int:
        """Drop every stored point for an account set (identity removed/renamed)."""
        try:
            res = (
                self.client.table("portfolio_value_series")
                .delete()
                .eq("account_key", account_key)
                .execute()
            )
            n = len(res.data or [])
            if n:
                logger.info(
                    "portfolio_value_series: removed %d stale rows for %s", n, account_key
                )
            return n
        except Exception as e:
            logger.warning("portfolio_value_series delete failed for %s: %s", account_key, e)
            return 0
