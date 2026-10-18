# validate_perf_table.py
# READ-ONLY. Compares a user-supplied quarter-end table (Net invested / SPY / QQQ)
# against the app's own data:
#   Net invested <- MoneyMovement + BonusPayment net_cash_amount, FX-converted to
#                   the account currency at the transaction date (same rule as
#                   portfolio_service._cached_net_deposits).
#   SPY / QQQ    <- DCA simulation: every net deposit is notionally invested in
#                   the ETF at its transaction date using price_history closes,
#                   then valued at each quarter end.
# Nothing is mutated. Every table read is a select.
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402
from shared.fx_service import FXService  # noqa: E402

# Quarter-end valuation dates implied by the user's table.
QUARTER_ENDS: list[tuple[str, str]] = [
    ("2021 Q1", "2021-03-31"), ("2021 Q2", "2021-06-30"), ("2021 Q3", "2021-09-30"),
    ("2021 Q4", "2021-12-31"), ("2022 Q1", "2022-03-31"), ("2022 Q2", "2022-06-30"),
    ("2022 Q3", "2022-09-30"), ("2022 Q4", "2022-12-31"), ("2023 Q1", "2023-03-31"),
    ("2023 Q2", "2023-06-30"), ("2023 Q3", "2023-09-30"), ("2023 Q4", "2023-12-31"),
    ("2024 Q1", "2024-03-31"), ("2024 Q2", "2024-06-30"), ("2024 Q3", "2024-09-30"),
    ("2024 Q4", "2024-12-31"), ("2025 Q1", "2025-03-31"), ("2025 Q2", "2025-06-30"),
    ("2025 Q3", "2025-09-30"), ("2025 Q4", "2025-12-31"), ("2026 Q1", "2026-03-31"),
    ("2026 Q2", "2026-06-30"), ("2026 Q3", "2026-09-30"), ("Latest", "2026-10-16"),
]

# The user's table, transcribed exactly.
USER_TABLE: list[tuple[str, float, float, float]] = [
    ("2021 Q1", 3500, 3674, 3551), ("2021 Q2", 5750, 6291, 6316),
    ("2021 Q3", 7000, 7542, 7596), ("2021 Q4", 8000, 9438, 9499),
    ("2022 Q1", 13000, 14159, 13852), ("2022 Q2", 24000, 21845, 20390),
    ("2022 Q3", 29200, 25549, 24203), ("2022 Q4", 31210, 29582, 26151),
    ("2023 Q1", 35710, 36424, 36409), ("2023 Q2", 37760, 41744, 44212),
    ("2023 Q3", 41460, 43962, 46500), ("2023 Q4", 41460, 49079, 53285),
    ("2024 Q1", 47132, 60361, 63921), ("2024 Q2", 47132, 63004, 69085),
    ("2024 Q3", 47132, 66628, 70475), ("2024 Q4", 49514, 70614, 76331),
    ("2025 Q1", 54870, 72680, 75072), ("2025 Q2", 55419, 81106, 89017),
    ("2025 Q3", 60451, 92902, 102233), ("2025 Q4", 64449, 99378, 108716),
    ("2026 Q1", 68735, 99184, 106426), ("2026 Q2", 70735, 116179, 137935),
    ("2026 Q3", 95130, 143607, 164230), ("Latest", 96130, 147530, 166078),
]


