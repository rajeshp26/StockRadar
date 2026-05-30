"""
Shared utilities for StockerPro End-to-End tests.

Provides:
  - Auth token generation (Firebase ID token)
  - Supabase client creation
  - Test user lifecycle management

Usage:
    from tests.e2e.helpers import get_auth_headers, get_supabase
"""

import os
import sys
import json
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

def _try_load_google_credentials() -> dict | None:
    """Load google_credentials.json from backend directory."""
    paths = [
        _BACKEND_DIR / "google_credentials.json",
        _PROJECT_ROOT / "google_credentials.json",
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    return None


def _try_generate_id_token(uid: str | None = None, email: str | None = None) -> str | None:
    """
    Generate a Firebase ID token using Admin SDK.
    Falls back: google_credentials.json → FIREBASE_ADMIN_* env vars.
    """
    try:
        import firebase_admin
        from firebase_admin import credentials, auth
    except ImportError:
        logger.warning("firebase-admin not installed; cannot auto-generate token")
        return None

    if firebase_admin._apps:
        firebase_admin.get_app()
    else:
        creds_dict = _try_load_google_credentials()
        if creds_dict:
            cred = credentials.Certificate(creds_dict)
            project_id = creds_dict.get("project_id")
            firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)
        else:
            pid = os.environ.get("FIREBASE_ADMIN_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID")
            client_email = os.environ.get("FIREBASE_ADMIN_CLIENT_EMAIL")
            private_key = os.environ.get("FIREBASE_ADMIN_PRIVATE_KEY")
            if pid and client_email and private_key:
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": pid,
                    "client_email": client_email,
                    "private_key": private_key.replace("\\n", "\n"),
                    "private_key_id": "",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                })
                firebase_admin.initialize_app(cred, {"projectId": pid})
            else:
                logger.warning("No Firebase credentials available for token generation")
                return None

    resolve_uid = uid or os.environ.get("E2E_TEST_UID", "e2e-test-user")
    resolve_email = email or os.environ.get("E2E_TEST_EMAIL", "e2e-test@stockerpro-test.com")

    try:
        user = auth.get_user_by_email(resolve_email)
    except auth.UserNotFoundError:
        user = auth.create_user(
            uid=resolve_uid,
            email=resolve_email,
            password=os.environ.get("E2E_TEST_PASSWORD", "StockerPro123!"),
        )
    except Exception:
        logger.exception("Failed to look up or create Firebase user")
        return None

    try:
        custom_token = auth.create_custom_token(user.uid).decode("utf-8")
    except Exception:
        logger.exception("Failed to create Firebase custom token")
        return None

    api_key = os.environ.get("FIREBASE_WEB_API_KEY")
    if not api_key:
        logger.warning("FIREBASE_WEB_API_KEY not set; cannot exchange custom token for ID token")
        return None

    try:
        import requests
        resp = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}",
            json={"token": custom_token, "returnSecureToken": True},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["idToken"]
    except Exception:
        logger.exception("Token exchange with Firebase Identity Toolkit failed")
        return None


def get_id_token(uid: str | None = None, email: str | None = None) -> str:
    """
    Get a valid Firebase ID token for E2E tests.
    Priority: E2E_AUTH_TOKEN env var → auto-generate from Admin SDK.
    """
    token = os.environ.get("E2E_AUTH_TOKEN")
    if token:
        return token
    generated = _try_generate_id_token(uid, email)
    if generated:
        return generated
    raise RuntimeError(
        "Cannot authenticate for E2E tests. Set E2E_AUTH_TOKEN env var, "
        "or provide Firebase Admin credentials (google_credentials.json or FIREBASE_ADMIN_* env vars) "
        "plus FIREBASE_WEB_API_KEY for token exchange."
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
