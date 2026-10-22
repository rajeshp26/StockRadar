# infrastructure/repositories/benchmark_series_repository.py
"""
Repository for the materialised benchmark comparison series (migration 015).

The benchmark series is the same-cash-flows dollar simulation served by
``/portfolio/performance/compare`` and its holding twin. It is deterministic
for any date whose inputs have not moved, so recomputing it on every timeline
selection is waste: the period selector only changes the visible slice.

This repository is the storage half of that read model. One row per
(account_key, symbol, series_date); a period read is a slice; a new date is an
append. Correctness is enforced by the fingerprint columns, never by trust:

* ``get_series`` returns the stored rows AND the build's own fingerprint so the
  caller can decide whether the rows are still valid. It never returns rows
  whose fingerprint the caller has not compared.
* ``upsert_points`` writes the full series for one build (a rebuild replaces,
  it does not merge into stale rows).
* ``delete_account_key`` drops an account set whose identity no longer exists.

Degradation: when the table is absent or unreachable (a fresh clone before
migration 015 is applied), the read methods return an empty result rather than
raising, so the caller falls back to live simulation. The write methods log and
swallow, because failing a *read* request over a cache write is never correct.
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
class StoredBenchmarkSeries:
    """One build of a benchmark series as stored.

    ``points`` are ordered by date ascending. ``fingerprint`` is the build's
    own hash: the caller compares it against the hash it computes from current
    inputs before trusting ``points``.
    """
    fingerprint: str | None = None
    inception_date: date | None = None
    initial_value: float | None = None
    last_mark_date: date | None = None
    computed_at: Any | None = None
    points: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.points


class BenchmarkSeriesRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_series(
        self, account_key: str, symbol: str,
        start_date: date | None = None, end_date: date | None = None,
    ) -> StoredBenchmarkSeries:
        """Read a stored series (optionally sliced) plus its build metadata.

        Returns an empty result when nothing is stored, the table is missing,
        or the read fails - the caller then simulates live. A partial read is
        never returned: if pagination stops short, the build's own
        ``last_mark_date`` cannot be trusted for tail slicing, so the caller's
        fingerprint check would still pass on an incomplete series. Any read
        error therefore discards everything read so far.
        """
        try:
            rows: list[dict[str, Any]] = []
            offset = 0
            while True:
                q = (
                    self.client.table("benchmark_series")
                    .select("series_date, value, inception_date, initial_value, "
                            "fingerprint, computed_at, last_mark_date")
                    .eq("account_key", account_key)
                    .eq("symbol", symbol)
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
                "benchmark_series read unavailable for %s/%s (%s) - "
                "falling back to live simulation",
                account_key, symbol, e,
            )
            return StoredBenchmarkSeries()

        if not rows:
            return StoredBenchmarkSeries()

        def _as_date(v: Any) -> date | None:
            if v is None:
                return None
            if isinstance(v, str):
                return date.fromisoformat(v)
            if isinstance(v, date):
                return v
            return None

        # Metadata is written identically on every row of a build, so the
        # first row carries it. `last_mark_date` is the MAX across the slice,
        # not the first row's value: a windowed read (start_date > inception)
        # excludes the early rows, and the tail marker must still describe the
        # whole stored build.
        last_mark = max(
            (d for d in (_as_date(r.get("last_mark_date")) for r in rows) if d),
            default=None,
        )
        return StoredBenchmarkSeries(
            fingerprint=rows[0].get("fingerprint"),
            inception_date=_as_date(rows[0].get("inception_date")),
            initial_value=(
                float(rows[0]["initial_value"])
                if rows[0].get("initial_value") is not None else None
            ),
            last_mark_date=last_mark,
            computed_at=rows[0].get("computed_at"),
            points=[
                {"date": r["series_date"], "value": float(r["value"])}
                for r in rows
            ],
        )

    def get_point_dates(self, account_key: str, symbol: str) -> list[str]:
        """All stored dates for a build, ascending (used to detect coverage).

        Returns [] on any failure, matching ``get_series``.
        """
        try:
            res = (
                self.client.table("benchmark_series")
                .select("series_date")
                .eq("account_key", account_key)
                .eq("symbol", symbol)
                .order("series_date", desc=False)
                .execute()
            )
            return [r["series_date"] for r in (res.data or [])]
        except Exception as e:
            logger.info("benchmark_series date read failed (%s)", e)
            return []

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_points(
        self,
        account_key: str,
        symbol: str,
        points: list[dict[str, Any]],
        inception_date: date,
        initial_value: float,
        fingerprint: str,
        last_mark_date: date,
    ) -> int:
        """Write a full build for (account_key, symbol).

        The build is authoritative for the dates it covers: rows for those
        dates are replaced. Dates the build does NOT cover are left alone -
        deleting them is ``prune_before``'s job, kept separate so a partial
        rebuild cannot silently truncate stored history.
        """
        if not points:
            return 0
        rows = [
            {
                "account_key": account_key,
                "symbol": symbol,
                "series_date": (
                    p["date"].isoformat() if isinstance(p["date"], date) else str(p["date"])
                ),
                "value": float(p["value"]),
                "inception_date": inception_date.isoformat(),
                "initial_value": float(initial_value),
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
                    self.client.table("benchmark_series")
                    .upsert(chunk, on_conflict="account_key,symbol,series_date")
                    .execute()
                )
                written += len(res.data or chunk)
            except Exception as e:
                logger.warning(
                    "benchmark_series upsert failed for %s/%s chunk %d: %s",
                    account_key, symbol, i, e,
                )
        return written

    def delete_account_key(self, account_key: str) -> int:
        """Drop every stored point for an account set (identity removed/renamed)."""
        try:
            res = (
                self.client.table("benchmark_series")
                .delete()
                .eq("account_key", account_key)
                .execute()
            )
            n = len(res.data or [])
            if n:
                logger.info("benchmark_series: removed %d stale rows for %s", n, account_key)
            return n
        except Exception as e:
            logger.warning("benchmark_series delete failed for %s: %s", account_key, e)
            return 0
