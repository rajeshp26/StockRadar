import os

os.environ.setdefault("SUPABASE_URL", "http://test.db.local")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "eyJtest_supabase_service_key_for_testing_only_abcd")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("ENVIRONMENT", "development")

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@pytest.fixture
def mock_supabase_client():
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.neq.return_value = table
    table.gte.return_value = table
    table.lte.return_value = table
    table.in_.return_value = table
    table.or_.return_value = table
    table.is_.return_value = table
    table.limit.return_value = table
    table.execute.return_value = MagicMock(data=[], count=None)
    return client


@pytest.fixture
def mock_financial_repo(mock_supabase_client):
    repo = MagicMock()
    repo.client = mock_supabase_client
    repo.get_companies_with_upcoming_earnings = AsyncMock()
    repo.get_company_refresh_info = AsyncMock()
    repo.upsert_all_financials = AsyncMock(return_value={"income_statements": 0, "balance_sheets": 0, "cash_flows": 0, "earnings": 0, "dividends": 0})
    repo.update_company_refresh_metadata = AsyncMock()
    repo.acquire_company_lock = AsyncMock(return_value=True)
    repo.release_company_lock = AsyncMock()
    repo.upsert_price_history = AsyncMock()
    repo.update_price_refresh_marker = AsyncMock()
    repo.upsert_splits = AsyncMock()
    repo.upsert_revenue_forecast = AsyncMock()
    repo.upsert_earnings_forecast = AsyncMock()
    repo.upsert_company_summary = AsyncMock()
    repo.get_companies_for_market_data = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_defeat_beta_provider():
    provider = MagicMock()
    provider.get_all_financials_optimized = AsyncMock()
    provider.get_price_history_optimized = AsyncMock(return_value=[])
    provider.get_splits_optimized = AsyncMock(return_value=[])
    provider.fetch_revenue_forecast = AsyncMock(return_value=[])
    provider.fetch_earnings_forecast = AsyncMock(return_value=[])
    provider.get_company_summary_optimized = AsyncMock(return_value=None)
    return provider
