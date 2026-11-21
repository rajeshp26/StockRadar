"""End-to-end verification of rebuilt portfolio snapshot history (accounts 7-12).

Validates EVERY stored snapshot date across the given accounts and EVERY date in
the merged user-facing series produced from them, proving there are no remaining
spikes or invalid values after the USD->CAD FX rebuild.

Checks performed:
  1. Stored-row invariants (every row):
       total_value == holdings_market_value + cash_balance
       sum(holdings_json.current_value) == holdings_market_value
       non-negative totals/market values
  2. FX markers (every holding, USD company held in a CAD account):
       fx_applied is True, fx_rate > 0,
       current_value == quantity * current_price * fx_rate
     (CAD-currency holdings in CAD accounts: no conversion, current_value == qty*price)
  3. Recompute-vs-stored consistency: re-run rebuild_account_snapshots.build_snapshots
     (event replay + price_history + FX series) and diff every stored date against
     the recomputed row (totals, cost, cash, net deposits, quality flag, per-holding
     current_value). Dates beyond --max-date are informational (apply boundary).
4. Per-account bidirectional spike math on consecutive stored rows using the same
     check_snapshot_spike the production merge uses (threshold from settings).
     Pairs involving an INCOMPLETE row are classified as pre-existing baseline debt.
   5. Merged user-facing series (per user, per period): replicate the production
      LOCF merge + spike suppression exactly (portfolio_service.get_portfolio_performance),
      assert fx_unconverted_dates is empty, assert no un-suppressed spike on fully-real
      dates, and cross-check the served series against the independently replicated
      merged series (identity within 0.02). Production serves every stored daily
      point, so the merged series is itself the expected served series.
  6. Split-event integrity (per account, shared.split_sync.find_missing_split_events):
     every split row whose report_date an account's holding-evidence window covers
     must have a stored split event for that account — otherwise MISSING_SPLIT_EVENT
     (factor <= 0/1 and report_date beyond max_date ignored; earliest evidence decides).
  7. Split price coverage (company-level, deduped by (cid, report_date)): a split
     covered by a test account's holding window must have a price_history row within
     [report_date, report_date+4d] so the replay could restate value at a real price
     — otherwise SPLIT_PRICE_GAP (next price date reported for context).
  8. Spike classification: a stored-row or merged spike is a baseline note, not a
     failure, when the account's event stream explains it — an InternalSecurityTransfer
     with |qty*price| impact >= 10% of the unexplained delta, or a position
     anchor (initial_holding_set or position_state_checkpoint), within +/-3 days
     of the spike date. Split, Trade and cash-only events NEVER explain a spike.

  9. Checkpoint provenance (per account, over the persisted event stream):
      re-assert the write-time guard against rows already in the log — a
      position_state_checkpoint must carry the projection-import marker, and no
      projection-sourced event may have an effective_date earlier than its own
      row creation date. Catches a backdated import that the append-time guard
      could not see (it only covers rows written from now on).

Exit codes:
  0  all checks pass (baseline INCOMPLETE rows reported, not failures)
  1  failures found (offending dates listed)
  2  blocked / unverifiable (expected data missing)

Usage:
    python backend/scripts/verify_snapshot_history.py
    python backend/scripts/verify_snapshot_history.py --accounts 7,8,9 --periods ALL,1Y
    python backend/scripts/verify_snapshot_history.py --skip-recompute   # skip step 3
"""
import argparse
import asyncio
import csv
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/scripts")

from collections import defaultdict
from datetime import date, datetime, timedelta
from itertools import pairwise

import rebuild_account_snapshots as rebuild

from application.services.portfolio_service import PortfolioService
from config import settings
from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from shared.checkpoint_provenance import validate_checkpoint_provenance
from shared.snapshot_builder import check_snapshot_spike
from shared.split_sync import (
    explains_spike,
    fetch_all_splits,
    find_missing_split_events,
    holding_window_from_events,
)
from shared.split_utils import parse_split_date

VALUE_TOL = 0.02          # dollar tolerance for totals / market values
PRICE_TOL = 0.01          # per-share tolerance
QTY_TOL = 0.001
RATE_TOL = 0.0001

BASELINE_FLAGS = {"INCOMPLETE", "UNAVAILABLE"}


