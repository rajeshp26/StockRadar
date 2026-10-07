"""Shared price snapshot utilities. Single source of truth for CDR logic and price resolution."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from shared.cdr_utils import trace_division

STALE_THRESHOLD_MIN = 5


def get_cdr_maps_for_companies(
    supabase_client,
    company_ids: Iterable[int],
) -> tuple[dict[int, float], set]:
    ids = list({int(c) for c in company_ids})
    if not ids:
        return {}, set()

    comp = (
        supabase_client.table("companies")
        .select("company_id, cdr_ratio")
        .in_("company_id", ids)
        .execute()
    )
    ratios: dict[int, float] = {}
    for r in comp.data or []:
        if r.get("cdr_ratio") is not None:
            ratios[r["company_id"]] = float(r["cdr_ratio"])

    if not ratios:
        return {}, set()

    hold = (
        supabase_client.table("portfolio_holdings")
        .select("company_id, exchange_override")
        .in_("company_id", list(ratios.keys()))
        .execute()
    )
    rows = hold.data or []
    total_by_cid: dict[int, int] = {}
    tor_by_cid: dict[int, int] = {}
    for r in rows:
        cid = int(r["company_id"])
        total_by_cid[cid] = total_by_cid.get(cid, 0) + 1
        if r.get("exchange_override") == "TOR":
            tor_by_cid[cid] = tor_by_cid.get(cid, 0) + 1
    # Unanimous rule: a company is company-global TOR only when ALL its
    # holdings rows are TOR. A mixed company (CDR in one account, direct in
    # another - e.g. AAPL) must not be divided here; per-account pricing in
    # snapshot_builder handles those with the account-scoped override.
    tor_cids: set = {
        cid for cid, total in total_by_cid.items()
        if tor_by_cid.get(cid, 0) == total
    }
    return ratios, tor_cids


def apply_cdr_adjustment(
    price: float,
    prev_close: float | None,
    company_id: int,
    cdr_ratios: dict[int, float],
    tor_cids: set,
    default_cdr: float = 10.0,
) -> tuple[float, float | None]:
    if company_id in tor_cids:
        ratio = cdr_ratios.get(company_id, default_cdr)
        if ratio and ratio > 0:
            trace_division(
                "price_utils", company_id, price, ratio, price / ratio,
                price_source="unanimous",
            )
            price = price / ratio
            if prev_close is not None:
                prev_close = prev_close / ratio
    return price, prev_close


def _is_price_fresh(last_updated: Any) -> bool:
    if last_updated is None:
        return False
    try:
        dt = datetime.fromisoformat(str(last_updated))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age_min = (datetime.now(UTC) - dt).total_seconds() / 60
        return age_min <= STALE_THRESHOLD_MIN
    except (ValueError, TypeError):
        return False


def build_price_snapshot(
    supabase_client,
    company_ids: list[int],
    source: str = "db_cached",
) -> dict[int, dict[str, Any]]:
    if not company_ids:
        return {}

    md_res = (
        supabase_client.table("current_market_data")
        .select("company_id, current_price, close_price, last_updated")
        .in_("company_id", company_ids)
        .execute()
    )
    md_map = {r["company_id"]: r for r in (md_res.data or [])}

    cdr_ratios, tor_cids = get_cdr_maps_for_companies(supabase_client, company_ids)

    result: dict[int, dict[str, Any]] = {}

    for cid in company_ids:
        md = md_map.get(cid)
        if not md or md.get("current_price") is None:
            continue

        is_stale = not _is_price_fresh(md.get("last_updated"))

        price, prev_close = apply_cdr_adjustment(
            float(md["current_price"]),
            md.get("close_price"),
            cid, cdr_ratios, tor_cids,
        )

        change = 0.0
        change_pct = 0.0
        if prev_close is not None and prev_close != 0:
            change = price - prev_close
            change_pct = (change / prev_close) * 100

        result[cid] = {
            "price": round(price, 4),
            "prevClose": round(prev_close, 4) if prev_close else None,
            "change": round(change, 4),
            "changePercent": round(change_pct, 4),
            "source": source,
            "lastUpdated": str(md.get("last_updated", "")),
            "isStale": is_stale,
        }

    return result
