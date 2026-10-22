# application/services/benchmark_series_guard.py
"""
Recomputation guard for the materialised benchmark series (migration 015).

Same gate vocabulary as ``recompute_guard.RecomputeGuard`` (Gate 1 timestamp,
Gate 2 fingerprint), applied to a different artefact. Kept as a separate module
rather than bolted onto the valuation guard because the dependency shapes are
unrelated: a valuation depends on company fundamentals, a benchmark series
depends on an ordered cash-flow list and the price rows of one index.

Gates
─────
Gate 1 - Timestamp / coverage (always runs)
    Is there a stored build at all, and does it cover the requested window?
    Two coverage facts matter and each has its own reason token:

      * ``no_prior_series``        nothing stored → build from inception
      * ``series_inception_later`` the earliest cash flow is now earlier than
                                   the stored inception → an import moved
                                   inception, the whole series moved with it
      * ``series_ends_before``     the stored build stops before the requested
                                   end date → the tail is missing
      * ``series_covered``         stored coverage spans the window; only the
                                   inputs can still invalidate it (Gate 2)

Gate 2 - Fingerprint (runs when Gate 1 reports coverage)
    Does a SHA-256 hash of the exact inputs still match the stored one?
    The hash covers the account identity, symbol, inception, seed, the ordered
    cash-flow list and a cheap content signature of the benchmark price rows.
    A mismatch means the same dates would now produce different dollars -
    which is precisely the class of change (price correction, backfill,
    restated split) that a timestamp-only check cannot see, because those rows
    arrive with an older ``price_date`` than the build.

Tail recompute
──────────────
Coverage plus a matching fingerprint does not mean "serve and stop". The
series is append-only in time: dates up to ``last_mark_date`` are frozen, dates
after it do not exist yet. ``missing_after`` returns the first date the caller
must compute, so a request that has advanced a day computes one day, not five
years.

What this guard deliberately does NOT do
────────────────────────────────────────
It does not decide *how* to simulate; it never touches prices or cash flows.
It answers three questions only: is there a usable stored series, must it be
rebuilt from scratch, and from which date must the caller compute. That keeps
the correctness argument in one place and the arithmetic in another.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from shared.finance_math import build_fingerprint

logger = logging.getLogger(__name__)

# ── Reason tokens (closed vocabulary, surfaced in logs) ──────────────────────
NO_PRIOR_SERIES = "no_prior_series"
SERIES_INCEPTION_LATER = "series_inception_later"
SERIES_ENDS_BEFORE = "series_ends_before"
SERIES_COVERED = "series_covered"
FINGERPRINT_MATCH = "fingerprint_match"
FINGERPRINT_MISMATCH = "fingerprint_mismatch"
NO_STORED_FINGERPRINT = "no_stored_fingerprint"


@dataclass
class BenchmarkReuseDecision:
    """Outcome of the guard: serve, rebuild, or extend from a date."""
    can_reuse: bool
    rebuild: bool
    reason: str
    gate: int
    # First date the caller must compute. None = nothing to compute (serve as is).
    compute_from: date | None = None
    # Dates already stored and still valid; the caller may serve these directly.
    reusable_dates: list[str] = field(default_factory=list)

    @property
    def must_compute(self) -> bool:
        return self.rebuild or self.compute_from is not None


def compute_series_fingerprint(
    account_key: str,
    symbol: str,
    inception_date: date,
    initial_value: float,
    cashflows: list[dict[str, Any]],
    price_signature: dict[str, Any],
) -> str:
    """Fingerprint over the exact inputs that produce one benchmark series.

    ``cashflows`` must already be the ordered, anchor-filtered list the
    simulator will replay - the fingerprint hashes what is used, not what was
    fetched, so a cash flow excluded by the anchor rule cannot invalidate a
    series it does not affect.

    ``price_signature`` is a cheap content signature of the benchmark's price
    rows (see ``price_signature`` below), not the rows themselves: hashing
    ~2,000 prices per request would cost more than the simulation it guards.
    """
    return build_fingerprint({
        "account_key": account_key,
        "symbol": symbol,
        "inception_date": inception_date.isoformat(),
        "initial_value": round(float(initial_value), 4),
        "cashflows": [
            {
                "date": (cf["date"].isoformat()
                         if isinstance(cf["date"], date) else str(cf["date"])),
                "amount": round(float(cf.get("amount") or 0), 4),
            }
            for cf in cashflows
        ],
        "price_signature": price_signature,
    })


def price_signature(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Content signature of a benchmark price series.

    Cheap to compute and sensitive to exactly the changes that move a
    simulated dollar: which dates exist, and the first/last price on each.
    ``row_count`` catches an inserted or deleted date, ``first``/``last``
    catch a corrected or backfilled price at either end. It is deliberately
    NOT a full hash of every price: a mid-series correction that leaves both
    ends and the count unchanged is invisible to this signature.

    shortcut: signature covers count + first/last price only, not every price.
    Upgrade when a mid-series price correction is observed to leave a served
    benchmark point stale - then hash the full (date, price) list, or store a
    per-row checksum.
    """
    if not rows:
        return {"row_count": 0, "first": None, "last": None}
    ordered = sorted(
        (
            (r["price_date"].isoformat()
             if isinstance(r.get("price_date"), date) else str(r.get("price_date"))),
            float(
                (r.get("adj_close") if r.get("adj_close") is not None
                 else r.get("close_price")) or 0
            ),
        )
        for r in rows
        if r.get("price_date") is not None
    )
    if not ordered:
        return {"row_count": 0, "first": None, "last": None}
    return {
        "row_count": len(ordered),
        "first": [ordered[0][0], round(ordered[0][1], 6)],
        "last": [ordered[-1][0], round(ordered[-1][1], 6)],
    }


