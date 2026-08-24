"""
Test fixtures for dividend pipeline tests (§7.6.5).

All fixtures are callable factories that compute dates relative to
date.today() so that predictions always fall in the future — no
need to freeze time or patch date.
"""

from datetime import date, timedelta
from typing import Any


def build_quarterly_8(today: date | None = None) -> list[dict[str, Any]]:
    """8 quarterly payments with last ~90 days before today.
    avg_gap ≈ 91d → quarterly band (36-100).
    Expected: next ≈ last + 3 months via relativedelta.
    """
    today = today or date.today()
    last_ex = today - timedelta(days=90)
    payments = []
    for i in range(8):
        d = last_ex - timedelta(days=91 * i)
        payments.append({
            "ex_dividend_date": d.isoformat(),
            "dividend_amount": 0.27 if i < 2 else 0.25,
            "dividend_type": "regular",
        })
    return payments


def build_monthly_12(today: date | None = None) -> list[dict[str, Any]]:
    """12 monthly payments with last ~20 days before today.
    avg_gap ≈ 30d → monthly band (≤35).
    Expected: next ≈ last + round(avg_gap) days.
    """
    today = today or date.today()
    last_ex = today - timedelta(days=20)
    payments = []
    for i in range(12):
        d = last_ex - timedelta(days=30 * i)
        payments.append({
            "ex_dividend_date": d.isoformat(),
            "dividend_amount": 0.07,
            "dividend_type": "regular",
        })
    return payments


def build_semi_annual_6(today: date | None = None) -> list[dict[str, Any]]:
    """6 semi-annual payments with last ~100 days before today.
    avg_gap ≈ 182d → semi-annual band (101-200).
    Expected: next ≈ last + 6 months via relativedelta.
    """
    today = today or date.today()
    last_ex = today - timedelta(days=100)
    amounts = [0.50, 0.50, 0.48, 0.48, 0.45, 0.45]
    payments = []
    for i in range(6):
        d = last_ex - timedelta(days=182 * i)
        payments.append({
            "ex_dividend_date": d.isoformat(),
            "dividend_amount": amounts[i],
            "dividend_type": "regular",
        })
    return payments


def build_annual_5(today: date | None = None) -> list[dict[str, Any]]:
    """5 annual payments with last ~200 days before today.
    avg_gap ≈ 365d → annual band (>200).
    Expected: next ≈ last + 1 year via relativedelta.
    """
    today = today or date.today()
    last_ex = today - timedelta(days=200)
    amounts = [1.00, 0.95, 0.90, 0.85, 0.80]
    payments = []
    for i in range(5):
        d = last_ex - timedelta(days=365 * i)
        payments.append({
            "ex_dividend_date": d.isoformat(),
            "dividend_amount": amounts[i],
            "dividend_type": "regular",
        })
    return payments


def build_quarterly_4(today: date | None = None) -> list[dict[str, Any]]:
    """Exactly 4 quarterly payments (boundary test)."""
    return build_quarterly_8(today)[:4]


def build_quarterly_with_special(today: date | None = None) -> list[dict[str, Any]]:
    """Quarterly-8 + one special dividend.
    Expected: same as quarterly-8 (special excluded).
    """
    base = build_quarterly_8(today)
    # Insert a special ~midway
    special_date = (date.fromisoformat(base[3]["ex_dividend_date"]) - timedelta(days=30)).isoformat()
    return base + [{
        "ex_dividend_date": special_date,
        "dividend_amount": 0.50,
        "dividend_type": "special",
    }]


def build_all_special(today: date | None = None) -> list[dict[str, Any]]:
    """4 all-special payments.
    Expected: falls back to raw rows (graceful degradation).
    """
    today = today or date.today()
    last_ex = today - timedelta(days=90)
    return [
        {"ex_dividend_date": (last_ex - timedelta(days=91 * i)).isoformat(),
         "dividend_amount": 0.50, "dividend_type": "special"}
        for i in range(4)
    ]


def build_insufficient_3(today: date | None = None) -> list[dict[str, Any]]:
    """Only 3 payments — < 4 guard.
    Expected: None.
    """
    return build_quarterly_8(today)[:3]


def build_self_feed(today: date | None = None) -> list[dict[str, Any]]:
    """Quarterly-8 + 2 prediction rows (NULL amount).
    Expected: same as quarterly-8 (NULL rows excluded).
    """
    base = build_quarterly_8(today)
    today_d = today or date.today()
    return base + [
        {"ex_dividend_date": (today_d + timedelta(days=90)).isoformat(),
         "dividend_amount": None, "dividend_type": "regular"},
        {"ex_dividend_date": (today_d + timedelta(days=180)).isoformat(),
         "dividend_amount": None, "dividend_type": "regular"},
    ]


def build_suspended(today: date | None = None) -> list[dict[str, Any]]:
    """Payments ending 3+ years ago — suspended payer.
    Expected: None (next_date < today guard).
    """
    today = today or date.today()
    far_past = today - timedelta(days=1100)  # ~3 years ago
    payments = []
    for i in range(8):
        d = far_past - timedelta(days=91 * i)
        payments.append({
            "ex_dividend_date": d.isoformat(),
            "dividend_amount": 0.25,
            "dividend_type": "regular",
        })
    return payments
