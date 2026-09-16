# application/services/residual_income_service.py
#
# CHANGES IN THIS VERSION
# ─────────────────────────────────────────────────────────────────────────────
# Bug 1 fix (CRITICAL):
#   resolved_inputs was referenced inside insert_valuation_run's input_snapshot
#   but was never defined anywhere in _compute_and_persist. This caused a
#   NameError on every RI valuation run, which propagated through
#   insert_valuation_run (which re-raises), meaning no valuation_runs row was
#   ever written for RI. Consequently get_last_output_snapshot returned None,
#   get_cached returned None, and the UI showed nothing.
#
#   Fix: resolved_inputs dict is now assembled immediately after all inputs are
#   resolved (k_e, g_ri, tg_used, bv_per_share, eps0 are all in scope) and
#   before any DB write. The structure matches _RI_NUMERIC_THRESHOLDS in
#   recompute_guard.py and the resolve_current_inputs return value in this
#   same service — they all share the same field names.
#
#   The early-abort path (shares unavailable) also gets its own minimal
#   resolved_inputs block so that path writes a complete audit record too.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Any

from application.services.ai_service import generate_suitability_summary
from application.services.recompute_guard import RecomputeGuard
from application.services.residual_income_suitability import evaluate_residual_income_suitability
from domain.models.valuation_residual_income import (
    ResidualIncomeRequestOverrides,
    ResidualIncomeResponse,
    ResidualIncomeValuation,
)
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import (
    build_fingerprint,
    clamp,
    pct_or_frac_to_frac,
    safe_float,
)
from shared.time_utils import now_iso

logger = logging.getLogger(__name__)


