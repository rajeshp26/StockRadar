# application/services/prompts/wacc_roic.py
"""
WACC / ROIC narrative prompt builder.

Structured prompt following the pattern of suitability.py.
Generates plain-English explanations of a company's cost of capital
and return on invested capital for retail investors.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def build_wacc_roic_prompt(
    symbol: str,
    wacc: Optional[float] = None,
    cost_of_equity: Optional[float] = None,
    beta: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    equity_risk_premium: Optional[float] = None,
    equity_weight: Optional[float] = None,
    debt_weight: Optional[float] = None,
    cost_of_debt: Optional[float] = None,
    tax_rate: Optional[float] = None,
    roic_current: Optional[float] = None,
    roic_average_5y: Optional[float] = None,
    roic_trend: Optional[str] = None,
    spread: Optional[float] = None,
) -> str:
    """
    Build a structured prompt for WACC/ROIC narrative generation.

    Accepts either WACC-only, ROIC-only, or combined parameters.
    The prompt adapts to what is available.
    """

    has_wacc  = wacc is not None
    has_roic  = roic_current is not None
    has_spread = spread is not None

    # -- WACC section -------------------------------------------------------
    wacc_lines: List[str] = []
    if has_wacc:
        wacc_lines.append(f"WACC (Weighted Average Cost of Capital): {_fmt(wacc, as_pct=True)}")
        if cost_of_equity is not None:
            wacc_lines.append(f"Cost of Equity (CAPM): {_fmt(cost_of_equity, as_pct=True)}")
        if beta is not None:
            wacc_lines.append(f"Beta: {_fmt(beta, decimals=2)}")
        if risk_free_rate is not None:
            wacc_lines.append(f"Risk-Free Rate: {_fmt(risk_free_rate, as_pct=True)}")
        if equity_risk_premium is not None:
            wacc_lines.append(f"Equity Risk Premium: {_fmt(equity_risk_premium, as_pct=True)}")
        if equity_weight is not None:
            wacc_lines.append(f"Equity Weight: {_fmt(equity_weight, as_pct=True)}")
        if debt_weight is not None:
            wacc_lines.append(f"Debt Weight: {_fmt(debt_weight, as_pct=True)}")
        if cost_of_debt is not None:
            wacc_lines.append(f"Pre-Tax Cost of Debt: {_fmt(cost_of_debt, as_pct=True)}")
        if tax_rate is not None:
            wacc_lines.append(f"Effective Tax Rate: {_fmt(tax_rate, as_pct=True)}")

    # -- ROIC section --------------------------------------------------------
    roic_lines: List[str] = []
    if has_roic:
        roic_lines.append(f"Current ROIC: {_fmt(roic_current, as_pct=True)}")
        if roic_average_5y is not None:
            roic_lines.append(f"5-Year Average ROIC: {_fmt(roic_average_5y, as_pct=True)}")
        if roic_trend is not None:
            roic_lines.append(f"ROIC Trend: {roic_trend}")

    # -- Spread section -----------------------------------------------------
    spread_lines: List[str] = []
    if has_spread:
        direction = "positive" if spread and spread > 0 else "negative"
        spread_lines.append(f"ROIC - WACC Spread: {_fmt(spread, as_pct=True)} ({direction})")
        if spread and spread > 0:
            spread_lines.append("Interpretation: Company earns more on its capital than it costs — value creation.")
        else:
            spread_lines.append("Interpretation: Company earns less on its capital than it costs — value destruction.")

    # -- Build the prompt body ----------------------------------------------
    blocks: List[str] = []

    if has_wacc:
        blocks.append("=== WACC COMPONENTS ===\n" + "\n".join(f"  {l}" for l in wacc_lines))

    if has_roic:
        blocks.append("=== ROIC ANALYSIS ===\n" + "\n".join(f"  {l}" for l in roic_lines))

    if has_spread:
        blocks.append("=== VALUE CREATION SPREAD ===\n" + "\n".join(f"  {l}" for l in spread_lines))

    body = "\n\n".join(blocks)

    # -- Instructions -------------------------------------------------------
    if has_wacc and has_roic and has_spread:
        return f"""Analyse the WACC, ROIC, and value creation spread for {symbol.upper()}. Write a 3-4 sentence plain-English summary for retail investors.

{body}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.

Sentence 1: What is the WACC, what does it mean in plain English (is capital cheap or expensive), and what are the key drivers (beta, debt weight, cost of debt)?
Sentence 2: What is the current ROIC, how does it compare to the 5-year average, and what is the trend?
Sentence 3: Is the company creating or destroying value (ROIC vs WACC spread)? How much economic profit (or loss) per dollar of invested capital?
Sentence 4: What should an investor watch — is the trend improving or deteriorating, and what could change the WACC or ROIC materially?"""

    elif has_wacc:
        return f"""Analyse the cost of capital (WACC) for {symbol.upper()}. Write a 2-3 sentence plain-English summary.

{body}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.

Sentence 1: What is the WACC and what are its main drivers (cost of equity vs cost of debt)?
Sentence 2: Is the WACC reasonable for the company's risk profile? What does the beta and capital structure say?
Sentence 3: How does the cost of debt compare to the cost of equity, and what is the tax benefit of debt?"""

    elif has_roic:
        return f"""Analyse the Return on Invested Capital (ROIC) for {symbol.upper()}. Write a 2-3 sentence plain-English summary.

{body}

=== NOW WRITE THE SUMMARY FOR {symbol.upper()} ===
Output only the paragraph. No labels. No headers. Complete every sentence.

Sentence 1: What is the current ROIC and how does it compare historically?
Sentence 2: Is the trend improving or deteriorating, and what does that suggest about the competitive advantage?
Sentence 3: How capital-efficient is the business — does it earn a high return on every dollar invested?"""

    return ""