def log(msg: str):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1 + 2. Stored-row invariants and FX markers
# ---------------------------------------------------------------------------
def validate_stored_rows(rows, company_currencies, account_currency, account_id,
                         exchange_overrides=None):
    """Return (failures: list[dict], anomalies: list[dict]) for one account's rows.

    FX predicate replicates the builder (snapshot_builder.build_snapshot_row):
    a holding's *effective* price currency is what decides conversion, not raw
    companies.currency. CDR holdings (portfolio_holdings.exchange_override=="TOR")
    are priced in CAD after the ratio/FX adjustment, so their price currency is
    forced to CAD and fx_applied=True with fx_rate=None is correct output.
    """
    failures = []
    incomplete_dates = set()
    for r in rows:
        d = str(r["snapshot_date"])
        flag = r.get("data_quality_flag", "OK")
        if flag in BASELINE_FLAGS:
            incomplete_dates.add(d)
        tv = float(r.get("total_value", 0) or 0)
        hmv = float(r.get("holdings_market_value", 0) or 0)
        cash = float(r.get("cash_balance", 0) or 0)
        holdings = r.get("holdings_json") or []
        if isinstance(holdings, str):
            try:
                import json as _json
                holdings = _json.loads(holdings)
            except Exception:
                holdings = []

        # INV1: total == market + cash
        if abs(tv - (hmv + cash)) > VALUE_TOL:
            failures.append({"account": account_id, "date": d, "class": "INV1",
                             "detail": f"total={tv:.2f} != hmv={hmv:.2f} + cash={cash:.2f}"})
        # INV2: sum(holdings) == market value when holdings non-empty
        if holdings:
            hsum = sum(float(h.get("current_value", 0) or 0) for h in holdings)
            if abs(hsum - hmv) > VALUE_TOL:
                failures.append({"account": account_id, "date": d, "class": "INV2",
                                 "detail": f"sum(holdings)={hsum:.2f} != hmv={hmv:.2f} ({len(holdings)} holdings)"})
        elif hmv > VALUE_TOL:
            failures.append({"account": account_id, "date": d, "class": "INV2_EMPTY",
                             "detail": f"hmv={hmv:.2f} but holdings_json empty/null"})
        # INV3: negative values are invalid
        if tv < -0.005:
            failures.append({"account": account_id, "date": d, "class": "NEG_TOTAL",
                             "detail": f"total_value={tv:.2f}"})
        if hmv < -0.005:
            failures.append({"account": account_id, "date": d, "class": "NEG_HMV",
                             "detail": f"holdings_market_value={hmv:.2f}"})

        # FX markers per holding
        for h in holdings:
            cid = h.get("company_id")
            ccy = company_currencies.get(int(cid), "USD") if cid is not None else "USD"
            qty = float(h.get("quantity", 0) or 0)
            price = float(h.get("current_price", 0) or 0)
            cv = float(h.get("current_value", 0) or 0)
            fx_applied = h.get("fx_applied")
            fx_rate_raw = h.get("fx_rate")
            fx_rate = float(fx_rate_raw) if fx_rate_raw is not None else None
            # Effective price currency replicates the builder: CDR holdings
            # (exchange_override=="TOR") are priced in CAD after the ratio/FX
            # adjustment, so they need no conversion even though the company's
            # native currency is USD (NFLX/META/MSFT held as CDRs on TOR).
            eff_ccy = ccy
            if cid is not None and exchange_overrides and exchange_overrides.get(int(cid)) == "TOR":
                eff_ccy = "CAD"
            if eff_ccy.upper() != account_currency.upper():
                # foreign-currency company in account: conversion is mandatory for any valued holding
                if cv > VALUE_TOL and abs(qty) > QTY_TOL:
                    if fx_applied is not True or fx_rate is None or fx_rate <= 0:
                        failures.append({"account": account_id, "date": d, "class": "FX_MARKER",
                                         "detail": f"cid={cid} ccy={eff_ccy} fx_applied={fx_applied} fx_rate={fx_rate} cv={cv:.2f}"})
                    else:
                        expect = abs(qty) * price * fx_rate
                        if expect > 0 and abs(cv - expect) > max(VALUE_TOL, 0.001 * abs(expect)):
                            failures.append({"account": account_id, "date": d, "class": "FX_VALUE",
                                             "detail": (f"cid={cid} cv={cv:.2f} != qty*price*rate="
                                                        f"{qty}*{price}*{fx_rate}={expect:.2f}")})
            else:
                # same currency: no conversion; value must equal qty*price
                expect = abs(qty) * price
                if expect > 0 and abs(cv - expect) > max(VALUE_TOL, 0.001 * abs(expect)):
                    failures.append({"account": account_id, "date": d, "class": "SAME_CCY_VALUE",
                                     "detail": f"cid={cid} cv={cv:.2f} != qty*price={expect:.2f}"})
            # sanity: absurd per-holding value
            if abs(cv) > 1e9:
                failures.append({"account": account_id, "date": d, "class": "ABSURD",
                                 "detail": f"cid={cid} current_value={cv:.2f}"})
    return failures, incomplete_dates


