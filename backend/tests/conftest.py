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

from unittest.mock import AsyncMock, MagicMock

import pytest


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
    table.order.return_value = table
    table.range.return_value = table
    table.limit.return_value = table
    table.update.return_value = table
    table.upsert.return_value = table
    table.insert.return_value = table
    table.delete.return_value = table
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


# ─── Moat Test Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def mock_moat_repo():
    repo = MagicMock()
    repo.get_company_context = MagicMock(return_value={
        "company_id": 1, "currency": "USD", "sector": "Technology",
        "industry": "Software", "ticker_symbol": "AAPL",
    })
    repo.get_financial_ratios_history = AsyncMock(return_value=[
        {"fiscal_year": 2024, "roic": 0.32, "roe": 0.45, "gross_margin": 0.43,
         "operating_margin": 0.30, "net_margin": 0.25, "asset_turnover": 0.88},
        {"fiscal_year": 2023, "roic": 0.30, "roe": 0.42, "gross_margin": 0.42,
         "operating_margin": 0.29, "net_margin": 0.24, "asset_turnover": 0.85},
        {"fiscal_year": 2022, "roic": 0.35, "roe": 0.48, "gross_margin": 0.43,
         "operating_margin": 0.31, "net_margin": 0.26, "asset_turnover": 0.90},
        {"fiscal_year": 2021, "roic": 0.33, "roe": 0.46, "gross_margin": 0.42,
         "operating_margin": 0.30, "net_margin": 0.25, "asset_turnover": 0.87},
        {"fiscal_year": 2020, "roic": 0.28, "roe": 0.40, "gross_margin": 0.40,
         "operating_margin": 0.27, "net_margin": 0.21, "asset_turnover": 0.82},
    ])
    repo.get_income_statements_annual = AsyncMock(return_value=[
        {"fiscal_year": 2024, "revenue": 100_000, "ebit": 30_000,
         "net_income": 25_000, "income_tax_expense": 5_000, "shares_outstanding_diluted": 1000},
    ])
    repo.get_balance_sheet_latest = AsyncMock(return_value={
        "fiscal_year": 2024, "total_assets": 200_000,
        "shareholders_equity": 80_000, "total_debt": 40_000,
        "cash_and_cash_equivalents": 20_000, "property_plant_equipment_net": 30_000,
    })
    repo.get_cash_flow_latest = AsyncMock(return_value={
        "fiscal_year": 2024, "cash_from_operating_activities": 35_000,
        "capital_expenditures": -8_000, "depreciation_amortization": 5_000,
    })
    repo.get_company_summary_latest = AsyncMock(return_value={
        "market_cap": 500_000, "enterprise_value": 520_000,
        "beta": 1.2, "shares_outstanding": 1000,
    })
    repo.get_industry_multiples = AsyncMock(return_value={
        "sector": "Technology", "industry": "Software",
        "avg_roic": 0.15, "avg_gross_margin": 0.50, "sample_size": 100,
    })
    repo.get_moat_analysis = AsyncMock(return_value=None)
    repo.upsert_moat_analysis = AsyncMock(return_value=True)
    repo.get_moat_keyword_evidence = AsyncMock(return_value=[])
    repo.delete_moat_keyword_evidence = AsyncMock(return_value=True)
    repo.insert_moat_keyword_evidence = AsyncMock(return_value=True)
    repo.get_moat_ai_narrative = AsyncMock(return_value=None)
    repo.upsert_moat_ai_narrative = AsyncMock(return_value=True)
    repo.get_current_market_price = AsyncMock(return_value=150.0)
    return repo


@pytest.fixture
def sample_tenk_text():
    return """
    === Business ===
    Apple designs, manufactures, and markets smartphones, personal computers, tablets,
    wearables, and accessories. The company's proprietary iOS ecosystem creates significant
    switching costs for users. Apple's brand recognition is among the strongest globally.
    The company holds a large portfolio of patents and intellectual property.
    Apple's supply chain is one of the most efficient in the world, providing scale efficiencies.

    === Risk Factors ===
    The company faces intense competition in the technology sector.
    Changes in consumer preferences could impact demand.
    The company's reliance on third-party manufacturers poses supply chain risks.

    === Management Discussion ===
    Revenue grew 8% year-over-year driven by strong Services performance.
    Operating margin improved to 30% due to operating leverage.
    The company generated $90 billion in operating cash flow.
    R&D spending increased as the company invests in proprietary technology.
    Customer retention rates remain above 90%.
    """

# Merged from the former tests/backend/conftest.py during test-tree consolidation.
os.environ.setdefault("FIREBASE_ADMIN_CLIENT_EMAIL", "test@test.iam.gserviceaccount.com")
os.environ.setdefault("FIREBASE_ADMIN_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMOCK\n-----END PRIVATE KEY-----")
import warnings as _warnings
_warnings.filterwarnings("ignore", category=DeprecationWarning)