# backend/application/services/ai_service.py
"""
AI service — generates plain-English suitability summaries via Gemini REST API.

Fixes applied (2026-03-05):
  1. thinkingConfig moved INSIDE generationConfig (was a sibling key — silently
     ignored by Gemini, causing thinking tokens to consume the entire output budget)
  2. systemInstruction added as a separate field so the model weights formatting
     rules more heavily than the data context
  3. Branch A (broken formula) example now uses neutral "XYZ Corp" placeholder,
     not a hardcoded ticker
  4. _prompt_ddm: broken-formula branch for DDM-NO-DIV and g>=k cases
  5. _prompt_dcf: broken-formula branch for DCF-NO-FORECAST, DCF-GE-WACC,
     negative base FCF, and missing per-share bridge
  6. All metric display blocks filter to available (non-None) values only —
     no N/A fields are shown to the model, eliminating N/A starvation
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={key}"
)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_suitability_summary(
    symbol:           str,
    method:           str,
    score:            int,
    category:         str,
    flags:            List[dict],
    evidence:         Optional[Dict[str, Any]] = None,
    valuation_inputs: Optional[Dict[str, Any]] = None,
    input_decisions:  Optional[Dict[str, Any]] = None,
    timeout:          float = 8.0,
) -> Optional[str]:
    """
    Generate a plain-English suitability summary via Gemini REST.
    Returns None (never raises) if key missing, call fails, or times out.
    """
    key = settings.GEMINI_API_KEY or ""
    if not key:
        logger.info("[AI] GEMINI_API_KEY not set — suitability summaries disabled")
        return None

    model = settings.GEMINI_MODEL
    url   = _GEMINI_URL.format(model=model, key=key)

    prompt = _build_prompt(
        symbol, method, score, category, flags,
        evidence or {}, valuation_inputs or {}, input_decisions or {},
    )

    logger.info(
        "[AI] Sending prompt for %s/%s (%d chars):\n--- PROMPT START ---\n%s\n--- PROMPT END ---",
        symbol, method, len(prompt), prompt,
    )

    system_instruction = (
        "You are a financial analysis assistant writing plain-English summaries "
        "for retail investors. You always complete every sentence fully. "
        "You never use bullet points, headers, or labels. "
        "You only reference metric values that are explicitly provided — never invent numbers."
    )

    body = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 600,
            "temperature":     0.1,
            "topP":            0.85,
            # thinkingConfig MUST be inside generationConfig for gemini-2.5-flash.
            # As a top-level sibling key it is silently ignored and thinking tokens
            # consume the entire output budget, leaving ~0 tokens for the response.
            "thinkingConfig": {
                "thinkingBudget": 0,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body)
            if not resp.is_success:
                logger.warning(
                    "[AI] Gemini %s for %s/%s | body: %s",
                    resp.status_code, symbol, method, resp.text[:500],
                )
                return None
            data = resp.json()
            candidate = data.get("candidates", [{}])[0]
            finish    = candidate.get("finishReason", "UNKNOWN")
            usage     = data.get("usageMetadata", {})
            summary = (
                candidate
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
            )
            if summary:
                logger.info(
                    "[AI] %s/%s: %d chars | finishReason=%s | prompt=%s out=%s thinking=%s\n"
                    "--- AI OUTPUT START ---\n%s\n--- AI OUTPUT END ---",
                    symbol, method, len(summary), finish,
                    usage.get("promptTokenCount"),
                    usage.get("candidatesTokenCount"),
                    usage.get("thoughtsTokenCount"),
                    summary,
                )
            else:
                logger.warning(
                    "[AI] Empty response %s/%s | finishReason=%s | usage=%s | raw=%s",
                    symbol, method, finish, usage, str(data)[:300],
                )
            return summary or None
    except httpx.TimeoutException:
        logger.warning("[AI] Suitability summary timed out for %s/%s", symbol, method)
        return None
    except Exception as exc:
        logger.warning("[AI] Suitability summary failed for %s/%s: %s", symbol, method, exc)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(val: Any, as_pct: bool = False, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if as_pct:
            return f"{f * 100:.{decimals}f}%"
        return f"{f:.{decimals}f}"
    except Exception:
        return str(val)


def _critical_flags(flags: List[dict]) -> List[dict]:
    skip = {"-SCORECARD", "-DATA-COVERAGE", "-REPO-KEYS"}
    return [
        f for f in flags
        if f.get("severity") in ("critical", "high")
        and not any(f.get("code", "").endswith(s) for s in skip)
    ]


def _input_source_summary(input_decisions: Dict[str, Any], method: str) -> str:
    lines = []

    if method == "rule1":
        eps = input_decisions.get("eps0", {})
        if eps:
            lines.append(f"EPS₀: value={_fmt(eps.get('value'))}, source={eps.get('source','?')}, "
                         f"snapshotDate={eps.get('snapshotDate','?')}")

        g = input_decisions.get("growth", {})
        if g:
            lines.append(f"Growth: raw={_fmt(g.get('valueRaw'), as_pct=True)}, "
                         f"clamped={_fmt(g.get('valueClamped'), as_pct=True)}, "
                         f"source={g.get('source','?')}")

        pe = input_decisions.get("futurePE", {})
        if pe:
            lines.append(f"Future PE: selected={_fmt(pe.get('selected'))}, rule={pe.get('rule','?')}")

        assum = input_decisions.get("assumptions", {})
        if assum:
            lines.append(f"Assumptions: discountRate={_fmt(assum.get('discountRate'), as_pct=True)}, "
                         f"horizonYears={assum.get('horizonYears','?')}, "
                         f"MOS={_fmt(assum.get('mos'), as_pct=True)}")

    elif method in ("ddm_gordon", "ddm_two_stage"):
        ddm = input_decisions.get("ddm", input_decisions)
        lines.append(f"D₀ source: {ddm.get('d0Source','?')}")

        k_ev = ddm.get("requiredReturn", {})
        if k_ev:
            lines.append(f"k (required return): source={k_ev.get('source','?')}, "
                         f"raw={_fmt(k_ev.get('kRaw'), as_pct=True)}, "
                         f"final={_fmt(k_ev.get('kFinal'), as_pct=True)}, "
                         f"beta={_fmt(k_ev.get('beta'))}, "
                         f"rf={_fmt(k_ev.get('rf'), as_pct=True)}, "
                         f"erp={_fmt(k_ev.get('erp'), as_pct=True)}, "
                         f"clamped={k_ev.get('clamped', False)}")

        g_ev = ddm.get("dividendGrowthRate", {})
        if g_ev:
            lines.append(f"g (div growth): source={g_ev.get('source','?')}, "
                         f"gHist={_fmt(g_ev.get('gHist'), as_pct=True)}, "
                         f"gSgr={_fmt(g_ev.get('gSgr'), as_pct=True)}, "
                         f"raw={_fmt(g_ev.get('gRaw'), as_pct=True)}, "
                         f"final={_fmt(g_ev.get('gFinal'), as_pct=True)}, "
                         f"clamped={g_ev.get('clamped', False)}")

    elif method == "dcf":
        dcf = input_decisions.get("dcf", input_decisions)

        bf = dcf.get("baseFcf", {})
        if bf:
            lines.append(f"Base FCF: OCF={_fmt(bf.get('cashFromOperatingActivities'))}, "
                         f"capex={_fmt(bf.get('capitalExpenditures'))}, "
                         f"FCF={_fmt(bf.get('computedFcf'))}, "
                         f"fiscalYear={bf.get('asOfFiscalYear','?')}")

        gr = dcf.get("fcfGrowthRate", {})
        if gr:
            lines.append(f"FCF growth: source={gr.get('source','?')}, "
                         f"raw={_fmt(gr.get('valueRaw'), as_pct=True)}, "
                         f"final={_fmt(gr.get('valueFinal'), as_pct=True)}")

        w = dcf.get("wacc", {})
        if w:
            lines.append(f"WACC: source={w.get('source','?')}, "
                         f"raw={_fmt(w.get('valueRaw'), as_pct=True)}, "
                         f"final={_fmt(w.get('valueFinal'), as_pct=True)}, "
                         f"clamped={w.get('clamped', False)} "
                         f"(floor={_fmt(w.get('waccFloor'), as_pct=True)}, "
                         f"cap={_fmt(w.get('waccCap'), as_pct=True)})")

        t = dcf.get("terminal", {})
        if t:
            if t.get("method") == "perpetuity_growth":
                lines.append(f"Terminal: perpetuity_growth, "
                             f"g={_fmt(t.get('gFinal'), as_pct=True)} (source={t.get('source','?')}), "
                             f"CF(n+1)={_fmt(t.get('cfNPlus1'))}, valid={t.get('valid','?')}")
            else:
                lines.append(f"Terminal: exit_multiple, "
                             f"multiple={_fmt(t.get('exitMultiple'))}x, "
                             f"terminalEBITDA={_fmt(t.get('terminalEbitda'))}")

        nd = dcf.get("netDebt", {})
        if nd:
            lines.append(f"Net debt: source={nd.get('source','?')}, value={_fmt(nd.get('value'))}")

        sh = dcf.get("sharesOutstanding", {})
        if sh:
            lines.append(f"Shares: source={sh.get('source','?')}, value={_fmt(sh.get('value'))}")

    return "\n".join(f"  {l}" for l in lines) if lines else "  (not available)"
    

# ── Prompt router ─────────────────────────────────────────────────────────────

def _build_prompt(
    symbol:           str,
    method:           str,
    score:            int,
    category:         str,
    flags:            List[dict],
    evidence:         Dict[str, Any],
    valuation_inputs: Dict[str, Any],
    input_decisions:  Dict[str, Any],
) -> str:
    if method == "rule1":
        return _prompt_rule1(symbol, score, category, flags, evidence, valuation_inputs, input_decisions)
    elif method in ("ddm_gordon", "ddm_two_stage"):
        return _prompt_ddm(symbol, method, score, category, flags, evidence, valuation_inputs, input_decisions)
    elif method == "dcf":
        return _prompt_dcf(symbol, score, category, flags, evidence, valuation_inputs, input_decisions)
    elif method == "owner_earnings":
        return _prompt_owner_earnings(symbol, score, category, flags, evidence, valuation_inputs, input_decisions)
    elif method == "residual_income":
        return _prompt_residual_income(symbol, score, category, flags, evidence, valuation_inputs, input_decisions)
    elif method == "magic_formula":
        return _prompt_magic_formula(symbol, score, category, flags, evidence, valuation_inputs)
    elif method == "canslim":
        return _prompt_canslim(symbol, score, category, flags, evidence)
    else:
        return _prompt_generic(symbol, method, score, category, flags)


# ── Rule #1 prompt ────────────────────────────────────────────────────────────

def _prompt_rule1(symbol, score, category, flags, ev, vi, id_) -> str:
    fs    = ev.get("final_scoring", {})
    points = fs.get("points", "N/A")
    total  = fs.get("totalPossible", "N/A")
    hfail  = fs.get("hardFail", False)

    eps_cagr = ev.get("growth_eps_cagr", {}).get("cagr")
    rev_cagr = ev.get("growth_revenue_cagr", {}).get("cagr")
    ni_ev    = ev.get("eps_quality_positive_net_income_years", {})
    eps_vol  = ev.get("eps_quality_volatility", {}).get("volatility")
    drawdown = ev.get("cyclicality_eps_drawdown_5y")
    dte      = ev.get("balance_debt_to_equity")
    int_cov  = ev.get("balance_interest_coverage")
    fcf_conv = ev.get("cashflow_fcf_conversion", {}).get("fcfConversion")
    dilution = ev.get("cashflow_share_dilution_cagr")
    roic     = ev.get("compounding_roic_avg_5y")

    currency = vi.get("currency", "USD")
    eps0     = vi.get("eps0")
    growth   = vi.get("growth")
    fpe      = vi.get("futurePE")
    sticker  = vi.get("stickerPrice")
    mos_p    = vi.get("mosPrice")
    dr       = vi.get("discountRate")
    horizon  = vi.get("horizonYears")
    mos      = vi.get("mos")
    feps     = vi.get("futureEPS")
    fprice   = vi.get("futurePrice")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}" for f in crit[:4]) or "  None"
    id_trace  = _input_source_summary(id_, "rule1")

    # ── Detect broken/sparse conditions ───────────────────────────────────
    eps_negative   = eps0 is not None and float(eps0) < 0
    formula_broken = eps_negative or (sticker is not None and float(sticker) == 0.0 and eps_negative)

    metric_vals = [eps_cagr, rev_cagr, ni_ev.get("positive"), eps_vol, drawdown,
                   dte, int_cov, fcf_conv, dilution, roic]
    available  = sum(1 for v in metric_vals if v is not None)
    na_count   = len(metric_vals) - available
    data_sparse = na_count >= 6

    g_raw     = id_.get("growth", {}).get("valueRaw")
    g_clamped = id_.get("growth", {}).get("valueClamped")
    growth_clamped_positive = (
        g_raw is not None and g_clamped is not None
        and float(g_raw) < 0 and float(g_clamped) > 0
    )
    clamp_note = ""
    if growth_clamped_positive:
        clamp_note = (
            f"\nNOTE: Raw growth was {_fmt(g_raw, as_pct=True)} (negative) but was clamped to "
            f"{_fmt(g_clamped, as_pct=True)} by the system floor. This floor does NOT fix the "
            f"negative EPS problem — growing a negative EPS at any positive rate still yields "
            f"a negative future value."
        )

    gaps = [k for k, v in ev.get("data_coverage", {}).items()
            if isinstance(v, dict) and v.get("availableYears", 99) < v.get("requiredYears", 0)]
    gaps_text = ", ".join(gaps) or "None"

    # Build available-only metrics block
    mlines = []
    if rev_cagr is not None: mlines.append(f"Revenue CAGR (5y): {_fmt(rev_cagr, as_pct=True)} [pass: ≥5%]")
    if eps_cagr is not None: mlines.append(f"EPS CAGR (5y): {_fmt(eps_cagr, as_pct=True)} [pass: ≥8%]")
    if ni_ev.get("positive") is not None:
        mlines.append(f"Positive NI years: {ni_ev.get('positive')} of {ni_ev.get('total')} [pass: ≥80%]")
    if eps_vol  is not None: mlines.append(f"EPS volatility: {_fmt(eps_vol, as_pct=True)} [pass: <30%]")
    if drawdown is not None: mlines.append(f"EPS drawdown (5y): {_fmt(drawdown, as_pct=True)} [pass: <30%]")
    if dte      is not None: mlines.append(f"Debt/Equity: {_fmt(dte)} [pass: <0.8]")
    if int_cov  is not None: mlines.append(f"Interest coverage: {_fmt(int_cov)}x [pass: >5x]")
    if fcf_conv is not None: mlines.append(f"FCF conversion: {_fmt(fcf_conv, as_pct=True)} [pass: ≥70%]")
    if dilution is not None: mlines.append(f"Share dilution CAGR: {_fmt(dilution, as_pct=True)} [pass: ≤0%]")
    if roic     is not None: mlines.append(f"ROIC (5y avg): {_fmt(roic, as_pct=True)} [pass: ≥15%]")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (no metrics computable — insufficient history)"

    # ══════════════════════════════════════════════════════════════════════
    # BRANCH A — Negative EPS / broken formula
    # ══════════════════════════════════════════════════════════════════════
    if formula_broken:
        example = (
            '"XYZ Corp scores 9/100 (Poor) and is fundamentally unsuitable for Rule #1 because '
            'the formula requires a positive, growing earnings base — XYZ has never reported '
            'positive net income in 5 years (0 of 5) and carries a trailing EPS of -$1.60, '
            'meaning Future EPS = EPS₀ × (1+g)^n stays at or below zero regardless of the '
            'growth rate applied, and both Sticker Price and MOS Price resolve to $0.00. '
            'The system clamped a raw growth estimate of -2.0% up to 2.0%, but this floor is '
            'cosmetic — growing a negative number at any positive rate still yields a negative '
            'future value, so the clamp does not rescue the valuation. '
            'The balance sheet deepens the concern: debt/equity of 8.2x and interest coverage '
            'of -22.5x indicate the company is both unprofitable and financially over-levered. '
            'An investor should not use this output; the right action is to monitor whether XYZ '
            'achieves sustained positive net income before revisiting Rule #1."'
        )
        return f"""Analyse this Rule #1 suitability for {symbol.upper()}. The formula cannot produce a valid result because EPS is negative.