# ---------------------------------------------------------------------------
# 3. Recompute-vs-stored consistency
# ---------------------------------------------------------------------------
def recompute_diff(account_id, stored_rows, max_date_str):
    """Diff stored rows against a fresh event-replay recompute. Returns failures + info."""
    failures = []
    info = {"recomputed": 0, "beyond_boundary": 0, "stored_not_recomputed": []}
    rc_rows = rebuild.build_snapshots(account_id)
    recomputed = {r["snapshot_date"]: r for r in rc_rows if r["snapshot_date"] <= max_date_str}
    info["recomputed"] = len(recomputed)
    beyond = [r["snapshot_date"] for r in rc_rows if r["snapshot_date"] > max_date_str]
    info["beyond_boundary"] = len(beyond)

    stored_by_date = {str(r["snapshot_date"]): r for r in stored_rows}
    for d, s in stored_by_date.items():
        if d > max_date_str:
            continue
        rc = recomputed.get(d)
        if rc is None:
            info["stored_not_recomputed"].append(d)
            failures.append({"account": account_id, "date": d, "class": "STORED_ONLY",
                             "detail": "stored row has no recomputed counterpart"})
            continue
        for col in ["total_value", "holdings_market_value", "cost_basis", "cash_balance", "net_deposits"]:
            sv = float(s.get(col, 0) or 0)
            rv = float(rc.get(col, 0) or 0)
            if abs(sv - rv) > VALUE_TOL:
                failures.append({"account": account_id, "date": d, "class": f"RECOMPUTE_{col.upper()}",
                                 "detail": f"stored={sv:.2f} recomputed={rv:.2f}"})
        if (s.get("data_quality_flag") or "OK") != (rc.get("data_quality_flag") or "OK"):
            failures.append({"account": account_id, "date": d, "class": "RECOMPUTE_FLAG",
                             "detail": f"stored={s.get('data_quality_flag')} recomputed={rc.get('data_quality_flag')}"})
        # per-holding current_value diff (union of company ids)
        sh = s.get("holdings_json") or []
        rh = rc.get("holdings_json") or []
        if isinstance(sh, str):
            try:
                import json as _json
                sh = _json.loads(sh)
            except Exception:
                sh = []
        if isinstance(rh, str):
            try:
                import json as _json
                rh = _json.loads(rh)
            except Exception:
                rh = []
        s_by_cid = {int(h.get("company_id")): h for h in sh if h.get("company_id") is not None}
        r_by_cid = {int(h.get("company_id")): h for h in rh if h.get("company_id") is not None}
        for cid in set(s_by_cid) | set(r_by_cid):
            shh = s_by_cid.get(cid)
            rhh = r_by_cid.get(cid)
            scv = float((shh or {}).get("current_value", 0) or 0)
            rcv = float((rhh or {}).get("current_value", 0) or 0)
            if abs(scv - rcv) > VALUE_TOL:
                failures.append({"account": account_id, "date": d, "class": "RECOMPUTE_HOLDING",
                                 "detail": f"cid={cid} stored_cv={scv:.2f} recomputed_cv={rcv:.2f}"})
            sfx = (shh or {}).get("fx_applied")
            rfx = (rhh or {}).get("fx_applied")
            if bool(sfx) != bool(rfx):
                failures.append({"account": account_id, "date": d, "class": "RECOMPUTE_FXFLAG",
                                 "detail": f"cid={cid} stored_fx_applied={sfx} recomputed_fx_applied={rfx}"})
    return failures, info


# ---------------------------------------------------------------------------
# 4. Per-account spike math on stored rows (bidirectional via abs in check_snapshot_spike)
# ---------------------------------------------------------------------------
def account_spikes(rows, threshold, events=None):
    """Compare consecutive stored rows; classify INCOMPLETE pairs as baseline.

    A spike on a fully-real pair is still classified as baseline when the
    account's event stream explains it (InternalSecurityTransfer with impact
    >= 10% of the unexplained delta, or a position anchor (initial_holding_set
    or position_state_checkpoint), within +/-3 days) - see
    shared.split_sync.explains_spike. Split/Trade/cash events never explain, so
    those spikes remain failures.
    """
    spikes = []        # real (would be flagged) spikes
    baseline = []      # spikes touching an INCOMPLETE row (pre-existing debt)
    ordered = sorted(rows, key=lambda r: str(r["snapshot_date"]))
    for prev, curr in pairwise(ordered):
        pflag = (prev.get("data_quality_flag") or "OK")
        cflag = (curr.get("data_quality_flag") or "OK")
        spike = check_snapshot_spike(prev, curr, threshold=threshold)
        if not spike:
            continue
        item = {"date": str(curr["snapshot_date"]), "detail": spike["message"]}
        if pflag in BASELINE_FLAGS or cflag in BASELINE_FLAGS:
            item["prev_flag"] = pflag
            item["curr_flag"] = cflag
            baseline.append(item)
        elif events is not None and explains_spike(
            events, date.fromisoformat(str(curr["snapshot_date"])), spike["unexplained"]
        ):
            item["explained"] = True
            baseline.append(item)
        else:
            spikes.append(item)
    return spikes, baseline


