from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


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


def _critical_flags(flags: list[dict]) -> list[dict]:
    skip = {"-SCORECARD", "-DATA-COVERAGE", "-REPO-KEYS"}
    return [
        f for f in flags
        if f.get("severity") in ("critical", "high")
        and not any(f.get("code", "").endswith(s) for s in skip)
    ]


def _input_source_summary(input_decisions: dict[str, Any], method: str) -> str:
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


def build_suitability_prompt(
    symbol: str,
    method: str,
    score: int,
    category: str,
    flags: list[dict],
    evidence: dict[str, Any],
    valuation_inputs: dict[str, Any],
    input_decisions: dict[str, Any],
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

    if formula_broken:
        return _rule1_broken(symbol, score, category, points, total, hfail, eps0, currency, g_raw, g_clamped,
                             sticker, mos_p, metrics_block, available, len(metric_vals), gaps_text, id_trace, crit_text)

    if data_sparse:
        return _rule1_sparse(symbol, score, category, points, total, hfail, metrics_block, available,
                             len(metric_vals), na_count, gaps_text, eps0, currency, growth, fpe, horizon, dr,
                             mos, sticker, mos_p, id_trace, crit_text, clamp_note)

    return _rule1_rich(symbol, score, category, points, total, hfail, metrics_block, available,
                       len(metric_vals), eps0, currency, growth, fpe, feps, fprice, sticker, mos_p,
                       horizon, dr, mos, id_trace, crit_text, clamp_note)


def _rule1_broken(symbol, score, category, points, total, hfail, eps0, currency, g_raw, g_clamped,
                  sticker, mos_p, metrics_block, available, total_metrics, gaps_text, id_trace, crit_text):
    return f"""Analyse this Rule #1 suitability for {symbol.upper()}. The formula cannot produce a valid result because EPS is negative.
Do NOT describe the sticker/MOS price as meaningful values — they are $0 because the math breaks down.
Instead explain WHY the formula fails and what the evidence reveals about financial health.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== FORMULA BREAKDOWN ===
EPS₀ = {_fmt(eps0)} {currency} ← NEGATIVE: Future EPS = EPS₀ × (1+g)^n ≤ 0 regardless of g
Growth input: raw={_fmt(g_raw, as_pct=True)}, clamped to={_fmt(g_clamped, as_pct=True)}
Result: Sticker={_fmt(sticker)} {currency}, MOS Price={_fmt(mos_p)} {currency} — both meaningless

=== AVAILABLE METRIC EVIDENCE ({available} of {total_metrics} computable) ===
{metrics_block}

=== DATA GAPS ===
{gaps_text}

=== INPUT DECISIONS ===
{id_trace}

=== CRITICAL FLAGS ===
{crit_text}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why the Rule #1 formula fails with negative EPS, (2) what the available metrics say about financial health, (3) what an investor should do instead."""


def _rule1_sparse(symbol, score, category, points, total, hfail, metrics_block, available,
                  total_metrics, na_count, gaps_text, eps0, currency, growth, fpe, horizon, dr,
                  mos, sticker, mos_p, id_trace, crit_text, clamp_note):
    return f"""Analyse this Rule #1 suitability for {symbol.upper()}. Most metrics are N/A due to limited history.
Write a summary that is honest about what IS known and frames the data gaps as a confidence issue.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== AVAILABLE METRIC EVIDENCE ({available} of {total_metrics} computable) ===
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

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Explicitly mention how many metrics were computable and how that affects confidence in the sticker price."""


def _rule1_rich(symbol, score, category, points, total, hfail, metrics_block, available,
                total_metrics, eps0, currency, growth, fpe, feps, fprice, sticker, mos_p,
                horizon, dr, mos, id_trace, crit_text, clamp_note):
    return f"""Analyse this Rule #1 suitability and valuation for {symbol.upper()}. Write a 3-4 sentence plain-English summary.

=== SCORECARD ===
Score: {score}/100 | Category: {category} | Passes: {points}/{total} | Hard fail: {hfail}

=== FORMULA ===
Future EPS = EPS₀ × (1+g)^n | Future Price = Future EPS × PE
Sticker = Future Price / (1+r)^n | MOS Price = Sticker × (1 - MOS%)

=== AVAILABLE METRICS ({available} of {total_metrics} computable) ===
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

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + the 1-2 biggest metric failures with actual values.
Sentence 2: Input reliability — were growth and PE from good sources or fallbacks?
Sentence 3: What the formula produces and whether sticker/MOS are trustworthy.
Sentence 4: What an investor must verify before trusting this valuation."""


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

    has_no_div = any(f.get("code") == "DDM-NO-DIV" for f in flags)
    has_g_ge_k = (
        any(f.get("code") == "DDM-GE-K" for f in flags)
        or (g is not None and k is not None and float(g) >= float(k) and method == "ddm_gordon")
    )
    formula_broken = has_no_div or has_g_ge_k

    def _payout(v):
        if v is None: return "N/A"
        f = float(v)
        return f"{f:.1f}%" if f > 1.0 else f"{f*100:.1f}%"

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

    if formula_broken:
        if has_no_div:
            reason    = "the company pays no dividends — DDM has no inputs"
            breakdown = "DDM requires a dividend stream to discount. Without dividends there is no D₀, D₁, or growth to work with."
        else:
            reason    = f"g ({_fmt(g, as_pct=True)}) ≥ k ({_fmt(k, as_pct=True)}) — Gordon formula denominator is zero or negative"
            breakdown = (
                f"Gordon Growth formula: Intrinsic = D₁ / (k - g). "
                f"With g={_fmt(g, as_pct=True)} and k={_fmt(k, as_pct=True)}, "
                f"(k-g) ≤ 0, making the result infinite or negative."
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

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) why the DDM formula fails, (2) what the dividend track record looks like, (3) what the investor should do (Two-Stage or wait)."""

    if method == "ddm_gordon":
        formula = f"Intrinsic = D₁ / (k - g) = {_fmt(d1)} / ({_fmt(k, as_pct=True)} - {_fmt(g, as_pct=True)}) = {_fmt(intrinsic)} {currency}"
    else:
        formula = f"Two-Stage DDM: PV(high-growth dividends) + PV(Gordon terminal value) = {_fmt(intrinsic)} {currency}"

    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"

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

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + dividend consistency (paid years, volatility, CAGR).
Sentence 2: How k and g were derived — are they realistic and is g < k well-satisfied?
Sentence 3: Payout sustainability — are dividends covered by earnings and FCF?
Sentence 4: How much to trust the intrinsic value of {_fmt(intrinsic)} {currency} and the main risk."""


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

    has_no_forecast  = any(f.get("code") == "DCF-NO-FORECAST" for f in flags)
    has_g_ge_wacc    = any(f.get("code") == "DCF-GE-WACC"     for f in flags)
    has_no_per_share = any(f.get("code") == "DCF-NO-PER-SHARE" for f in flags)
    base_fcf_neg     = base_fcf is not None and float(base_fcf) < 0
    formula_broken   = has_no_forecast or has_g_ge_wacc or (intrinsic is None and has_no_per_share)

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

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Cover: (1) exactly why the formula fails, (2) what the cash flow evidence shows, (3) what investors should monitor."""

    upside_text = f"{_fmt(upside, as_pct=True)} vs current price" if upside is not None else "N/A"

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
Cover: (1) why the RI formula fails (negative equity or missing data), (2) what the ROE vs CoE evidence shows about economic profit, (3) what an investor should watch."""

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

    excluded = any(f.get("code") == "MF-SECTOR-EXCLUDED" for f in flags)
    neg_ebit = any(f.get("code") == "MF-NEGATIVE-EBIT"   for f in flags)

    mlines = []
    if ey_pct  is not None: mlines.append(f"Earnings yield: {_fmt(ey_pct)}% (EBIT/EV)")
    if roc_pct is not None: mlines.append(f"Return on capital: {_fmt(roc_pct)}% (EBIT/(NWC+NFA))")
    if ebit    is not None: mlines.append(f"TTM EBIT: {_fmt(ebit)} {currency}")
    if ev_val  is not None: mlines.append(f"Enterprise value: {_fmt(ev_val)} {currency}")
    metrics_block = "\n".join(f"  {l}" for l in mlines) or "  (insufficient data)"

    if excluded:
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

    return f"""Analyse this Magic Formula suitability for {symbol.upper()}. Write a 3-4 sentence plain-English summary.
=== SCORECARD ===
Score: {score}/100 | Category: {category} | Sector: {sector} | Industry: {industry}
=== MAGIC FORMULA METRICS ===
{metrics_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + what the earnings yield and ROC values mean in plain English.
Sentence 2: How the earnings yield compares to the sector context (if available).
Sentence 3: What the ROC level says about capital efficiency.
Sentence 4: The key limitation — no universe ranking means this is a screen, not a rank."""


def _prompt_canslim(symbol, score, category, flags, ev) -> str:
    crit      = _critical_flags(flags)
    crit_text = "\n".join(
        f"  - {f.get('code')} ({f.get('severity')}): {f.get('message','')}"
        for f in crit[:4]
    ) or "  None"

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

    return f"""Analyse this CANSlim suitability for {symbol.upper()}. Write a 3-4 sentence plain-English summary following O'Neil's framework.
=== COMPOSITE ===
Score: {score}/100 | Category: {category}
=== LETTER DETAIL ===
{letters_block}
=== CRITICAL FLAGS ===
{crit_text}
=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.
Sentence 1: Verdict + the 2 strongest or weakest letters (C and A carry most weight) with actual values.
Sentence 2: N, S, and L signals — what do price position, volume, and relative strength show?
Sentence 3: M — what is the current market condition and does it support new purchases?
Sentence 4: Note any unavailable letters and how they affect confidence in the composite score."""


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
