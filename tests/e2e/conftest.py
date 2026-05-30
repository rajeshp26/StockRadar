"""
Shared pytest configuration for End-to-End tests.

All E2E tests are skipped unless RUN_E2E=true is set.
Provides fixtures for real Supabase client, HTTP client, auth, and account scoping.
"""

import os
import sys
from pathlib import Path
from typing import List

import pytest

# ── Markers ──────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: End-to-end test requiring real infrastructure")


# ── Skip gating ─────────────────────────────────────────────────────────

def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    """Skip all E2E tests unless RUN_E2E=true is set."""
    run = os.environ.get("RUN_E2E", "").lower() in ("true", "1", "yes")
    if run:
        return
    skip_msg = (
        "Set RUN_E2E=true with real Supabase credentials to run. "
        "Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "
        "and one of: E2E_AUTH_TOKEN or Firebase Admin credentials"
    )
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(pytest.mark.skip(reason=skip_msg))


# ── Path setup ──────────────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def e2e_supabase():
    """Real Supabase client for direct DB verification."""
    from database import supabase
    return supabase


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.environ.get("E2E_BASE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def e2e_auth_headers() -> dict:
    """Authorization headers using a real Firebase ID token."""
    from tests.e2e.helpers import get_auth_headers
    return get_auth_headers()


@pytest.fixture(scope="session")
def e2e_single_holding_headers(e2e_auth_headers) -> dict:
    """
    Headers for a user with only 1 holding (or the same user if no dedicated token).
    Set E2E_SINGLE_HOLDING_TOKEN to a different user's token.
    """
    token = os.environ.get("E2E_SINGLE_HOLDING_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return e2e_auth_headers


@pytest.fixture(scope="session")
def e2e_account_ids() -> list[int]:
    """Account IDs for scoping tests. Set via E2E_ACCOUNT_IDS."""
    raw = os.environ.get("E2E_ACCOUNT_IDS")
    if raw:
        return [int(x) for x in raw.split(",") if x.strip()]
    return []


@pytest.fixture(scope="session")
async def e2e_http_client(e2e_base_url):
    """Real httpx client against the running backend."""
    import httpx
    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(
        base_url=e2e_base_url, timeout=30.0, transport=transport
    ) as client:
        yield client