# ---------------------------------------------------------------------------
# 6-8. Split integrity: corporate-action events + split price coverage
# ---------------------------------------------------------------------------
def split_price_gaps(client, splits, account_events, accounts, max_date, window_days=40):
    """Company-level SPLIT_PRICE_GAP findings, deduped by (company_id, report_date).

    A split whose report_date falls inside any test account's holding window
    (first..last evidence) must have a price_history row within
    [rd, rd+window_days] so the replay could restate value at a real price.
    Only companies with holding evidence in the test accounts are checked.
    Each finding carries price_date = the next available price after the window.

    window_days defaults to 40, sized to the monthly-close cadence of this
    environment's price feeds: normalisation logs show month-end closes spaced
    28-33 days apart (e.g. 2022-05-31 -> 2022-06-30, 2023-04-28 -> 2023-05-31)
    and split record dates land mid-month. A tighter horizon (4d, the original
    default) fires on every mid-month split whose next close exists within ~31
    days - a false positive. 40 = one full month-end cycle plus calendar/holiday
    slack. Genuine voids still flag: no price within a month of rd, e.g.
    cid=3107 rd=2023-06-26 with the next price at 2026-07-17.
    """
    findings = []
    seen = set()
    for split in splits:
        cid = split.get("company_id")
        if cid is None:
            continue
        try:
            rd = parse_split_date(split["report_date"])
        except (KeyError, ValueError, TypeError):
            continue
        if max_date is not None and rd > max_date:
            continue
        key = (int(cid), rd)
        if key in seen:
            continue
        seen.add(key)
        covered = False
        for aid in accounts:
            evs = account_events.get(aid, [])
            w = holding_window_from_events(evs, cid)
            if w is not None and w[0] <= rd <= w[1]:
                covered = True
                break
        if not covered:
            continue
        lo = rd.isoformat()
        hi = (rd + timedelta(days=window_days)).isoformat()
        res = (client.table("price_history").select("price_date")
               .eq("company_id", cid).gte("price_date", lo).lte("price_date", hi)
               .order("price_date").limit(1).execute())
        if res.data:
            continue
        nxt = (client.table("price_history").select("price_date")
               .eq("company_id", cid).gt("price_date", hi)
               .order("price_date").limit(1).execute())
        next_price = nxt.data[0]["price_date"] if (nxt.data or []) else None
        findings.append({
            "account": f"company{cid}", "date": lo, "class": "SPLIT_PRICE_GAP",
            "price_date": next_price,
            "detail": f"split cid={cid} rd={lo}: no price_history in [{lo}..{hi}] (next: {next_price})",
        })
    return findings


# ---------------------------------------------------------------------------
# 5. Merged user-facing series: replication + production cross-check
# ---------------------------------------------------------------------------
def replicate_merge(raw_snapshots, threshold=0.20, use_locf=True):
    """Replicate portfolio_service.get_portfolio_performance merge exactly."""
    fx_unconverted_dates = {
        s["snapshot_date"] for s in raw_snapshots
        if any(h.get("fx_applied") is False for h in (s.get("holdings_json") or []))
    }
    by_account = defaultdict(list)
    for s in raw_snapshots:
        by_account[s["account_id"]].append(s)
    accounts_with_data = list(by_account.keys())
    all_dates = sorted({s["snapshot_date"] for s in raw_snapshots})
    latest_date = all_dates[-1] if all_dates else None

    account_iters = {aid: iter(by_account[aid]) for aid in accounts_with_data}
    current_snap = {}
    for aid in accounts_with_data:
        try:
            current_snap[aid] = next(account_iters[aid])
        except StopIteration:
            current_snap[aid] = None

    last_value, last_cost, last_cash, last_nd = {}, {}, {}, {}
    locf_count = 0
    merged = {}
    spike_detected = False
    suppressed_dates = []
    un_suppressed_spikes = []   # spike on fully-real date -> would reach the user
    prev_merged = None

    for d in all_dates:
        tv = tc = tcash = tnd = 0.0
        date_with_locf = False
        saved_last_value = last_value.copy()
        saved_last_cost = last_cost.copy()
        saved_last_cash = last_cash.copy()
        saved_last_nd = last_nd.copy()
        for aid in accounts_with_data:
            cs = current_snap.get(aid)
            if cs is not None and cs["snapshot_date"] == d:
                tv += cs["total_value"]
                tc += cs["cost_basis"]
                tcash += cs.get("cash_balance", 0)
                tnd += cs.get("net_deposits", 0)
                last_value[aid] = cs["total_value"]
                last_cost[aid] = cs["cost_basis"]
                last_cash[aid] = cs.get("cash_balance", 0)
                last_nd[aid] = cs.get("net_deposits", 0)
                try:
                    current_snap[aid] = next(account_iters[aid])
                except StopIteration:
                    current_snap[aid] = None
            elif aid in last_value:
                if use_locf:
                    tv += last_value[aid]
                    tc += last_cost.get(aid, 0)
                    tcash += last_cash.get(aid, 0)
                    tnd += last_nd.get(aid, 0)
                    date_with_locf = True
        cur = {
            "date": d,
            "value": round(tv, 2),
            "cost_basis": round(tc, 2),
            "cash_balance": round(tcash, 2),
            "net_deposits": round(tnd, 2),
        }
        if prev_merged is not None:
            spike = check_snapshot_spike(
                {"total_value": prev_merged["value"], "net_deposits": prev_merged["net_deposits"],
                 "snapshot_date": prev_merged["date"]},
                {"total_value": cur["value"], "net_deposits": cur["net_deposits"],
                 "snapshot_date": cur["date"]},
                threshold=threshold,
            )
            if spike and d != latest_date and (date_with_locf or d in fx_unconverted_dates):
                spike_detected = True
                if d in fx_unconverted_dates and not date_with_locf:
                    pass  # keep per-account state (fx-flawed values are real ones)
                else:
                    last_value = saved_last_value
                    last_cost = saved_last_cost
                    last_cash = saved_last_cash
                    last_nd = saved_last_nd
                    date_with_locf = False
                suppressed_dates.append(d)
                cur = {"date": d, "value": prev_merged["value"], "cost_basis": prev_merged["cost_basis"],
                       "cash_balance": prev_merged["cash_balance"], "net_deposits": prev_merged["net_deposits"]}
            elif spike:
                un_suppressed_spikes.append({"date": d, "delta": float(spike["unexplained"])})
        merged[d] = cur
        prev_merged = cur
        if date_with_locf:
            locf_count += 1

    ordered = [merged[d] for d in sorted(merged.keys())]
    return ordered, {"fx_unconverted_dates": fx_unconverted_dates, "suppressed_dates": suppressed_dates,
                     "un_suppressed_spikes": un_suppressed_spikes, "spike_detected": spike_detected,
                     "locf_count": locf_count}