Do NOT describe the sticker/MOS price as meaningful values — they are $0 because the math breaks down.
Instead explain WHY the formula fails and what the evidence reveals about financial health.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== FORMULA BREAKDOWN ===
EPS₀ = {_fmt(eps0)} {currency} ← NEGATIVE: Future EPS = EPS₀ × (1+g)^n ≤ 0 regardless of g
Growth input: raw={_fmt(g_raw, as_pct=True)}, clamped to={_fmt(g_clamped, as_pct=True)}{clamp_note}
Result: Sticker={_fmt(sticker)} {currency}, MOS Price={_fmt(mos_p)} {currency} — both meaningless

=== AVAILABLE METRIC EVIDENCE ({available} of {len(metric_vals)} computable) ===
{metrics_block}

=== DATA GAPS ===
{gaps_text}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why the Rule #1 formula fails with negative EPS, (2) what the available metrics say about financial health, (3) what an investor should do instead."""

    # ══════════════════════════════════════════════════════════════════════
    # BRANCH B — Formula valid but data sparse
    # ══════════════════════════════════════════════════════════════════════
    if data_sparse:
        example = (
            '"ACME scores 45/100 (Caution) with only 4 of 10 metrics computable due to limited '
            'financial history, which reduces confidence in this Rule #1 assessment. '
            'Of the available metrics, revenue CAGR of 12.3% clears the 5% threshold and '
            'debt/equity of 0.6x is safely below 0.8x, but interest coverage of 2.1x falls '
            'below the 5x minimum and triggers a hard fail on balance sheet safety. '
            'The growth input of 8% was sourced from an analyst earnings forecast because '
            'insufficient EPS history exists — this is a lower-confidence assumption than '
            'the formula ideally requires. '
            'Until at least 5 years of EPS, ROIC, and FCF data are available, the sticker '
            'price of $34.20 should be treated as preliminary."'
        )
        return f"""Analyse this Rule #1 suitability for {symbol.upper()}. Most metrics are N/A due to limited history.
Write a summary that is honest about what IS known and frames the data gaps as a confidence issue.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== AVAILABLE METRIC EVIDENCE ({available} of {len(metric_vals)} computable) ===
{metrics_block}

=== DATA GAPS ({na_count} metrics not computable) ===
{gaps_text}

=== FORMULA INPUTS ===
EPS₀={_fmt(eps0)} {currency}, g={_fmt(growth, as_pct=True)}, Future PE={_fmt(fpe)}
n={horizon} yrs, discount={_fmt(dr, as_pct=True)}, MOS={_fmt(mos, as_pct=True)}
→ Sticker={_fmt(sticker)} {currency}, MOS Price={_fmt(mos_p)} {currency}{clamp_note}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Explicitly mention how many metrics were computable and how that affects confidence in the sticker price."""

    # ══════════════════════════════════════════════════════════════════════
    # BRANCH C — Formula valid, data rich
    # ══════════════════════════════════════════════════════════════════════
    example = (
        '"ACME scores 33/100 (Poor) primarily because EPS CAGR of -4.2% is negative and only '
        '3 of 5 years had positive net income, triggering a hard fail that makes Rule #1 '
        'unsuitable regardless of other metrics. '
        'The 8% growth input came from a revenue CAGR approximation rather than earnings '
        'history, and the future PE of 15x was set by the industry median rule — both '
        'inputs are low-confidence fallbacks rather than company-specific data. '
        'Applying the formula produces a sticker of $18.40 and MOS price of $9.20, but '
        'these are unreliable because the compounding assumption breaks down when base '
        'earnings are inconsistent. '
        'Before trusting this valuation, confirm that ACME has returned to sustained '
        'profitability and that at least 5 years of positive EPS history is available."'
    )
    return f"""Analyse this Rule #1 suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== FORMULA ===
Future EPS = EPS₀ × (1+g)^n | Future Price = Future EPS × PE
Sticker = Future Price / (1+r)^n | MOS Price = Sticker × (1 - MOS%)

=== AVAILABLE METRICS ({available} of {len(metric_vals)} computable) ===
{metrics_block}

=== FORMULA INPUTS ===
EPS₀={_fmt(eps0)} {currency}, g={_fmt(growth, as_pct=True)}, Future PE={_fmt(fpe)}
n={horizon} yrs, discount={_fmt(dr, as_pct=True)}, MOS={_fmt(mos, as_pct=True)}
→ Future EPS={_fmt(feps)} {currency}, Future Price={_fmt(fprice)} {currency}
→ Sticker={_fmt(sticker)} {currency}, MOS Price={_fmt(mos_p)} {currency}{clamp_note}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + the 1-2 biggest metric failures with actual values.
Sentence 2: Input reliability — were growth and PE from good sources or fallbacks?
Sentence 3: What the formula produces and whether sticker/MOS are trustworthy.
Sentence 4: What an investor must verify before trusting this valuation."""


