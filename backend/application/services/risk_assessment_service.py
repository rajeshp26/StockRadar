from __future__ import annotations
import logging
import math
import statistics
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from domain.models.risk_assessment import (
    RiskAssessmentResponse,
    CompositeScore,
    BearCase,
    ScenarioResult,
    RiskMetric,
    RiskLayer,
    RiskDataQuality,
    RiskAiNarrative,
    BusinessFragility,
    BalanceSheetRisk,
    ValuationCompressionRisk,
    EarningsStressRisk,
    DrawdownRisk,
    CrisisDrawdown,
    LayerName,
    RiskCategory,
    RiskSeverity,
)
from application.services.moat_analysis_service import MoatAnalysisService
from application.services.moat_wacc_service import MoatWaccService
from infrastructure.repositories.risk_repository import RiskRepository
from shared.finance_math import safe_float, safe_div

logger = logging.getLogger(__name__)

_LAYER_WEIGHTS: Dict[LayerName, float] = {
    "business_fragility": 0.20,
    "balance_sheet": 0.25,
    "valuation_compression": 0.20,
    "earnings_stress": 0.25,
    "drawdown_risk": 0.10,
}

_SECTOR_RECURRENCE: Dict[str, str] = {
    "Technology": "High",
    "Healthcare": "High",
    "Consumer Defensive": "High",
    "Communication Services": "High",
    "Financial Services": "Medium",
    "Financials": "Medium",
    "Utilities": "High",
    "Real Estate": "Medium",
    "Industrials": "Medium",
    "Energy": "Low",
    "Basic Materials": "Low",
    "Consumer Cyclical": "Low",
}

_CRISIS_PERIODS: List[Dict[str, Any]] = [
    {"name": "COVID Crash", "start": date(2020, 2, 19), "end": date(2020, 3, 23)},
    {"name": "2022 Rate Hike", "start": date(2022, 1, 3), "end": date(2022, 10, 12)},
]


