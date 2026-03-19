# application/services/recompute_guard.py
"""
Three-Gate Recomputation Guard for Valuations (DDM · Rule #1 · DCF · OE · RI)

Single decision point controlling whether a valuation should be recomputed.
Implements three progressive gates so only genuinely material input changes
trigger full recomputation.

Architecture
────────────
Gate 1 — Timestamp   (always runs)
    Are any dependency tables newer than the last valuation run?
    Fast: 2 DB queries. Catches the obvious case where no data has moved.

Gate 2 — Fingerprint  (runs when Gate 1 fires)
    Have the actual SOURCE VALUES that feed this method's inputs changed?
    Compares a SHA-256 hash of the specific field values (dividends, ROE,
    beta, params) against the hash stored in the last run's input_snapshot.
    Eliminates the dominant false-positive source: scheduled jobs that
    always advance computed_at / snapshot_date even when data is identical.

Gate 3 — Materiality  (runs when Gate 2 fires, invoked from service layer)
    Are the resolved inputs (D0, g, k etc.) different enough to matter?
    Structural changes (source-path flips) are unconditionally material.
    Numeric changes are evaluated against per-field significance thresholds
    expressed in basis points (rates) or relative percentages (dollar/ratio).
    This guard exposes is_material_change() and record_immaterial_change();
    the service layer is responsible for resolving inputs before calling them.

Bypass rules
────────────
- force=True                        → skip all gates
- no_prior_valuation (Gate 1)       → skip Gates 2 & 3 (nothing to compare)
- any override field non-null       → skip Gates 2 & 3 (explicit user intent)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Per-field materiality specification (DDM) ─────────────────────────────────
#
# Threshold design rationale:
#
#   Rates use "absolute_bps": the Fed moves in 25 bps increments.
#   Sub-25-bps rate changes are market noise, not actionable for a DDM model.
#   Wider 50-bps tolerance for intermediate inputs (g_hist, g_sgr) since they
#   are blended/clamped before reaching the final g.
#
#   Dollar/ratio fields use "relative": scales correctly across company sizes.
#   0.5% relative for D0 ≈ $0.01 on a $2/share TTM dividend — minimum
#   meaningful precision for dividends declared in whole cents.
#
#   Beta uses 2% relative: beta is a noisy statistical estimate. A 2% move
#   on beta=0.85 produces only ~1 bps change in k — genuinely immaterial.

_DDM_NUMERIC_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "d0": {
        "method":    "relative",
        "threshold": 0.005,       # 0.5%
    },
    "g_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,      # 25 bps
    },
    "k_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,      # 25 bps
    },
    "g_hist": {
        "method":    "absolute_bps",
        "threshold": 0.0050,      # 50 bps — intermediate input
    },
    "g_sgr": {
        "method":    "absolute_bps",
        "threshold": 0.0050,      # 50 bps — intermediate input
    },
    "beta": {
        "method":    "relative",
        "threshold": 0.02,        # 2%
    },
}

# Structural fields: a change in the source path is always material,
# regardless of whether the resulting numeric value happens to be similar.
# This catches: "beta went missing → fallback to default k" and similar.
_DDM_STRUCTURAL_FIELDS: Tuple[str, ...] = ("g_source", "k_source", "d0_source")

# ── Per-field materiality specification (DCF) ─────────────────────────────────
#
# base_fcf: 2% relative — FCF is inherently volatile (timing of capex, WC swings).
#   Sub-2% change in FCF → sub-0.5bps change in WACC-implied value. Noise.
# wacc_final: 25bps absolute — standard rate-change granularity.
# terminal_g_final: 25bps absolute — same rationale as DDM g.
# net_debt: 1% relative — balance sheet item, stable; 1% ≈ rounding on reported figures.
# shares: 0.5% relative — dilution moves in whole-share blocks; 0.5% is below
#   minimum meaningful buyback/issuance threshold for large-cap.
_DCF_NUMERIC_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "base_fcf": {
        "method":    "relative",
        "threshold": 0.02,       # 2%
    },
    "wacc_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
    "terminal_g_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
    "net_debt": {
        "method":    "relative",
        "threshold": 0.01,       # 1%
    },
    "shares": {
        "method":    "relative",
        "threshold": 0.005,      # 0.5%
    },
}

_DCF_STRUCTURAL_FIELDS: Tuple[str, ...] = (
    "wacc_source",
    "terminal_g_source",
    "terminal_method",      # perpetuity_growth → exit_multiple is always material
)

# ── Per-field materiality specification (Owner Earnings) ──────────────────────
#
# base_oe: 2% relative — OE is more volatile than FCF (net income sensitivity).
# g_oe_final: 50bps absolute — OE growth is noisier than a rate; wider tolerance.
# discount_rate_final: 25bps absolute — standard rate granularity.
# terminal_g_final: 25bps absolute — same as DCF.
# net_debt / shares: same as DCF.

_OE_NUMERIC_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "base_oe": {
        "method":    "relative",
        "threshold": 0.02,       # 2%
    },
    "g_oe_final": {
        "method":    "absolute_bps",
        "threshold": 0.0050,     # 50 bps
    },
    "discount_rate_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
    "terminal_g_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
    "net_debt": {
        "method":    "relative",
        "threshold": 0.01,       # 1%
    },
    "shares": {
        "method":    "relative",
        "threshold": 0.005,      # 0.5%
    },
}

_OE_STRUCTURAL_FIELDS: Tuple[str, ...] = (
    "g_oe_source",
    "discount_rate_source",
)


# ── Per-field materiality specification (Residual Income) ─────────────────────
#
# bv_per_share: 0.5% relative — book value is directly from balance sheet; very stable.
# eps0: 1% relative — EPS can move with currency/shares; 1% = below reporting precision.
# k_e_final: 25bps absolute — CAPM cost of equity.
# g_ri_final: 50bps absolute — EPS CAGR proxy is noisier; wider tolerance.
# terminal_g_final: 25bps absolute.

_RI_NUMERIC_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "bv_per_share": {
        "method":    "relative",
        "threshold": 0.005,      # 0.5%
    },
    "eps0": {
        "method":    "relative",
        "threshold": 0.01,       # 1%
    },
    "k_e_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
    "g_ri_final": {
        "method":    "absolute_bps",
        "threshold": 0.0050,     # 50 bps
    },
    "terminal_g_final": {
        "method":    "absolute_bps",
        "threshold": 0.0025,     # 25 bps
    },
}

_RI_STRUCTURAL_FIELDS: Tuple[str, ...] = (
    "k_e_source",     # "capm" → "default.k_default (beta missing)" = structural
    "g_ri_source",    # "eps_cagr_approx" → "default.g_default" = structural
)

# ── Decision dataclass ────────────────────────────────────────────────────────

@dataclass
class RecomputeDecision:
    should_recompute:       bool
    last_valuation_at:      Optional[datetime]
    latest_dependency_at:   Optional[datetime]
    reason:                 str
    # Gate 1 reason tokens:
    #   "no_prior_valuation" | "no_dependencies" | "dependencies_newer" |
    #   "up_to_date" | "forced"
    # Gate 2 reason tokens:
    #   "fingerprint_match" | "fingerprint_mismatch" | "no_stored_fingerprint"
    # Gate 3 reason tokens (set by service, readable in logs):
    #   "immaterial_data_change" | "<field>_material_change" |
    #   "<field>_path_change" | "<field>_null_transition" |
    #   "no_gate3_for_method" | "no_stored_resolved"
    # Bypass reason tokens:
    #   "override_present"
    gate:           int              = 1
    change_details: Dict[str, Any]  = field(default_factory=dict)


# ── Guard ─────────────────────────────────────────────────────────────────────

class RecomputeGuard:
    """
    Central freshness controller used by all valuation services and schedulers.

    Repository contract (ValuationRepository must implement):
      get_last_valuation_ts(company_id, method)         → Optional[datetime]
      get_latest_dependency_ts(company_id, method)      → Optional[datetime]
      get_last_input_snapshot(company_id, method)       → Optional[Dict]
      update_valuation_fingerprint(company_id, method, fingerprint) → None
    """

    def __init__(self, valuation_repo: "ValuationRepository"):
        self.repo = valuation_repo

    # ── Gate 1: Timestamp ──────────────────────────────────────────────────────

    async def should_recompute(
        self, company_id: int, method: str = "rule1"
    ) -> RecomputeDecision:
        """
        Gate 1: compare last valuation run_at against latest dependency timestamp.
        This is the existing check, unchanged in semantics.
        """
        last_val_ts   = await self.repo.get_last_valuation_ts(company_id, method=method)
        latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id, method=method)

        if last_val_ts is None:
            logger.debug(
                "[GATE1][%s][%s] No prior valuation → recompute", company_id, method
            )
            return RecomputeDecision(
                True, None, latest_dep_ts, "no_prior_valuation", gate=1
            )

        if latest_dep_ts is None:
            logger.debug(
                "[GATE1][%s][%s] No dependency timestamps → recompute", company_id, method
            )
            return RecomputeDecision(
                True, last_val_ts, None, "no_dependencies", gate=1
            )

        if latest_dep_ts > last_val_ts:
            logger.debug(
                "[GATE1][%s][%s] Dependencies newer (dep=%s last=%s) → proceed to Gate 2",
                company_id, method, latest_dep_ts, last_val_ts,
            )
            return RecomputeDecision(
                True, last_val_ts, latest_dep_ts, "dependencies_newer", gate=1
            )

        logger.debug("[GATE1][%s][%s] Up to date → cached", company_id, method)
        return RecomputeDecision(
            False, last_val_ts, latest_dep_ts, "up_to_date", gate=1
        )

    async def cached_or_recompute(
        self,
        company_id: int,
        force:      bool = False,
        method:     str  = "rule1",
    ) -> RecomputeDecision:
        """
        Convenience helper for callers that use only Gate 1 (Rule1 scheduler,
        DCF before Phase 2c, etc.).  Force always bypasses everything.
        """
        if force:
            last_val_ts   = await self.repo.get_last_valuation_ts(company_id, method=method)
            latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id, method=method)
            logger.debug("[GATE1][%s][%s] Forced recompute", company_id, method)
            return RecomputeDecision(
                True, last_val_ts, latest_dep_ts, "forced", gate=1
            )
        return await self.should_recompute(company_id=company_id, method=method)

    async def should_recompute_rule1(self, company_id: int) -> RecomputeDecision:
        return await self.should_recompute(company_id=company_id, method="rule1")

    # ── Gate 2: Fingerprint ────────────────────────────────────────────────────
# Valid fingerprint: 16-character lowercase hex string produced by
# shared.finance_math.build_fingerprint (SHA-256 truncated to 16 chars).
    _VALID_FINGERPRINT_RE = re.compile(r'^[0-9a-f]{16}$')
    async def check_fingerprint(
        self,
        company_id:          int,
        method:              str,
        current_fingerprint: str,
    ) -> RecomputeDecision:
        """
        Gate 2: compare the current dependency fingerprint against the one stored
        in the last valuation run's input_snapshot["dependency_fingerprint"].

        A fingerprint is a SHA-256 hash built from the exact source field values
        that feed this method's inputs (e.g. for DDM: TTM dividend amounts, 10-year
        DPS series, latest ROE, retention ratio, beta, method params hash).

        Returns should_recompute=False  when fingerprints match → source data is
        byte-for-byte identical to what produced the last run.  The dependency table
        timestamps advanced (triggering Gate 1) but values did not change.  This is
        the normal case for HuggingFace-sourced data on quiet days.

        Returns should_recompute=True with reason "no_stored_fingerprint" when the
        last run predates the fingerprint feature — treated as a one-time recompute
        that will then store the fingerprint for all future requests.
        """
        last_val_ts   = await self.repo.get_last_valuation_ts(company_id, method=method)
        latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id, method=method)

        snap               = await self.repo.get_last_input_snapshot(company_id, method=method)
        stored_fingerprint = (snap or {}).get("dependency_fingerprint")

        if stored_fingerprint is not None:
            if not isinstance(stored_fingerprint, str) or not _VALID_FINGERPRINT_RE.match(stored_fingerprint):
                logger.warning(
                    "[GATE2][%s][%s] Stored fingerprint is malformed (type=%s value=%.40r) "
                    "— treating as absent; one-time recompute will restore valid fingerprint.",
                    company_id, method,
                    type(stored_fingerprint).__name__,
                    stored_fingerprint,
                )
                stored_fingerprint = None
        if not stored_fingerprint:
            logger.debug(
                "[GATE2][%s][%s] No stored fingerprint → one-time recompute to populate",
                company_id, method,
            )
            return RecomputeDecision(
                True, last_val_ts, latest_dep_ts,
                "no_stored_fingerprint", gate=2,
                change_details={"current_fp": current_fingerprint, "stored_fp": None},
            )

        if current_fingerprint == stored_fingerprint:
            logger.debug(
                "[GATE2][%s][%s] Fingerprint match → cached "
                "(timestamp noise eliminated, no source data change)",
                company_id, method,
            )
            return RecomputeDecision(
                False, last_val_ts, latest_dep_ts,
                "fingerprint_match", gate=2,
                change_details={"fingerprint": current_fingerprint},
            )

        logger.debug(
            "[GATE2][%s][%s] Fingerprint mismatch → proceed to Gate 3",
            company_id, method,
        )
        return RecomputeDecision(
            True, last_val_ts, latest_dep_ts,
            "fingerprint_mismatch", gate=2,
            change_details={
                "current_fp": current_fingerprint,
                "stored_fp":  stored_fingerprint,
            },
        )

    # ── Gate 3: Materiality ────────────────────────────────────────────────────

    def is_material_change(
        self,
        resolved_current: Dict[str, Any],
        resolved_stored:  Dict[str, Any],
        method:           str,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Gate 3: determine whether resolved input changes are economically significant.

        Called by the SERVICE LAYER after lightweight input resolution (DdmService
        .resolve_current_inputs), only when Gate 2 confirmed source data changed.
        This guard never resolves inputs itself — it only evaluates two resolved dicts.

        Returns:
          (is_material: bool, reason_token: str, details: dict)

        Structural changes (source-path flips, null transitions) are always material.
        Numeric changes are evaluated against per-field significance thresholds.
        See _DDM_NUMERIC_THRESHOLDS and _DDM_STRUCTURAL_FIELDS at module top.
        """
        if method in {"ddm_gordon", "ddm_two_stage"}:
            return self._is_material_ddm(resolved_current, resolved_stored)

        if method == "dcf":
            return self._is_material_generic(
                resolved_current, resolved_stored,
                _DCF_NUMERIC_THRESHOLDS, _DCF_STRUCTURAL_FIELDS, method,
            )
        if method == "owner_earnings":
            return self._is_material_generic(
                resolved_current, resolved_stored,
                _OE_NUMERIC_THRESHOLDS, _OE_STRUCTURAL_FIELDS, method,
            )
        if method == "residual_income":
            return self._is_material_generic(
                resolved_current, resolved_stored,
                _RI_NUMERIC_THRESHOLDS, _RI_STRUCTURAL_FIELDS, method,
            )

        # rule1: suitability scorecard is categorical; fingerprint-only guard
        # (no Gate 3 numeric thresholds — Gate 2 fingerprint mismatch = always material)
        logger.debug(
            "[GATE3][%s] No Gate 3 specification → treating as material", method
        )
        return True, "no_gate3_for_method", {}

    def _is_material_generic(
        self,
        current:          Dict[str, Any],
        stored:           Dict[str, Any],
        numeric_thresholds: Dict[str, Dict[str, Any]],
        structural_fields:  Tuple[str, ...],
        method:           str,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        details: Dict[str, Any] = {}

        # ── Structural checks ──────────────────────────────────────────────
        for struct_field in structural_fields:
            cv = current.get(struct_field)
            sv = stored.get(struct_field)
            if cv != sv:
                reason  = f"{struct_field}_path_change"
                details = {struct_field: {"stored": sv, "current": cv}}
                logger.debug(
                    "[GATE3][%s] Structural change on %s: '%s' → '%s'",
                    method, struct_field, sv, cv,
                )
                return True, reason, details

        # ── Numeric checks ─────────────────────────────────────────────────
        for fname, spec in numeric_thresholds.items():
            cv = current.get(fname)
            sv = stored.get(fname)

            if cv is None and sv is None:
                continue

            if (cv is None) != (sv is None):
                reason  = f"{fname}_null_transition"
                details = {fname: {"stored": sv, "current": cv, "reason": "null_transition"}}
                logger.debug(
                    "[GATE3][%s] Null transition on %s: %s → %s", method, fname, sv, cv
                )
                return True, reason, details

            cv_f      = float(cv)
            sv_f      = float(sv)
            method_   = spec["method"]
            threshold = spec["threshold"]

            if method_ == "relative":
                denom    = max(abs(sv_f), 1e-10)
                delta    = abs(cv_f - sv_f) / denom
                material = delta > threshold
                details[fname] = {
                    "stored":             sv_f,
                    "current":            cv_f,
                    "relative_delta_pct": round(delta * 100, 4),
                    "threshold_pct":      round(threshold * 100, 4),
                    "material":           material,
                }
            elif method_ == "absolute_bps":
                delta    = abs(cv_f - sv_f)
                material = delta > threshold
                details[fname] = {
                    "stored":             sv_f,
                    "current":            cv_f,
                    "absolute_delta_bps": round(delta * 10_000, 2),
                    "threshold_bps":      round(threshold * 10_000, 2),
                    "material":           material,
                }
            else:
                material = cv_f != sv_f
                details[fname] = {"stored": sv_f, "current": cv_f, "material": material}

            if material:
                logger.debug(
                    "[GATE3][%s] Material change on %s: %s → %s  %s",
                    method, fname, sv_f, cv_f, details[fname],
                )
                return True, f"{fname}_material_change", details

        logger.debug(
            "[GATE3][%s] All fields within significance thresholds → immaterial", method
        )
        return False, "immaterial_data_change", details


    def _is_material_ddm(
        self,
        current: Dict[str, Any],
        stored:  Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        details: Dict[str, Any] = {}

        # ── Structural checks: source-path changes are always material ─────────
        for struct_field in _DDM_STRUCTURAL_FIELDS:
            cv = current.get(struct_field)
            sv = stored.get(struct_field)
            if cv != sv:
                reason  = f"{struct_field}_path_change"
                details = {struct_field: {"stored": sv, "current": cv}}
                logger.debug(
                    "[GATE3][DDM] Structural change on %s: '%s' → '%s'",
                    struct_field, sv, cv,
                )
                return True, reason, details

        # ── Numeric checks: threshold-based significance per field ─────────────
        for fname, spec in _DDM_NUMERIC_THRESHOLDS.items():
            cv = current.get(fname)
            sv = stored.get(fname)

            # Both absent → no change, nothing to evaluate
            if cv is None and sv is None:
                continue

            # One side is None → structural null transition (data appeared/disappeared)
            if (cv is None) != (sv is None):
                reason  = f"{fname}_null_transition"
                details = {fname: {"stored": sv, "current": cv, "reason": "null_transition"}}
                logger.debug(
                    "[GATE3][DDM] Null transition on %s: %s → %s", fname, sv, cv
                )
                return True, reason, details

            cv_f      = float(cv)
            sv_f      = float(sv)
            method_   = spec["method"]
            threshold = spec["threshold"]

            if method_ == "relative":
                denom  = max(abs(sv_f), 1e-10)
                delta  = abs(cv_f - sv_f) / denom
                material = delta > threshold
                details[fname] = {
                    "stored":             sv_f,
                    "current":            cv_f,
                    "relative_delta_pct": round(delta * 100, 4),
                    "threshold_pct":      round(threshold * 100, 4),
                    "material":           material,
                }

            elif method_ == "absolute_bps":
                delta    = abs(cv_f - sv_f)
                material = delta > threshold
                details[fname] = {
                    "stored":              sv_f,
                    "current":             cv_f,
                    "absolute_delta_bps":  round(delta * 10_000, 2),
                    "threshold_bps":       round(threshold * 10_000, 2),
                    "material":            material,
                }

            else:
                material = cv_f != sv_f
                details[fname] = {"stored": sv_f, "current": cv_f, "material": material}

            if material:
                logger.debug(
                    "[GATE3][DDM] Material change on %s: %s → %s  %s",
                    fname, sv_f, cv_f, details[fname],
                )
                return True, f"{fname}_material_change", details

        logger.debug("[GATE3][DDM] All fields within significance thresholds → immaterial")
        return False, "immaterial_data_change", details

    # ── Gate 3 action: advance fingerprint on immaterial skip ─────────────────

    async def record_immaterial_change(
        self,
        company_id:      int,
        method:          str,
        new_fingerprint: str,
    ) -> None:
        """
        Gate 3 skip action: patch the dependency_fingerprint in the most recent
        valuation run's input_snapshot without writing a new run record.

        Why this matters
        ────────────────
        If we skip recompute (Gate 3 says immaterial) but do NOT update the stored
        fingerprint, the NEXT request will see the same fingerprint mismatch and
        run Gates 2 & 3 again, wasting the resolution queries.

        By advancing the fingerprint here, subsequent requests pass Gate 2 cleanly
        (fingerprint_match) until the next genuine source data change.

        This is a lightweight JSONB patch on a single row — not a new valuation run.
        Failure is non-fatal: the worst outcome is one redundant Gate 3 evaluation.
        """
        try:
            await self.repo.update_valuation_fingerprint(
                company_id=company_id,
                method=method,
                new_fingerprint=new_fingerprint,
            )
            logger.debug(
                "[GATE3][%s][%s] Stored fingerprint advanced after immaterial change",
                company_id, method,
            )
        except Exception as exc:
            logger.warning(
                "[GATE3][%s][%s] Failed to advance fingerprint (non-fatal, "
                "Gate 3 will re-evaluate next request): %s",
                company_id, method, exc,
            )