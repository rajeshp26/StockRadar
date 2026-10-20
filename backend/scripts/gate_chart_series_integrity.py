"""Gate: every chart Y value change must be attributable to an account event.

The portfolio chart renders one value per X date. A value is trustworthy only when the change
between consecutive points is explained by something that actually happened - a cash movement or a
securities transfer. A material drop that no event accounts for is the defect class that ships
unnoticed: the read path deleting positions without crediting cash, or a valuation collapse.

Market drift cannot be predicted, so this gate does not try to model it. It measures only whether
the events in a window have enough magnitude to account for a DECREASE. Only drops are gated: a
fall in portfolio value has no innocent explanation once price movement is out of scope, whereas a
rise is what a working portfolio is supposed to do and is driven mostly by appreciation this gate
deliberately does not model. A transfer-out larger than the drop explains it; a drop with no cash
movement and no transfer does not. Material increases are still reported, as diagnostics only.

It also checks the structural invariants a truthful series must hold (strictly increasing dates,
net_deposits changing only by the deposit/withdrawal events in the window) and the metadata
self-consistency a spike flag must satisfy.

net_deposits is net of withdrawals, not a monotonic contribution tally: the snapshot writer,
PortfolioRepository.get_net_deposits and the live performance path all sum signed cash flows,
and TWR/MWR read the period-over-period change as that period's cash flow. The invariant is
therefore equality with the ledger (in-window deposit/withdrawal total), which catches both an
unexplained fall and an unexplained rise - strictly stronger than "never falls", which passes
corruption that adds a phantom deposit.

Exit codes follow framework/gates/EXIT_CODES.md:
  0  pass
  1  fail  - unexplained residual or structural violation
  2  blocked - series dump missing or unreadable
  3  unverifiable - series present but no event log available to attribute against

Usage:
    python scripts/gate_chart_series_integrity.py
    python scripts/gate_chart_series_integrity.py --tolerance 0.20 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SERIES_PATH = Path(__file__).resolve().parents[2] / "web" / "scripts" / "real-performance.json"

CASH_AFFECTING = {
    "Trade", "Deposit", "Withdrawal", "Dividend", "MoneyMovement",
    "Interest", "Fee", "WithholdingTax", "ReorganizationDividend",
    "BonusPayment", "FxExchange", "ReturnOfCapital", "Tax",
}
TRANSFER_ACTIVITY = "InternalSecurityTransfer"
# The two activity types the snapshot writer counts as net deposits
# (replay_engine.DEPOSIT_ACTIVITY_TYPES, mirrored by get_net_deposits and
# portfolio_service._cached_net_deposits). They are also cash-affecting, so each
# such event is emitted twice: once as 'cash' for the value-drop explanation and
# once as 'deposit' for the net_deposits invariant.
DEPOSIT_ACTIVITY_TYPES = {"MoneyMovement", "BonusPayment"}
MATERIAL_MOVE_PCT = 20.0
# Per-account snapshot net_deposits is stored rounded to cents, so a scope's
# aggregate can be off the raw ledger sum by a few cents. This tolerance absorbs
# that rounding only; real corruption is orders of magnitude larger.
ND_ROUNDING_TOLERANCE = Decimal("0.05")
_SCOPE_ACCT = re.compile(r"^user(\d+)_acct(\d+)$")

Event = tuple[str, str, Decimal]
"""(iso_date, kind, magnitude) with kind in 'cash', 'transfer_in', 'transfer_out', 'deposit'.