# ── DDM prompt ────────────────────────────────────────────────────────────────

def _prompt_ddm(symbol, method, score, category, flags, ev, vi, id_) -> str:
    fs          = ev.get("final_scoring", {})
    passes      = fs.get("passes", "N/A")
    total       = fs.get("totalPossible", "N/A")
    hfail       = fs.get("hardFail", False)
    recommended = fs.get("recommendedModel", "N/A")
    model_label = "Gordon Growth" if method == "ddm_gordon" else "Two-Stage"

    div_ev      = ev.get("m1_dividend_paid_years_10y", {})
    div_vol     = ev.get("m2_dividend_volatility_10y", {}).get("volatility")
    payout_eps  = ev.get("m3_earnings_payout_ratio")
    payout_fcf  = ev.get("m4_fcf_payout_ratio")
    nd_ebitda   = ev.get("m5_net_debt_to_ebitda")
    int_cov     = ev.get("m6_interest_coverage")
    div_cagr    = ev.get("m7_dividend_cagr")

    currency  = vi.get("currency", "USD")
    d0        = vi.get("currentDps")
    d1        = vi.get("nextYearDps")
    g         = vi.get("dividendGrowthRate")
    k         = vi.get("requiredReturn")
    intrinsic = vi.get("intrinsicValue")
    upside    = vi.get("upsideDownsidePct")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}" for f in crit[:4]) or "  None"
    id_trace  = _input_source_summary(id_, method)

    # Detect broken formula
    has_no_div = any(f.get("code") == "DDM-NO-DIV" for f in flags)
    has_g_ge_k = (
        any(f.get("code") == "DDM-GE-K" for f in flags)
        or (g is not None and k is not None and float(g) >= float(k) and method == "ddm_gordon")
    )
    formula_broken = has_no_div or has_g_ge_k

    # Normalise payout ratios (may be fraction or percentage)
    def _payout(v):
        if v is None: return "N/A"
        f = float(v)
        return f"{f:.1f}%" if f > 1.0 else f"{f*100:.1f}%"

    # Available-only metrics block
    mlines = []
    paid = div_ev.get("paidYears")
    tot  = div_ev.get("totalYears")
    if paid  is not None: mlines.append(f"Dividend history (10y): {paid} of {tot} years paid [pass: ≥8]")
    if div_vol   is not None: mlines.append(f"Dividend volatility: {_fmt(div_vol, as_pct=True)} [pass: <25%]")
    if div_cagr  is not None: mlines.append(f"Dividend CAGR: {_fmt(div_cagr, as_pct=True)} [pass: 3–10%]")
    if payout_eps is not None: mlines.append(f"Earnings payout ratio: {_payout(payout_eps)} [pass: 25–70%]")
    if payout_fcf is not None: mlines.append(f"FCF payout ratio: {_payout(payout_fcf)} [pass: <70%]")
    if nd_ebitda is not None: mlines.append(f"Net Debt / EBITDA: {_fmt(nd_ebitda)}x [pass: <3x]")
    if int_cov   is not None: mlines.append(f"Interest coverage: {_fmt(int_cov)}x [pass: >4x]")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    # ── BRANCH A: Formula invalid ──────────────────────────────────────────
    if formula_broken:
        if has_no_div:
            reason    = "the company pays no dividends — DDM has no inputs"
            breakdown = "DDM requires a dividend stream to discount. Without dividends there is no D₀, D₁, or growth to work with."
        else:
            reason    = f"g ({_fmt(g, as_pct=True)}) ≥ k ({_fmt(k, as_pct=True)}) — Gordon formula denominator is zero or negative"
            breakdown = (
                f"Gordon Growth formula: Intrinsic = D₁ / (k - g). "
                f"With g={_fmt(g, as_pct=True)} and k={_fmt(k, as_pct=True)}, "
                f"(k-g) ≤ 0, making the result infinite or negative. "
                f"The Two-Stage model handles this by separating high-growth and stable phases."
            )

        example = (
            '"XYZ Corp scores 43/100 (Caution) but the Gordon Growth DDM formula cannot produce '
            'a valid intrinsic value because g of 10.5% meets the required return k of 10.0% — '
            'the denominator (k-g) equals zero, making the formula undefined. '
            'The required return k=10.0% was derived via CAPM using a beta of 1.1 and an ERP '
            'of 5.5%, while g=10.5% came from the minimum of historical dividend CAGR and '
            'sustainable growth rate — both are reasonable estimates, but their convergence '
            'breaks the Gordon constraint. '
            'The dividend track record is strong (10 of 10 years paid, 12% volatility), so '
            'the underlying business is DDM-eligible — the fix is to switch to Two-Stage DDM '
            'which separates the high-growth phase from the stable terminal phase and avoids '
            'the g ≥ k constraint."'
        )
        return f"""Analyse this DDM ({model_label}) suitability for {symbol.upper()}.
The formula cannot produce a valid intrinsic value because {reason}.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total} | Hard fail: {hfail}

=== FORMULA BREAKDOWN ===
{breakdown}
D₀={_fmt(d0)} {currency}, D₁={_fmt(d1)} {currency}, g={_fmt(g, as_pct=True)}, k={_fmt(k, as_pct=True)}
Intrinsic Value = {_fmt(intrinsic)} {currency} (invalid)

=== AVAILABLE METRIC EVIDENCE ===
{metrics_block}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why the DDM formula fails, (2) what the dividend track record looks like, (3) what the investor should do (Two-Stage or wait)."""

    # ── BRANCH B: Valid formula ────────────────────────────────────────────
    if method == "ddm_gordon":
        formula = f"Intrinsic = D₁ / (k - g) = {_fmt(d1)} / ({_fmt(k, as_pct=True)} - {_fmt(g, as_pct=True)}) = {_fmt(intrinsic)} {currency}"
    else:
        formula = f"Two-Stage DDM: PV(high-growth dividends) + PV(Gordon terminal value) = {_fmt(intrinsic)} {currency}"

    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"

    example = (
        '"JNJ scores 71/100 (Good) with dividends paid in 10 of 10 years and volatility of 8%, '
        'confirming the consistent history Gordon Growth DDM requires. '
        'k of 9.2% was derived via CAPM using a beta of 0.68 and an ERP of 5.5%, while g of '
        '5.1% closely matches the historical dividend CAGR of 5.3%, so the g < k constraint '
        'is comfortably satisfied and the growth assumption is well-anchored in history. '
        'Payout ratios are healthy — earnings payout at 48% and FCF payout at 41% — confirming '
        'dividends are sustainably covered without straining the balance sheet. '
        'The intrinsic value of $172.40 carries reasonable confidence; the main risk is rising '
        'interest rates which would increase k and compress the intrinsic value."'
    )

    return f"""Analyse this DDM ({model_label}) suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}
Hard fail: {hfail} | Scorecard recommends: {recommended}

=== FORMULA RESULT ===
{formula}
Upside / downside: {upside_text}

=== AVAILABLE METRICS ===
{metrics_block}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + dividend consistency (paid years, volatility, CAGR).
Sentence 2: How k and g were derived — are they realistic and is g < k well-satisfied?
Sentence 3: Payout sustainability — are dividends covered by earnings and FCF?
Sentence 4: How much to trust the intrinsic value of {_fmt(intrinsic)} {currency} and the main risk."""


