# application/services/ddm_service.py
"""
DDM Service — Three-Gate Caching

Gate 1 — Timestamp:   Are dependency tables newer than the last valuation run?
Gate 2 — Fingerprint: Have source data VALUES actually changed?
Gate 3 — Materiality: Are resolved inputs (D0, g, k) economically significant changes?

Only a change that passes all three gates triggers full recomputation.

Bypass rules (always go straight to recompute):
  force=True                → explicit caller request
  no_prior_valuation        → nothing to compare (Gate 1)
  any override field set    → explicit user inputs, always honour them

Variants: ddm_gordon, ddm_two_stage
Price policy: intrinsic is cached; current price & upside computed at read-time only.
AI summary: called AFTER intrinsic, upside, and g (g2 for two-stage) are finalised.
"""
from __future__ import annotations

import logging
from typing import Any

from application.services.ai_service import generate_suitability_summary
from application.services.ddm_suitability import evaluate_ddm_suitability
from application.services.recompute_guard import RecomputeGuard
from domain.models.valuation_ddm import DdmRequestOverrides, DdmResponse, DdmValuation
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import (
    build_fingerprint,
    clamp,
    pct_or_frac_to_frac,
    safe_float,
)
from shared.time_utils import now_iso, now_utc

logger = logging.getLogger(__name__)


# ── Service ────────────────────────────────────────────────────────────────────