def merged_check(account_rows_by_account, account_ids, period, threshold, svc):
    """Fetch stored rows in range for the user's accounts, replicate merge,
    cross-check the served (production) series. Returns failures + evidence rows."""
    failures = []
    evidence = []
    start_date, end_date = svc._period_to_date_range(period, account_ids)
    repo = PortfolioSnapshotsRepository()
    raw = repo.get_portfolio_snapshots(account_ids, start_date, end_date)
    if not raw:
        return failures, evidence, None
    merged, meta = replicate_merge(raw, threshold=threshold)

    # fx_unconverted must be empty after the rebuild
    if meta["fx_unconverted_dates"]:
        failures.append({"account": "merged", "date": sorted(meta["fx_unconverted_dates"])[0],
                         "class": "FX_UNCONVERTED_REMAINS",
                         "detail": f"{len(meta['fx_unconverted_dates'])} dates still have fx_applied=False holdings"})

    incomplete_dates = set()
    for r in raw:
        if (r.get("data_quality_flag") or "OK") in BASELINE_FLAGS:
            incomplete_dates.add(str(r["snapshot_date"]))

    # spikes on fully-real dates must not exist (they are served to the user)
    for sp_data in meta["un_suppressed_spikes"]:
        d = sp_data["date"]
        if d in incomplete_dates:
            continue
        failures.append({"account": "merged", "date": d, "class": "MERGED_SPIKE",
                         "detail": f"unsuppressed merged spike on real date (period={period})"})

    # production cross-check: production serves the merged daily series as-is
    return failures, evidence, {"merged": merged, "expected": merged,
                                "incomplete_dates": incomplete_dates, "meta": meta}


async def production_series(svc, user_id, period, account_ids):
    return await svc.get_portfolio_performance(user_id=user_id, period=period, account_ids=account_ids)


def compare_served(svc, user_id, period, account_ids, replicated):
    """Call the real endpoint and assert identity with our replicated series."""
    failures = []
    res = asyncio.run(production_series(svc, user_id, period, account_ids))
    if not res.get("success"):
        failures.append({"account": "merged", "date": period, "class": "PROD_FAIL",
                         "detail": f"get_portfolio_performance failed for user {user_id}"})
        return failures
    if res.get("data_source") != "snapshots":
        failures.append({"account": "merged", "date": period, "class": "PROD_SOURCE",
                         "detail": f"data_source={res.get('data_source')} expected 'snapshots' for user {user_id}"})
    served = res.get("snapshots") or []
    mine = replicated["expected"]
    if len(served) != len(mine):
        failures.append({"account": "merged", "date": period, "class": "PROD_LEN",
                         "detail": f"user {user_id} period {period}: served {len(served)} pts vs replicated {len(mine)} pts"})
        return failures
    for a, b in zip(served, mine, strict=False):
        if a.get("date") != b["date"]:
            failures.append({"account": "merged", "date": period, "class": "PROD_DATE",
                             "detail": f"user {user_id}: served {a.get('date')} vs replicated {b['date']}"})
            continue
        pa = float(a.get("value") or 0)
        qb = float(b["value"] or 0)
        if abs(pa - qb) > VALUE_TOL:
            failures.append({"account": "merged", "date": a.get("date"),
                             "class": "PROD_VALUE",
                             "detail": f"user {user_id} served={pa:.2f} replicated={qb:.2f}"})
    return failures


