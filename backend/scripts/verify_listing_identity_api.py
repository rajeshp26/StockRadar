"""Real-stack API proof for listing identity (AC-4/AC-8).

Drives the LIVE uvicorn server against the local Supabase stack with a real
HS256 JWT, then proves that META/NMS/COMMON and META/NEO/CDR are two distinct
watchlist rows with distinct security_id, provider symbol and effective price.

The two listing-specific endpoints under test are:
  POST /watchlist-items          -> persists the selected security_id
  GET  /watchlists/{id}/prices   -> listing-keyed prices (securityId in payload)
  POST /watchlists/{id}/structure-> listing identity + prices

Setup/teardown (seeding one deterministic CDR quote, deleting one test item) is
done directly against Supabase and is always reverted on exit.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8000")
AUTH_ID = os.environ.get(
    "TEST_LISTING_AUTH_ID", "59a7ced9-aa7c-4f34-b77e-266fc8a8e796"
)
WATCHLIST_ID = int(os.environ.get("TEST_LISTING_WATCHLIST_ID", "6"))
META_NMS = 2833
META_NEO = 3128
TEST_EMAIL = "listing-identity-test@stockerpro.local"

failures: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    if not ok:
        failures.append(name)


def token() -> str:
    return jwt.encode(
        {
            "sub": AUTH_ID,
            "aud": "authenticated",
            "email": TEST_EMAIL,
            "exp": int(time.time()) + 3600,
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )


def wait_for_api(client: httpx.Client) -> bool:
    for _ in range(8):
        try:
            if client.get("/health", timeout=3).status_code == 200:
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    from supabase import create_client

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    # --- snapshot state we will mutate, for exact teardown -------------------
    prior_item = sb.table("watchlist_items").select("watchlist_item_id").eq(
        "watchlist_id", WATCHLIST_ID
    ).eq("security_id", META_NEO).execute().data
    prior_quote = sb.table("quotes").select("*").eq("security_id", META_NEO).execute().data

    added_item_id: int | None = None
    headers = {"Authorization": f"Bearer {token()}"}

    try:
        with httpx.Client(base_url=BASE, headers=headers, timeout=30) as client:
            if not wait_for_api(client):
                print("BLOCKED real-stack API unreachable at", BASE)
                return 2

            # --- 1. ADD the second META listing via the live API ------------
            add_payload = {
                "watchlist_id": WATCHLIST_ID,
                "symbol": "META",
                "security_id": META_NEO,
                "exchange": "NEO",
                "kind": "CDR",
                "currency": "CAD",
                "provider_symbol": "META.NE",
                "target_buy": None,
                "target_sell": None,
            }
            res = client.post("/watchlist-items", json=add_payload)
            check("add META.NE HTTP 201", res.status_code == 201,
                  f"{res.status_code} {res.text[:300]}")
            if res.status_code != 201:
                return 1
            body = res.json()
            item = body["watchlist_item"]
            added_item_id = item["watchlist_item_id"]
            check("add response keeps exact security_id", item.get("security_id") == META_NEO,
                  item.get("security_id"))
            check("add response keeps provider_symbol", item.get("provider_symbol") == "META.NE",
                  item.get("provider_symbol"))
            check("add response keeps exchange/kind",
                  item.get("exchange") == "NEO" and item.get("kind") == "CDR",
                  (item.get("exchange"), item.get("kind")))

            # --- 2. Seed a deterministic CDR quote (setup only) -------------
            seeded_quote = {
                "security_id": META_NEO,
                "current_price": 500.0,   # native META.NE quote
                "close_price": 490.0,
                "source": "listing_identity_test",
                "is_stale": False,
                "last_updated": "2026-11-22T00:00:00Z",
            }
            sb.table("quotes").upsert(seeded_quote, on_conflict="security_id").execute()

            # --- 3. Persistence proof: two META rows, distinct securities ---
            rows = sb.table("watchlist_items").select("security_id").eq(
                "watchlist_id", WATCHLIST_ID
            ).eq("company_id", 145).execute().data
            sec_ids = {r["security_id"] for r in rows}
            check("both META listings persist with distinct security_id",
                  {META_NMS, META_NEO}.issubset(sec_ids), sorted(str(x) for x in sec_ids))

            # --- 4. Prices endpoint is listing-keyed ------------------------
            pres = client.get(f"/watchlists/{WATCHLIST_ID}/prices", params={"page_size": 50})
            check("GET prices HTTP 200", pres.status_code == 200, pres.status_code)
            meta_rows = [p for p in pres.json()["prices"] if p["symbol"] == "META"]
            by_sid = {p.get("securityId"): p for p in meta_rows}
            check("prices returns both META securityIds",
                  {META_NMS, META_NEO}.issubset(by_sid), list(by_sid))
            nms_price = by_sid.get(META_NMS, {}).get("price")
            neo_price = by_sid.get(META_NEO, {}).get("price")
            check("CDR effective price = native / ratio (500/10=50)",
                  neo_price is not None and abs(neo_price - 50.0) < 0.01, neo_price)
            check("two listings return distinct prices",
                  nms_price is not None and neo_price is not None and nms_price != neo_price,
                  (nms_price, neo_price))

            # --- 5. Structure endpoint keeps identity + prices -------------
            sres = client.post(f"/watchlists/{WATCHLIST_ID}/structure")
            check("POST structure HTTP 200", sres.status_code == 200, sres.status_code)
            meta_stocks = [s for s in sres.json()["stocks"] if s["symbol"] == "META"]
            by_sid_s = {s.get("securityId"): s for s in meta_stocks}
            check("structure returns both META listings",
                  {META_NMS, META_NEO}.issubset(by_sid_s), list(by_sid_s))
            neo = by_sid_s.get(META_NEO, {})
            nms = by_sid_s.get(META_NMS, {})
            check("structure keeps exchange/kind/providerSymbol per listing",
                  neo.get("exchange") == "NEO" and neo.get("kind") == "CDR"
                  and neo.get("providerSymbol") == "META.NE"
                  and nms.get("exchange") == "NMS" and nms.get("kind") == "COMMON",
                  (neo.get("exchange"), neo.get("kind"), neo.get("providerSymbol"),
                   nms.get("exchange"), nms.get("kind")))
            check("structure prices are distinct",
                  neo.get("price") is not None and nms.get("price") is not None
                  and neo["price"] != nms["price"],
                  (nms.get("price"), neo.get("price")))

    finally:
        # --- teardown: remove the item we added, restore prior quote --------
        if added_item_id is not None:
            try:
                with httpx.Client(base_url=BASE, headers=headers, timeout=15) as client:
                    client.post("/watchlist-items/delete", json={"item_id": added_item_id})
            except Exception as exc:
                print("WARN teardown delete failed:", exc)
        try:
            if prior_item:
                # item already existed; leave quote as-is only if we seeded it
                if not prior_quote:
                    sb.table("quotes").delete().eq("security_id", META_NEO).execute()
            elif prior_quote:
                sb.table("quotes").upsert(prior_quote[0], on_conflict="security_id").execute()
            else:
                sb.table("quotes").delete().eq("security_id", META_NEO).execute()
        except Exception as exc:
            print("WARN teardown quote restore failed:", exc)

    if failures:
        print(f"LISTING_IDENTITY_API_FAILED ({len(failures)} checks): {failures}")
        return 1
    print("LISTING_IDENTITY_API_VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
