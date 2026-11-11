"""
User Sync — End-to-End Test

Validates the /users/sync endpoint end-to-end:
  1. Simulates a NEW user login → Expects 201 Created
  2. Simulates an EXISTING user login → Expects 200 OK

No mocking. Requires RUN_E2E=true + real Supabase credentials + backend running.
"""

import uuid

import pytest


@pytest.mark.e2e
class TestUserSyncE2E:
    """Validate user sync lifecycle end-to-end."""

    ENDPOINT = "/users/sync"

    async def test_new_user_creates_account(self, e2e_http_client, e2e_auth_headers):
        """A new user should get 201 Created."""
        new_email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
        resp = await e2e_http_client.post(
            self.ENDPOINT,
            json={"email": new_email, "username": "E2E New User"},
            headers=e2e_auth_headers,
        )
        assert resp.status_code == 201, (
            f"New user sync expected 201, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "user_id" in data or "id" in data

    async def test_existing_user_returns_200(self, e2e_http_client, e2e_auth_headers):
        """An existing user should get 200 OK."""
        email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
        # First call creates
        create_resp = await e2e_http_client.post(
            self.ENDPOINT,
            json={"email": email, "username": "E2E Existing User"},
            headers=e2e_auth_headers,
        )
        assert create_resp.status_code == 201

        # Second call with same email should return 200
        lookup_resp = await e2e_http_client.post(
            self.ENDPOINT,
            json={"email": email, "username": "E2E Existing User"},
            headers=e2e_auth_headers,
        )
        assert lookup_resp.status_code == 200, (
            f"Existing user sync expected 200, got {lookup_resp.status_code}: {lookup_resp.text[:200]}"
        )

    async def test_user_sync_without_auth(self, e2e_http_client):
        """Unauthenticated request should be rejected."""
        resp = await e2e_http_client.post(
            self.ENDPOINT,
            json={"email": "noauth@example.com", "username": "No Auth"},
        )
        assert resp.status_code in (401, 403)
