"""Verify the repaired provider symbols against the live catalog and Yahoo.

This is the post-fix observation that unit tests cannot provide: the seven
symbols that used to return Yahoo 404 are read back from the real database and
then requested from the real provider. The probe carries its own controls so a
blocked network or a broken yfinance API cannot be mistaken for a pass:

  * positive control  AAPL     - a valid ticker must return a real price;
  * negative control  T.TO.TO  - the logged defect signature must NOT resolve.

The JSON artifact is the durable evidence. Any problem exits non-zero.

Usage:
    python scripts/verify_provider_symbols_live.py \
        --output ../../.planning/verification/provider_symbol_live_check.json
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

LOCAL_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
SECURITY_IDS = (9, 123, 634, 2605, 3006, 3010, 3115)
POSITIVE_CONTROL = "AAPL"
NEGATIVE_CONTROL = "T.TO.TO"  # the exact doubled suffix from the incident log
REPEATED_SUFFIX_SQL = (
    "SELECT security_id, symbol, provider_symbol FROM public.securities "
    "WHERE security_id = ANY(%s) ORDER BY security_id"
)


def _catalog_rows() -> list[dict]:
    import psycopg2

    conn = psycopg2.connect(LOCAL_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(REPEATED_SUFFIX_SQL, (list(SECURITY_IDS),))
            return [
                {"security_id": row[0], "symbol": row[1], "provider_symbol": row[2]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def _yahoo_probe(symbol: str) -> dict:
    """Return a real price, or the provider's raw rejection text as evidence.

    yfinance logs HTTP 404 to stderr before raising a secondary KeyError, so
    stderr is captured as well as the exception. Without that capture the exact
    "Quote not found for symbol: T.TO.TO" signature would be lost.
    """
    import yfinance as yf

    stderr = io.StringIO()
    error = None
    price = None
    currency = None
    with contextlib.redirect_stderr(stderr):
        try:
            fast_info = yf.Ticker(symbol).fast_info
            price = getattr(fast_info, "last_price", None)
            currency = fast_info.get("currency")
        except Exception as exc:  # noqa: BLE001 - the raw provider error is the evidence
            error = f"{type(exc).__name__}: {exc}"
    diagnostics = (stderr.getvalue() + "\n" + (error or "")).strip()
    not_found = "404" in diagnostics or "Quote not found" in diagnostics
    if not_found:
        status = "not_found"
    elif error:
        status = "error"
    elif price:
        status = "ok"
    else:
        status = "no_price"
    return {
        "status": status,
        "price": price,
        "currency": currency,
        "error": diagnostics[:600] or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    artifact = {
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "database": LOCAL_DB,
        "security_ids": list(SECURITY_IDS),
        "controls": {},
        "catalog": [],
        "yahoo": [],
        "problems": [],
    }

    try:
        rows = _catalog_rows()
    except Exception as exc:  # noqa: BLE001 - unreachable DB is unverifiable, not pass
        artifact["problems"].append(f"catalog unreachable: {exc}")
        rows = []

    artifact["catalog"] = rows
    if len(rows) != len(SECURITY_IDS):
        artifact["problems"].append(
            f"expected {len(SECURITY_IDS)} catalog rows, found {len(rows)}"
        )
    for row in rows:
        if row["provider_symbol"] != row["symbol"]:
            artifact["problems"].append(
                f"security {row['security_id']}: provider_symbol "
                f"{row['provider_symbol']!r} != symbol {row['symbol']!r}"
            )

    # Controls first. If they fail, the probe itself is not trustworthy and no
    # downstream symbol result can be used as evidence.
    artifact["controls"][POSITIVE_CONTROL] = _yahoo_probe(POSITIVE_CONTROL)
    artifact["controls"][NEGATIVE_CONTROL] = _yahoo_probe(NEGATIVE_CONTROL)
    if artifact["controls"][POSITIVE_CONTROL]["status"] != "ok":
        artifact["problems"].append(
            f"positive control {POSITIVE_CONTROL} did not resolve - "
            "yahoo/probe path is unverifiable (network?)"
        )
    if artifact["controls"][NEGATIVE_CONTROL]["status"] == "ok":
        artifact["problems"].append(
            f"negative control {NEGATIVE_CONTROL} unexpectedly resolved - "
            "probe cannot detect the defect signature"
        )

    for row in rows:
        if artifact["problems"]:
            break
        symbol = row["provider_symbol"]
        result = {"symbol": symbol, **_yahoo_probe(symbol)}
        artifact["yahoo"].append(result)
        if result["status"] != "ok":
            artifact["problems"].append(
                f"Yahoo did not return a price for {symbol} "
                f"({result['status']}): {result['error']}"
            )
        time.sleep(0.3)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps({"artifact": str(output), "problems": artifact["problems"]},
                     indent=2))
    return 1 if artifact["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