class DdmService:
    """Dividend Discount Model valuation service with three-gate caching."""

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo  = repo
        self.guard = guard

    # ── Public entry point ─────────────────────────────────────────────────────

    async def compute_ddm_if_stale(
        self,
        symbol:    str,
        user_id:   int | None,
        variant:   str,
        overrides: DdmRequestOverrides | None = None,
        force:     bool = False,
    ) -> DdmResponse:
        overrides  = overrides or DdmRequestOverrides()
        method     = "ddm_gordon" if variant == "gordon" else "ddm_two_stage"
        ctx        = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")

        # ── Force: bypass all three gates ─────────────────────────────────────
        if force:
            logger.info(
                "[VALUATION][DDM][%s] forced recompute: company=%s symbol=%s",
                method, company_id, symbol,
            )
            dep_values  = await self.repo.get_ddm_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, method, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 1: Timestamp ──────────────────────────────────────────────────
        gate1 = await self.guard.should_recompute(company_id, method=method)

        if not gate1.should_recompute:
            logger.debug(
                "[VALUATION][DDM][%s] Gate 1 → cached (up_to_date): %s",
                method, symbol,
            )
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info(
            "[VALUATION][DDM][%s] Gate 1 fired: company=%s symbol=%s "
            "reason=%s dep_ts=%s last_ts=%s",
            method, company_id, symbol,
            gate1.reason, gate1.latest_dependency_at, gate1.last_valuation_at,
        )

        # ── No prior valuation: skip Gates 2 & 3 ──────────────────────────────
        # Nothing stored to compare fingerprint or resolved inputs against.
        if gate1.reason == "no_prior_valuation":
            dep_values  = await self.repo.get_ddm_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, method, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Override present: bypass Gates 2 & 3 ──────────────────────────────
        # User explicitly supplied inputs → respect them unconditionally.
        # We still build and store the fingerprint so subsequent non-override
        # requests can benefit from Gate 2.
        if self._has_overrides(overrides):
            logger.info(
                "[VALUATION][DDM][%s] Override present → bypass Gates 2&3: %s",
                method, symbol,
            )
            dep_values  = await self.repo.get_ddm_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, method, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 2: Fingerprint ────────────────────────────────────────────────
        dep_values  = await self.repo.get_ddm_dependency_values(company_id)
        fingerprint = build_fingerprint(dep_values)

        gate2 = await self.guard.check_fingerprint(company_id, method, fingerprint)
        if not gate2.should_recompute:
            logger.info(
                "[VALUATION][DDM][%s] Gate 2 → cached (fingerprint_match): %s",
                method, symbol,
            )
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info(
            "[VALUATION][DDM][%s] Gate 2 fired: company=%s symbol=%s reason=%s",
            method, company_id, symbol, gate2.reason,
        )

        # ── Gate 3: Materiality ────────────────────────────────────────────────
        # Source data is different from what produced the last run.
        # Check whether the resolved inputs (D0, g, k) moved enough to matter.
        last_input_snap = await self.repo.get_last_input_snapshot(company_id, method)
        stored_resolved = (last_input_snap or {}).get("resolved")

        if stored_resolved:
            defaults         = await self.repo.get_method_params(company_id, method=method)
            current_resolved = await self.resolve_current_inputs(company_id, overrides, defaults)
            is_material, gate3_reason, gate3_details = self.guard.is_material_change(
                current_resolved, stored_resolved, method
            )

            if not is_material:
                logger.info(
                    "[VALUATION][DDM][%s] Gate 3 → cached (immaterial): "
                    "company=%s symbol=%s reason=%s details=%s",
                    method, company_id, symbol, gate3_reason, gate3_details,
                )
                # Advance the stored fingerprint so Gate 2 passes cleanly next time
                await self.guard.record_immaterial_change(company_id, method, fingerprint)
                return await self._serve_cached(
                    symbol, company_id, currency, sector, user_id, method, overrides
                )

            logger.info(
                "[VALUATION][DDM][%s] Gate 3 → recompute (material): "
                "company=%s symbol=%s reason=%s",
                method, company_id, symbol, gate3_reason,
            )
        else:
            # No stored resolved block (run predates this feature) → proceed to recompute
            # which will store the resolved block for future Gate 3 comparisons.
            logger.debug(
                "[VALUATION][DDM][%s] Gate 3 skipped: no stored resolved inputs yet: %s",
                method, symbol,
            )

        # ── Full recompute ─────────────────────────────────────────────────────
        return await self._compute_and_persist(
            symbol, company_id, currency, sector, user_id, method, overrides,
            dependency_fingerprint=fingerprint,
        )

    async def get_cached(
        self, symbol: str, variant: str = "gordon"
    ) -> DdmResponse | None:
        """
        Pure cache read — no gate logic, no recompute, no DB writes.
        Returns None if no prior DDM valuation exists for this variant.
        Used by GET /valuations/{symbol}/ddm for instant tab loads.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            return None
        company_id = int(ctx["company_id"])

        method = "ddm_gordon" if variant == "gordon" else "ddm_two_stage"
        snap   = await self.repo.get_last_output_snapshot(
            company_id=company_id, method=method
        )
        if not snap:
            return None

        valuation_payload     = snap.get("valuation")     or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload            = snap.get("dataQuality")   or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )

        # Refresh currentPrice and upside at read time
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic     = safe_float(valuation_payload.get("intrinsicValue"))
        upside        = None
        if (current_price is not None and float(current_price) > 0
                and intrinsic is not None and intrinsic > 0):
            upside = (float(intrinsic) - float(current_price)) / float(current_price)
        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "DDM-NO-AUDIT", "severity": "info",
                    "message": "No prior DDM valuation run found; run Recompute once.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return DdmResponse(
            valuation=DdmValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )


    # ── Cached path ────────────────────────────────────────────────────────────

    async def _serve_cached(
        self,
        symbol:    str,
        company_id: int,
        currency:  str,
        sector:    str | None,
        user_id:   int | None,
        method:    str,
        overrides: DdmRequestOverrides,
    ) -> DdmResponse:
        """
        Hydrate and return the last persisted output snapshot with a fresh price.
        Falls back to full recompute if no snapshot exists (defensive guard).
        """
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info(
                "[VALUATION][DDM][%s] Cached path: snapshot missing, recomputing: %s",
                method, symbol,
            )
            dep_values  = await self.repo.get_ddm_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, method, overrides,
                dependency_fingerprint=fingerprint,
            )

        valuation_payload     = snap.get("valuation")     or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload            = snap.get("dataQuality")   or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )

        # Read-time price only — intrinsic is intentionally cached
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic     = float(valuation_payload.get("intrinsicValue") or 0.0)
        upside        = None
        if current_price is not None and float(current_price) > 0 and intrinsic > 0:
            upside = (intrinsic - float(current_price)) / float(current_price)
        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0,
                "category": "Caution",
                "flags": [{
                    "code": "DDM-NO-AUDIT",
                    "severity": "info",
                    "message": (
                        "No prior DDM valuation run found; suitability scorecard "
                        "not available on cached path."
                    ),
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return DdmResponse(
            valuation=DdmValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )

    # ── Gate helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _has_overrides(overrides: DdmRequestOverrides) -> bool:
        """
        True if ANY user-supplied override field is non-null.
        Override presence means Gates 2 & 3 are bypassed — the user explicitly
        requested computation with specific inputs.
        """
        return any([
            overrides.currentDps         is not None,
            overrides.requiredReturn      is not None,
            overrides.dividendGrowthRate  is not None,
            overrides.beta                is not None,
            overrides.riskFreeRate        is not None,
            overrides.equityRiskPremium   is not None,
            overrides.highGrowthYears     is not None,
            overrides.highGrowthRate      is not None,
            overrides.stableGrowthRate    is not None,
        ])

    async def resolve_current_inputs(
        self,
        company_id: int,
        overrides:  DdmRequestOverrides,
        defaults:   dict[str, Any],
    ) -> dict[str, Any]:
        """
        Lightweight input resolution for Gate 3 comparison.

        Resolves D0, g, and k using the SAME resolver methods as _compute_and_persist
        but WITHOUT computing intrinsic value, calling the AI service, or persisting.

        Returns a dict with the same keys stored in input_snapshot["resolved"], with
        values rounded to 4 decimal places (basis-point precision for rates).

        Called only when Gate 2 fires (fingerprint mismatch), which after Phase 1
        will be infrequent — only when HuggingFace actually publishes new data.
        """
        # ── D0 ──────────────────────────────────────────────────────────────
        d0        = overrides.currentDps
        d0_source = "override.currentDps" if d0 is not None else None
        if d0 is None:
            d0        = await self.repo.get_dividend_ttm_dps(company_id)
            d0_source = "dividend_history_ttm"

        if d0 is None or float(d0) <= 0:
            # No dividend — return a zero-sentinel so Gate 3 can detect
            # a transition from dividend to no-dividend as structural.
            return {
                "d0":        0.0,
                "d0_source": "no_dividend",
                "g_final":   0.0,
                "g_source":  "no_dividend",
                "g_hist":    None,
                "g_sgr":     None,
                "k_final":   0.0,
                "k_source":  "no_dividend",
                "beta":      None,
            }

        d0 = float(d0)

        # ── k ───────────────────────────────────────────────────────────────
        k_final, k_evidence = await self._resolve_required_return(
            company_id, overrides, defaults
        )

        # ── g ───────────────────────────────────────────────────────────────
        g_final, g_evidence = await self._resolve_dividend_growth(
            company_id, overrides, defaults, k_final
        )

        return {
            "d0":        round(d0, 4),
            "d0_source": d0_source,
            "g_final":   round(g_final, 4),
            "g_source":  g_evidence.get("source"),
            "g_hist":    round(float(g_evidence["gHist"]), 4)
                         if g_evidence.get("gHist") is not None else None,
            "g_sgr":     round(float(g_evidence["gSgr"]), 4)
                         if g_evidence.get("gSgr") is not None else None,
            "k_final":   round(k_final, 4),
            "k_source":  k_evidence.get("source"),
            "beta":      round(float(k_evidence["beta"]), 4)
                         if k_evidence.get("beta") is not None else None,
        }

    # ── Full computation + persistence ─────────────────────────────────────────

    async def _compute_and_persist(
        self,
        symbol:                 str,
        company_id:             int,
        currency:               str,
        sector:                 str | None,
        user_id:                int | None,
        method:                 str,
        overrides:              DdmRequestOverrides,
        dependency_fingerprint: str | None = None,
    ) -> DdmResponse:
        """
        Full DDM computation path.  Resolves D0/g/k, computes intrinsic, runs
        suitability + AI summary, then persists two records:
          1. ddm_valuations  (analytics stream)
          2. valuation_runs  (audited snapshot — input + output + resolved inputs)

        dependency_fingerprint: pre-computed fingerprint from Gate 2 path.
          Stored in input_snapshot so future Gate 2 checks have something to compare.
          None only on legacy force-calls that pre-date the fingerprint feature.
        """
        defaults = await self.repo.get_method_params(company_id, method=method)

        # ── Resolve D0 ─────────────────────────────────────────────────────
        d0        = overrides.currentDps
        d0_source = "override.currentDps" if d0 is not None else None
        if d0 is None:
            d0        = await self.repo.get_dividend_ttm_dps(company_id)
            d0_source = "dividend_history_ttm"

        current_price = await self.repo.get_current_market_price(company_id)

        input_decisions: dict[str, Any] = {"d0Source": d0_source}
        flags: list[DiagnosticFlag]     = []
        fallbacks_used                  = False

        # ── Early exit: no dividend ────────────────────────────────────────
        if d0 is None or float(d0) <= 0:
            flags.append(DiagnosticFlag(
                code="DDM-NO-DIV",
                severity="critical",
                message="No dividend data available (D0 missing). DDM is not applicable.",
                recommendation=(
                    "Use non-dividend valuation methods "
                    "(Rule #1 / DCF / Owner Earnings)."
                ),
            ))
            ddm_score, ddm_category, ddm_flags, ddm_evidence = await evaluate_ddm_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
            )
            flags.extend(ddm_flags)
            suitability_summary = await generate_suitability_summary(
                symbol=symbol, method=method,
                score=int(ddm_score), category=ddm_category,
                flags=[f.dict() for f in flags], evidence=ddm_evidence,
                valuation_inputs={
                    "currency": currency, "currentDps": 0.0, "nextYearDps": 0.0,
                    "dividendGrowthRate": 0.0, "requiredReturn": 0.0,
                    "intrinsicValue": 0.0, "currentPrice": current_price,
                    "upsideDownsidePct": None,
                },
                input_decisions={"ddm": input_decisions},
            )
            valuation = DdmValuation(
                symbol=symbol.upper(), companyId=company_id, currency=currency,
                method="gordon" if method == "ddm_gordon" else "two_stage",
                currentDps=0.0, nextYearDps=0.0, dividendGrowthRate=0.0,
                requiredReturn=0.0, intrinsicValue=0.0,
                currentPrice=current_price, upsideDownsidePct=None,
            )
            # Store a no-dividend resolved block so Gate 3 can detect
            # a future transition to a dividend-paying state as structural.
            resolved_inputs = {
                "d0": 0.0,   "d0_source": "no_dividend",
                "g_final": 0.0, "g_source": "no_dividend",
                "g_hist": None,  "g_sgr": None,
                "k_final": 0.0,  "k_source": "no_dividend",
                "beta": None,
                "resolved_at": now_iso(),
            }
            now_iso_str = now_iso()
            output_snapshot = {
                "valuation": valuation.dict(),
                "applicability": {
                    "score": ddm_score, "category": ddm_category,
                    "flags": [f.dict() for f in flags],
                    "suitabilitySummary": suitability_summary,
                },
                "dataQuality": {
                    "freshnessDays": {"lastComputedAt": now_iso_str},
                    "fallbacksUsed": True,
                    "inputDecisions": {"ddm": input_decisions},
                },
                "suitabilityEvidence": ddm_evidence,
                "lastComputedAt": now_iso_str,
            }
            await self.repo.insert_valuation_run(
                company_id=company_id, method=method,
                run={
                    "run_by_user_id":    user_id,
                    "input_snapshot":    {
                        "overrides":              overrides.dict(),
                        "dependency_fingerprint": dependency_fingerprint,
                        "resolved":               resolved_inputs,
                    },
                    "assumption_snapshot": defaults,
                    "output_snapshot":   output_snapshot,
                    "data_version_tag":  None,
                    "notes":             overrides.notes,
                },
            )
            return DdmResponse(
                valuation=valuation,
                applicability=Applicability(
                    score=int(ddm_score), category=ddm_category,
                    flags=flags, suitabilitySummary=suitability_summary,
                ),
                dataQuality=DataQuality(
                    freshnessDays={}, fallbacksUsed=True,
                    inputDecisions={"ddm": input_decisions},
                ),
            )

        d0 = float(d0)

        # ── Resolve k and g ────────────────────────────────────────────────
        k, k_evidence = await self._resolve_required_return(company_id, overrides, defaults)
        input_decisions["requiredReturn"] = k_evidence

        g, g_evidence = await self._resolve_dividend_growth(company_id, overrides, defaults, k)
        input_decisions["dividendGrowthRate"] = g_evidence

        # Capture g BEFORE any two-stage reassignment.
        # Gate 3 compares the base resolved growth rate used for the initial D1
        # projection; g2 is a computation-internal variable, not a raw input.
        g_resolved_for_gate3 = g

        # ── Build resolved inputs block ────────────────────────────────────
        # Stored in input_snapshot["resolved"] so future Gate 3 evaluations
        # have a precise record of what inputs produced this run.
        # Values rounded to 4dp (basis-point precision for rates, sub-cent for D0).
        resolved_inputs: dict[str, Any] = {
            "d0":        round(d0, 4),
            "d0_source": d0_source,
            "g_final":   round(g_resolved_for_gate3, 4),
            "g_source":  g_evidence.get("source"),
            "g_hist":    round(float(g_evidence["gHist"]), 4)
                         if g_evidence.get("gHist") is not None else None,
            "g_sgr":     round(float(g_evidence["gSgr"]), 4)
                         if g_evidence.get("gSgr") is not None else None,
            "k_final":   round(float(k), 4),
            "k_source":  k_evidence.get("source"),
            "beta":      round(float(k_evidence["beta"]), 4)
                         if k_evidence.get("beta") is not None else None,
            "resolved_at": now_iso(),
        }

        d1 = d0 * (1.0 + g)

        # ── Guardrail flags ────────────────────────────────────────────────
        if k_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="DDM-K-CLAMP", severity="info",
                message="Required return (k) was clamped to safety bounds.",
                evidence=k_evidence,
            ))
        if g_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="DDM-G-CLAMP", severity="info",
                message="Dividend growth (g) was clamped to safety bounds.",
                evidence=g_evidence,
            ))

        # ── Intrinsic value ────────────────────────────────────────────────
        intrinsic   = 0.0
        pv_stage1   = None
        pv_terminal = None

        if method == "ddm_gordon":
            if g >= k:
                flags.append(DiagnosticFlag(
                    code="DDM-GE-K", severity="critical",
                    message=(
                        "Dividend growth rate (g) must be less than required return (k) "
                        "for Gordon model."
                    ),
                    evidence={"g": g, "k": k},
                    recommendation="Use Two-Stage DDM or lower g / raise k.",
                ))
                intrinsic = 0.0
            else:
                intrinsic = d1 / (k - g)

        else:  # two_stage
            n      = int(
                overrides.highGrowthYears if overrides.highGrowthYears is not None
                else defaults.get("twostageyearsdefault", 5)
            )
            g1_cap = float(defaults.get("g1_cap",    0.12))
            g2_def = float(defaults.get("g2default", 0.03))
            gap    = float(defaults.get("ggaptok",   0.01))

            g1 = (
                float(overrides.highGrowthRate)
                if overrides.highGrowthRate is not None
                else min(g, g1_cap)
            )
            g1 = clamp(g1, 0.0, g1_cap)

            g2 = (
                float(overrides.stableGrowthRate)
                if overrides.stableGrowthRate is not None
                else g2_def
            )
            g2 = pct_or_frac_to_frac(g2)
            if g2 >= k:
                g2 = max(0.0, k - gap)
                flags.append(DiagnosticFlag(
                    code="DDM-G2-ADJUST", severity="medium",
                    message="Stable growth rate (g2) adjusted to ensure g2 < k.",
                    evidence={"g2Adjusted": g2, "k": k, "gap": gap},
                ))

            pv1 = 0.0
            for t in range(1, n + 1):
                dt   = d0 * ((1.0 + g1) ** t)
                pv1 += dt  / ((1.0 + k) ** t)

            dn    = d0 * ((1.0 + g1) ** n)
            dn1   = dn * (1.0 + g2)
            tv_n  = dn1 / (k - g2) if k > g2 else 0.0
            pv_tv = tv_n / ((1.0 + k) ** n)

            pv_stage1   = pv1
            pv_terminal = pv_tv
            intrinsic   = pv1 + pv_tv

            # ⚠ g reassigned to g2 so AI summary receives the stable-phase rate
            #   shown on the valuation card.  resolved_inputs captured g BEFORE
            #   this reassignment (see g_resolved_for_gate3 above).
            g = g2

        # ── Upside (requires finalised intrinsic) ─────────────────────────
        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic > 0:
            upside = (intrinsic - float(current_price)) / float(current_price)

        # ── Suitability scorecard ──────────────────────────────────────────
        ddm_score, ddm_category, ddm_flags, ddm_evidence = await evaluate_ddm_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
        )
        flags.extend(ddm_flags)

        # ── AI summary ─────────────────────────────────────────────────────
        # Called here — AFTER intrinsic, upside, and g (g2 for two-stage) finalised.
        suitability_summary = await generate_suitability_summary(
            symbol=symbol, method=method,
            score=int(ddm_score), category=ddm_category,
            flags=[f.dict() for f in flags], evidence=ddm_evidence,
            valuation_inputs={
                "currency":           currency,
                "currentDps":         d0,
                "nextYearDps":        float(d1),
                "dividendGrowthRate": float(g),   # g2 for two-stage (correctly reassigned)
                "requiredReturn":     float(k),
                "intrinsicValue":     float(intrinsic),
                "currentPrice":       current_price,
                "upsideDownsidePct":  upside,
            },
            input_decisions={"ddm": input_decisions},
        )

        # ── Build valuation object ─────────────────────────────────────────
        valuation = DdmValuation(
            symbol=symbol.upper(), companyId=company_id, currency=currency,
            method="gordon" if method == "ddm_gordon" else "two_stage",
            currentDps=d0, nextYearDps=float(d1),
            dividendGrowthRate=float(g), requiredReturn=float(k),
            intrinsicValue=float(intrinsic),
            highGrowthYears=(None if method == "ddm_gordon" else n),
            highGrowthRate=(None  if method == "ddm_gordon" else float(g1)),
            stableGrowthRate=(None if method == "ddm_gordon" else float(g2)),
            pvStage1=pv_stage1, pvTerminal=pv_terminal,
            currentPrice=current_price, upsideDownsidePct=upside,
        )

        # ── Persist: ddm_valuations (analytics stream) ─────────────────────
        try:
            await self.repo.insert_ddm_valuation(payload={
                "company_id":                  company_id,
                "analysis_date":               now_utc().date().isoformat(),
                "current_dps":                 d0,
                "next_year_dps":               float(d1),
                "dividend_growth_rate":        float(g),
                "required_return":             float(k),
                "intrinsic_value_gordon":      float(intrinsic) if method == "ddm_gordon" else None,
                "high_growth_years":           valuation.highGrowthYears,
                "high_growth_rate":            valuation.highGrowthRate,
                "stable_growth_rate":          valuation.stableGrowthRate,
                "intrinsic_value_multistage":  float(intrinsic) if method != "ddm_gordon" else None,
                "current_stock_price":         current_price,
                "upside_downside_pct":         upside,
                "analyst_name":               overrides.analystName,
                "notes":                       overrides.notes,
            })
        except Exception as exc:
            logger.error("insert_ddm_valuation failed: %s", exc)

        # ── Persist: valuation_runs (audited record) ───────────────────────
        # input_snapshot now carries three things:
        #   "overrides"              — what the user supplied (unchanged)
        #   "dependency_fingerprint" — SHA-256 of source field values (Gate 2)
        #   "resolved"               — actual D0/g/k used (Gate 3)
        now_iso_str = now_iso()
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score":              ddm_score,
                "category":           ddm_category,
                "flags":              [f.dict() for f in flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays":  {"lastComputedAt": now_iso_str},
                "fallbacksUsed":  fallbacks_used,
                "inputDecisions": {"ddm": input_decisions},
            },
            "suitabilityEvidence": ddm_evidence,
            "lastComputedAt":      now_iso_str,
        }
        await self.repo.insert_valuation_run(
            company_id=company_id, method=method,
            run={
                "run_by_user_id":    user_id,
                "input_snapshot":    {
                    "overrides":              overrides.dict(),
                    "dependency_fingerprint": dependency_fingerprint,
                    "resolved":               resolved_inputs,
                },
                "assumption_snapshot": defaults,
                "output_snapshot":   output_snapshot,
                "data_version_tag":  None,
                "notes":             overrides.notes,
            },
        )

        return DdmResponse(
            valuation=valuation,
            applicability=Applicability(
                score=ddm_score, category=ddm_category,
                flags=flags, suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=fallbacks_used,
                inputDecisions={"ddm": input_decisions},
            ),
        )

    # ── Resolvers (logic unchanged; used by both Gate 3 and full compute) ──────

    async def _resolve_required_return(
        self,
        company_id: int,
        overrides:  DdmRequestOverrides,
        defaults:   dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        k_floor     = float(defaults.get("kfloor",    0.07))
        k_cap       = float(defaults.get("kcap",      0.14))
        k_default   = float(defaults.get("kdefault",  0.10))
        rf_default  = float(defaults.get("rfdefault", 0.045))
        erp_default = float(defaults.get("erpdefault", 0.055))

        if overrides.requiredReturn is not None:
            k_raw   = float(overrides.requiredReturn)
            k_final = clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "override.requiredReturn",
                "kRaw": k_raw, "kFinal": k_final,
                "kFloor": k_floor, "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        beta = overrides.beta
        if beta is None:
            beta = await self.repo.get_beta_latest(company_id)
        rf  = float(overrides.riskFreeRate)      if overrides.riskFreeRate      is not None else rf_default
        erp = float(overrides.equityRiskPremium) if overrides.equityRiskPremium is not None else erp_default

        if beta is None:
            k_raw   = k_default
            k_final = clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "default.kdefault (beta missing)",
                "beta": None, "rf": rf, "erp": erp,
                "kRaw": k_raw, "kFinal": k_final,
                "kFloor": k_floor, "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        k_raw   = rf + float(beta) * erp
        k_final = clamp(k_raw, k_floor, k_cap)
        return k_final, {
            "source": "capm-ish",
            "beta": float(beta), "rf": rf, "erp": erp,
            "kRaw": k_raw, "kFinal": k_final,
            "kFloor": k_floor, "kCap": k_cap,
            "clamped": k_raw != k_final,
        }

    async def _resolve_dividend_growth(
        self,
        company_id: int,
        overrides:  DdmRequestOverrides,
        defaults:   dict[str, Any],
        k:          float,
    ) -> tuple[float, dict[str, Any]]:
        g_floor   = float(defaults.get("gfloor",    0.02))
        g_cap     = float(defaults.get("gcap",      0.10))
        gap_to_k  = float(defaults.get("ggaptok",   0.01))
        g_default = float(defaults.get("g2default", 0.04))

        if overrides.dividendGrowthRate is not None:
            g_raw    = pct_or_frac_to_frac(float(overrides.dividendGrowthRate))
            g_stable = min(g_raw, max(0.0, k - gap_to_k))
            g_final  = clamp(g_stable, g_floor, g_cap)
            return g_final, {
                "source": "override.dividendGrowthRate",
                "gRaw": g_raw, "gAfterStability": g_stable, "gFinal": g_final,
                "gFloor": g_floor, "gCap": g_cap, "gapToK": gap_to_k, "k": k,
                "clamped": (g_final != g_raw) or (g_raw != g_stable),
            }

        g_hist     = await self.repo.get_dividend_cagr(company_id, years=10)
        g_sgr      = await self.repo.get_sustainable_dividend_growth(company_id)
        candidates = [g for g in [g_hist, g_sgr] if g is not None]

        if not candidates:
            g_raw  = g_default
            source = "default.g2default (missing hist & sgr)"
        else:
            g_raw  = float(min(candidates))
            source = (
                "min(g_hist, g_sgr)" if (g_hist is not None and g_sgr is not None)
                else ("g_hist" if g_hist is not None else "g_sgr")
            )

        g_stable = min(g_raw, max(0.0, k - gap_to_k))
        g_final  = clamp(g_stable, g_floor, g_cap)
        return g_final, {
            "source": source,
            "gHist": g_hist, "gSgr": g_sgr,
            "gRaw": g_raw, "gAfterStability": g_stable, "gFinal": g_final,
            "gFloor": g_floor, "gCap": g_cap, "gapToK": gap_to_k, "k": k,
            "clamped": (g_final != g_raw) or (g_raw != g_stable),
        }
