# application/services/portfolio_value_series_guard.py
"""
Recomputation guard for the materialised portfolio value curve (migration 017).

Shares the gate vocabulary of ``benchmark_series_guard`` and
``recompute_guard`` (Gate 1 coverage, Gate 2 fingerprint) because it guards the
same class of artefact by the same argument: a deterministic series over inputs
that are immutable in the past.

Gates
─────
Gate 1 - Coverage (always runs)
    * ``no_prior_series``     nothing stored -> build the whole curve
    * ``series_ends_before``  stored build stops before the requested end date
                              -> only the tail is missing
    * ``series_covered``      stored coverage spans the window; Gate 2 decides

Gate 2 - Fingerprint
    A SHA-256 over account_key and the ordered snapshot INPUT rows the build
    was computed from. A mismatch means the same dates would now produce
    different values - the class of change a timestamp-only check cannot see,
    because a corrected or backdated snapshot arrives with an older date than
    the build. The request path reads those same rows every time (they are the
    chart's own input), so recomputing the hash costs nothing extra.

Tail recompute
──────────────
Coverage plus a matching fingerprint does not mean "serve and stop". The curve
is append-only in time: dates up to ``last_mark_date`` are frozen, later dates
do not exist yet. ``compute_from`` names the first date the caller must compute,
so advancing one day computes one day, not five years.

What this guard deliberately does NOT do
────────────────────────────────────────
It does not decide *how* to aggregate snapshots into the curve, and it does not
touch the database. It answers three questions only: is there a usable stored
curve, must it be rebuilt, and from which date must the caller compute.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from application.services.portfolio_response_cache import (
    compute_snapshot_fingerprint,
)
from shared.finance_math import build_fingerprint

logger = logging.getLogger(__name__)

# ── Reason tokens (closed vocabulary, surfaced in logs) ──────────────────────
NO_PRIOR_SERIES = "no_prior_series"
SERIES_ENDS_BEFORE = "series_ends_before"
SERIES_COVERED = "series_covered"
FINGERPRINT_MATCH = "fingerprint_match"
FINGERPRINT_MISMATCH = "fingerprint_mismatch"


@dataclass
class PortfolioReuseDecision:
    """Outcome of the guard: serve, rebuild, or extend from a date."""

    can_reuse: bool
    rebuild: bool
    reason: str
    gate: int
    compute_from: date | None = None
    reusable_dates: list[str] = field(default_factory=list)

    @property
    def must_compute(self) -> bool:
        return self.rebuild or self.compute_from is not None


def compute_portfolio_series_fingerprint(
    account_key: str,
    raw_snapshots: list[dict[str, Any]],
) -> str:
    """Fingerprint over the exact INPUTS that produce the curve.

    Hashes the per-account snapshot scalars the build was computed from - the
    rows the request path already reads - so an appended, corrected or
    BACKDATED snapshot changes the hash before any stored point is served.
    That is the property a hash of the stored points cannot have: the inputs
    are what a stored curve must be checked against, and checking the artifact
    against itself only proves it was written intact, not that it is current.

    The row-level column set lives in the response cache module (Layer 3), so
    both fingerprints are guaranteed to change on exactly the same edits.
    """
    return build_fingerprint({
        "account_key": account_key,
        "snapshot_inputs": compute_snapshot_fingerprint(raw_snapshots),
    })


class PortfolioValueSeriesGuard:
    """Decides reuse / rebuild / tail-extension for a stored portfolio curve."""

    def decide(
        self,
        stored_fingerprint: str | None,
        stored_last_mark: date | None,
        expected_fingerprint: str,
        required_end: date,
    ) -> PortfolioReuseDecision:
        """Gate 1 then Gate 2. Pure function of the compared values.

        Side-effect free (the repository does the I/O) so the decision logic is
        unit-testable without a database - the failure this prevents is a guard
        whose behaviour can only be observed against live data.
        """
        # ── Gate 1: coverage ────────────────────────────────────────────────
        if stored_fingerprint is None or stored_last_mark is None:
            return PortfolioReuseDecision(
                can_reuse=False, rebuild=True,
                reason=NO_PRIOR_SERIES, gate=1,
            )

        # ── Gate 2: fingerprint ─────────────────────────────────────────────
        if stored_fingerprint != expected_fingerprint:
            return PortfolioReuseDecision(
                can_reuse=False, rebuild=True,
                reason=FINGERPRINT_MISMATCH, gate=2,
            )

        # Coverage + fingerprint agree: stored dates still hold. The curve is
        # append-only, so only dates after the mark remain to compute.
        if stored_last_mark < required_end:
            return PortfolioReuseDecision(
                can_reuse=True, rebuild=False,
                reason=SERIES_ENDS_BEFORE, gate=1,
                compute_from=stored_last_mark,
            )

        return PortfolioReuseDecision(
            can_reuse=True, rebuild=False,
            reason=FINGERPRINT_MATCH, gate=2,
        )
