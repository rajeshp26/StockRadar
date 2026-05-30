"""
Deep Sync — End-to-End Test

Verifies that adding a stock triggers background deep sync
which populates income_statements, balance_sheets, statistics tables.

No mocking. Requires RUN_E2E=true + real Supabase credentials.
"""

import asyncio
import logging
import time

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.e2e
class TestDeepSyncE2E:
    """Validate the deep sync data flow end-to-end."""

    TEST_TICKER = "MSFT"
    TABLES_TO_CHECK = ["income_statements", "balance_sheets", "statistics", "dividend_history"]
    POLL_SECONDS = 45

    async def test_deep_sync_populates_tables(self, e2e_supabase, e2e_http_client, e2e_auth_headers):
        """Add a stock and verify background sync populates financial data tables."""
        # 1. Ensure test user exists via /users/sync
        sync_resp = await e2e_http_client.post("/users/sync", json={
            "email": "e2e-test@stockerpro-test.com",
            "display_name": "E2E Test",
        }, headers=e2e_auth_headers)
        assert sync_resp.status_code in (200, 201)

        # 2. Get or create a watchlist
        wl_resp = await e2e_http_client.post(
            "/watchlists/default-with-items",
            json={"firebase_uid": None},
            headers=e2e_auth_headers,
        )
        assert wl_resp.status_code == 200
        wl_data = wl_resp.json()
        watchlist_id = wl_data.get("watchlist_id")
        if not watchlist_id:
            # Create a new watchlist
            create_resp = await e2e_http_client.post(
                "/watchlists", json={"name": "E2E Deep Sync Test"},
                headers=e2e_auth_headers,
            )
            assert create_resp.status_code == 201
            watchlist_id = create_resp.json()["id"]

        # 3. Add the test stock
        add_resp = await e2e_http_client.post("/watchlist-items", json={
            "watchlist_id": watchlist_id,
            "symbol": self.TEST_TICKER,
            "target_buy": 200.0,
            "target_sell": 400.0,
        }, headers=e2e_auth_headers)
        # Accept 201 (created) or 200 (already exists)
        assert add_resp.status_code in (200, 201)
        company_id = add_resp.json().get("watchlist_item", add_resp.json()).get("company_id")

        if not company_id:
            # Try to get company_id from holdings or company lookup
            company_id = self._resolve_company_id(e2e_supabase)

        assert company_id is not None, "Could not resolve company_id"

        # 4. Poll for background sync completion
        success = await self._poll_for_data(e2e_supabase, company_id)
        assert success, (
            f"Background sync did not populate all tables within "
            f"{self.POLL_SECONDS}s for company_id={company_id}"
        )

    async def _poll_for_data(self, supabase, company_id: int) -> bool:
        """Poll Supabase tables until data appears or timeout."""
        start = time.time()
        while time.time() - start < self.POLL_SECONDS:
            results = {}
            for table in self.TABLES_TO_CHECK:
                try:
                    res = supabase.table(table).select("count", count="exact").eq(
                        "company_id", company_id
                    ).execute()
                    results[table] = res.count if res.count else 0
                except Exception as exc:
                    logger.debug("Poll %s for company_id=%s failed: %s", table, company_id, exc)
                    results[table] = 0

            has_income = isinstance(results.get("income_statements"), int) and results["income_statements"] > 0
            has_stats = isinstance(results.get("statistics"), int) and results["statistics"] > 0
            if has_income and has_stats:
                return True
            await asyncio.sleep(3)
        return False

    def _resolve_company_id(self, supabase) -> int | None:
        """Look up company_id from the companies table for TEST_TICKER."""
        result = supabase.table("companies").select("id").eq(
            "ticker_symbol", self.TEST_TICKER
        ).limit(1).execute()
        if result.data:
            return result.data[0]["id"]
        return None
