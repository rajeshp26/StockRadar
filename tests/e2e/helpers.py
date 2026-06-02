"""
Shared utilities for StockerPro End-to-End tests.

Provides:
  - Auth token generation (Supabase access token)
  - Supabase client creation
  - Test user lifecycle management

Usage:
    from tests.e2e.helpers import get_auth_headers, get_supabase
"""

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"


def _ensure_backend_on_path():
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))


# ── Auth ─────────────────────────────────────────────────────────────────

def _try_generate_supabase_token(uid: str | None = None, email: str | None = None) -> str | None:
    """
    Generate a Supabase access token for E2E testing.

    Uses the Supabase service role key to create or retrieve a test user,
    then generates a sign-in token. Falls back to E2E_SUPABASE_TOKEN env var.
    """
    try:
        from supabase import create_client, Client
    except ImportError:
        logger.warning("supabase package not installed; cannot auto-generate token")
        return None

    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_key:
        logger.warning("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for token generation")
        return None

    resolve_email = email or os.environ.get("E2E_TEST_EMAIL", "e2e-test@stockerpro-test.com")
    resolve_password = os.environ.get("E2E_TEST_PASSWORD", "StockerPro123!")

    try:
        admin: Client = create_client(supabase_url, service_key)

        try:
            admin.auth.admin.create_user({
                "email": resolve_email,
                "password": resolve_password,
                "email_confirm": True,
            })
            logger.info(f"Created test user: {resolve_email}")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"Test user already exists: {resolve_email}")
            else:
                logger.exception("Failed to create test user")
                return None

        client: Client = create_client(supabase_url, os.environ.get("SUPABASE_ANON_KEY", ""))
        result = client.auth.sign_in_with_password({
            "email": resolve_email,
            "password": resolve_password,
        })
        return result.session.access_token
    except Exception:
        logger.exception("Failed to generate Supabase access token")
        return None


def get_id_token(uid: str | None = None, email: str | None = None) -> str:
    """
    Get a valid Supabase access token for E2E tests.
    Priority: E2E_AUTH_TOKEN env var → auto-generate from Supabase Admin.
    """
    token = os.environ.get("E2E_AUTH_TOKEN")
    if token:
        return token
    generated = _try_generate_supabase_token(uid, email)
    if generated:
        return generated
    raise RuntimeError(
        "Cannot authenticate for E2E tests. Set E2E_AUTH_TOKEN env var, "
        "or provide SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and SUPABASE_ANON_KEY env vars."
    )


def get_auth_headers(uid: str | None = None, email: str | None = None) -> dict:
    """Get Authorization headers for E2E API calls."""
    return {"Authorization": f"Bearer {get_id_token(uid, email)}"}


# ── Supabase ─────────────────────────────────────────────────────────────

def get_supabase():
    """Get a real Supabase client from the database module."""
    _ensure_backend_on_path()
    from database import supabase
    return supabase


# ── Test Data Helpers ────────────────────────────────────────────────────

def upsert_test_account(supabase, user_id: int, account_name: str = "E2E Test Account", account_type: str = "brokerage") -> int:
    """Create or retrieve a test portfolio account. Returns the account ID."""
    data = {
        "user_id": user_id,
        "name": account_name,
        "type": account_type,
        "currency": "USD",
    }
    result = supabase.table("portfolio_accounts").upsert(data, on_conflict="user_id,name").execute()
    return result.data[0]["id"]


def upsert_test_holding(supabase, account_id: int, symbol: str, quantity: float = 10.0, avg_cost: float = 100.0) -> int:
    """Create a test holding. Returns holding ID."""
    data = {
        "account_id": account_id,
        "symbol": symbol,
        "quantity": quantity,
        "average_cost": avg_cost,
        "currency": "USD",
    }
    result = supabase.table("portfolio_holdings").upsert(
        data, on_conflict="account_id,symbol"
    ).execute()
    return result.data[0]["id"]


def upsert_test_snapshot(supabase, user_id: int, date_str: str, total_value: float, cash: float = 0.0):
    """Create a portfolio performance snapshot."""
    data = {
        "user_id": user_id,
        "snapshot_date": date_str,
        "total_value": total_value,
        "cash": cash,
    }
    supabase.table("portfolio_performance").upsert(
        data, on_conflict="user_id,snapshot_date"
    ).execute()


def cleanup_test_data(supabase, user_id: int):
    """Remove all E2E test data for a given user."""
    for table in ["portfolio_performance", "portfolio_holdings", "portfolio_accounts"]:
        supabase.table(table).delete().eq("user_id", user_id).execute()