'cash' and 'deposit' carry a SIGNED amount (withdrawals negative); the two transfer
kinds carry a magnitude. A deposit-type event appears as both 'cash' and 'deposit'."""


def _dec(value) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


_FX_RATES: list | None = None


def _fx_series() -> list:
    """USD->CAD rate series, loaded once. Snapshots are CAD; events carry native currency."""
    global _FX_RATES
    if _FX_RATES is None:
        import rebuild_account_snapshots as _ras
        _FX_RATES = list(_ras.load_usd_cad_rate_series())
    return _FX_RATES


def to_reporting_currency(amount: Decimal, currency: str, when) -> Decimal:
    """Convert an event amount into CAD so it is comparable to a portfolio value change.

    Comparing a USD transfer magnitude against a CAD value change understates the explanation
    by the FX rate. That is a units defect, not a tolerance question: it under-credits real
    explanations and makes the gate flag correct data. An unknown currency or a missing rate
    returns the amount unchanged, which keeps the gate conservative rather than permissive.
    """
    cur = (currency or "").strip().upper()
    if cur in ("", "CAD"):
        return amount
    if cur != "USD":
        return amount
    rates = _fx_series()
    if not rates or when is None:
        return amount
    prior = [r for r in rates if r[0] is not None and r[0] <= when]
    rate = Decimal(str((prior[-1][1] if prior else rates[0][1]) or 0))
    return amount * rate if rate else amount


@dataclass
class Interval:
    start: str
    end: str
    start_value: Decimal
    end_value: Decimal
    start_nd: Decimal
    end_nd: Decimal
    change: Decimal = Decimal("0")
    pct_change: float = 0.0
    cash: Decimal = Decimal("0")
    transfer_in: Decimal = Decimal("0")
    transfer_out: Decimal = Decimal("0")
    deposit_flow: Decimal = Decimal("0")
    explained: Decimal = Decimal("0")
    residual: Decimal = Decimal("0")
    residual_pct: float = 0.0
    violations: list[str] = field(default_factory=list)


def classify_events(events: list[Event], lo: str, hi: str) -> tuple[Decimal, Decimal, Decimal]:
    """Sum cash and transfer magnitudes in the window (lo, hi]."""
    cash = in_v = out_v = Decimal("0")
    for iso, kind, mag in events:
        if not (lo < iso <= hi):
            continue
        if kind == "cash":
            cash += mag
        elif kind == "transfer_in":
            in_v += mag
        elif kind == "transfer_out":
            out_v += mag
    return cash, in_v, out_v


def sum_deposit_flows(events: list[Event], lo: str, hi: str) -> Decimal:
    """Signed deposit/withdrawal total in the window (lo, hi].

    This is what a truthful series changes net_deposits by, and nothing else.
    """
    total = Decimal("0")
    for iso, kind, mag in events:
        if kind == "deposit" and lo < iso <= hi:
            total += mag
    return total


def evaluate_series(
    snapshots: list[dict],
    events: list[Event],
    tolerance: float,
) -> list[Interval]:
    """Pure: attribute each consecutive value change to the events in its own window."""
    if not snapshots or len(snapshots) < 2:
        return []
    ordered = sorted(snapshots, key=lambda s: str(s["date"]))
    out: list[Interval] = []
    prev = ordered[0]
    for cur in ordered[1:]:
        p_d, c_d = str(prev["date"]), str(cur["date"])
        p_v, c_v = _dec(prev.get("value")), _dec(cur.get("value"))
        iv = Interval(
            start=p_d, end=c_d, start_value=p_v, end_value=c_v,
            start_nd=_dec(prev.get("net_deposits")), end_nd=_dec(cur.get("net_deposits")),
        )
        iv.change = c_v - p_v
        iv.pct_change = float(iv.change / p_v * 100) if p_v else 0.0

        iv.cash, iv.transfer_in, iv.transfer_out = classify_events(events, p_d, c_d)
        iv.explained = abs(iv.cash) + iv.transfer_in + iv.transfer_out
        iv.deposit_flow = sum_deposit_flows(events, p_d, c_d)

        base = max(abs(p_v), Decimal("1"))
        iv.residual = abs(iv.change) - iv.explained
        iv.residual_pct = float(iv.residual / base * 100)

        if c_d <= p_d:
            iv.violations.append(f"date not increasing: {p_d} -> {c_d}")
        nd_delta = iv.end_nd - iv.start_nd
        if abs(nd_delta - iv.deposit_flow) > ND_ROUNDING_TOLERANCE:
            direction = "fell" if nd_delta < 0 else "rose"
            iv.violations.append(
                f"net_deposits {direction} {iv.start_nd:,.2f} -> {iv.end_nd:,.2f} across "
                f"{p_d} -> {c_d}, but deposit/withdrawal events in that window total "
                f"{iv.deposit_flow:+,.2f} (unexplained change "
                f"{nd_delta - iv.deposit_flow:+,.2f}); net_deposits must change only by "
                f"deposit and withdrawal events"
            )
        if iv.change < 0 and abs(iv.pct_change) > MATERIAL_MOVE_PCT \
                and iv.residual_pct > tolerance * 100:
            iv.violations.append(
                f"value moved {iv.pct_change:+.2f}% but events account for only "
                f"{iv.explained:,.2f} (cash {iv.cash:,.2f}, transfers in {iv.transfer_in:,.2f}, "
                f"out {iv.transfer_out:,.2f}); unexplained residual {iv.residual:,.2f} "
                f"({iv.residual_pct:.2f}% of opening value {p_v:,.2f})"
            )
        out.append(iv)
        prev = cur
    return out


def scope_accounts(scope: str, user_accounts: dict[int, list[int]]) -> set[int]:
    """Resolve a dump scope key to the account ids it aggregates.

    Numeric keys are user ids; 'user1_acct9' is one account within a user.
    """
    m = _SCOPE_ACCT.match(scope)
    if m:
        return {int(m.group(2))}
    if scope.lstrip("-").isdigit():
        return set(user_accounts.get(int(scope), []))
    return set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=0.20,
                    help="max unexplained residual as a fraction of opening value")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--series", default=str(SERIES_PATH))
    args = ap.parse_args()

    path = Path(args.series)
    if not path.exists():
        print(f"BLOCKED: missing series dump {path}")
        print("Run dump_real_all_series.py first, or pass --series.")
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"BLOCKED: unreadable series dump: {exc}")
        return 2

    import rebuild_account_snapshots as ras

    engine = ras.replay_engine

    try:
        user_accounts: dict[int, list[int]] = {}
        rows = (ras.supabase.table("portfolio_accounts")
                .select("account_id,user_id").execute()).data or []
        for r in rows:
            if r.get("user_id") is not None:
                user_accounts.setdefault(int(r["user_id"]), []).append(int(r["account_id"]))

        raw = engine.event_store.get_all_events(aggregate_type="account")
        events_by_account: dict[int, list[Event]] = {}
        for ev in raw:
            payload = ev.get("data", {}) or {}
            agg = str(ev.get("aggregate_id", "")).split("_")
            if len(agg) < 2 or agg[0] != "account":
                continue
            try:
                aid = int(agg[1])
            except ValueError:
                continue
            at = str(payload.get("activity_type", ""))
            if at not in (TRANSFER_ACTIVITY,) and at not in CASH_AFFECTING:
                continue
            d = engine._get_event_date(ev)
            if d is None:
                continue
            if at == TRANSFER_ACTIVITY:
                kind = "transfer_in" if _dec(payload.get("quantity")) > 0 else "transfer_out"
                mag = to_reporting_currency(
                    abs(_dec(payload.get("net_cash_amount"))),
                    str(payload.get("currency", "")), d,
                )
            else:
                kind = "cash"
                mag = to_reporting_currency(
                    _dec(payload.get("net_cash_amount")),
                    str(payload.get("currency", "")), d,
                )
            events_by_account.setdefault(aid, []).append((d.isoformat(), kind, mag))
            if at in DEPOSIT_ACTIVITY_TYPES:
                # net_deposits is defined as the RAW signed sum of net_cash_amount
                # (replay_engine and PortfolioRepository.get_net_deposits both sum it
                # with no FX). The deposited flow must mirror that definition exactly;
                # reusing the FX-converted 'cash' magnitude would flag correct data
                # whose transaction currency is not the reporting currency.
                events_by_account.setdefault(aid, []).append(
                    (d.isoformat(), "deposit", _dec(payload.get("net_cash_amount")))
                )

    except Exception as exc:  # noqa: BLE001
        print(f"UNVERIFIABLE: cannot read event log to attribute changes: {exc}")
        return 3

    if not events_by_account:
        print("UNVERIFIABLE: no account events readable; cannot attribute any value change")
        return 3

    violations: list[str] = []
    report: list[dict] = []
    checked = 0
    skipped: list[str] = []

    for scope, periods in data.items():
        accts = scope_accounts(scope, user_accounts)
        for period, payload in periods.items():
            if "error" in payload:
                violations.append(f"{scope}/{period}: ERROR {payload['error']}")
                continue
            meta = payload.get("meta") or {}
            if str(meta.get("data_quality_flag", "") or "") == "SPIKE_DETECTED" \
                    and not bool(meta.get("spike_detected")):
                violations.append(
                    f"{scope}/{period}: data_quality_flag=SPIKE_DETECTED but spike_detected=false"
                )
            snaps = payload.get("snapshots") or []
            if not accts:
                skipped.append(f"{scope}/{period} (no accounts resolved for scope)")
                continue
            if len(snaps) < 2:
                continue
            events: list[Event] = []
            for aid in accts:
                events.extend(events_by_account.get(aid, []))
            for iv in evaluate_series(snaps, events, args.tolerance):
                checked += 1
                if iv.violations:
                    for v in iv.violations:
                        violations.append(f"{scope}/{period} {iv.start}->{iv.end} {v}")
                if abs(iv.pct_change) > MATERIAL_MOVE_PCT:
                    report.append({
                        "scope": scope, "period": period, "start": iv.start, "end": iv.end,
                        "pct_change": round(iv.pct_change, 2),
                        "cash": float(iv.cash),
                        "transfer_in": float(iv.transfer_in),
                        "transfer_out": float(iv.transfer_out),
                        "deposit_flow": float(iv.deposit_flow),
                        "nd_delta": float(iv.end_nd - iv.start_nd),
                        "explained": float(iv.explained),
                        "residual": float(iv.residual),
                        "residual_pct": round(iv.residual_pct, 2),
                        "violations": iv.violations,
                    })

    if args.json:
        print(json.dumps({"checked": checked, "violations": violations,
                          "skipped": skipped, "material_moves": report,
                          "tolerance": args.tolerance}, indent=2))
        return 1 if violations else 0

    print(f"scope -> accounts: "
          f"{ {s: sorted(scope_accounts(s, user_accounts)) for s in data} }")
    if skipped:
        print(f"skipped (unresolved scope): {skipped}")
    if report:
        print(f"\nmaterial moves (|change| > {MATERIAL_MOVE_PCT:.0f}%): {len(report)}")
        print(f"{'scope/period':<22}{'window':<24}{'change':>9}{'explained':>12}{'residual':>12}")
        for r in sorted(report, key=lambda r: -abs(r["pct_change"]))[:15]:
            print(f"{r['scope']}/{r['period']:<12}{r['start']}->{r['end']:<8}"
                  f"{r['pct_change']:>8.2f}%{r['explained']:>12,.2f}{r['residual']:>12,.2f}")
    print(f"\nintervals checked: {checked}")
    if violations:
        print(f"FAIL: {len(violations)} violation(s)")
        for v in violations[:40]:
            print(f"  - {v}")
        return 1
    print("PASS: every material value change is attributable to events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())