# ── DCF prompt ────────────────────────────────────────────────────────────────

def _prompt_dcf(symbol, score, category, flags, ev, vi, id_) -> str:
    fs    = ev.get("final_scoring", {})
    passes = fs.get("passes", "N/A")
    total  = fs.get("totalPossible", "N/A")

    fcf_pos  = ev.get("m1_fcf_positivity_5y", {})
    fcf_vol  = ev.get("m2_fcf_volatility", {})
    rev_ev   = ev.get("m3_revenue_cagr_5y", {})
    rev_vol  = ev.get("m4_revenue_volatility", {}).get("stdev")
    lev_ev   = ev.get("m5_net_debt_to_ebitda", {})
    ic_ev    = ev.get("m6_interest_coverage", {})
    capex_ev = ev.get("m7_capex_to_revenue", {})

    currency  = vi.get("currency", "USD")
    base_fcf  = vi.get("baseFcf")
    n_years   = vi.get("forecastYears")
    wacc      = vi.get("waccUsed")
    term_g    = vi.get("terminalGrowthRateUsed")
    term_meth = vi.get("terminalMethod", "N/A")
    intrinsic = vi.get("intrinsicValuePerShare")
    ev_val    = vi.get("enterpriseValue")
    upside    = vi.get("upsideDownsidePct")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}" for f in crit[:4]) or "  None"
    id_trace  = _input_source_summary(id_, "dcf")

    # Detect broken formula
    has_no_forecast  = any(f.get("code") == "DCF-NO-FORECAST" for f in flags)
    has_g_ge_wacc    = any(f.get("code") == "DCF-GE-WACC"     for f in flags)
    has_no_per_share = any(f.get("code") == "DCF-NO-PER-SHARE" for f in flags)
    base_fcf_neg     = base_fcf is not None and float(base_fcf) < 0
    formula_broken   = has_no_forecast or has_g_ge_wacc or (intrinsic is None and has_no_per_share)

    # Available-only metrics block
    mlines = []
    pos  = fcf_pos.get("positiveYears")
    eyrs = fcf_pos.get("yearsEvaluated")
    fvol = fcf_vol.get("volatility")
    fmn  = fcf_vol.get("mean")
    rc   = rev_ev.get("cagr")
    rsp  = rev_ev.get("spanYears", "?")
    nd   = lev_ev.get("netDebtToEbitda")
    ebi  = lev_ev.get("ebitda")
    ic   = ic_ev.get("interestCoverage")
    cr   = capex_ev.get("avg")
    if pos  is not None: mlines.append(f"FCF positive years (5y): {pos} of {eyrs} [pass: ≥4]")
    if fvol is not None: mlines.append(f"FCF volatility: {_fmt(fvol, as_pct=True)} | mean FCF={_fmt(fmn)} {currency} [pass: <40%]")
    if rc   is not None: mlines.append(f"Revenue CAGR ({rsp}y): {_fmt(rc, as_pct=True)} [pass: ≥4%]")
    if rev_vol is not None: mlines.append(f"Revenue YoY volatility: {_fmt(rev_vol, as_pct=True)} [pass: <10%]")
    if nd   is not None: mlines.append(f"Net Debt / EBITDA: {_fmt(nd)}x | EBITDA={_fmt(ebi)} {currency} [pass: <3x]")
    if ic   is not None: mlines.append(f"Interest coverage: {_fmt(ic)}x [pass: >4x]")
    if cr   is not None: mlines.append(f"Capex / Revenue (5y avg): {_fmt(cr, as_pct=True)} [pass: <8%]")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    coverage  = ev.get("data_coverage", {})
    na_items  = [k for k, v in coverage.items() if isinstance(v, dict) and not v.get("availableYears")]
    gaps_text = ", ".join(na_items) or "None"

    # ── BRANCH A: Formula invalid ──────────────────────────────────────────
    if formula_broken:
        if has_no_forecast:
            breakdown = (
                f"No FCF forecast could be built — base FCF={_fmt(base_fcf)} {currency} "
                f"and/or no FCF growth rate was configured. Without a forecast series "
                f"there are no cash flows to discount."
            )
        elif has_g_ge_wacc:
            breakdown = (
                f"Terminal growth rate g={_fmt(term_g, as_pct=True)} ≥ WACC={_fmt(wacc, as_pct=True)}. "
                f"The perpetuity formula TV = CF(n+1)/(WACC-g) requires WACC > g; "
                f"with this constraint violated the terminal value is infinite or negative."
            )
        elif base_fcf_neg:
            breakdown = (
                f"Base FCF is negative ({_fmt(base_fcf)} {currency}). "
                f"Growing a negative base at any positive rate compounds the problem — "
                f"forecast FCFs remain negative, making the discounting result meaningless."
            )
        else:
            breakdown = "Intrinsic value per share could not be computed (missing net debt or shares outstanding)."

        example = (
            '"XYZ Corp scores 29/100 (Poor) and DCF cannot produce a valid intrinsic value '
            'because the base FCF of -$2.1B is negative — the company is cash flow negative '
            'and compounding that at any growth rate produces increasingly negative forecast '
            'cash flows, making discounting meaningless. '
            'FCF was positive in only 1 of 5 years with a mean of -$800M, revenue CAGR of '
            '28% is strong but has not yet converted to positive cash generation, and '
            'net debt/EBITDA of 4.2x adds balance sheet pressure. '
            'Investors should not rely on this DCF output; the right action is to track '
            'when XYZ achieves sustained positive FCF before rerunning, at which point '
            'the formula will have a valid base to discount."'
        )
        return f"""Analyse this DCF suitability for {symbol.upper()}. The formula cannot produce a valid intrinsic value.
Do NOT describe the intrinsic value as meaningful — instead explain WHY the formula breaks down.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}

=== FORMULA BREAKDOWN ===
{breakdown}
Base FCF: {_fmt(base_fcf)} {currency} | WACC: {_fmt(wacc, as_pct=True)} | Terminal g: {_fmt(term_g, as_pct=True)}
Enterprise Value: {_fmt(ev_val)} {currency} | Intrinsic/share: {_fmt(intrinsic)} {currency}

=== AVAILABLE METRIC EVIDENCE ===
{metrics_block}

=== DATA GAPS ===
{gaps_text}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) exactly why the formula fails, (2) what the cash flow evidence shows, (3) what investors should monitor."""

    # ── BRANCH B: Valid formula ────────────────────────────────────────────
    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"

    example = (
        '"MSFT scores 86/100 (Good) with FCF positive in 5 of 5 years and FCF volatility of '
        '18%, confirming the cash flow stability that makes DCF reliable here. '
        'The base FCF of $72.3B came from the latest annual cash flow statement and a growth '
        'rate of 12% was applied from method defaults, with WACC of 9.0% also from defaults — '
        'both are reasonable but neither is company-specifically derived, so the investor '
        'should sense-check whether 12% FCF growth is sustainable given the 14% revenue CAGR. '
        'The terminal growth rate of 3.0% is well below the 5-year revenue CAGR, providing a '
        'conservative perpetuity anchor, and net debt/EBITDA of 0.4x means leverage poses no '
        'material equity bridge risk. '
        'The intrinsic value of $412 per share carries moderate confidence — the key '
        'sensitivity is the FCF growth assumption; halving it to 6% would materially '
        'reduce the output."'
    )

    return f"""Analyse this DCF suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}

=== FORMULA INPUTS & RESULT ===
Base FCF={_fmt(base_fcf)} {currency}, forecast={n_years} yrs, WACC={_fmt(wacc, as_pct=True)}
Terminal method={term_meth}, terminal g={_fmt(term_g, as_pct=True)}
Enterprise Value={_fmt(ev_val)} {currency} | Intrinsic/share={_fmt(intrinsic)} {currency}
Upside/downside: {upside_text}

=== AVAILABLE METRICS ===
{metrics_block}

=== DATA GAPS ===
{gaps_text}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Is FCF reliable enough for DCF? Cite positive years and volatility.
Sentence 2: Are the forecast inputs (base FCF, growth, WACC) well-supported or defaults/fallbacks?
Sentence 3: Are the terminal value assumptions conservative? Does leverage pose a risk?
Sentence 4: How much to trust {_fmt(intrinsic)} {currency}/share and the single biggest sensitivity risk."""