def page(table: str, cols: str, batch: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        part = (
            supabase.table(table).select(cols)
            .range(start, start + batch - 1).execute().data or []
        )
        rows.extend(part)
        if len(part) < batch:
            break
        start += batch
    return rows


def to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def main() -> int:
    fx = FXService(supabase)

    # ── accounts + currency ────────────────────────────────────────────
    accts = page("portfolio_accounts", "account_id, user_id, currency, is_active")
    acct_ccy = {a["account_id"]: (a.get("currency") or "CAD").upper() for a in accts}
    print(f"accounts: {len(accts)}  currencies: "
          f"{sorted(set(acct_ccy.values())) or '(none)'}")

    # ── cash-flow transactions (deposits/withdrawals) ──────────────────
    txn_cols = ("account_id, transaction_date, net_cash_amount, currency, "
                "activity_type")
    txns = page("portfolio_transactions", txn_cols)
    flows = [t for t in txns if (t.get("activity_type") or "") in
             ("MoneyMovement", "BonusPayment")]
    print(f"cash-flow transactions: {len(flows)} of {len(txns)} total")

    if not flows:
        print("NO CASH-FLOW DATA - cannot validate net invested")
        return 2

    dated = [to_date(t["transaction_date"]) for t in flows]
    print(f"flow date range: {min(d for d in dated if d)} .. "
          f"{max(d for d in dated if d)}")

    # Convert every flow to a single report currency (the report is in $,
    # so USD; each flow is first converted into its own account currency by
    # the app, then we take the account-currency total as-is and also show
    # a USD-converted variant when the account is not USD).
    per_day: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    per_day_usd: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in flows:
        d = to_date(t["transaction_date"])
        amt = Decimal(str(t.get("net_cash_amount") or 0))
        ccy = (t.get("currency") or acct_ccy.get(t["account_id"], "CAD")).upper()
        per_day[d] += amt
        if ccy == "USD":
            per_day_usd[d] += amt
        else:
            rate = fx.get_rate(ccy, "USD", d)
            per_day_usd[d] += amt * rate if rate else Decimal("0")

    # ── ETF prices from price_history (same table the app uses) ────────
    def etf_prices(symbol: str) -> dict[date, Decimal]:
        ctx = (supabase.table("companies")
               .select("company_id").eq("ticker_symbol", symbol.upper()).limit(1)
               .execute().data)
        if not ctx:
            print(f"  {symbol}: NOT FOUND in companies")
            return {}
        cid = ctx[0]["company_id"]
        rows: list[dict] = []
        start = 0
        while True:
            part = (supabase.table("price_history")
                    .select("price_date, close_price")
                    .eq("company_id", cid)
                    .order("price_date").range(start, start + 999).execute().data or [])
            rows.extend(part)
            if len(part) < 1000:
                break
            start += 1000
        out = {to_date(r["price_date"]): Decimal(str(r["close_price"]))
               for r in rows if r.get("close_price")}
        print(f"  {symbol}: company_id={cid} prices={len(out)} "
              f"range={min(out) if out else '-'} .. {max(out) if out else '-'}")
        return out

    print("\nprice_history:")
    spy_px = etf_prices("SPY")
    qqq_px = etf_prices("QQQ")

    def last_on_or_before(prices: dict[date, Decimal], d: date) -> Decimal | None:
        best = None
        for pd_, px in prices.items():
            if pd_ <= d and (best is None or pd_ > best[0]):
                best = (pd_, px)
        return best[1] if best else None

    # ── compute per quarter end ────────────────────────────────────────
    print("\n" + "=" * 130)
    print(f"{'Quarter':<10} {'Net inv (app)':>14} {'User NI':>10} {'d NI':>10} "
          f"{'SPY nofx':>12} {'User SPY':>10} {'d SPY nf':>10} "
          f"{'QQQ nofx':>12} {'User QQQ':>10} {'d QQQ nf':>10} "
          f"| {'SPY usd':>10} {'QQQ usd':>10}")
    print("=" * 130)

    cumulative = Decimal("0")
    cumulative_usd = Decimal("0")
    spy_units = Decimal("0")
    qqq_units = Decimal("0")
    # Variant B: same DCA but the CAD flow is treated 1:1 as USD (no FX).
    # This tests whether the user's table came from a simulation that ignored
    # the CAD->USD conversion (all 6 accounts are CAD; SPY/QQQ trade in USD).
    spy_units_nofx = Decimal("0")
    qqq_units_nofx = Decimal("0")
    running = sorted(per_day.items())          # native CAD, for no-FX variant
    running_usd = sorted(per_day_usd.items())  # USD-converted
    idx = 0
    idx_usd = 0

    user_by_q = {q: (ni, s, k) for q, ni, s, k in USER_TABLE}

    for q, d_str in QUARTER_ENDS:
        qd = date.fromisoformat(d_str)
        while idx < len(running) and running[idx][0] <= qd:
            flow_date, amt_native = running[idx]
            for px_map, box in ((spy_px, "spy"), (qqq_px, "qqq")):
                px = last_on_or_before(px_map, flow_date)
                if px is not None and px > 0:
                    if box == "spy":
                        spy_units_nofx += amt_native / px
                    else:
                        qqq_units_nofx += amt_native / px
            idx += 1
        while idx_usd < len(running_usd) and running_usd[idx_usd][0] <= qd:
            flow_date, amt_usd = running_usd[idx_usd]
            for px_map, box in ((spy_px, "spy"), (qqq_px, "qqq")):
                px = last_on_or_before(px_map, flow_date)
                if px is not None and px > 0:
                    if box == "spy":
                        spy_units += amt_usd / px
                    else:
                        qqq_units += amt_usd / px
            idx_usd += 1
        # cumulative net invested in native account-currency sum
        native = sum(a for fd, a in per_day.items() if fd <= qd)

        spy_v = last_on_or_before(spy_px, qd)
        qqq_v = last_on_or_before(qqq_px, qd)
        spy_val = spy_units * spy_v if spy_v else Decimal("0")
        qqq_val = qqq_units * qqq_v if qqq_v else Decimal("0")
        spy_val_nf = spy_units_nofx * spy_v if spy_v else Decimal("0")
        qqq_val_nf = qqq_units_nofx * qqq_v if qqq_v else Decimal("0")

        u_ni, u_spy, u_qqq = user_by_q.get(q, (0, 0, 0))
        d_ni = float(native) - u_ni
        d_spy = float(spy_val) - u_spy
        d_qqq = float(qqq_val) - u_qqq
        d_spy_nf = float(spy_val_nf) - u_spy
        d_qqq_nf = float(qqq_val_nf) - u_qqq

        print(f"{q:<10} {float(native):>14,.0f} {u_ni:>10,.0f} {d_ni:>+10,.0f} "
              f"{float(spy_val_nf):>12,.0f} {u_spy:>10,.0f} {d_spy_nf:>+10,.0f} "
              f"{float(qqq_val_nf):>12,.0f} {u_qqq:>10,.0f} {d_qqq_nf:>+10,.0f} "
              f"| {float(spy_val):>10,.0f} {float(qqq_val):>10,.0f}")

    print("=" * 130)
    print("Net inv (app) = sum of net_cash_amount in native CAD")
    print("SPY/QQQ (user-vs-nofx) = DCA treating CAD flow as USD 1:1 (no FX)")
    print("SPY/QQQ (usd-conv)     = DCA of FX-converted-to-USD flow (right two cols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