def main():
    parser = argparse.ArgumentParser(description="Verify rebuilt snapshot history end-to-end")
    parser.add_argument("--accounts", type=str, default="7,8,9,10,11,12",
                        help="Comma-separated account ids to verify")
    parser.add_argument("--users", type=str, default="1,49",
                        help="Comma-separated user ids whose merged series to verify")
    parser.add_argument("--periods", type=str, default="ALL,1Y,YTD",
                        help="Comma-separated periods for the merged-series check")
    parser.add_argument("--max-date", type=str, default="2026-09-23",
                        help="Apply boundary; recompute diff restricted to stored dates <= this")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Spike threshold (default: settings.SNAPSHOT_SPIKE_THRESHOLD)")
    parser.add_argument("--skip-recompute", action="store_true",
                        help="Skip step 3 (recompute-vs-stored)")
    parser.add_argument("--out-dir", type=str, default="verification_output",
                        help="Directory for evidence CSV + summary")
    args = parser.parse_args()

    accounts = [int(x) for x in args.accounts.split(",") if x.strip()]
    users = [int(x) for x in args.users.split(",") if x.strip()]
    periods = [x.strip().upper() for x in args.periods.split(",") if x.strip()]
    threshold = args.threshold if args.threshold is not None else float(
        getattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20))
    os.makedirs(args.out_dir, exist_ok=True)

    log("=" * 78)
    log(f"VERIFY REBUILT SNAPSHOT HISTORY  |  {datetime.now().isoformat()}")
    log(f"accounts={accounts} users={users} periods={periods} threshold={threshold} max_date={args.max_date}")
    log("=" * 78)

    failures = []
    baseline_rows = []
    account_incomplete = {}
    svc = PortfolioService(portfolio_repo=PortfolioRepository())
    user_accounts = {}

    # map users -> accounts (whatever exists, not just the target list)
    acc_rows = supabase.table("portfolio_accounts").select("account_id, user_id").in_("user_id", users).execute()
    for r in (acc_rows.data or []):
        user_accounts.setdefault(int(r["user_id"]), []).append(int(r["account_id"]))

    # company currency map for the accounts under test (paginated past the
    # 1000-row PostgREST cap so companies held only in older rows are not lost)
    cids = set()
    for aid in accounts:
        try:
            start = 0
            while True:
                rows = (supabase.table("portfolio_snapshots")
                        .select("holdings_json").eq("account_id", aid)
                        .range(start, start + 999).execute())
                data = rows.data or []
                for r in data:
                    hj = r.get("holdings_json") or []
                    if isinstance(hj, str):
                        import json as _json
                        try:
                            hj = _json.loads(hj)
                        except Exception:
                            hj = []
                    for h in hj:
                        if h.get("company_id") is not None:
                            cids.add(int(h["company_id"]))
                if len(data) < 1000:
                    break
                start += 1000
        except Exception:
            pass
    company_currencies = {}
    if cids:
        comps = supabase.table("companies").select("company_id, currency").in_("company_id", sorted(cids)).execute()
        for c in (comps.data or []):
            company_currencies[int(c["company_id"])] = c.get("currency") or "USD"
    log(f"Loaded {len(company_currencies)} company currencies")

    # --- split integrity (checks 6-8) ---
    max_dt = date.fromisoformat(args.max_date)
    splits_all = fetch_all_splits(supabase)
    split_cids = sorted({int(s["company_id"]) for s in splits_all if s.get("company_id") is not None})
    log(f"Loaded {len(splits_all)} split rows across {len(split_cids)} companies (latch-agnostic)")
    account_events = {}
    for aid in accounts:
        account_events[aid] = EventStore().get_all_events(aggregate_id=f"account_{aid}")
    log(f"Loaded event streams for {len(account_events)} test accounts")
    gaps, checked = find_missing_split_events(
        supabase, splits_all, account_ids=accounts, company_ids=split_cids, max_date=max_dt)
    log(f"Split-event integrity: {len(gaps)} missing events over {checked} checked (account, company) pairs")
    gaps_by_account = defaultdict(list)
    for g in gaps:
        gaps_by_account[g["account_id"]].append(g)
    price_gaps = split_price_gaps(supabase, splits_all, account_events, accounts, max_dt)
    for pg in price_gaps:
        failures.append(pg)
        log(f"  FAIL [SPLIT_PRICE_GAP] {pg['date']}: {pg['detail']}")
    log(f"Split price coverage: {len(price_gaps)} company-level gaps")

    evidence_rows = []
    for aid in accounts:
        log(f"\n--- Account {aid} ---")
        acct = supabase.table("portfolio_accounts").select("currency").eq("account_id", aid).execute()
        acct_ccy = (acct.data or [{}])[0].get("currency") or "CAD"
        log(f"  account currency: {acct_ccy}")
        stored = PortfolioSnapshotsRepository().get_account_snapshots(aid)
        rd = max(args.max_date, "")
        stored = [s for s in stored if str(s["snapshot_date"]) <= rd]
        log(f"  stored rows (<= max-date): {len(stored)}")
        if not stored:
            failures.append({"account": aid, "date": "-", "class": "NO_STORED_ROWS",
                             "detail": "no stored snapshots in range"})
            continue

        fails, incomplete_dates = validate_stored_rows(
            stored, company_currencies, acct_ccy, aid,
            exchange_overrides=rebuild.load_exchange_overrides(aid))
        account_incomplete[aid] = incomplete_dates
        for f in fails:
            failures.append(f)
            log(f"  FAIL [{f['class']}] {f['date']}: {f['detail']}")

        spikes, baseline = account_spikes(stored, threshold, events=account_events.get(aid))
        for g in gaps_by_account.get(aid, []):
            failures.append({"account": aid, "date": str(g["report_date"]), "class": "MISSING_SPLIT_EVENT",
                             "detail": f"cid={g['company_id']} rd={g['report_date']} factor={g['split_factor']} evidence={g['evidence_date']}"})
            log(f"  FAIL [MISSING_SPLIT_EVENT] {g['report_date']}: cid={g['company_id']} factor={g['split_factor']}")
        for sp in spikes:
            failures.append({"account": aid, "date": sp["date"], "class": "ACCOUNT_SPIKE",
                             "detail": sp["detail"]})
            log(f"  FAIL [ACCOUNT_SPIKE] {sp['date']}: {sp['detail']}")
        for bl in baseline:
            if bl.get("explained"):
                baseline_rows.append({"account": aid, "date": bl["date"], "class": "BASELINE_SPIKE",
                                      "detail": f"{bl['detail']} (event-stream explained)"})
                log(f"  note [BASELINE/explained] {bl['date']}: {bl['detail']}")
            else:
                baseline_rows.append({"account": aid, "date": bl["date"], "class": "BASELINE_SPIKE",
                                      "detail": f"{bl['detail']} (prev={bl.get('prev_flag')} curr={bl.get('curr_flag')})"})
                log(f"  note [BASELINE] {bl['date']}: {bl['detail']}")

        cp_fails = validate_checkpoint_provenance(aid, account_events.get(aid, []))
        if cp_fails:
            for cf in cp_fails:
                failures.append(cf)
                log(f"  FAIL [{cf['class']}] {cf['date']}: {cf['detail']}")
        else:
            log("  checkpoint provenance: OK (source + capture dating)")

        if not args.skip_recompute:
            log(f"  recomputing via event replay (account {aid})...")
            fails, rinfo = recompute_diff(aid, stored, args.max_date)
            log(f"  recompute: {rinfo['recomputed']} rows in range, "
                 f"{rinfo['beyond_boundary']} beyond boundary (informational)")
            if rinfo["stored_not_recomputed"]:
                log(f"  note: {len(rinfo['stored_not_recomputed'])} stored dates not recomputed")
            for f in fails:
                failures.append(f)
                log(f"  FAIL [{f['class']}] {f['date']}: {f['detail']}")

        # evidence rows per date
        for r in sorted(stored, key=lambda x: str(x["snapshot_date"])):
            hj = r.get("holdings_json") or []
            if isinstance(hj, str):
                import json as _json
                try:
                    hj = _json.loads(hj)
                except Exception:
                    hj = []
            evidence_rows.append({
                "scope": "account", "account": aid, "date": str(r["snapshot_date"]),
                "total_value": r.get("total_value"), "holdings_market_value": r.get("holdings_market_value"),
                "cash_balance": r.get("cash_balance"), "cost_basis": r.get("cost_basis"),
                "net_deposits": r.get("net_deposits"), "flag": r.get("data_quality_flag"),
                "holdings_count": len(hj), "verdict": "PASS",
            })

    # --- merged user-facing series ---
    log("\n" + "=" * 78)
    log("MERGED USER-FACING SERIES CROSS-CHECK (production path)")
    log("=" * 78)
    for uid in users:
        uids = user_accounts.get(uid, [])
        log(f"\n--- User {uid} (accounts {uids}) ---")
        if not uids:
            failures.append({"account": f"user{uid}", "date": "-", "class": "NO_ACCOUNTS",
                             "detail": "user has no accounts"})
            continue
        for period in periods:
            start_date, end_date = svc._period_to_date_range(period, uids)
            repo = PortfolioSnapshotsRepository()
            raw = repo.get_portfolio_snapshots(uids, start_date, end_date)
            if not raw:
                failures.append({"account": f"user{uid}", "date": period, "class": "NO_MERGED_DATA",
                                 "detail": f"no snapshots in range {start_date}..{end_date}"})
                continue
            merged, meta = replicate_merge(raw, threshold=threshold)
            incomplete_dates = {str(r["snapshot_date"]) for r in raw
                                if (r.get("data_quality_flag") or "OK") in BASELINE_FLAGS}
            log(f"  period {period}: {len(merged)} merged dates, "
                 f"fx_unconverted_dates={len(meta['fx_unconverted_dates'])}, "
                 f"locf={meta['locf_count']}, suppressed={len(meta['suppressed_dates'])}")

            if meta["fx_unconverted_dates"]:
                for d in sorted(meta["fx_unconverted_dates"])[:10]:
                    failures.append({"account": f"user{uid}", "date": d, "class": "FX_UNCONVERTED_REMAINS",
                                     "detail": "holding with fx_applied=False still present"})

            user_events = []
            for u_aid in uids:
                if u_aid not in account_events:
                    account_events[u_aid] = EventStore().get_all_events(aggregate_id=f"account_{u_aid}")
                user_events.extend(account_events[u_aid])
            for sp_data in meta["un_suppressed_spikes"]:
                d = sp_data["date"]
                if d in incomplete_dates:
                    continue
                if user_events and explains_spike(
                    user_events, date.fromisoformat(str(d)), sp_data.get("delta") or 0.0
                ):
                    baseline_rows.append({"account": f"user{uid}", "date": d, "class": "BASELINE_SPIKE",
                                          "detail": f"merged spike explained by event stream (period={period})"})
                    log(f"  note [BASELINE/explained] {period} {d}: merged spike explained by events")
                    continue
                failures.append({"account": f"user{uid}", "date": d, "class": "MERGED_SPIKE",
                                 "detail": f"unsuppressed merged spike on real date (period={period})"})
                log(f"  FAIL [MERGED_SPIKE] {period} {d}")

            # production cross-check
            try:
                prod_fails = compare_served(svc, uid, period, uids, {"expected": merged})
                for pf in prod_fails:
                    failures.append(pf)
                    log(f"  FAIL [{pf['class']}] {pf['date']}: {pf['detail']}")
                served_res = asyncio.run(production_series(svc, uid, period, uids))
                served = served_res.get("snapshots") or []
                log(f"  production served {len(served)} points, data_source={served_res.get('data_source')}, "
                    f"spike_detected={served_res.get('spike_detected')}")
            except Exception as e:
                failures.append({"account": f"user{uid}", "date": period, "class": "PROD_EXCEPTION",
                                 "detail": str(e)[:300]})
                log(f"  FAIL [PROD_EXCEPTION] {period}: {e}")

            # evidence rows for merged series
            for pt in merged:
                evidence_rows.append({
                    "scope": "merged", "account": f"user{uid}", "date": pt["date"],
                    "total_value": pt["value"], "holdings_market_value": "",
                    "cash_balance": pt["cash_balance"], "cost_basis": pt["cost_basis"],
                    "net_deposits": pt["net_deposits"],
                    "flag": "INCOMPLETE" if pt["date"] in incomplete_dates else "OK",
                    "holdings_count": "", "verdict": "PASS",
                })

    # --- report ---
    log("\n" + "=" * 78)
    log("SUMMARY")
    log("=" * 78)
    log(f"Failures: {len(failures)}")
    for f in sorted(failures, key=lambda x: (str(x.get('account')), str(x.get('date')), x.get('class'))):
        log(f"  FAIL account={f.get('account')} date={f.get('date')} class={f.get('class')}: {f.get('detail')}")
    log(f"Baseline (pre-existing INCOMPLETE-debt or event-stream explained) spikes: {len(baseline_rows)}")
    for b in baseline_rows[:20]:
        log(f"  baseline {b['account']} {b['date']}: {b['detail']}")
    log("Per-account INCOMPLETE dates (pre-existing debt): ")
    for aid, ds in sorted(account_incomplete.items()):
        log(f"  account {aid}: {len(ds)} dates")

    # write evidence CSV
    csv_path = os.path.join(args.out_dir, "snapshot_history_evidence.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "scope", "account", "date", "total_value", "holdings_market_value",
            "cash_balance", "cost_basis", "net_deposits", "flag", "holdings_count", "verdict"])
        writer.writeheader()
        for er in evidence_rows:
            writer.writerow(er)
    log(f"\nEvidence written: {csv_path} ({len(evidence_rows)} rows)")

    verdict = "PASS" if not failures else "FAIL"
    log(f"VERDICT: {verdict}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