def _prompt_owner_earnings(symbol, score, category, flags, ev, vi, id_) -> str:
    fs     = ev.get("final_scoring", {})
    passes = fs.get("passes", "N/A")
    total  = fs.get("totalPossible", "N/A")

    # Evidence from owner_earnings_suitability.py
    pos_ev   = ev.get("m1_oe_positivity",   {})
    vol_ev   = ev.get("m2_oe_volatility",   {})
    mgn_ev   = ev.get("m3_oe_margin",       {})
    cagr_ev  = ev.get("m4_oe_cagr",         {})
    cd_ev    = ev.get("m5_capex_da_ratio",   {})
    lev_ev   = ev.get("m6_net_debt_to_ebitda", {})
    roic_ev  = ev.get("m7_roic_5y",         {})

    currency  = vi.get("currency", "USD")
    base_oe   = vi.get("baseOe")
    intrinsic = vi.get("intrinsicValuePerShare")
    upside    = vi.get("upsideDownsidePct")
    g         = vi.get("oeGrowthRateUsed")
    r         = vi.get("discountRateUsed")
    tg        = vi.get("terminalGrowthRateUsed")
    ev_val    = vi.get("enterpriseValue")
    n_years   = vi.get("forecastYears")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in crit[:4]
    ) or "  None"

    # Available-only metrics block
    mlines = []
    pos_y = pos_ev.get("positiveYears")
    tot_y = pos_ev.get("totalYears")
    vol   = vol_ev.get("volatility")
    mu    = vol_ev.get("mean")
    mgn   = mgn_ev.get("avg")
    oe_cagr = cagr_ev.get("cagr")
    cd    = cd_ev.get("avg")
    nd    = lev_ev.get("ratio")
    roic  = roic_ev.get("roicAvg")

    if pos_y  is not None: mlines.append(f"OE positive years (5y): {pos_y} of {tot_y} [pass: ≥4]")
    if vol    is not None: mlines.append(f"OE volatility (StdDev/|Mean|): {_fmt(vol, as_pct=True)} | mean OE={_fmt(mu)} {currency} [pass: <40%]")
    if mgn    is not None: mlines.append(f"OE margin (5y avg): {_fmt(mgn, as_pct=True)} [pass: ≥5%]")
    if oe_cagr is not None: mlines.append(f"OE CAGR (5y): {_fmt(oe_cagr, as_pct=True)} [pass: ≥4%]")
    if cd     is not None: mlines.append(f"Capex / D&A ratio (5y avg): {_fmt(cd)}x [pass: <1.5x]")
    if nd     is not None: mlines.append(f"Net Debt / EBITDA: {_fmt(nd)}x [pass: <3x]")
    if roic   is not None: mlines.append(f"ROIC (5y avg): {_fmt(roic, as_pct=True)} [pass: ≥15%]")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    formula_broken = intrinsic is None
    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"

    if formula_broken:
        return f"""Analyse this Owner Earnings suitability for {symbol.upper()}. The model could not produce an intrinsic value (missing base OE or growth rate).
Explain why it breaks down and what the evidence shows about earnings quality.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}
=== FORMULA BREAKDOWN ===
Base OE: {_fmt(base_oe)} {currency} | OE growth: {_fmt(g, as_pct=True)} | Discount rate: {_fmt(r, as_pct=True)}
Intrinsic/share: unavailable
=== AVAILABLE METRIC EVIDENCE ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why the OE formula cannot compute an intrinsic value, (2) what the available metrics reveal about earnings quality, (3) what an investor should monitor."""

    return f"""Analyse this Owner Earnings (Buffett Method) suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}
=== FORMULA RESULT ===
OE = Net Income + D&A − Maintenance Capex
Base OE: {_fmt(base_oe)} {currency}/yr | growth: {_fmt(g, as_pct=True)} | discount: {_fmt(r, as_pct=True)} | terminal g: {_fmt(tg, as_pct=True)} | horizon: {n_years} yrs
Enterprise Value: {_fmt(ev_val)} {currency} | Intrinsic/share: {_fmt(intrinsic)} {currency}
Upside/downside: {upside_text}
=== AVAILABLE METRICS ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + OE consistency (positive years, volatility, CAGR) with actual values.
Sentence 2: Are the OE margin and capital intensity (Capex/D&A) sustainable? Reference ROIC.
Sentence 3: Are discount rate and terminal growth assumptions conservative? Note leverage risk if present.
Sentence 4: How much to trust the intrinsic value of {_fmt(intrinsic)} {currency}/share and the main sensitivity risk."""


