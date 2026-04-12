# backend/application/services/canslim_service.py
"""
CANSlim Analysis Service (William O'Neil).

C — Current quarterly earnings (YoY, same quarter)
A — Annual EPS growth (3–5yr CAGR, each year positive)
N — New product / near 52-week high / revenue acceleration
S — Supply and demand (float size, volume trend)
L — Leader or laggard (RS vs benchmark, role='us_market')
I — Institutional sponsorship (unavailable — no 13F data)
M — Market direction (benchmark 50/200 SMA)

Cached in valuation_runs (method='canslim'), 24-hour staleness window.
L and M use live price data via the provider; other letters use DB data.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.models.analysis_canslim import (
    CANSlimDataQuality,
    CANSlimLetters,
    CANSlimMarketCondition,
    CANSlimResponse,
    DiagnosticFlag,
    LetterEvidence,
    LetterScore,
)
from infrastructure.repositories.analysis_repository import AnalysisRepository
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import safe_float

logger = logging.getLogger(__name__)

_CACHE_MAX_AGE_HOURS = 24
_FETCH_DAYS_BENCHMARK = 420   # enough for 200-day SMA

# O'Neil letter weights
_WEIGHTS = {"C": 0.20, "A": 0.20, "N": 0.10, "S": 0.15, "L": 0.15, "I": 0.10, "M": 0.10}


class CANSlimService:
    def __init__(
        self,
        valuation_repo: ValuationRepository,
        analysis_repo: AnalysisRepository,
        defeat_beta_provider: Any,
        yfinance_provider: Any,
    ) -> None:
        self._repo = valuation_repo
        self._arepo = analysis_repo
        self._dbeta = defeat_beta_provider
        self._yf = yfinance_provider

    # ── Public entry ──────────────────────────────────────────────────────────

    async def get_canslim(
        self, symbol: str, force: bool = False
    ) -> CANSlimResponse:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"

        if not force:
            cached = await self._serve_cached(company_id, symbol, currency)
            if cached:
                return cached

        return await self._compute_and_cache(symbol, company_id, currency)

    # ── Cache ─────────────────────────────────────────────────────────────────

    async def _serve_cached(
        self, company_id: int, symbol: str, currency: str
    ) -> Optional[CANSlimResponse]:
        snap = await self._repo.get_last_output_snapshot(company_id, "canslim")
        if not snap:
            return None
        last_computed = snap.get("lastComputedAt")
        if last_computed:
            try:
                ts = datetime.fromisoformat(last_computed.replace("Z", "+00:00"))
                age = datetime.utcnow().replace(tzinfo=ts.tzinfo) - ts
                if age > timedelta(hours=_CACHE_MAX_AGE_HOURS):
                    return None
            except Exception:
                return None
        try:
            return CANSlimResponse(**snap["response"])
        except Exception as e:
            logger.warning("CANSlim cache hydration failed: %s", e)
            return None

    # ── Full computation ──────────────────────────────────────────────────────

    async def _compute_and_cache(
        self, symbol: str, company_id: int, currency: str
    ) -> CANSlimResponse:
        now_iso = datetime.utcnow().isoformat() + "Z"

        # ── Parallel DB reads ──────────────────────────────────────────────────
        (
            q_earnings,
            annual_is,
            q_revenue,
            monthly_prices,
            shares_latest,
            ratios_latest,
        ) = await asyncio.gather(
            self._arepo.get_quarterly_earnings_series(company_id, limit=12),
            self._repo.get_income_statements_annual(company_id, limit=6),
            self._arepo.get_quarterly_revenue_series(company_id, limit=8),
            self._arepo.get_price_history_monthly(company_id, months=15),
            self._arepo.get_shares_outstanding_latest(company_id),
            self._repo.get_derived_metrics_latest(company_id),
        )

        # ── Benchmark resolution ───────────────────────────────────────────────
        benchmark = await self._arepo.get_benchmark("us_market")
        benchmark_symbol = benchmark["symbol"] if benchmark else "SPY"
        benchmark_company_id = benchmark["company_id"] if benchmark else None

        # ── Live benchmark price fetch ─────────────────────────────────────────
        benchmark_prices: List[Dict] = []
        if benchmark_company_id:
            start = date.today() - timedelta(days=_FETCH_DAYS_BENCHMARK)
            try:
                benchmark_prices = await self._dbeta.fetch_price_history(
                    benchmark_symbol, benchmark_company_id, start_date=start
                )
            except Exception as e:
                logger.warning("[CANSLIM] Benchmark price fetch failed: %s", e)
            if not benchmark_prices and self._yf:
                try:
                    import pandas as pd
                    df = await asyncio.to_thread(
                        self._yf.get_price_history_df, benchmark_symbol
                    )
                    if df is not None and not df.empty:
                        df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
                        df = df[df["price_date"] >= pd.Timestamp(start)]
                        benchmark_prices = [
                            {
                                "price_date": str(r["price_date"].date()),
                                "close_price": r.get("close_price"),
                                "volume": r.get("volume"),
                            }
                            for _, r in df.iterrows()
                            if r.get("close_price") is not None
                        ]
                except Exception as e:
                    logger.warning("[CANSLIM] YFinance benchmark fallback failed: %s", e)

        benchmark_prices = sorted(benchmark_prices, key=lambda b: str(b["price_date"]))
        bench_closes = [float(b["close_price"]) for b in benchmark_prices if b.get("close_price")]

        # ── Score each letter ──────────────────────────────────────────────────
        letter_C = self._score_C(q_earnings, q_revenue)
        letter_A = self._score_A(annual_is)
        letter_N = self._score_N(monthly_prices, q_revenue)
        letter_S = self._score_S(monthly_prices, shares_latest)
        letter_L = self._score_L(monthly_prices, bench_closes)
        letter_I = self._score_I()
        letter_M, market_condition = self._score_M(bench_closes, benchmark_symbol)

        letters = CANSlimLetters(
            C=letter_C, A=letter_A, N=letter_N, S=letter_S,
            L=letter_L, I=letter_I, M=letter_M,
        )

        # ── Composite score ────────────────────────────────────────────────────
        unavailable = [k for k, ls in letters.__dict__.items() if not ls.available]
        available_weight = sum(
            _WEIGHTS[k] for k, ls in letters.__dict__.items() if ls.available
        )
        # Confidence: penalty for unavailable letters proportional to their weight
        confidence = available_weight if available_weight < 1.0 else 1.0
        confidence_note = None
        if unavailable:
            confidence_note = (
                f"Letters {', '.join(unavailable)} could not be scored. "
                f"Composite confidence adjusted to {confidence:.0%}."
            )

        raw_score = 0.0
        for k, ls in letters.__dict__.items():
            if ls.available:
                raw_score += ls.score * _WEIGHTS[k]
        # Normalize to full 0-100 scale based on available weights
        composite = int(raw_score / available_weight) if available_weight > 0 else 0
        composite = max(0, min(100, composite))

        category = "Strong" if composite >= 70 else "Moderate" if composite >= 45 else "Weak"

        # ── Global flags ───────────────────────────────────────────────────────
        global_flags: List[DiagnosticFlag] = []
        if market_condition.condition in ("distribution", "downtrend"):
            global_flags.append(DiagnosticFlag(
                code="CS-MARKET-CAUTION",
                severity="high",
                message="Market is in distribution or downtrend — O'Neil advises against new purchases.",
                recommendation="Wait for a confirmed uptrend (Follow-Through Day) before acting.",
            ))
        if letter_C.score < 40 and letter_A.score < 40:
            global_flags.append(DiagnosticFlag(
                code="CS-WEAK-EARNINGS",
                severity="medium",
                message="Both C and A (the two highest-weight criteria) are weak.",
            ))

        dq = CANSlimDataQuality(
            letters_fully_scored=sum(1 for ls in letters.__dict__.values() if ls.available),
            letters_unavailable=unavailable,
            benchmark_role="us_market",
            benchmark_symbol=benchmark_symbol,
            confidence_adjustment=round(confidence, 3),
            confidence_note=confidence_note,
            last_computed_at=now_iso,
        )

        response = CANSlimResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            currency=currency,
            letters=letters,
            composite_score=composite,
            composite_category=category,
            market_condition=market_condition,
            flags=global_flags,
            data_quality=dq,
        )

        # ── Persist ────────────────────────────────────────────────────────────
        await self._repo.insert_valuation_run(
            company_id=company_id,
            method="canslim",
            run={
                "run_by_user_id": None,
                "input_snapshot": {"symbol": symbol, "benchmark": benchmark_symbol},
                "assumption_snapshot": {"weights": _WEIGHTS},
                "output_snapshot": {
                    "response": response.dict(),
                    "lastComputedAt": now_iso,
                },
                "data_version_tag": None,
                "notes": None,
            },
        )

        return response

    # ── C — Current quarterly earnings ────────────────────────────────────────

    def _score_C(
        self,
        q_earnings: List[Dict],
        q_revenue: List[Dict],
    ) -> LetterScore:
        """YoY same-quarter EPS comparison + revenue acceleration check."""
        if len(q_earnings) < 5:
            return self._unavailable_letter(
                "C",
                "Current quarterly earnings",
                "Fewer than 5 quarterly EPS rows available.",
            )

        # Build year/quarter index
        by_yq: Dict[Tuple[int, int], float] = {}
        for r in q_earnings:
            fy = r.get("fiscal_year")
            fq = r.get("fiscal_quarter")
            eps = safe_float(r.get("eps_reported_diluted"))
            if fy and fq and eps is not None:
                by_yq[(int(fy), int(fq))] = eps

        # Most recent quarter
        sorted_q = sorted(by_yq.keys(), reverse=True)
        if not sorted_q:
            return self._unavailable_letter("C", "Current quarterly earnings", "No EPS data found.")

        curr_y, curr_q = sorted_q[0]
        curr_eps = by_yq[(curr_y, curr_q)]
        prior_eps = by_yq.get((curr_y - 1, curr_q))

        if prior_eps is None:
            return self._unavailable_letter(
                "C", "Current quarterly earnings",
                "Prior year same-quarter EPS not available for YoY comparison.",
            )

        if prior_eps == 0:
            yoy_growth = 1.0 if curr_eps > 0 else -1.0
        else:
            yoy_growth = (curr_eps - prior_eps) / abs(prior_eps)

        # Growth acceleration: compare this Q's growth to prior Q's growth
        accel_note = ""
        if len(sorted_q) >= 2:
            prev_y, prev_q = sorted_q[1]
            prev_eps = by_yq.get((prev_y, prev_q))
            prev_prior = by_yq.get((prev_y - 1, prev_q))
            if prev_eps is not None and prev_prior is not None and prev_prior != 0:
                prev_growth = (prev_eps - prev_prior) / abs(prev_prior)
                if yoy_growth > prev_growth + 0.05:
                    accel_note = "Growth rate accelerating."
                elif yoy_growth < prev_growth - 0.05:
                    accel_note = "Growth rate decelerating — monitor."

        # Revenue YoY check
        rev_note = ""
        rev_by_yq: Dict[Tuple[int, int], float] = {}
        for r in q_revenue:
            fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
            rev = safe_float(r.get("revenue"))
            if fy and fq and rev:
                rev_by_yq[(int(fy), int(fq))] = rev

        curr_rev = rev_by_yq.get((curr_y, curr_q))
        prior_rev = rev_by_yq.get((curr_y - 1, curr_q))
        rev_growth: Optional[float] = None
        if curr_rev and prior_rev and prior_rev > 0:
            rev_growth = (curr_rev - prior_rev) / prior_rev
            if rev_growth >= 0.25:
                rev_note = f"Revenue also grew {rev_growth:.0%} YoY — confirms earnings quality."
            elif rev_growth < 0:
                rev_note = f"Revenue declined {rev_growth:.0%} YoY despite EPS growth — review quality."

        # Score
        if yoy_growth >= 0.50:
            score = 95
        elif yoy_growth >= 0.25:
            score = 80
        elif yoy_growth >= 0.15:
            score = 60
        elif yoy_growth >= 0.0:
            score = 35
        else:
            score = 10

        if accel_note.startswith("Growth rate accelerating"):
            score = min(100, score + 8)
        elif "Decelerating" in accel_note or "decelerating" in accel_note:
            score = max(0, score - 10)

        signal = "bullish" if score >= 60 else "bearish" if score < 35 else "neutral"
        headline = f"EPS grew {yoy_growth:+.0%} YoY (Q{curr_q} {curr_y} vs Q{curr_q} {curr_y-1})"
        if accel_note:
            headline += f". {accel_note}"
        if rev_note:
            headline += f" {rev_note}"

        return LetterScore(
            letter="C",
            name="Current quarterly earnings",
            score=score,
            weight=_WEIGHTS["C"],
            available=True,
            signal=signal,
            headline=headline,
            evidence=LetterEvidence(
                metrics={
                    "current_eps": round(curr_eps, 4),
                    "prior_year_eps": round(prior_eps, 4),
                    "yoy_growth_pct": round(yoy_growth * 100, 1),
                    "revenue_growth_pct": round(rev_growth * 100, 1) if rev_growth is not None else None,
                    "quarter": f"Q{curr_q} {curr_y}",
                },
                data_source="database",
            ),
        )

    # ── A — Annual earnings growth ────────────────────────────────────────────

    def _score_A(self, annual_is: List[Dict]) -> LetterScore:
        if len(annual_is) < 3:
            return self._unavailable_letter(
                "A", "Annual earnings growth",
                "Fewer than 3 years of annual income statement data.",
            )

        # Sort oldest-first
        rows = sorted(annual_is, key=lambda r: r.get("fiscal_year") or 0)

        eps_series: List[Tuple[int, float]] = []
        for r in rows:
            fy = r.get("fiscal_year")
            eps = safe_float(r.get("eps_diluted") or r.get("net_income_to_common"))
            if fy and eps is not None:
                eps_series.append((int(fy), eps))

        if len(eps_series) < 3:
            return self._unavailable_letter(
                "A", "Annual earnings growth",
                "Insufficient EPS data across annual rows.",
            )

        # 3-year and 5-year CAGR
        def _cagr(series: List[Tuple[int, float]], years: int) -> Optional[float]:
            if len(series) < years + 1:
                return None
            recent = series[-years - 1:]
            v0, vN = recent[0][1], recent[-1][1]
            n = recent[-1][0] - recent[0][0]
            if n <= 0 or v0 <= 0 or vN <= 0:
                return None
            try:
                return (vN / v0) ** (1.0 / n) - 1.0
            except Exception:
                return None

        cagr_3y = _cagr(eps_series, 3)
        cagr_5y = _cagr(eps_series, 5)
        primary_cagr = cagr_5y if cagr_5y is not None else cagr_3y

        # All years positive (last 3)
        last3 = [eps for _, eps in eps_series[-3:]]
        all_positive = all(e > 0 for e in last3)
        consecutive_growth = all(
            last3[i] > last3[i - 1] for i in range(1, len(last3))
        )

        if primary_cagr is None:
            score = 5
        elif primary_cagr >= 0.25 and all_positive:
            score = 95
        elif primary_cagr >= 0.25:
            score = 75
        elif primary_cagr >= 0.15 and all_positive:
            score = 65
        elif primary_cagr >= 0.15:
            score = 50
        elif primary_cagr >= 0.05:
            score = 35
        else:
            score = 10

        if consecutive_growth:
            score = min(100, score + 5)

        signal = "bullish" if score >= 60 else "bearish" if score < 35 else "neutral"
        cagr_display = f"{primary_cagr:.0%}" if primary_cagr is not None else "N/A"
        headline = f"{len(eps_series[-5:])}-year EPS CAGR: {cagr_display}. "
        headline += "All 3 recent years positive." if all_positive else "Some negative EPS years detected."

        return LetterScore(
            letter="A",
            name="Annual earnings growth",
            score=score,
            weight=_WEIGHTS["A"],
            available=True,
            signal=signal,
            headline=headline,
            evidence=LetterEvidence(
                metrics={
                    "cagr_3y_pct": round(cagr_3y * 100, 1) if cagr_3y else None,
                    "cagr_5y_pct": round(cagr_5y * 100, 1) if cagr_5y else None,
                    "all_positive_last_3y": all_positive,
                    "consecutive_growth": consecutive_growth,
                    "eps_series": [(y, round(e, 4)) for y, e in eps_series[-5:]],
                },
                data_source="database",
            ),
        )

    # ── N — New product / near 52-week high ───────────────────────────────────

    def _score_N(
        self, monthly_prices: List[Dict], q_revenue: List[Dict]
    ) -> LetterScore:
        if not monthly_prices:
            return self._unavailable_letter(
                "N", "Near 52-week high / something new",
                "No price history available.",
            )

        prices_sorted = sorted(monthly_prices, key=lambda b: str(b["price_date"]))
        closes = [float(b.get("close_price") or 0) for b in prices_sorted if b.get("close_price")]
        highs = [float(b.get("high_price") or b.get("close_price") or 0) for b in prices_sorted]

        if not closes:
            return self._unavailable_letter("N", "Near 52-week high / something new", "No close prices.")

        current = closes[-1]
        high_52w = max(highs[-13:]) if len(highs) >= 13 else max(highs)
        pct_from_high = (current - high_52w) / high_52w * 100 if high_52w else 0

        # Revenue acceleration (last 2 quarters vs prior 2 quarters)
        rev_accel = False
        rev_by_yq: Dict[Tuple[int, int], float] = {}
        for r in q_revenue:
            fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
            rev = safe_float(r.get("revenue"))
            if fy and fq and rev:
                rev_by_yq[(int(fy), int(fq))] = rev

        sorted_q = sorted(rev_by_yq.keys(), reverse=True)
        if len(sorted_q) >= 4:
            recent = [rev_by_yq.get((y, q), 0) for y, q in sorted_q[:2]]
            prior = [rev_by_yq.get((y, q), 0) for y, q in sorted_q[2:4]]
            if all(r > 0 for r in recent + prior):
                recent_avg = sum(recent) / 2
                prior_avg = sum(prior) / 2
                rev_accel = recent_avg > prior_avg * 1.10

        # Score
        if pct_from_high >= -5 and rev_accel:
            score = 90
        elif pct_from_high >= -5:
            score = 70
        elif pct_from_high >= -15 and rev_accel:
            score = 65
        elif pct_from_high >= -15:
            score = 50
        elif rev_accel:
            score = 35
        else:
            score = 20

        signal = "bullish" if score >= 60 else "neutral" if score >= 40 else "bearish"
        headline = (
            f"Price is {abs(pct_from_high):.1f}% {'below' if pct_from_high < 0 else 'at'} "
            f"52-week high (${high_52w:.2f})."
        )
        if rev_accel:
            headline += " Revenue accelerating — positive N signal."
        headline += " Note: 'new product/management' requires qualitative judgment."

        return LetterScore(
            letter="N",
            name="Near 52-week high / something new",
            score=score,
            weight=_WEIGHTS["N"],
            available=True,
            signal=signal,
            headline=headline,
            evidence=LetterEvidence(
                metrics={
                    "current_price": round(current, 2),
                    "high_52w": round(high_52w, 2),
                    "pct_from_52w_high": round(pct_from_high, 1),
                    "revenue_accelerating": rev_accel,
                },
                data_source="database",
            ),
            flags=["Qualitative 'new' catalyst (product/management) not automated."],
        )

    # ── S — Supply and demand ─────────────────────────────────────────────────

    def _score_S(
        self, monthly_prices: List[Dict], shares: Optional[float]
    ) -> LetterScore:
        prices_sorted = sorted(monthly_prices, key=lambda b: str(b["price_date"]))
        volumes = [int(b.get("volume") or 0) for b in prices_sorted]
        closes = [float(b.get("close_price") or 0) for b in prices_sorted if b.get("close_price")]

        score = 50   # start neutral

        # Float size signal
        float_flag = ""
        if shares is not None:
            if shares > 5e8:
                float_flag = f"Large float ({shares/1e6:.0f}M shares) — harder to move on institutional demand."
                score -= 10
            elif shares < 5e7:
                float_flag = f"Small float ({shares/1e6:.0f}M shares) — can move quickly on buying interest."
                score += 10

        # Volume trend: recent 3 months vs prior 9 months
        vol_signal = "neutral"
        if len(volumes) >= 12:
            recent_vol = sum(volumes[-3:]) / 3
            prior_vol = sum(volumes[-12:-3]) / 9
            if prior_vol > 0:
                vol_ratio = recent_vol / prior_vol
                if vol_ratio > 1.25:
                    vol_signal = "accumulation"
                    score += 15
                elif vol_ratio < 0.80:
                    vol_signal = "distribution"
                    score -= 15

        # Price/volume confirmation (rising price on rising volume = accumulation)
        if len(closes) >= 4 and len(volumes) >= 4:
            price_up = closes[-1] > closes[-4]
            vol_up = volumes[-1] > volumes[-4]
            if price_up and vol_up:
                score += 5
            elif not price_up and vol_up:
                score -= 5

        score = max(0, min(100, score))
        signal = "bullish" if score >= 65 else "bearish" if score < 35 else "neutral"

        headline = f"Volume signal: {vol_signal}."
        if float_flag:
            headline += f" {float_flag}"

        return LetterScore(
            letter="S",
            name="Supply and demand",
            score=score,
            weight=_WEIGHTS["S"],
            available=True,
            signal=signal,
            headline=headline,
            evidence=LetterEvidence(
                metrics={
                    "shares_outstanding": int(shares) if shares else None,
                    "float_category": (
                        "large" if shares and shares > 5e8
                        else "small" if shares and shares < 5e7
                        else "mid"
                    ) if shares else None,
                    "volume_signal": vol_signal,
                },
                data_source="database",
            ),
            flags=["Monthly price_history used for volume — daily bars provide higher resolution."],
        )

    # ── L — Leader or laggard ─────────────────────────────────────────────────

    def _score_L(
        self,
        monthly_prices: List[Dict],
        bench_closes: List[float],
    ) -> LetterScore:
        if not monthly_prices or len(bench_closes) < 13:
            return self._unavailable_letter(
                "L", "Leader or laggard (RS vs benchmark)",
                "Insufficient price history for stock or benchmark.",
            )

        prices_sorted = sorted(monthly_prices, key=lambda b: str(b["price_date"]))
        stock_closes = [
            float(b.get("close_price") or 0)
            for b in prices_sorted if b.get("close_price")
        ]

        if len(stock_closes) < 13:
            return self._unavailable_letter(
                "L", "Leader or laggard (RS vs benchmark)",
                "Less than 13 months of stock price history.",
            )

        # 12-month return (use monthly bars — 13th bar from the end is ~1yr ago)
        stock_return = (stock_closes[-1] - stock_closes[-13]) / stock_closes[-13]
        bench_return = (bench_closes[-1] - bench_closes[-13]) / bench_closes[-13]

        rs_ratio = stock_return / bench_return if bench_return != 0 else 1.0
        outperformance = stock_return - bench_return

        if outperformance >= 0.20:
            score = 95
        elif outperformance >= 0.10:
            score = 80
        elif outperformance >= 0.02:
            score = 65
        elif outperformance >= -0.05:
            score = 45
        elif outperformance >= -0.15:
            score = 25
        else:
            score = 10

        signal = "bullish" if score >= 60 else "bearish" if score < 35 else "neutral"
        headline = (
            f"12-month return: stock {stock_return:+.1%} vs benchmark {bench_return:+.1%}. "
            f"Outperformance: {outperformance:+.1%}. "
        )
        headline += (
            "Note: true O'Neil RS rank requires a full-universe percentile calculation."
        )

        return LetterScore(
            letter="L",
            name="Leader or laggard (RS vs benchmark)",
            score=score,
            weight=_WEIGHTS["L"],
            available=True,
            signal=signal,
            headline=headline,
            evidence=LetterEvidence(
                metrics={
                    "stock_12m_return_pct": round(stock_return * 100, 1),
                    "benchmark_12m_return_pct": round(bench_return * 100, 1),
                    "outperformance_pct": round(outperformance * 100, 1),
                    "rs_ratio": round(rs_ratio, 2),
                },
                data_source="live_fetch",
            ),
            flags=["RS ratio vs benchmark — full percentile rank unavailable without universe data."],
        )

    # ── I — Institutional sponsorship ─────────────────────────────────────────

    def _score_I(self) -> LetterScore:
        return LetterScore(
            letter="I",
            name="Institutional sponsorship",
            score=0,
            weight=_WEIGHTS["I"],
            available=False,
            signal="unavailable",
            headline="13F institutional holdings data not yet integrated.",
            evidence=LetterEvidence(
                metrics={},
                data_source="unavailable",
            ),
            flags=[
                "Requires 13F SEC EDGAR integration (edgartools). "
                "Scoring withheld — composite confidence adjusted accordingly."
            ],
        )

    # ── M — Market direction ──────────────────────────────────────────────────

    def _score_M(
        self, bench_closes: List[float], benchmark_symbol: str
    ) -> Tuple[LetterScore, CANSlimMarketCondition]:
        if len(bench_closes) < 51:
            condition = CANSlimMarketCondition(
                condition="unknown",
                spy_price=None,
                spy_sma50=None,
                spy_sma200=None,
                sma50_vs_200="unknown",
                sma200_slope="unknown",
                description="Insufficient benchmark data to classify market direction.",
            )
            return (
                self._unavailable_letter(
                    "M", "Market direction",
                    f"Fewer than 51 {benchmark_symbol} bars available.",
                ),
                condition,
            )

        price = bench_closes[-1]
        sma50 = sum(bench_closes[-50:]) / 50
        sma200 = sum(bench_closes[-200:]) / 200 if len(bench_closes) >= 200 else None

        # SMA200 slope (20-bar change)
        if len(bench_closes) >= 220:
            sma200_old = sum(bench_closes[-220:-20]) / 200
            sma200_slope = (
                "rising" if sma200 and sma200 > sma200_old * 1.005
                else "falling" if sma200 and sma200 < sma200_old * 0.995
                else "flat"
            )
        else:
            sma200_slope = "unknown"

        sma50_vs_200 = "unknown"
        if sma200:
            sma50_vs_200 = "above" if sma50 >= sma200 else "below"

        # Market condition classification
        if (
            sma200
            and price > sma200
            and sma50 >= sma200
            and sma200_slope == "rising"
        ):
            mkt_condition = "confirmed_uptrend"
            mkt_description = (
                f"{benchmark_symbol} above rising 200-day SMA with 50-day above 200-day — confirmed uptrend."
            )
            m_score = 90
        elif sma200 and price > sma200 and sma50 >= sma200:
            mkt_condition = "confirmed_uptrend"
            mkt_description = f"{benchmark_symbol} above 200-day SMA, 50-day above 200-day."
            m_score = 70
        elif sma200 and price > sma200 and sma50 < sma200:
            mkt_condition = "uptrend_pressure"
            mkt_description = f"{benchmark_symbol} above 200-day SMA but 50-day below — uptrend under pressure."
            m_score = 45
        elif sma200 and price < sma200 and sma50 < sma200 and sma200_slope == "falling":
            mkt_condition = "downtrend"
            mkt_description = f"{benchmark_symbol} below falling 200-day SMA — primary downtrend."
            m_score = 10
        elif sma200 and price < sma200:
            mkt_condition = "distribution"
            mkt_description = f"{benchmark_symbol} below 200-day SMA — distribution phase."
            m_score = 25
        else:
            mkt_condition = "uptrend_pressure"
            mkt_description = "Insufficient data for full market classification."
            m_score = 45

        signal = (
            "bullish" if m_score >= 60
            else "bearish" if m_score < 35
            else "neutral"
        )

        market_condition = CANSlimMarketCondition(
            condition=mkt_condition,
            spy_price=round(price, 2),
            spy_sma50=round(sma50, 2),
            spy_sma200=round(sma200, 2) if sma200 else None,
            sma50_vs_200=sma50_vs_200,
            sma200_slope=sma200_slope,
            description=mkt_description,
        )

        letter = LetterScore(
            letter="M",
            name="Market direction",
            score=m_score,
            weight=_WEIGHTS["M"],
            available=True,
            signal=signal,
            headline=mkt_description,
            evidence=LetterEvidence(
                metrics={
                    "benchmark": benchmark_symbol,
                    "price": round(price, 2),
                    "sma50": round(sma50, 2),
                    "sma200": round(sma200, 2) if sma200 else None,
                    "sma200_slope": sma200_slope,
                    "condition": mkt_condition,
                },
                data_source="live_fetch",
            ),
        )

        return letter, market_condition

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _unavailable_letter(
        letter: str, name: str, reason: str
    ) -> LetterScore:
        return LetterScore(
            letter=letter,
            name=name,
            score=0,
            weight=_WEIGHTS[letter],
            available=False,
            signal="unavailable",
            headline=reason,
            evidence=LetterEvidence(metrics={}, data_source="unavailable"),
            flags=[reason],
        )