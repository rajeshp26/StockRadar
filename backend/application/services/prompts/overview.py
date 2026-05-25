from __future__ import annotations

from typing import Any, Dict, List, Optional

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

OVERVIEW_FALLBACK = {
    "bestMethod":      "rule1",
    "bestMethodLabel": "Rule #1 (Phil Town)",
    "reasoning":       "Multiple valuation methods have been computed for this company.",
    "consensus":       "Mixed",
    "confidenceNote":  "Review individual method diagnostics for full context.",
}


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


def build_overview_prompt(
    symbol: str,
    sector: Optional[str],
    currency: str,
    current_price: Optional[float],
    methods: Dict[str, Any],
) -> str:
    sector_str = sector or "Unknown"
    price_str  = f"{currency}{current_price:,.2f}" if current_price else "N/A"

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

=== NOW WRITE THE RECOMMENDATION FOR {symbol} ===
Respond with ONLY valid JSON. No markdown fences. No text before or after the JSON object."""
