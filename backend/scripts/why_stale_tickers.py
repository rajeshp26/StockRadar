# why_stale_tickers.py
# READ-ONLY. For the tickers stuck at 2026-09-30 (SPY, QQQ, NVDA + ETF cluster),
# find recorded failures: dead_letter jobs, last_error, and refresh requests.
# This answers WHY those specific tickers stopped, with the system's own log.
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

load_dotenv(_backend / ".env")

from database import supabase  # noqa: E402

STALE_IDS = {61: "SPY", 379: "QQQ"}
# add NVDA + a few of the ETF cluster
rows = (supabase.table("companies").select("company_id, ticker_symbol")
        .in_("ticker_symbol",
             ["SPY", "QQQ", "NVDA", "NVDY", "CONY", "QYLD", "TSLY",
              "QDTE", "SVOL", "WEED", "CRF", "AAPL", "MSFT"])
        .execute().data or [])
for r in rows:
    STALE_IDS[r["company_id"]] = r["ticker_symbol"]

print("=== jobs for these resource_ids (any status) ===")
# jobs may reference the company via resource_id (string or int)
for cid, tk in sorted(STALE_IDS.items(), key=lambda x: x[1]):
    try:
        js = (supabase.table("jobs")
              .select("job_type, status, created_at, last_error, "
                      "last_error_at, attempts, max_attempts, resource_id")
              .eq("resource_id", str(cid))
              .order("created_at", desc=True).limit(6).execute().data or [])
    except Exception as e:
        print(f"  {tk}: jobs query failed: {e}")
        js = []
    if not js:
        # try int form
        try:
            js = (supabase.table("jobs")
                  .select("job_type, status, created_at, last_error, "
                          "last_error_at, attempts, resource_id")
                  .eq("resource_id", cid)
                  .order("created_at", desc=True).limit(6).execute().data or [])
        except Exception:
            js = []
    print(f"\n  --- {tk} (id {cid}): {len(js)} job rows ---")
    for j in js:
        err = (j.get("last_error") or "")[:220]
        print(f"    {j.get('created_at')} {j.get('job_type')}/"
              f"{j.get('status')} attempts={j.get('attempts')} "
              f"res={j.get('resource_id')}")
        if err:
            print(f"      ERR: {err}")

print("\n=== dead_letter jobs: resource_type + id distribution (recent 40) ===")
dl = (supabase.table("jobs")
      .select("job_type, resource_type, resource_id, created_at, last_error")
      .eq("status", "dead_letter")
      .order("created_at", desc=True).limit(40).execute().data or [])
from collections import Counter  # noqa: E402
print("  by resource_type:", dict(Counter(
    (j.get("resource_type"), j.get("job_type")) for j in dl)))
# how many dead letters reference our stale ids
stale_idset = {str(c) for c in STALE_IDS}
hit = [j for j in dl if str(j.get("resource_id")) in stale_idset]
print(f"  dead letters hitting our stale tickers: {len(hit)}")
for j in hit[:10]:
    print(f"    {j.get('created_at')} {j.get('job_type')} res={j.get('resource_id')} "
          f"ERR={(j.get('last_error') or '')[:160]}")

print("\n=== company_refresh_requests for these companies ===")
try:
    rq = (supabase.table("company_refresh_requests")
          .select("*").in_("company_id", list(STALE_IDS))
          .order("created_at", desc=True).limit(20).execute().data or [])
    if rq:
        print(f"  cols: {sorted(rq[0].keys())}")
        for r in rq:
            print("   " + ", ".join(
                f"{k}={str(r.get(k))[:60]}" for k in sorted(r)
                if k in ("company_id", "status", "state", "created_at",
                         "error", "last_error", "reason", "requested_at")))
    else:
        print("  (no rows)")
except Exception as e:
    print(f"  query failed: {e}")
