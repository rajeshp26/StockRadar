"""REG-CORE-LEGACY: the legacy `default-with-items` endpoint must price a
watchlist row from its own `security_id` quote, never from a company-level
`exchange_override == 'TOR'` CDR adjustment.

The selected listing (META/NEO/CDR, security_id 3128) is a distinct tradable
instrument from META/NMS (security_id 2833). A company-scoped exchange override
cannot distinguish them and was the original symbol-keyed pricing defect.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

META_NEO = {
    "security_id": 3128,
    "symbol": "META",
    "exchange": "NEO",
    "kind": "CDR",
    "currency": "CAD",
    "provider_symbol": "META.NE",
    "cdr_ratio": 10.0,
}


def _query(data):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.in_.return_value = q
    q.execute.return_value = MagicMock(data=data)
    return q


@pytest.fixture
def service():
    from application.services.watchlist_service import WatchlistService

    svc = WatchlistService(*[MagicMock() for _ in range(4)])
    svc.user_repo.find_by_firebase_uid.return_value = {"user_id": 1}
    svc.watchlist_repo.find_default_by_user_id.return_value = {
        "id": 10, "watchlist_name": "My Watchlist", "is_default": True
    }
    svc.watchlist_repo.get_items_by_watchlist_id.return_value = [
        {
            "watchlist_item_id": 100,
            "security_id": 3128,
            "target_buy": None,
            "target_sell": None,
            "companies": {
                "company_id": 145,
                "ticker_symbol": "META",
                "company_name": "Meta Platforms",
            },
        }
    ]
    return svc


def test_cdr_price_comes_from_security_id_quote_not_exchange_override(service):
    def table(name):
        if name == "securities":
            return _query([META_NEO])
        # No company-level CDR override or market data is needed for a listing
        # that carries its own quote.
        return _query([])

    with patch("application.services.watchlist_service.supabase") as sb, patch(
        "infrastructure.repositories.security_repository.SecurityRepository.get_quotes",
        return_value={
            3128: {
                "security_id": 3128,
                "current_price": 500.0,  # native META.NE quote
                "close_price": 490.0,
                "last_updated": "2026-11-22T00:00:00Z",
            }
        },
    ):
        sb.table.side_effect = table
        result = service.get_default_watchlist_with_items("uid")

    # 500.0 native quote / 10.0 CDR ratio = 50.0 effective price.
    assert result.stocks[0].price == pytest.approx(50.0)
    assert result.stocks[0].change == pytest.approx(1.0)


def test_company_exchange_override_is_never_queried(service):
    queried = []

    def table(name):
        queried.append(name)
        if name == "securities":
            return _query([META_NEO])
        return _query([])

    with patch("application.services.watchlist_service.supabase") as sb, patch(
        "infrastructure.repositories.security_repository.SecurityRepository.get_quotes",
        return_value={3128: {"security_id": 3128, "current_price": 500.0,
                             "close_price": 490.0, "last_updated": "x"}},
    ):
        sb.table.side_effect = table
        service.get_default_watchlist_with_items("uid")

    assert "portfolio_holdings" not in queried, (
        "exchange_override must not be read for pricing"
    )