def _prompt_residual_income(symbol, score, category, flags, ev, vi, id_) -> str:
    fs     = ev.get("final_scoring", {})
    passes = fs.get("passes", "N/A")
    total  = fs.get("totalPossible", "N/A")

    # Evidence from residual_income_suitability.py
    eq_ev    = ev.get("m1_equity_positivity",  {})
    roe_ev   = ev.get("m2_roe_vs_ke",          {})
    roe_c_ev = ev.get("m3_roe_consistency",    {})
    bv_ev    = ev.get("m4_bv_growth",          {})
    lev_ev   = ev.get("m5_net_debt_to_equity", {})
    eps_ev   = ev.get("m6_eps_positivity",     {})
    roic_ev  = ev.get("m7_roic_5y",            {})

    currency  = vi.get("currency", "USD")
    bv        = vi.get("bvPerShare")
    eps0      = vi.get("eps0")
    roe0      = vi.get("roe0")
    ke        = vi.get("costOfEquityUsed")
    ri0       = vi.get("ri0PerShare")
    intrinsic = vi.get("intrinsicValuePerShare")
    upside    = vi.get("upsideDownsidePct")
    g         = vi.get("riGrowthRateUsed")
    tg        = vi.get("terminalGrowthRateUsed")
    n_years   = vi.get("forecastYears")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in crit[:4]
    ) or "  None"

    # Available-only metrics
    mlines = []
    roe_avg  = roe_ev.get("roeAvg")
    ke_used  = roe_ev.get("keUsed")
    spread   = (roe_avg - ke_used) if (roe_avg is not None and ke_used is not None) else None
    roe_pos  = roe_c_ev.get("positiveYears")
    roe_tot  = roe_c_ev.get("totalYears")
    bv_cagr  = bv_ev.get("cagr")
    nd_eq    = lev_ev.get("ratio")
    eps_pos  = eps_ev.get("positiveYears")
    eps_tot  = eps_ev.get("totalYears")
    roic     = roic_ev.get("roicAvg")

    if spread   is not None: mlines.append(f"ROE − CoE spread: {_fmt(spread, as_pct=True)} (ROE={_fmt(roe_avg, as_pct=True)}, CoE={_fmt(ke_used, as_pct=True)}) [pass: spread>0]")
    if roe_pos  is not None: mlines.append(f"ROE positive years: {roe_pos} of {roe_tot} [pass: ≥4]")
    if bv_cagr  is not None: mlines.append(f"Book value CAGR (5y): {_fmt(bv_cagr, as_pct=True)} [pass: ≥3%]")
    if eps_pos  is not None: mlines.append(f"EPS positive years (5y): {eps_pos} of {eps_tot} [pass: ≥4]")
    if nd_eq    is not None: mlines.append(f"Net Debt / Equity: {_fmt(nd_eq)}x [pass: <1.5x]")
    if roic     is not None: mlines.append(f"ROIC (5y avg): {_fmt(roic, as_pct=True)} [pass: ≥10%]")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    spread_text = f"{_fmt(spread, as_pct=True)} (value {'creating' if spread and spread > 0 else 'destroying'})" if spread is not None else "N/A"
    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"
    formula_broken = intrinsic is None

    if formula_broken:
        return f"""Analyse this Residual Income suitability for {symbol.upper()}. The model could not produce an intrinsic value.
Explain the specific failure and what the evidence reveals about value creation.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}
=== FORMULA BREAKDOWN ===
RI = Intrinsic = BV₀/share + PV(EPS − CoE × BV) + Terminal
BV/share: {_fmt(bv)} {currency} | EPS: {_fmt(eps0)} {currency} | ROE: {_fmt(roe0, as_pct=True)} | CoE: {_fmt(ke, as_pct=True)}
RI₀/share: {_fmt(ri0)} {currency} | Intrinsic: unavailable
=== AVAILABLE METRIC EVIDENCE ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
+Cover: (1) why the RI formula fails (negative equity or missing data), (2) what the ROE vs CoE evidence shows about economic profit, (3) what an investor should watch."""

    return f"""Analyse this Residual Income (Economic Profit) suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {passes}/{total}
=== FORMULA RESULT ===
Intrinsic = BV₀/share + Σ[(ROE−CoE)×BVₜ₋₁]/(1+CoE)ᵗ + Terminal
BV/share={_fmt(bv)} {currency} | EPS={_fmt(eps0)} {currency} | ROE={_fmt(roe0, as_pct=True)} | CoE={_fmt(ke, as_pct=True)}
RI₀/share={_fmt(ri0)} {currency} | ROE−CoE spread={spread_text}
g={_fmt(g, as_pct=True)} | terminal g={_fmt(tg, as_pct=True)} | horizon={n_years} yrs
Intrinsic/share={_fmt(intrinsic)} {currency} | Upside/downside={upside_text}
=== AVAILABLE METRICS ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + the ROE vs CoE spread — is the company generating or destroying value above its cost of equity?
Sentence 2: Is book value growing consistently? Are earnings reliably positive to anchor the RI stream?
Sentence 3: Are the CoE and growth assumptions defensible? Does leverage pose a risk to the book value anchor?
Sentence 4: How much to trust the intrinsic value of {_fmt(intrinsic)} {currency}/share and the main sensitivity risk."""


def _prompt_magic_formula(symbol, score, category, flags, ev, vi) -> str:
    """
    Prompt for Greenblatt Magic Formula suitability summary.
    evidence keys: earnings_yield, return_on_capital, enterprise_value,
                   ttm_ebit, sector, industry
    valuation_inputs keys: currency, earnings_yield_pct, roc_pct
    """
    ey      = ev.get("earnings_yield")
    roc     = ev.get("return_on_capital")
    ev_val  = ev.get("enterprise_value")
    ebit    = ev.get("ttm_ebit")
    sector  = ev.get("sector") or "Unknown"
    industry = ev.get("industry") or "Unknown"
    currency = vi.get("currency", "USD")
    ey_pct  = vi.get("earnings_yield_pct")
    roc_pct = vi.get("roc_pct")

    crit      = _critical_flags(flags)
    crit_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in crit[:4]
    ) or "  None"

    # Detect excluded sector
    excluded = any(f.get("code") == "MF-SECTOR-EXCLUDED" for f in flags)
    neg_ebit = any(f.get("code") == "MF-NEGATIVE-EBIT"   for f in flags)

    # Available-only metrics block
    mlines = []
    if ey_pct  is not None: mlines.append(f"Earnings yield: {_fmt(ey_pct)}% (EBIT/EV)")
    if roc_pct is not None: mlines.append(f"Return on capital: {_fmt(roc_pct)}% (EBIT/(NWC+NFA))")
    if ebit    is not None: mlines.append(f"TTM EBIT: {_fmt(ebit)} {currency}")
    if ev_val  is not None: mlines.append(f"Enterprise value: {_fmt(ev_val)} {currency}")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    if excluded:
        example = (
            '"GS scores 0/100 (Not Applicable) because Greenblatt explicitly excludes '
            'Financial Services companies from the Magic Formula — banks and brokerages use '
            'leverage as an operating input, so EBIT divided by net working capital plus '
            'net fixed assets produces a nonsensical return-on-capital figure that cannot '
            'be compared to industrial or technology businesses. '
            'The formula\'s two metrics are mechanically computable but carry no analytical '
            'meaning in a financial firm context; the right approach for GS is price-to-book '
            'combined with ROE or residual income analysis."'
        )
        return f"""Analyse this Magic Formula suitability for {symbol.upper()}. The company is excluded from the formula by Greenblatt's own guidelines.
Do NOT describe earnings yield or ROC as meaningful metrics for this company.
Explain WHY the sector exclusion exists and what the right alternative approach is.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Sector: {sector} | Industry: {industry}
=== SECTOR EXCLUSION ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why Greenblatt excludes this sector, (2) what alternative valuation method suits it."""

    if neg_ebit:
        return f"""Analyse this Magic Formula suitability for {symbol.upper()}. The formula requires positive EBIT.
Explain why negative EBIT breaks both metrics and what that reveals about the company.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Sector: {sector} | Industry: {industry}
=== FORMULA BREAKDOWN ===
TTM EBIT: {_fmt(ebit)} {currency} — negative value makes Earnings Yield and ROC both negative and meaningless.
=== CRITICAL FLAGS ===
{crit_text}
=== AVAILABLE DATA ===
{metrics_block}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why negative EBIT breaks both Magic Formula metrics, (2) what it signals about the business, (3) when to revisit."""

    example = (
        '"AAPL scores 85/100 (Applicable) with an earnings yield of 7.2% and return on capital '
        'of 48.3%, both of which comfortably clear the thresholds Greenblatt found empirically '
        'predictive of market outperformance. '
        'The earnings yield compares favourably to the Technology sector\'s implied earnings '
        'yield of 3.8% (derived from the industry median EV/EBITDA of 26x), suggesting the '
        'market is paying less per dollar of operating earnings for AAPL than for its peers. '
        'The return on capital of 48.3% reflects AAPL\'s asset-light model — net working capital '
        'and net fixed assets together are modest relative to the operating profit they generate. '
        'Note that without a ranked universe these metrics cannot produce a Magic Formula rank '
        'score; they are best used as a screen for whether the company meets Greenblatt\'s '
        'quality and valuation thresholds rather than as a standalone buy signal."'
    )
    return f"""Analyse this Magic Formula suitability for {symbol.upper()}. Write a 3-4 sentence plain-English summary.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Sector: {sector} | Industry: {industry}
=== MAGIC FORMULA METRICS ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + what the earnings yield and ROC values mean in plain English.
Sentence 2: How the earnings yield compares to the sector context (if available).
Sentence 3: What the ROC level says about capital efficiency.
Sentence 4: The key limitation — no universe ranking means this is a screen, not a rank."""