class BenchmarkSeriesGuard:
    """Decides reuse / rebuild / tail-extension for a stored benchmark series."""

    def decide(
        self,
        stored_fingerprint: str | None,
        stored_inception: date | None,
        stored_last_mark: date | None,
        expected_fingerprint: str,
        required_inception: date,
        required_end: date,
    ) -> BenchmarkReuseDecision:
        """Gate 1 then Gate 2. Pure function of the compared values.

        Kept side-effect free (the repository does the I/O) so the decision
        logic is unit-testable without a database - the failure this prevents
        is a guard whose behaviour can only be observed against live data.
        """
        # ── Gate 1: coverage ────────────────────────────────────────────────
        if stored_fingerprint is None or stored_last_mark is None:
            return BenchmarkReuseDecision(
                can_reuse=False, rebuild=True,
                reason=NO_PRIOR_SERIES, gate=1,
            )

        if stored_inception is None or stored_inception > required_inception:
            # Cash flows now exist before the stored inception: every date in
            # the series was simulated without them, so none can be reused.
            return BenchmarkReuseDecision(
                can_reuse=False, rebuild=True,
                reason=SERIES_INCEPTION_LATER, gate=1,
            )

        # ── Gate 2: fingerprint ─────────────────────────────────────────────
        if stored_fingerprint != expected_fingerprint:
            return BenchmarkReuseDecision(
                can_reuse=False, rebuild=True,
                reason=FINGERPRINT_MISMATCH, gate=2,
            )

        # Coverage + fingerprint agree: stored dates still hold. The series is
        # append-only, so only dates after the mark remain to compute.
        if stored_last_mark < required_end:
            return BenchmarkReuseDecision(
                can_reuse=True, rebuild=False,
                reason=SERIES_ENDS_BEFORE, gate=1,
                compute_from=stored_last_mark,
            )

        return BenchmarkReuseDecision(
            can_reuse=True, rebuild=False,
            reason=FINGERPRINT_MATCH, gate=2,
        )