class RiskAssessmentService:
    def __init__(
        self,
        repo: RiskRepository,
        moat_service: MoatAnalysisService,
        wacc_service: MoatWaccService,
    ) -> None:
        self._repo = repo
        self._moat_service = moat_service
        self._wacc_service = wacc_service

    # ── Public API ─────────────────────────────────────────────────────────

    async def get_risk_assessment(
        self, symbol: str, force: bool = False
    ) -> RiskAssessmentResponse:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency", "USD")
        sector = ctx.get("sector", "")
        industry = ctx.get("industry", "")

        moat = None
        try:
            moat = await self._moat_service.get_moat_analysis(symbol, force=force)
        except Exception as e:
            logger.warning("Moat analysis failed for %s: %s", symbol, e)

        ratios = await self._repo.get_latest_financial_ratios(company_id)
        ratios_history = await self._repo.get_financial_ratios_history(company_id, years=5)
        prices = await self._repo.get_price_history_range(company_id, years=5)
        income = await self._repo.get_income_statements_annual(company_id, years=5)
        cash_flow = await self._repo.get_cash_flow_latest(company_id)
        current_price = await self._repo.get_current_market_price(company_id)
        if current_price is None and prices:
            sorted_prices = sorted(prices, key=lambda x: x.get("price_date", ""))
            close_vals = [safe_float(r.get("close_price")) for r in sorted_prices if safe_float(r.get("close_price")) is not None]
            if close_vals:
                current_price = close_vals[-1]

        layer1 = self._analyze_business_fragility(ctx, moat, ratios_history)
        layer2 = self._analyze_balance_sheet(ratios, cash_flow)
        layer3 = await self._analyze_valuation_compression(company_id)
        layer4 = self._analyze_earnings_stress(income)
        layer5 = self._analyze_drawdown_risk(prices, ctx)

        layers: Dict[LayerName, RiskLayer] = {
            "business_fragility": layer1,
            "balance_sheet": layer2,
            "valuation_compression": layer3,
            "earnings_stress": layer4,
            "drawdown_risk": layer5,
        }

        composite = self._compute_composite(layers)
        scenarios = self._compute_scenarios(income, current_price)
        composite.maximum_expected_loss_pct = self._compute_mel(scenarios)
        if scenarios:
            bear = next((s for s in scenarios if s.scenario == "bear"), None)
            if bear:
                composite.bear_case = BearCase(
                    eps_growth_assumption=bear.eps_growth,
                    exit_pe_ratio=bear.exit_pe,
                    future_value=bear.future_value,
                    current_price=current_price or 0.0,
                    downside_pct=bear.downside,
                )

        fallbacks = any(
            layer.metrics and all(m.status == "na" for m in layer.metrics)
            for layer in layers.values()
        )

        return RiskAssessmentResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            currency=currency,
            composite=composite,
            layers=layers,
            scenarios=scenarios,
            data_quality=RiskDataQuality(
                data_sources="financial_ratios + income_statements + company_summary + price_history",
                fiscal_year_end=None,
                fallbacks_used=fallbacks,
                last_computed_at=datetime.utcnow().isoformat() + "Z",
            ),
        )

    async def get_ai_narrative(self, symbol: str) -> RiskAiNarrative:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])
        cached = await self._repo.get_risk_ai_narrative(company_id)
        if cached:
            return RiskAiNarrative(
                narrative=cached.get("narrative", ""),
                model=cached.get("model", "openrouter/default"),
                generated_at=str(cached.get("generated_at", "")),
                generation_time_ms=cached.get("generation_time_ms"),
            )
        return RiskAiNarrative(
            narrative="AI summary not yet generated.",
            generated_at="",
        )

    async def generate_ai_narrative(
        self, symbol: str, assessment: RiskAssessmentResponse
    ) -> RiskAiNarrative:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        prompt = self._build_ai_prompt(assessment)
        narrative_text = await self._call_ai(prompt)
        start_ms = 0
        end_ms = 0

        if narrative_text:
            import time
            start_ms = int(time.time() * 1000)
            narrative_text = narrative_text
            end_ms = int(time.time() * 1000)

            payload = {
                "company_id": company_id,
                "symbol": symbol.upper(),
                "model": "openrouter/default",
                "narrative": narrative_text,
                "generation_time_ms": end_ms - start_ms,
            }
            await self._repo.upsert_risk_ai_narrative(company_id, payload)

            return RiskAiNarrative(
                narrative=narrative_text,
                model="openrouter/default",
                generated_at=datetime.utcnow().isoformat() + "Z",
                generation_time_ms=end_ms - start_ms,
            )

        return RiskAiNarrative(
            narrative="AI summary generation failed. Please try again later.",
        )

    # ── Layer 1: Business Fragility ────────────────────────────────────────

    def _analyze_business_fragility(
        self,
        ctx: Dict[str, Any],
        moat: Any,
        ratios_history: List[Dict[str, Any]],
    ) -> BusinessFragility:
        sector = ctx.get("sector", "")
        industry = ctx.get("industry", "")

        moat_score = moat.valuation.moat_score if moat and hasattr(moat, "valuation") else None
        moat_category = moat.valuation.moat_category if moat and hasattr(moat, "valuation") else None
        roic_spread = moat.valuation.roic_minus_wacc if moat and hasattr(moat, "valuation") else None

        recurrence = self._classify_recurrence(sector)
        pricing = self._assess_pricing_power(ratios_history)

        metrics = [
            RiskMetric(
                name="Moat Durability",
                value=moat_score,
                label=str(moat_category or "N/A"),
                status=self._moat_status(moat_category),
                weight=5,
            ),
            RiskMetric(
                name="Revenue Recurrence",
                label=recurrence,
                status=self._recurrence_status(recurrence),
                weight=3,
            ),
            RiskMetric(
                name="Pricing Power",
                label=pricing,
                status=self._pricing_status(pricing),
                weight=2,
            ),
        ]

        score = self._compute_layer_score(metrics, {"moat": 5, "recurrence": 3, "pricing": 2})
        return BusinessFragility(
            name="business_fragility",
            display_name="Business Fragility",
            score=score,
            category=self._score_to_severity(score),
            metrics=metrics,
            weight=_LAYER_WEIGHTS["business_fragility"],
            moat_score=moat_score,
            moat_category=moat_category,
            roic_minus_wacc=roic_spread,
            sector=sector,
            industry=industry,
            recurrence_classification=recurrence,
            pricing_power_assessment=pricing,
        )

    # ── Layer 2: Balance Sheet Risk ───────────────────────────────────────

    def _analyze_balance_sheet(
        self,
        ratios: Optional[Dict[str, Any]],
        cash_flow: Optional[Dict[str, Any]],
    ) -> BalanceSheetRisk:
        if not ratios:
            return BalanceSheetRisk(
                name="balance_sheet",
                display_name="Balance Sheet",
                score=0,
                category="severe",
                metrics=[RiskMetric(name="No Data", label="No Data", status="na", weight=1)],
                weight=_LAYER_WEIGHTS["balance_sheet"],
            )

        debt_ebitda = safe_float(ratios.get("debt_to_ebitda"))
        net_debt_ebitda = safe_float(ratios.get("net_debt_to_ebitda"))
        interest_cov = safe_float(ratios.get("interest_coverage"))
        current_ratio = safe_float(ratios.get("current_ratio"))
        quick_ratio = safe_float(ratios.get("quick_ratio"))
        debt_to_equity = safe_float(ratios.get("debt_to_equity"))
        fcf_conversion = safe_float(ratios.get("fcf_conversion"))

        fcf_stability = self._compute_fcf_stability(cash_flow)

        metrics = [
            RiskMetric(
                name="Debt/EBITDA",
                value=debt_ebitda,
                label=f"{debt_ebitda:.1f}x" if debt_ebitda is not None else "N/A",
                status=self._debt_ebitda_status(debt_ebitda),
                weight=4,
                threshold_description="< 2x pass, 2-4x caution, > 4x fail",
            ),
            RiskMetric(
                name="Interest Coverage",
                value=interest_cov,
                label=f"{interest_cov:.1f}x" if interest_cov is not None else "N/A",
                status=self._interest_coverage_status(interest_cov),
                weight=3,
            ),
            RiskMetric(
                name="Current Ratio",
                value=current_ratio,
                label=f"{current_ratio:.2f}" if current_ratio is not None else "N/A",
                status=self._ratio_status(current_ratio, 1.5, 1.0),
                weight=2,
            ),
            RiskMetric(
                name="Debt-to-Equity",
                value=debt_to_equity,
                label=f"{debt_to_equity:.2f}" if debt_to_equity is not None else "N/A",
                status=self._de_ratio_status(debt_to_equity),
                weight=2,
            ),
            RiskMetric(
                name="FCF Stability",
                value=fcf_stability,
                label=f"{fcf_stability:.0%}" if fcf_stability is not None else "N/A",
                status=self._fcf_stability_status(fcf_stability),
                weight=2,
            ),
        ]

        score = self._compute_layer_score(metrics, {})

        return BalanceSheetRisk(
            name="balance_sheet",
            display_name="Balance Sheet",
            score=score,
            category=self._score_to_severity(score),
            metrics=metrics,
            weight=_LAYER_WEIGHTS["balance_sheet"],
            debt_to_ebitda=debt_ebitda,
            net_debt_to_ebitda=net_debt_ebitda,
            interest_coverage=interest_cov,
            current_ratio=current_ratio,
            quick_ratio=quick_ratio,
            debt_to_equity=debt_to_equity,
            fcf_conversion=fcf_conversion,
            fcf_stability_pct=fcf_stability,
        )

    # ── Layer 3: Valuation Compression ────────────────────────────────────

    async def _analyze_valuation_compression(
        self,
        company_id: int,
    ) -> ValuationCompressionRisk:
        history = await self._repo.get_company_summary_history(company_id, years=5)

        if not history or len(history) < 2:
            latest = history[-1] if history else {}
            pe = safe_float(latest.get("trailing_pe"))
            ev_ebitda = safe_float(latest.get("enterprise_to_ebitda"))
            peg = safe_float(latest.get("peg_ratio"))

            metrics = [
                RiskMetric(name="P/E (5y)", value=pe, label=f"{pe:.1f}" if pe else "N/A", status="na", weight=3),
                RiskMetric(name="EV/EBITDA", value=ev_ebitda, label=f"{ev_ebitda:.1f}" if ev_ebitda else "N/A", status="na", weight=3),
            ]
            return ValuationCompressionRisk(
                name="valuation_compression",
                display_name="Valuation Compression",
                score=5.0,
                category="moderate",
                metrics=metrics,
                weight=_LAYER_WEIGHTS["valuation_compression"],
                pe_percentile=50.0,
                ev_ebitda_percentile=50.0,
            )

        pe_values = [safe_float(r.get("trailing_pe")) for r in history if safe_float(r.get("trailing_pe")) is not None]
        ev_ebitda_values = [safe_float(r.get("enterprise_to_ebitda")) for r in history if safe_float(r.get("enterprise_to_ebitda")) is not None]

        current_pe = pe_values[-1] if pe_values else None
        current_ev_ebitda = ev_ebitda_values[-1] if ev_ebitda_values else None
        peg = safe_float(history[-1].get("peg_ratio")) if history else None

        pe_percentile = self._compute_percentile(current_pe, pe_values) if pe_values else 50.0
        ev_ebitda_percentile = self._compute_percentile(current_ev_ebitda, ev_ebitda_values) if ev_ebitda_values else 50.0

        pe_min = min(pe_values) if pe_values else None
        pe_max = max(pe_values) if pe_values else None
        pe_median = statistics.median(pe_values) if len(pe_values) > 1 else (pe_values[0] if pe_values else None)

        metrics = [
            RiskMetric(
                name="P/E Percentile (5y)",
                value=pe_percentile,
                label=f"{pe_percentile:.0f}th" if pe_percentile is not None else "N/A",
                status=self._percentile_status(pe_percentile),
                weight=3,
            ),
            RiskMetric(
                name="EV/EBITDA Percentile",
                value=ev_ebitda_percentile,
                label=f"{ev_ebitda_percentile:.0f}th" if ev_ebitda_percentile is not None else "N/A",
                status=self._percentile_status(ev_ebitda_percentile),
                weight=3,
            ),
            RiskMetric(
                name="PEG Ratio",
                value=peg,
                label=f"{peg:.2f}" if peg is not None else "N/A",
                status=self._peg_status(peg),
                weight=2,
            ),
        ]

        score = self._compute_layer_score(metrics, {})

        return ValuationCompressionRisk(
            name="valuation_compression",
            display_name="Valuation Compression",
            score=score,
            category=self._score_to_severity(score),
            metrics=metrics,
            weight=_LAYER_WEIGHTS["valuation_compression"],
            pe_current=current_pe,
            pe_percentile=pe_percentile,
            pe_5y_min=pe_min,
            pe_5y_max=pe_max,
            pe_5y_median=pe_median,
            ev_ebitda_current=current_ev_ebitda,
            ev_ebitda_percentile=ev_ebitda_percentile,
            peg_ratio=peg,
        )

    # ── Layer 4: Earnings / Cash Flow Stress ──────────────────────────────

    def _analyze_earnings_stress(
        self,
        income_statements: List[Dict[str, Any]],
    ) -> EarningsStressRisk:
        if not income_statements or len(income_statements) < 2:
            return EarningsStressRisk(
                name="earnings_stress",
                display_name="Earnings Stress",
                score=5.0,
                category="moderate",
                metrics=[RiskMetric(name="No Data", label="No Data", status="na", weight=1)],
                weight=_LAYER_WEIGHTS["earnings_stress"],
            )

        sorted_is = sorted(income_statements, key=lambda x: x.get("fiscal_year", 0))

        eps_values = [safe_float(r.get("eps_diluted")) for r in sorted_is if safe_float(r.get("eps_diluted")) is not None]
        revenue_values = [safe_float(r.get("revenue")) for r in sorted_is if safe_float(r.get("revenue")) is not None]
        net_income_values = [safe_float(r.get("net_income")) for r in sorted_is if safe_float(r.get("net_income")) is not None]

        eps_cagr_5y = self._compute_cagr(eps_values) if len(eps_values) >= 2 else None
        eps_cagr_3y = self._compute_cagr(eps_values[-3:]) if len(eps_values) >= 3 else eps_cagr_5y
        rev_cagr_5y = self._compute_cagr(revenue_values) if len(revenue_values) >= 2 else None
        rev_cagr_3y = self._compute_cagr(revenue_values[-3:]) if len(revenue_values) >= 3 else rev_cagr_5y

        latest = sorted_is[-1]
        net_margin_current = safe_float(latest.get("net_margin")) or safe_div(
            safe_float(latest.get("net_income")), safe_float(latest.get("revenue"))
        )

        margin_trend = self._compute_margin_trend(sorted_is)
        eps_vol = self._compute_eps_volatility(eps_values)
        alignment = self._compute_revenue_eps_alignment(eps_values, revenue_values)

        metrics = [
            RiskMetric(
                name="EPS CAGR (5y)",
                value=eps_cagr_5y,
                label=f"{eps_cagr_5y:.1%}" if eps_cagr_5y is not None else "N/A",
                status=self._cagr_status(eps_cagr_5y),
                weight=3,
            ),
            RiskMetric(
                name="Revenue CAGR (5y)",
                value=rev_cagr_5y,
                label=f"{rev_cagr_5y:.1%}" if rev_cagr_5y is not None else "N/A",
                status=self._cagr_status(rev_cagr_5y),
                weight=2,
            ),
            RiskMetric(
                name="Net Margin",
                value=net_margin_current,
                label=f"{net_margin_current:.1%}" if net_margin_current is not None else "N/A",
                status=self._margin_status(net_margin_current),
                weight=2,
            ),
            RiskMetric(
                name="Margin Trend",
                label=margin_trend,
                status=self._margin_trend_status(margin_trend),
                weight=2,
            ),
            RiskMetric(
                name="EPS Stability",
                label=alignment,
                status=self._alignment_status(alignment),
                weight=2,
            ),
        ]

        score = self._compute_layer_score(metrics, {})

        return EarningsStressRisk(
            name="earnings_stress",
            display_name="Earnings Stress",
            score=score,
            category=self._score_to_severity(score),
            metrics=metrics,
            weight=_LAYER_WEIGHTS["earnings_stress"],
            eps_cagr_3y=eps_cagr_3y,
            eps_cagr_5y=eps_cagr_5y,
            revenue_cagr_3y=rev_cagr_3y,
            revenue_cagr_5y=rev_cagr_5y,
            net_margin_current=net_margin_current,
            operating_margin_trend=margin_trend,
            revenue_eps_alignment=alignment,
            eps_volatility=eps_vol,
        )

    # ── Layer 5: Drawdown Risk ────────────────────────────────────────────

    def _analyze_drawdown_risk(
        self,
        prices: List[Dict[str, Any]],
        ctx: Dict[str, Any],
    ) -> DrawdownRisk:
        if not prices or len(prices) < 2:
            return DrawdownRisk(
                name="drawdown_risk",
                display_name="Drawdown Risk",
                score=5.0,
                category="moderate",
                metrics=[RiskMetric(name="No Data", label="No Data", status="na", weight=1)],
                weight=_LAYER_WEIGHTS["drawdown_risk"],
            )

        sorted_prices = sorted(prices, key=lambda x: x.get("price_date", ""))
        close_values = [safe_float(r.get("close_price")) for r in sorted_prices if safe_float(r.get("close_price")) is not None]

        if len(close_values) < 2:
            return DrawdownRisk(
                name="drawdown_risk",
                display_name="Drawdown Risk",
                score=5.0,
                category="moderate",
                metrics=[RiskMetric(name="No Data", label="No Data", status="na", weight=1)],
                weight=_LAYER_WEIGHTS["drawdown_risk"],
            )

        price_dates = [r.get("price_date", "") for r in sorted_prices if safe_float(r.get("close_price")) is not None]

        max_dd_5y = self._compute_max_drawdown(close_values)
        max_dd_3y = self._compute_max_drawdown(close_values[-max(3, len(close_values) // 3 * 3):]) if len(close_values) > 3 else None
        max_dd_1y = self._compute_max_drawdown(close_values[-max(1, len(close_values) // 5):]) if len(close_values) > 1 else None

        current_price = close_values[-1]
        peak_price = max(close_values)
        current_drawdown = (current_price - peak_price) / peak_price if peak_price > 0 else 0.0

        beta_5y = safe_float(ctx.get("beta"))

        crisis_drawdowns = self._compute_crisis_drawdowns(close_values, price_dates)
        recovery_days = self._compute_recovery_time(close_values)

        metrics = [
            RiskMetric(
                name="Max Drawdown (5y)",
                value=max_dd_5y,
                label=f"{max_dd_5y:.1%}" if max_dd_5y is not None else "N/A",
                status=self._drawdown_status(max_dd_5y),
                weight=3,
            ),
            RiskMetric(
                name="Beta (5y)",
                value=beta_5y,
                label=f"{beta_5y:.2f}" if beta_5y is not None else "N/A",
                status=self._beta_status(beta_5y),
                weight=2,
            ),
            RiskMetric(
                name="Current Drawdown",
                value=current_drawdown,
                label=f"{current_drawdown:.1%}" if current_drawdown is not None else "N/A",
                status=self._drawdown_status(current_drawdown),
                weight=2,
            ),
            RiskMetric(
                name="Recovery Time",
                value=float(recovery_days) if recovery_days else None,
                label=f"{recovery_days}d" if recovery_days else "N/A",
                status="pass" if recovery_days and recovery_days < 365 else "caution" if recovery_days else "na",
                weight=1,
            ),
        ]

        score = self._compute_layer_score(metrics, {})

        return DrawdownRisk(
            name="drawdown_risk",
            display_name="Drawdown Risk",
            score=score,
            category=self._score_to_severity(score),
            metrics=metrics,
            weight=_LAYER_WEIGHTS["drawdown_risk"],
            max_drawdown_1y=max_dd_1y,
            max_drawdown_3y=max_dd_3y,
            max_drawdown_5y=max_dd_5y,
            beta_5y=beta_5y,
            current_drawdown=current_drawdown,
            crisis_drawdowns=crisis_drawdowns,
            recovery_time_days=recovery_days,
        )

    # ── Composite Scoring ─────────────────────────────────────────────────

    def _compute_composite(self, layers: Dict[LayerName, RiskLayer]) -> CompositeScore:
        total = 0.0
        weight_sum = 0.0

        for layer in layers.values():
            w = _LAYER_WEIGHTS.get(layer.name, 0.20)
            total += layer.score * w
            weight_sum += w

        if weight_sum > 0:
            composite_10 = total / weight_sum
        else:
            composite_10 = 5.0

        composite_100 = composite_10 * 10.0
        category = self._composite_category(composite_100)

        return CompositeScore(
            score=round(composite_100, 1),
            category=category,
            maximum_expected_loss_pct=0.0,
            bear_case=BearCase(
                eps_growth_assumption=0.0,
                exit_pe_ratio=0.0,
                future_value=0.0,
                current_price=0.0,
                downside_pct=0.0,
            ),
        )

    def _compute_scenarios(
        self,
        income_statements: List[Dict[str, Any]],
        current_price: Optional[float],
    ) -> Optional[List[ScenarioResult]]:
        if not income_statements or current_price is None:
            return None

        sorted_is = sorted(income_statements, key=lambda x: x.get("fiscal_year", 0))
        eps_values = [safe_float(r.get("eps_diluted")) for r in sorted_is if safe_float(r.get("eps_diluted")) is not None]

        if not eps_values or not eps_values[-1]:
            return None

        current_eps = eps_values[-1]
        eps_cagr = self._compute_cagr(eps_values) or 0.08
        years = 5

        scenarios: List[Dict[str, Any]] = [
            {"name": "bull", "eps_growth": max(eps_cagr * 1.8, 0.10), "exit_pe": 28, "probability": 0.25},
            {"name": "base", "eps_growth": max(eps_cagr, 0.05), "exit_pe": 22, "probability": 0.50},
            {"name": "bear", "eps_growth": max(eps_cagr * 0.3, 0.02), "exit_pe": 15, "probability": 0.20},
            {"name": "severe", "eps_growth": 0.0, "exit_pe": 12, "probability": 0.05},
        ]

        results = []
        for sc in scenarios:
            future_eps = current_eps * ((1.0 + sc["eps_growth"]) ** years)
            future_value = future_eps * sc["exit_pe"]
            total_return = (future_value / current_price) - 1.0
            downside = min(0.0, total_return)

            results.append(ScenarioResult(
                scenario=sc["name"],
                probability=sc["probability"],
                eps_growth=sc["eps_growth"],
                exit_pe=sc["exit_pe"],
                future_eps=round(future_eps, 2),
                future_value=round(future_value, 2),
                total_return=round(total_return, 4),
                downside=round(downside, 4),
            ))

        return results

    def _compute_mel(self, scenarios: Optional[List[ScenarioResult]]) -> float:
        if not scenarios:
            return 0.0
        weighted_loss = sum(
            s.probability * abs(s.downside) for s in scenarios if s.downside < 0
        )
        return round(weighted_loss * 100, 1)

    # ── AI Narrative ──────────────────────────────────────────────────────

    def _build_ai_prompt(self, assessment: RiskAssessmentResponse) -> str:
        layers_summary = []
        for layer in assessment.layers.values():
            metrics_str = "; ".join(
                f"{m.name}: {m.label} ({m.status})" for m in layer.metrics[:4]
            )
            layers_summary.append(f"{layer.display_name} ({layer.score:.1f}/10, {layer.category}): {metrics_str}")

        return (
            f"Provide a concise risk assessment summary for {assessment.symbol}. "
            f"Composite Score: {assessment.composite.score}/100 ({assessment.composite.category}). "
            f"Maximum Expected Loss: {assessment.composite.maximum_expected_loss_pct:.1f}%. "
            f"Layer breakdown:\n" + "\n".join(layers_summary) +
            f"\nBear case downside: {assessment.composite.bear_case.downside_pct:.1%}. "
            "Highlight the key risk factors and whether the company's risk profile is favorable. "
            "Keep the response to 2-3 paragraphs."
        )

    async def _call_ai(self, prompt: str) -> Optional[str]:
        try:
            from config import settings
            key = settings.OPEN_ROUTER_KEY or ""
            if not key:
                logger.info("OPEN_ROUTER_KEY not set — AI narrative disabled")
                return None

            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a financial risk analyst. Provide concise, specific risk assessments.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                logger.error("OpenRouter API error: %s %s", resp.status_code, resp.text)
                return None
        except ImportError:
            logger.warning("httpx not installed; AI narrative disabled")
            return None
        except Exception as e:
            logger.error("AI narrative call failed: %s", e)
            return None

    # ── Internal Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _classify_recurrence(sector: str) -> str:
        return _SECTOR_RECURRENCE.get(sector, "Medium")

    @staticmethod
    def _assess_pricing_power(ratios_history: List[Dict[str, Any]]) -> str:
        valid = [r for r in ratios_history if safe_float(r.get("gross_margin")) is not None]
        if len(valid) < 2:
            return "Unknown"
        margins = [safe_float(r["gross_margin"]) for r in valid]
        avg = sum(margins) / len(margins)
        if avg > 0.50:
            return "Strong"
        if avg > 0.30:
            return "Moderate"
        return "Weak"

    @staticmethod
    def _compute_fcf_stability(cash_flow: Optional[Dict[str, Any]]) -> Optional[float]:
        if not cash_flow:
            return None
        ocf = safe_float(cash_flow.get("cash_from_operating_activities"))
        capex = safe_float(cash_flow.get("capital_expenditures"))
        ni = safe_float(cash_flow.get("net_income"))
        if ocf is not None and ni is not None and ni != 0:
            return abs(ocf / ni)
        return None

    @staticmethod
    def _compute_cagr(values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None
        n = len(values) - 1
        start = values[0]
        end = values[-1]
        if start <= 0 or end <= 0:
            return None
        return (end / start) ** (1.0 / n) - 1.0

    @staticmethod
    def _compute_max_drawdown(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def _compute_crisis_drawdowns(
        close_values: List[float],
        price_dates: List[str],
    ) -> Optional[List[CrisisDrawdown]]:
        if len(close_values) != len(price_dates) or not close_values:
            return None

        results = []
        for crisis in _CRISIS_PERIODS:
            try:
                indices = [
                    i for i, d in enumerate(price_dates)
                    if crisis["start"].isoformat() <= d[:10] <= crisis["end"].isoformat()
                ]
                if len(indices) < 2:
                    continue
                window = [close_values[i] for i in indices]
                start_val = window[0]
                end_val = window[-1]
                max_dd = 0.0
                peak = window[0]
                for v in window:
                    if v > peak:
                        peak = v
                    dd = (v - peak) / peak
                    if dd < max_dd:
                        max_dd = dd

                results.append(CrisisDrawdown(
                    crisis_name=crisis["name"],
                    start_date=crisis["start"],
                    end_date=crisis["end"],
                    max_drawdown=round(max_dd, 4),
                    start_value=start_val,
                    end_value=end_val,
                ))
            except Exception:
                continue
        return results if results else None

    @staticmethod
    def _compute_recovery_time(close_values: List[float]) -> Optional[int]:
        if len(close_values) < 2:
            return None

        trough_idx = 0
        trough_val = close_values[0]
        for i, v in enumerate(close_values):
            if v < trough_val:
                trough_val = v
                trough_idx = i

        if trough_idx == 0:
            return None

        peak_val = close_values[0]
        for i in range(trough_idx):
            if close_values[i] > peak_val:
                peak_val = close_values[i]

        if peak_val <= trough_val:
            return None

        for i in range(trough_idx, len(close_values)):
            if close_values[i] >= peak_val:
                return i - trough_idx
        return len(close_values) - trough_idx

    @staticmethod
    def _compute_percentile(value: Optional[float], values: List[float]) -> float:
        if value is None or not values:
            return 50.0
        sorted_vals = sorted(values)
        count = len(sorted_vals)
        if count < 2:
            return 50.0
        below = sum(1 for v in sorted_vals if v <= value)
        return (below / count) * 100.0

    @staticmethod
    def _compute_margin_trend(income_statements: List[Dict[str, Any]]) -> str:
        margins = []
        for r in income_statements:
            ni = safe_float(r.get("net_income"))
            rev = safe_float(r.get("revenue"))
            margin = safe_div(ni, rev)
            if margin is not None:
                margins.append(margin)
        if len(margins) < 2:
            return "stable"
        recent = margins[-3:] if len(margins) >= 3 else margins
        first_half = recent[:len(recent)//2]
        second_half = recent[len(recent)//2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        if avg_second > avg_first * 1.05:
            return "expanding"
        if avg_second < avg_first * 0.95:
            return "contracting"
        return "stable"

    @staticmethod
    def _compute_eps_volatility(eps_values: List[float]) -> Optional[float]:
        if len(eps_values) < 2:
            return None
        growth_rates = []
        for i in range(1, len(eps_values)):
            if eps_values[i-1] > 0:
                g = (eps_values[i] - eps_values[i-1]) / abs(eps_values[i-1])
                growth_rates.append(g)
        if not growth_rates:
            return None
        return statistics.stdev(growth_rates) if len(growth_rates) > 1 else growth_rates[0]

    @staticmethod
    def _compute_revenue_eps_alignment(
        eps_values: List[float],
        revenue_values: List[float],
    ) -> str:
        if len(eps_values) < 3 or len(revenue_values) < 3:
            return "volatile"
        eps_cagr = None
        rev_cagr = None
        try:
            if eps_values[0] > 0 and eps_values[-1] > 0:
                eps_cagr = (eps_values[-1] / eps_values[0]) ** (1.0 / (len(eps_values) - 1)) - 1.0
            if revenue_values[0] > 0 and revenue_values[-1] > 0:
                rev_cagr = (revenue_values[-1] / revenue_values[0]) ** (1.0 / (len(revenue_values) - 1)) - 1.0
        except Exception:
            return "volatile"
        if eps_cagr is None or rev_cagr is None:
            return "volatile"
        ratio = abs(eps_cagr / rev_cagr) if rev_cagr != 0 else 0
        if 0.5 <= ratio <= 2.0:
            return "aligned"
        if ratio > 2.0:
            return "diverging"
        return "volatile"

    @staticmethod
    def _compute_layer_score(
        metrics: List[RiskMetric],
        weights: Dict[str, float],
    ) -> float:
        total = 0.0
        max_possible = 0.0
        for m in metrics:
            if m.status == "na":
                continue
            w = weights.get(m.name.lower().replace(" ", "_"), m.weight)
            if m.status == "pass":
                total += 10.0 * w
            elif m.status == "caution":
                total += 5.0 * w
            elif m.status == "fail":
                total += 1.0 * w
            max_possible += 10.0 * w

        if max_possible == 0:
            return 5.0
        raw = (total / max_possible) * 10.0
        return round(max(0.0, min(10.0, raw)), 1)

    @staticmethod
    def _score_to_severity(score: float) -> RiskSeverity:
        if score >= 9.0:
            return "low"
        if score >= 7.0:
            return "moderate"
        if score >= 5.0:
            return "elevated"
        if score >= 3.0:
            return "high"
        return "severe"

    @staticmethod
    def _composite_category(score: float) -> RiskCategory:
        if score >= 80:
            return "Very Low Downside"
        if score >= 60:
            return "Moderate"
        if score >= 40:
            return "Elevated"
        return "High Risk"

    # ── Status Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _moat_status(category: Optional[str]) -> str:
        if not category:
            return "na"
        if category in ("Wide", "Narrow"):
            return "pass"
        return "caution"

    @staticmethod
    def _recurrence_status(recurrence: str) -> str:
        if recurrence == "High":
            return "pass"
        if recurrence == "Medium":
            return "caution"
        return "fail"

    @staticmethod
    def _pricing_status(pricing: str) -> str:
        if pricing == "Strong":
            return "pass"
        if pricing == "Moderate":
            return "caution"
        return "fail"

    @staticmethod
    def _debt_ebitda_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value < 2.0:
            return "pass"
        if value < 4.0:
            return "caution"
        return "fail"

    @staticmethod
    def _interest_coverage_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value >= 10.0:
            return "pass"
        if value >= 5.0:
            return "caution"
        return "fail"

    @staticmethod
    def _ratio_status(value: Optional[float], pass_thresh: float, fail_thresh: float) -> str:
        if value is None:
            return "na"
        if value >= pass_thresh:
            return "pass"
        if value >= fail_thresh:
            return "caution"
        return "fail"

    @staticmethod
    def _de_ratio_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value < 1.0:
            return "pass"
        if value < 2.5:
            return "caution"
        return "fail"

    @staticmethod
    def _fcf_stability_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value >= 0.8:
            return "pass"
        if value >= 0.5:
            return "caution"
        return "fail"

    @staticmethod
    def _percentile_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value < 40:
            return "pass"
        if value < 70:
            return "caution"
        return "fail"

    @staticmethod
    def _peg_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value < 1.5:
            return "pass"
        if value < 3.0:
            return "caution"
        return "fail"

    @staticmethod
    def _cagr_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value >= 0.10:
            return "pass"
        if value >= 0.03:
            return "caution"
        return "fail"

    @staticmethod
    def _margin_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value >= 0.15:
            return "pass"
        if value >= 0.05:
            return "caution"
        return "fail"

    @staticmethod
    def _margin_trend_status(trend: str) -> str:
        if trend == "expanding":
            return "pass"
        if trend == "stable":
            return "caution"
        return "fail"

    @staticmethod
    def _alignment_status(alignment: str) -> str:
        if alignment == "aligned":
            return "pass"
        if alignment == "diverging":
            return "caution"
        return "fail"

    @staticmethod
    def _drawdown_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        v = abs(value)
        if v < 0.15:
            return "pass"
        if v < 0.30:
            return "caution"
        return "fail"

    @staticmethod
    def _beta_status(value: Optional[float]) -> str:
        if value is None:
            return "na"
        if value < 1.2:
            return "pass"
        if value < 1.5:
            return "caution"
        return "fail"