def _prompt_canslim(symbol, score, category, flags, ev) -> str:
    """
    Prompt for CANSlim composite suitability summary.
    evidence keys: letter scores passed as a flat dict from the composite.
    """
    crit      = _critical_flags(flags)
    crit_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in crit[:4]
    ) or "  None"

    # Extract per-letter data from evidence if provided
    letters_block = ""
    if ev:
        lines = []
        for letter in ("C", "A", "N", "S", "L", "I", "M"):
            ldata = ev.get(letter, {})
            if ldata:
                avail = ldata.get("available", True)
                sig   = ldata.get("signal", "N/A")
                head  = ldata.get("headline", "")
                sc    = ldata.get("score", "N/A")
                if avail:
                    lines.append(f"  {letter}: score={sc}/100, signal={sig} — {head[:120]}")
                else:
                    lines.append(f"  {letter}: unavailable — {head[:80]}")
        letters_block = "\n".join(lines) or "  (no letter detail available)"
    else:
        letters_block = "  (no letter detail available)"

    example = (
        '"NVDA scores 78/100 (Strong) across the CANSlim framework with particular strength '
        'in C and A — quarterly EPS grew 265% year-over-year in the most recent quarter and '
        'the 5-year EPS CAGR of 42% far exceeds O\'Neil\'s 25% minimum, with every year in '
        'the series positive. '
        'N scores well because price is within 3% of its 52-week high and revenue is '
        'accelerating, while S is neutral given a large float of 2.4 billion shares. '
        'L confirms leadership status with a 12-month return 48 percentage points above '
        'the S&P 500 benchmark, and M is bullish with SPY trading above its rising '
        '200-day SMA in a confirmed uptrend. '
        'The one structural gap is I — institutional sponsorship cannot be scored without '
        '13F data — which reduces composite confidence to 90%, meaning the 78 score should '
        'be read as approximately 78 ± 8 depending on institutional trend."'
    )
    return f"""Analyse this CANSlim suitability for {symbol.upper()}. Write a 3-4 sentence plain-English summary following O'Neil's framework.
=== COMPOSITE ===
Score: {score}/100 | Category: {category}
=== LETTER DETAIL ===
{letters_block}
=== CRITICAL FLAGS ===
{crit_text}
=== EXAMPLE OUTPUT — match this depth, replace all values with {symbol.upper()} data ===
{example}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + the 2 strongest or weakest letters (C and A carry most weight) with actual values.
Sentence 2: N, S, and L signals — what do price position, volume, and relative strength show?
Sentence 3: M — what is the current market condition and does it support new purchases?
Sentence 4: Note any unavailable letters and how they affect confidence in the composite score."""

# ── Generic fallback ──────────────────────────────────────────────────────────

def _prompt_generic(symbol, method, score, category, flags) -> str:
    sorted_flags = sorted(flags, key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "info"), 99))
    flags_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in sorted_flags[:3]
    ) or "  None"
    return f"""Write a 3-4 sentence plain-English suitability summary for retail investors.

Stock: {symbol.upper()} | Model: {method} | Score: {score}/100 | Category: {category}

Key flags:
{flags_text}

Output only the paragraph. No bullet points. No preamble.
Explain WHY suitability is {category}, reference the most important flags with their values, and state how much an investor should trust this valuation."""

# ─────────────────────────────────────────────────────────────────────────────
# generate_overview_summary
# Called by ValuationService.get_valuation_overview() to produce the
# cross-method AI recommendation shown in the Valuation Overview panel.
#
# Follows the EXACT same Gemini REST pattern as generate_suitability_summary:
#   - httpx.AsyncClient with configurable timeout
#   - thinkingBudget: 0 INSIDE generationConfig
#   - system_instruction as a separate field
#   - Returns None (never raises) on any failure
#
# Unlike generate_suitability_summary (returns str), this returns a dict
# because the frontend maps specific fields (bestMethod, consensus, etc.)
# to UI components.
# ─────────────────────────────────────────────────────────────────────────────
 
_METHOD_LABELS = {
    "rule1":           "Rule #1 (Phil Town)",
    "dcf":             "Discounted Cash Flow",
    "ddm_gordon":      "Dividend Discount Model",
    "owner_earnings":  "Owner Earnings",
    "residual_income": "Residual Income",
}
 
_METHOD_BEST_FOR = {
    "rule1":           "stable earnings compounders with predictable EPS growth and low debt",
    "dcf":             "companies with consistent positive free cash flow but no dividends",
    "ddm_gordon":      "dividend-paying companies with a long, stable dividend growth history",
    "owner_earnings":  "capital-intensive businesses where Buffett-style maintenance capex adjustment matters",
    "residual_income": "financial firms or asset-heavy companies where book value anchors intrinsic value",
}
 