class ResidualIncomeService:
    """
    Residual Income (Economic Profit / Ohlson Model) valuation service.

    Formula: Intrinsic/Share = BV₀/share + PV(RI stream) + PV(terminal RI)
    Where:   RI_t/share = EPS_t − k_e × BV_t/share  (projected at growth rate g)

    Architecture mirrors DdmService:
    - Cost of equity resolved via CAPM (rf + β × ERP).
    - No equity bridge (model is equity-native; BV already denominated per share).
    - Early exit if shareholders' equity ≤ 0 (book value anchor is broken).
    - AI summary called AFTER intrinsic value and upside are fully resolved.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    # ── Public entry point ────────────────────────────────────────────────────

    async def compute_residual_income_if_stale(
        self,
        symbol:    str,
        user_id:   int | None,
        overrides: ResidualIncomeRequestOverrides | None = None,
        force:     bool = False,
    ) -> ResidualIncomeResponse:
        overrides  = overrides or ResidualIncomeRequestOverrides()
        method     = "residual_income"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")

        # ── Force: bypass all gates ────────────────────────────────────────
        if force:
            dep_values  = await self.repo.get_ri_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][RI] forced recompute: %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 1: Timestamp ──────────────────────────────────────────────
        gate1 = await self.guard.should_recompute(company_id, method=method)

        if not gate1.should_recompute:
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info(
            "[VALUATION][RI] Gate 1 fired: %s reason=%s dep_ts=%s last_ts=%s",
            symbol, gate1.reason, gate1.latest_dependency_at, gate1.last_valuation_at,
        )

        # ── No prior valuation ─────────────────────────────────────────────
        if gate1.reason == "no_prior_valuation":
            dep_values  = await self.repo.get_ri_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Override present: bypass Gates 2 & 3 ──────────────────────────
        if self._has_overrides(overrides):
            dep_values  = await self.repo.get_ri_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][RI] Override present → bypass Gates 2&3: %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 2: Fingerprint ────────────────────────────────────────────
        dep_values  = await self.repo.get_ri_dependency_values(company_id)
        fingerprint = build_fingerprint(dep_values)

        gate2 = await self.guard.check_fingerprint(company_id, method, fingerprint)
        if not gate2.should_recompute:
            logger.info("[VALUATION][RI] Gate 2 → cached (fingerprint_match): %s", symbol)
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info("[VALUATION][RI] Gate 2 fired: %s reason=%s", symbol, gate2.reason)

        # ── Gate 3: Materiality ────────────────────────────────────────────
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
                    "[VALUATION][RI] Gate 3 → cached (immaterial): %s reason=%s",
                    symbol, gate3_reason,
                )
                await self.guard.record_immaterial_change(company_id, method, fingerprint)
                return await self._serve_cached(
                    symbol, company_id, currency, sector, user_id, method, overrides
                )
            logger.info(
                "[VALUATION][RI] Gate 3 → recompute (material): %s reason=%s",
                symbol, gate3_reason,
            )
        else:
            logger.debug("[VALUATION][RI] Gate 3 skipped: no stored resolved yet: %s", symbol)

        return await self._compute_and_persist(
            symbol, company_id, currency, sector, user_id, overrides,
            dependency_fingerprint=fingerprint,
        )

    # ── Pure cache read ────────────────────────────────────────────────────────

    async def get_cached(self, symbol: str) -> ResidualIncomeResponse | None:
        """
        Pure cache read — no gate logic, no recompute, no DB writes.
        Returns None if no prior Residual Income valuation exists.
        Used by GET /valuations/{symbol}/residual_income for instant tab loads.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            return None
        company_id = int(ctx["company_id"])

        snap = await self.repo.get_last_output_snapshot(
            company_id=company_id, method="residual_income"
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

        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps  = safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside        = None
        if (current_price is not None and float(current_price) > 0
                and intrinsic_ps is not None):
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)
        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "RI-NO-AUDIT", "severity": "info",
                    "message": "No prior RI valuation run found; run Recompute once.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return ResidualIncomeResponse(
            valuation=ResidualIncomeValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )

    # ── Cached path (gate bypass → serve last run) ─────────────────────────────

    async def _serve_cached(
        self,
        symbol:     str,
        company_id: int,
        currency:   str,
        sector:     str | None,
        user_id:    int | None,
        method:     str,
        overrides:  ResidualIncomeRequestOverrides,
    ) -> ResidualIncomeResponse:
        """Hydrate and return the last persisted output snapshot with a fresh price."""
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            dep_values  = await self.repo.get_ri_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        valuation_payload     = snap.get("valuation")     or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload            = snap.get("dataQuality")   or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )

        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps  = safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside        = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "RI-NO-AUDIT", "severity": "info",
                    "message": "No prior RI valuation run found; suitability scorecard not available on cached path.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return ResidualIncomeResponse(
            valuation=ResidualIncomeValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )

    # ── Gate helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _has_overrides(overrides: ResidualIncomeRequestOverrides) -> bool:
        return any([
            overrides.requiredReturn     is not None,
            overrides.beta               is not None,
            overrides.riskFreeRate       is not None,
            overrides.equityRiskPremium  is not None,
            overrides.riGrowthRate       is not None,
            overrides.terminalGrowthRate is not None,
            overrides.forecastYears      is not None,
        ])

    async def resolve_current_inputs(
        self,
        company_id: int,
        overrides:  ResidualIncomeRequestOverrides,
        defaults:   dict[str, Any],
    ) -> dict[str, Any]:
        """
        Lightweight input resolution for Gate 3 comparison.
        Returns the same field structure as resolved_inputs in _compute_and_persist
        so Gate 3 comparisons are meaningful.
        """
        shares: float | None = None
        try:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                latest = rows[-1]
                sh = safe_float(latest.get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares = float(sh)
                    logger.debug(
                        "[RI][%s] Gate3 shares=%.0f from %s",
                        company_id, shares, latest.get("_source", "unknown"),
                    )
        except Exception:
            pass
        if shares is None:
            try:
                summary = await self.repo.get_company_summary_latest(company_id)
                if summary:
                    sh = safe_float(
                        summary.get("shares_outstanding")
                        or summary.get("implied_shares_outstanding")
                    )
                    if sh and sh > 0:
                        shares = float(sh)
            except Exception:
                pass

        bv_per_share: float | None = None
        eps0:         float | None = None
        try:
            bs_row = await self.repo.get_balance_sheet_latest(company_id)
            equity = safe_float(bs_row.get("shareholders_equity")) if bs_row else None
            if equity is not None and shares and float(shares) > 0:
                bv_per_share = float(equity) / float(shares)
        except Exception:
            pass
        try:
            is_row = await self.repo.get_income_statement_latest(company_id)
            net_income = safe_float(
                (is_row or {}).get("net_income_to_common") or (is_row or {}).get("net_income")
            )
            if net_income is not None and shares and float(shares) > 0:
                eps0 = float(net_income) / float(shares)
        except Exception:
            pass

        k_e, k_evidence  = await self._resolve_cost_of_equity(company_id, overrides, defaults)
        g_ri, g_evidence = await self._resolve_ri_growth(company_id, overrides, defaults, k_e)

        tg_used: float | None = None
        if overrides.terminalGrowthRate is not None:
            tg_used = pct_or_frac_to_frac(float(overrides.terminalGrowthRate))
        else:
            tg_raw = safe_float(defaults.get("terminal_growth_default"))
            if tg_raw is not None:
                tg_used = pct_or_frac_to_frac(float(tg_raw))

        n = (
            int(overrides.forecastYears)
            if overrides.forecastYears is not None
            else int(defaults.get("forecast_years_default", 5))
        )

        return {
            "bv_per_share":     round(bv_per_share, 4) if bv_per_share is not None else None,
            "eps0":             round(eps0, 4)          if eps0         is not None else None,
            "k_e_final":        round(k_e, 4),
            "k_e_source":       k_evidence.get("source"),
            "g_ri_final":       round(g_ri, 4),
            "g_ri_source":      g_evidence.get("source"),
            "terminal_g_final": round(tg_used, 4)       if tg_used      is not None else None,
            "forecast_years":   n,
        }

    # ── Full computation + persistence ─────────────────────────────────────────

    async def _compute_and_persist(
        self,
        symbol:                 str,
        company_id:             int,
        currency:               str,
        sector:                 str | None,
        user_id:                int | None,
        overrides:              ResidualIncomeRequestOverrides,
        dependency_fingerprint: str | None = None,
    ) -> ResidualIncomeResponse:

        defaults = await self.repo.get_method_params(company_id, method="residual_income")
        flags: list[DiagnosticFlag] = []
        input_decisions: dict[str, Any] = {"ri": {}}
        fallbacks_used = False

        current_price = await self.repo.get_current_market_price(company_id)

        # ── Fetch base financial inputs ───────────────────────────────────────

        is_row         = await self.repo.get_income_statement_latest(company_id)
        bs_row         = await self.repo.get_balance_sheet_latest(company_id)
        shares_history = await self.repo.get_shares_history(company_id)

        shares: float | None = None

        if shares_history:
            latest = shares_history[-1]
            raw = latest.get("shares_outstanding_diluted")
            source = latest.get("_source", "unknown")
            if raw is not None:
                shares = float(raw)
                logger.debug(
                    "[RI][%s] shares=%.0f from %s (fiscal_year=%s)",
                    symbol, shares, source, latest.get("fiscal_year"),
                )
        else:
            logger.warning(
                "[RI][%s] get_shares_history returned empty (balance_sheets and "
                "income_statements both have no annual share rows), "
                "falling back to company_summary.shares_outstanding",
                 symbol,
            )
            try:
                summary = await self.repo.get_company_summary_latest(company_id)
                if summary:
                    raw = (
                        summary.get("shares_outstanding")
                        or summary.get("implied_shares_outstanding")
                    )
                    if raw:
                        shares = float(raw)
                        logger.info("[RI][%s] shares from company_summary: %s", symbol, shares)
            except Exception as e:
                logger.error("[RI][%s] company_summary fallback failed: %s", symbol, e)

        # ── Early abort: no shares ─────────────────────────────────────────────
        if shares is None or shares <= 0:
            logger.warning("[RI][%s] No shares available from any source, returning empty", symbol)
            n_default   = int(defaults.get("forecast_years_default", 5))
            k_e_default = float(defaults.get("k_default", 0.10))

            ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
                cost_of_equity=k_e_default,
            )
            abort_flags = flags + ri_flags
            abort_flags.append(DiagnosticFlag(
                code="RI-NO-SHARES", severity="critical",
                message="Shares outstanding unavailable from income_statements and company_summary.",
                recommendation="Trigger a financial data refresh for this company.",
            ))

            suitability_summary = None
            try:
                suitability_summary = await generate_suitability_summary(
                    symbol=symbol, method="residual_income",
                    score=int(ri_score), category=ri_category,
                    flags=[f.dict() for f in abort_flags], evidence=ri_evidence,
                    valuation_inputs={"currency": currency, "note": "Early abort — shares unavailable."},
                    input_decisions=input_decisions,
                )
            except Exception:
                pass

            _now_iso_ea = now_iso()

            # Bug 1 fix: early-abort path also has a fully defined resolved_inputs
            # so insert_valuation_run always receives a complete audit record.
            abort_resolved: dict[str, Any] = {
                "bv_per_share":     None,
                "eps0":             None,
                "k_e_final":        k_e_default,
                "k_e_source":       "default.k_default (early abort — shares unavailable)",
                "g_ri_final":       0.0,
                "g_ri_source":      "early_abort",
                "terminal_g_final": None,
                "forecast_years":   n_default,
                "resolved_at":      _now_iso_ea,
            }

            abort_valuation = ResidualIncomeValuation(
                symbol=symbol.upper(), companyId=company_id, currency=currency,
                forecastYears=n_default, costOfEquityUsed=k_e_default,
                currentPrice=current_price,
            )
            try:
                await self.repo.insert_valuation_run(
                    company_id=company_id,
                    method="residual_income",
                    run={
                        "run_by_user_id": user_id,
                        "input_snapshot": {
                            "overrides":              overrides.dict(),
                            "dependency_fingerprint": dependency_fingerprint,
                            "resolved":               abort_resolved,
                        },
                        "assumption_snapshot": defaults,
                        "output_snapshot": {
                            "valuation": abort_valuation.dict(),
                            "applicability": {
                                "score": int(ri_score), "category": ri_category,
                                "flags": [f.dict() for f in abort_flags],
                                "suitabilitySummary": suitability_summary,
                            },
                            "dataQuality": {
                                "freshnessDays": {"lastComputedAt": _now_iso_ea},
                                "fallbacksUsed": True,
                                "inputDecisions": input_decisions,
                            },
                            "earlyAbort": True, "lastComputedAt": _now_iso_ea,
                        },
                        "data_version_tag": None,
                        "notes": "early_abort:shares_not_available",
                    },
                )
            except Exception as e:
                logger.warning("[RI][%s] Failed to persist early-abort run: %s", symbol, e)

            return ResidualIncomeResponse(
                valuation=abort_valuation,
                applicability=Applicability(
                    score=int(ri_score), category=ri_category, flags=abort_flags,
                    suitabilitySummary=suitability_summary,
                ),
                dataQuality=DataQuality(
                    freshnessDays={"lastComputedAt": _now_iso_ea},
                    fallbacksUsed=True, inputDecisions=input_decisions,
                ),
            )

        equity = safe_float(bs_row.get("shareholders_equity")) if bs_row else None
        net_income = safe_float(
            (is_row or {}).get("net_income_to_common") or (is_row or {}).get("net_income")
        )
        bv_fy = (bs_row or {}).get("fiscal_year")

        # ── Early exit: negative or missing equity ─────────────────────────────

        if equity is None or equity <= 0:
            flags.append(DiagnosticFlag(
                code="RI-NEG-EQUITY", severity="critical",
                message=(
                    f"Shareholders' equity is "
                    f"{'missing' if equity is None else f'{equity:,.0f} (non-positive)'}. "
                    "RI model requires positive book equity as the valuation anchor."
                ),
                evidence={"equity": equity},
                recommendation=(
                    "Avoid RI model for companies with negative or zero book equity. "
                    "Use DCF or Owner Earnings instead."
                ),
            ))
            k_e_default = float(defaults.get("k_default", 0.10))
            ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
                cost_of_equity=k_e_default,
            )
            flags.extend(ri_flags)
            suitability_summary = await generate_suitability_summary(
                symbol=symbol, method="residual_income",
                score=int(ri_score), category=ri_category,
                flags=[f.dict() for f in flags], evidence=ri_evidence,
                valuation_inputs={"currency": currency, "equity": equity},
                input_decisions={"ri": input_decisions},
            )
            return ResidualIncomeResponse(
                valuation=ResidualIncomeValuation(
                    symbol=symbol.upper(), companyId=company_id, currency=currency,
                    forecastYears=int(defaults.get("forecast_years_default", 5)),
                    costOfEquityUsed=k_e_default,
                    currentPrice=current_price,
                ),
                applicability=Applicability(
                    score=int(ri_score), category=ri_category, flags=flags,
                    suitabilitySummary=suitability_summary,
                ),
                dataQuality=DataQuality(
                    freshnessDays={}, fallbacksUsed=True,
                    inputDecisions={"ri": input_decisions},
                ),
            )

        # ── Forecast years ─────────────────────────────────────────────────────

        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(clamp(float(overrides.forecastYears), 1, 20))
            input_decisions["ri"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["ri"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True

        # ── Cost of equity ─────────────────────────────────────────────────────

        k_e, k_evidence = await self._resolve_cost_of_equity(company_id, overrides, defaults)
        input_decisions["ri"]["costOfEquity"] = k_evidence
        if k_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="RI-K-CLAMP", severity="info",
                message="Cost of equity (k_e) was clamped to safety bounds.",
                evidence=k_evidence,
            ))

        # ── Base values ────────────────────────────────────────────────────────

        bv_per_share: float | None = None
        if equity is not None and shares is not None and float(shares) > 0:
            bv_per_share = float(equity) / float(shares)

        eps0: float | None = None
        if net_income is not None and shares is not None and float(shares) > 0:
            eps0 = float(net_income) / float(shares)

        roe0: float | None = None
        if net_income is not None and equity is not None and float(equity) > 0:
            roe0 = float(net_income) / float(equity)

        ri0_per_share: float | None = None
        if eps0 is not None and bv_per_share is not None:
            ri0_per_share = eps0 - k_e * bv_per_share
        elif roe0 is not None and bv_per_share is not None:
            ri0_per_share = bv_per_share * (roe0 - k_e)

        input_decisions["ri"]["baseValues"] = {
            "equity":      float(equity),
            "shares":      shares,
            "netIncome":   float(net_income) if net_income is not None else None,
            "bvPerShare":  bv_per_share,
            "eps0":        eps0,
            "roe0":        roe0,
            "ri0PerShare": ri0_per_share,
            "costOfEquity": k_e,
        }

        if ri0_per_share is None:
            flags.append(DiagnosticFlag(
                code="RI-NO-BASE", severity="critical",
                message="Cannot compute base RI per share (missing EPS or book value per share).",
                evidence=input_decisions["ri"]["baseValues"],
                recommendation="Ensure income_statements and balance_sheets are populated.",
            ))

        # ── RI growth rate ─────────────────────────────────────────────────────

        g_ri, g_evidence = await self._resolve_ri_growth(company_id, overrides, defaults, k_e)
        input_decisions["ri"]["riGrowthRate"] = g_evidence
        if g_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="RI-GROWTH-CLAMP", severity="info",
                message="RI growth rate was clamped to safety bounds.",
                evidence=g_evidence,
            ))

        # ── Terminal growth rate ───────────────────────────────────────────────

        tg_used: float | None = None
        tg_raw:  float | None = None

        if overrides.terminalGrowthRate is not None:
            tg_raw    = float(overrides.terminalGrowthRate)
            tg_source = "override.terminalGrowthRate"
        else:
            tg_raw    = safe_float(defaults.get("terminal_growth_default"))
            tg_source = "defaults.terminal_growth_default"
            if tg_raw is not None:
                fallbacks_used = True

        if tg_raw is not None:
            tg_used = pct_or_frac_to_frac(float(tg_raw))

        input_decisions["ri"]["terminalGrowthRate"] = {"source": tg_source, "value": tg_used}

        # ── Bug 1 fix: Build resolved_inputs BEFORE any DB write ──────────────
        #
        # Previously this dict was never constructed anywhere in this method,
        # causing a NameError at insert_valuation_run which re-raises, meaning
        # no valuation_runs row was ever written and the UI always saw None.
        #
        # Field names match _RI_NUMERIC_THRESHOLDS in recompute_guard.py and
        # the return value of resolve_current_inputs() in this service, so
        # Gate 3 comparisons are meaningful.
        resolved_inputs: dict[str, Any] = {
            "bv_per_share":     round(bv_per_share, 4) if bv_per_share is not None else None,
            "eps0":             round(eps0, 4)          if eps0         is not None else None,
            "k_e_final":        round(float(k_e), 4),
            "k_e_source":       k_evidence.get("source"),
            "g_ri_final":       round(float(g_ri), 4),
            "g_ri_source":      g_evidence.get("source"),
            "terminal_g_final": round(float(tg_used), 4) if tg_used is not None else None,
            "forecast_years":   int(n),
            "resolved_at":      now_iso(),
        }

        # ── Forecast RI per share ──────────────────────────────────────────────

        forecast_ri: list[float] = []
        if ri0_per_share is not None:
            forecast_ri = [
                float(ri0_per_share) * ((1.0 + g_ri) ** t)
                for t in range(1, n + 1)
            ]
        else:
            forecast_ri = [0.0] * n

        # ── Discount RI stream at k_e ──────────────────────────────────────────

        pv_ri: list[float] = []
        discount_factors: list[float] = []
        total_pv_ri = 0.0

        if k_e > 0:
            for t, ri_t in enumerate(forecast_ri, start=1):
                df = 1.0 / ((1.0 + k_e) ** t)
                pv = ri_t * df
                discount_factors.append(float(df))
                pv_ri.append(float(pv))
                total_pv_ri += float(pv)
        else:
            pv_ri            = [0.0] * n
            discount_factors = [0.0] * n

        # ── Terminal RI value ──────────────────────────────────────────────────

        terminal_ri_ps: float | None = None
        tv_ri:          float | None = None
        pv_tv_ri:       float | None = None

        if k_e > 0 and tg_used is not None:
            if tg_used >= k_e:
                flags.append(DiagnosticFlag(
                    code="RI-G-GE-K", severity="critical",
                    message="Terminal growth rate (g) must be less than cost of equity (k_e) for perpetuity formula.",
                    evidence={"g": tg_used, "ke": k_e},
                    recommendation="Lower terminal growth rate or raise cost of equity.",
                ))
            elif forecast_ri and float(forecast_ri[-1]) > 0:
                terminal_ri_ps = float(forecast_ri[-1]) * (1.0 + tg_used)
                tv_ri    = terminal_ri_ps / (k_e - tg_used)
                pv_tv_ri = tv_ri / ((1.0 + k_e) ** n)
            else:
                flags.append(DiagnosticFlag(
                    code="RI-TV-ZERO", severity="info",
                    message=(
                        "Terminal RI set to zero because RI_{n} ≤ 0 "
                        "(company not earning excess returns at end of forecast)."
                    ),
                    evidence={"riN": float(forecast_ri[-1]) if forecast_ri else None},
                    recommendation=(
                        "This is a conservative but valid choice. "
                        "Positive terminal RI requires RI_{n} > 0."
                    ),
                ))

        # ── Intrinsic value per share ──────────────────────────────────────────

        intrinsic_ps: float | None = None
        if bv_per_share is not None:
            intrinsic_ps = (
                float(bv_per_share)
                + float(total_pv_ri)
                + (float(pv_tv_ri) if pv_tv_ri is not None else 0.0)
            )

        # ── Upside (computed after intrinsic is final) ─────────────────────────

        upside: float | None = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        # ── Suitability scorecard ──────────────────────────────────────────────

        ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
            cost_of_equity=float(k_e), roe0=roe0,
        )
        flags.extend(ri_flags)

        # ── AI summary (called AFTER intrinsic and upside are finalised) ───────

        suitability_summary = await generate_suitability_summary(
            symbol=symbol,
            method="residual_income",
            score=int(ri_score),
            category=ri_category,
            flags=[f.dict() for f in flags],
            evidence=ri_evidence,
            valuation_inputs={
                "currency":               currency,
                "eps0":                   eps0,
                "bvPerShare":             bv_per_share,
                "roe0":                   roe0,
                "ri0PerShare":            ri0_per_share,
                "costOfEquityUsed":       float(k_e),
                "riGrowthRateUsed":       float(g_ri),
                "terminalGrowthRateUsed": tg_used,
                "forecastYears":          int(n),
                "intrinsicValuePerShare": float(intrinsic_ps) if intrinsic_ps is not None else None,
                "currentPrice":           current_price,
                "upsideDownsidePct":      upside,
            },
            input_decisions={"ri": input_decisions},
        )

        # ── Build valuation object ─────────────────────────────────────────────

        valuation = ResidualIncomeValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            forecastYears=int(n),
            costOfEquityUsed=float(k_e),
            betaUsed=k_evidence.get("beta"),
            rfUsed=k_evidence.get("rf"),
            erpUsed=k_evidence.get("erp"),
            riGrowthRateUsed=float(g_ri),
            terminalGrowthRateUsed=tg_used,
            eps0=eps0,
            bvPerShare=bv_per_share,
            roe0=roe0,
            ri0PerShare=ri0_per_share,
            bvFiscalYear=int(bv_fy) if isinstance(bv_fy, int) else None,
            forecastRiPerShare=[float(x) for x in forecast_ri],
            pvRiPerShare=[float(x) for x in pv_ri],
            discountFactors=[float(x) for x in discount_factors],
            totalPvRiPerShare=float(total_pv_ri),
            terminalRiPerShare=float(terminal_ri_ps) if terminal_ri_ps is not None else None,
            terminalValueRi=float(tv_ri) if tv_ri is not None else None,
            pvTerminalRiPerShare=float(pv_tv_ri) if pv_tv_ri is not None else None,
            intrinsicValuePerShare=float(intrinsic_ps) if intrinsic_ps is not None else None,
            currentPrice=current_price,
            upsideDownsidePct=upside,
        )

        # ── Audit run ──────────────────────────────────────────────────────────

        _now_iso = now_iso()
        output_snapshot: dict[str, Any] = {
            "valuation": valuation.dict(),
            "applicability": {
                "score":              ri_score,
                "category":           ri_category,
                "flags":              [f.dict() for f in flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays":  {"lastComputedAt": _now_iso},
                "fallbacksUsed":  bool(fallbacks_used),
                "inputDecisions": {"ri": input_decisions},
            },
            "suitabilityEvidence": ri_evidence,
            "lastComputedAt":      _now_iso,
        }

        # resolved_inputs is guaranteed defined above — NameError impossible.
        await self.repo.insert_valuation_run(
            company_id=company_id,
            method="residual_income",
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

        return ResidualIncomeResponse(
            valuation=valuation,
            applicability=Applicability(
                score=ri_score, category=ri_category, flags=flags,
                suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": _now_iso},
                fallbacksUsed=bool(fallbacks_used),
                inputDecisions={"ri": input_decisions},
            ),
        )

    # ── Cost of equity resolution ──────────────────────────────────────────────

    async def _resolve_cost_of_equity(
        self,
        company_id: int,
        overrides:  ResidualIncomeRequestOverrides,
        defaults:   dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        k_floor     = float(defaults.get("k_floor",    0.07))
        k_cap       = float(defaults.get("k_cap",      0.14))
        k_default   = float(defaults.get("k_default",  0.10))
        rf_default  = float(defaults.get("rf_default", 0.045))
        erp_default = float(defaults.get("erp_default", 0.055))

        if overrides.requiredReturn is not None:
            k_raw   = pct_or_frac_to_frac(float(overrides.requiredReturn))
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

        rf  = pct_or_frac_to_frac(float(overrides.riskFreeRate))      if overrides.riskFreeRate      is not None else rf_default
        erp = pct_or_frac_to_frac(float(overrides.equityRiskPremium)) if overrides.equityRiskPremium is not None else erp_default

        if beta is None:
            k_raw   = k_default
            k_final = clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "default.k_default (beta missing)",
                "beta": None, "rf": rf, "erp": erp,
                "kRaw": k_raw, "kFinal": k_final,
                "kFloor": k_floor, "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        k_raw   = rf + float(beta) * erp
        k_final = clamp(k_raw, k_floor, k_cap)
        return k_final, {
            "source": "capm",
            "beta": float(beta), "rf": rf, "erp": erp,
            "kRaw": k_raw, "kFinal": k_final,
            "kFloor": k_floor, "kCap": k_cap,
            "clamped": k_raw != k_final,
        }

    # ── RI growth rate resolution ──────────────────────────────────────────────

    async def _resolve_ri_growth(
        self,
        company_id: int,
        overrides:  ResidualIncomeRequestOverrides,
        defaults:   dict[str, Any],
        k_e:        float,
    ) -> tuple[float, dict[str, Any]]:
        """
        Resolve RI growth rate. Priority:
        1. Override.riGrowthRate
        2. EPS CAGR from history (proxy for RI growth)
        3. Defaults

        The growth rate is clamped so g < k_e (perpetuity stability requirement).
        """
        g_floor   = float(defaults.get("g_floor",    -0.05))
        g_cap     = float(defaults.get("g_cap",       0.15))
        g_default = float(defaults.get("g_default",   0.04))
        gap_to_k  = float(defaults.get("g_gap_to_k",  0.01))

        if overrides.riGrowthRate is not None:
            g_raw    = pct_or_frac_to_frac(float(overrides.riGrowthRate))
            g_stable = min(g_raw, max(g_floor, k_e - gap_to_k))
            g_final  = clamp(g_stable, g_floor, g_cap)
            return g_final, {
                "source": "override.riGrowthRate",
                "gRaw": g_raw, "gStable": g_stable, "gFinal": g_final,
                "gFloor": g_floor, "gCap": g_cap, "gapToK": gap_to_k, "ke": k_e,
                "clamped": g_final != g_raw,
            }

        g_hist: float | None = None
        try:
            eps_rows = await self.repo.get_eps_yearly_series(company_id)
            eps_pairs = sorted(
                [
                    (r["fiscal_year"], float(r["eps"]))
                    for r in eps_rows
                    if r.get("fiscal_year") and r.get("eps") is not None
                ],
                key=lambda t: t[0],
            )[-6:]
            if len(eps_pairs) >= 2:
                y0, v0 = eps_pairs[0]
                yN, vN = eps_pairs[-1]
                span = yN - y0
                if span > 0 and v0 > 0 and vN > 0:
                    g_hist = (vN / v0) ** (1.0 / span) - 1.0
        except Exception:
            g_hist = None

        if g_hist is not None:
            g_raw  = float(g_hist)
            source = "eps_cagr_approx"
        else:
            g_raw  = g_default
            source = "default.g_default"

        g_stable = min(g_raw, max(g_floor, k_e - gap_to_k))
        g_final  = clamp(g_stable, g_floor, g_cap)
        return g_final, {
            "source":    source,
            "gHistEps":  g_hist,
            "gRaw":      g_raw,
            "gStable":   g_stable,
            "gFinal":    g_final,
            "gFloor":    g_floor,
            "gCap":      g_cap,
            "gapToK":    gap_to_k,
            "ke":        k_e,
            "clamped":   g_final != g_raw,
        }