_OVERVIEW_FALLBACK = {
    "bestMethod":      "rule1",
    "bestMethodLabel": "Rule #1 (Phil Town)",
    "reasoning":       "Multiple valuation methods have been computed for this company.",
    "consensus":       "Mixed",
    "confidenceNote":  "Review individual method diagnostics for full context.",
}
 
 
def _build_overview_prompt(
    symbol:        str,
    sector:        Optional[str],
    currency:      str,
    current_price: Optional[float],
    methods:       Dict[str, Any],
) -> str:
    """
    Build the cross-method overview prompt.
 
    Only includes methods that have been computed (status="computed").
    Filters out N/A fields so the model cannot hallucinate missing values.
    """
    sector_str = sector or "Unknown"
    price_str  = f"{currency}{current_price:,.2f}" if current_price else "N/A"
 
    # ── Per-method summary lines (available values only) ──────────────────
    method_lines = []
    for method_id, data in methods.items():
        label   = _METHOD_LABELS.get(method_id, method_id)
        best_for = _METHOD_BEST_FOR.get(method_id, "general use")
 
        parts = [f"**{label}** (best for: {best_for})"]
 
        iv      = data.get("intrinsicValue")
        upside  = data.get("upsideDownside")
        score   = data.get("score")
        cat     = data.get("category")
 
        if iv      is not None: parts.append(f"intrinsic={currency}{iv:,.2f}")
        if upside  is not None: parts.append(f"upside={upside*100:+.1f}%")
        if score   is not None: parts.append(f"suitability={score}/100 ({cat})")
 
        method_lines.append("  - " + ", ".join(parts))
 
    methods_block = "\n".join(method_lines)
 
    # ── Convergence note ──────────────────────────────────────────────────
    computed_ivs = [
        float(v["intrinsicValue"])
        for v in methods.values()
        if v.get("intrinsicValue") is not None
    ]
    convergence_note = ""
    if len(computed_ivs) >= 2:
        lo, hi = min(computed_ivs), max(computed_ivs)
        spread_pct = (hi - lo) / lo * 100 if lo > 0 else None
        if spread_pct is not None:
            if spread_pct < 20:
                convergence_note = f"The methods show strong convergence (range {currency}{lo:,.2f}–{currency}{hi:,.2f}, spread {spread_pct:.0f}%), which increases confidence."
            elif spread_pct < 60:
                convergence_note = f"The methods show moderate divergence (range {currency}{lo:,.2f}–{currency}{hi:,.2f}, spread {spread_pct:.0f}%), which is normal given different assumptions."
            else:
                convergence_note = f"The methods diverge significantly (range {currency}{lo:,.2f}–{currency}{hi:,.2f}, spread {spread_pct:.0f}%), indicating high sensitivity to assumptions — use multiple methods and apply a margin of safety."
 
    # ── Example output ────────────────────────────────────────────────────
    example = (
        '{\n'
        '  "bestMethod": "dcf",\n'
        '  "bestMethodLabel": "Discounted Cash Flow",\n'
        '  "reasoning": "Discounted Cash Flow is the most appropriate method for MSFT because '
        'it generates substantial free cash flow ($72B in the latest year) with FCF positive '
        'in all 5 of the last 5 years and low volatility (18%), which is exactly the stable '
        'cash generation profile DCF requires. Rule #1 and Owner Earnings both agree that '
        'the stock appears undervalued — DCF at $412/share, Rule #1 at $390/share — '
        'providing useful cross-model confirmation. DDM is less reliable here because '
        'dividends are only a small portion of total shareholder returns.",\n'
        '  "consensus": "Undervalued",\n'
        '  "confidenceNote": "The main sensitivity is the 12% FCF growth assumption; '
        'if growth slows to 7% the intrinsic value would compress by roughly 25%."\n'
        '}'
    )
 
    return f"""You are a professional equity analyst. Analyse these valuation results for {symbol} and produce a cross-method recommendation.
 
Company: {symbol}
Sector: {sector_str}
Current Price: {price_str}
 
Computed Valuation Results:
{methods_block}
 
{f"Convergence note: {convergence_note}" if convergence_note else ""}
 
Method selection guidance:
- Rule #1: Most reliable for stable earnings compounders with 5+ years of consistent EPS growth.
- DCF: Most reliable when FCF is positive and predictable over 5+ years.
- DDM: Only reliable if dividends are consistently paid and growing; unreliable for non-dividend payers.
- Owner Earnings: Best when capital expenditure is a material part of the value story (manufacturing, infrastructure, retail).
- Residual Income: Best for banks, insurers, or asset-heavy firms where book value is the primary anchor.
 
Rules you MUST follow:
1. Only reference intrinsic values, upside %, and suitability scores that are explicitly provided above.
2. Your "reasoning" must explain WHY the chosen method fits this company's profile — not just which method wins.
3. If multiple methods agree on direction (all show upside or all show downside), note the convergence.
4. "consensus" must be exactly one of: Undervalued, Fairly Valued, Overvalued, Mixed.
5. "bestMethod" must be exactly one of: rule1, dcf, ddm_gordon, owner_earnings, residual_income.
6. Complete every sentence. Never use bullet points or labels inside the reasoning string.
 
=== EXAMPLE OUTPUT (replace all values with {symbol} data) ===
{example}
 
=== NOW WRITE THE RECOMMENDATION FOR {symbol} ===
Respond with ONLY valid JSON. No markdown fences. No text before or after the JSON object."""
 
 
async def generate_overview_summary(
    symbol:        str,
    sector:        Optional[str],
    currency:      str,
    current_price: Optional[float],
    methods:       Dict[str, Any],
    timeout:       float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Generate a cross-method valuation overview recommendation via Gemini REST.
 
    Returns a dict with keys:
      bestMethod, bestMethodLabel, reasoning, consensus, confidenceNote
 
    Returns None (never raises) if key missing, call fails, times out, or
    JSON parsing fails. Callers should treat None as "no recommendation available".
    """
    import json as _json
 
    key = settings.GEMINI_API_KEY or ""
    if not key:
        logger.info("[AI] GEMINI_API_KEY not set — overview summaries disabled")
        return None
 
    if not methods:
        return None
 
    model = settings.GEMINI_MODEL
    url   = _GEMINI_URL.format(model=model, key=key)
 
    prompt = _build_overview_prompt(
        symbol=symbol,
        sector=sector,
        currency=currency,
        current_price=current_price,
        methods=methods,
    )
 
    logger.info(
        "[AI] Sending overview prompt for %s (%d chars):\n--- PROMPT START ---\n%s\n--- PROMPT END ---",
        symbol, len(prompt), prompt,
    )
 
    system_instruction = (
        "You are a financial analysis assistant writing cross-method valuation recommendations "
        "for retail investors. You always respond with valid JSON only — no markdown, no preamble. "
        "You only reference metric values that are explicitly provided — never invent numbers. "
        "You complete every sentence in the reasoning field."
    )
 
    body = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 700,
            "temperature":     0.1,
            "topP":            0.85,
            # thinkingConfig MUST be inside generationConfig for gemini-2.5-flash.
            "thinkingConfig": {
                "thinkingBudget": 0,
            },
        },
    }
 
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body)
            if not resp.is_success:
                logger.warning(
                    "[AI] Gemini %s for overview/%s | body: %s",
                    resp.status_code, symbol, resp.text[:500],
                )
                return None
 
            data      = resp.json()
            candidate = data.get("candidates", [{}])[0]
            finish    = candidate.get("finishReason", "UNKNOWN")
            usage     = data.get("usageMetadata", {})
            raw = (
                candidate
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
            )
 
            logger.info(
                "[AI] overview/%s: %d chars | finishReason=%s | prompt=%s out=%s thinking=%s\n"
                "--- AI OUTPUT START ---\n%s\n--- AI OUTPUT END ---",
                symbol, len(raw), finish,
                usage.get("promptTokenCount"),
                usage.get("candidatesTokenCount"),
                usage.get("thoughtsTokenCount"),
                raw,
            )
 
            if not raw:
                logger.warning("[AI] Empty overview response for %s | finishReason=%s", symbol, finish)
                return None
 
            # Strip markdown fences if model adds them despite instruction
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1]
                if "```" in clean:
                    clean = clean.rsplit("```", 1)[0]
            clean = clean.strip()
 
            try:
                result = _json.loads(clean)
            except _json.JSONDecodeError as je:
                logger.warning(
                    "[AI] overview/%s: JSON parse failed (%s) | raw=%s",
                    symbol, je, raw[:300],
                )
                return None
 
            # Validate required keys
            required = {"bestMethod", "bestMethodLabel", "reasoning", "consensus", "confidenceNote"}
            if not required.issubset(result.keys()):
                missing = required - result.keys()
                logger.warning(
                    "[AI] overview/%s: missing keys %s in response", symbol, missing
                )
                # Return what we have rather than nothing — partial is better than None
                for k in missing:
                    result[k] = _OVERVIEW_FALLBACK.get(k, "")
 
            # Normalise bestMethod to a known value
            if result.get("bestMethod") not in _METHOD_LABELS:
                logger.warning(
                    "[AI] overview/%s: unknown bestMethod=%s, falling back",
                    symbol, result.get("bestMethod"),
                )
                # Pick the computed method with the highest suitability score as fallback
                best = max(methods.items(), key=lambda kv: kv[1].get("score") or 0)
                result["bestMethod"]      = best[0]
                result["bestMethodLabel"] = _METHOD_LABELS.get(best[0], best[0])
 
            return result
 
    except httpx.TimeoutException:
        logger.warning("[AI] Overview summary timed out for %s", symbol)
        return None
    except Exception as exc:
        logger.warning("[AI] Overview summary failed for %s: %s", symbol, exc)
        return None
 
