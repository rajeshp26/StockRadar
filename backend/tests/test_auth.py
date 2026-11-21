"""Tests for auth.get_current_user — Supabase JWT local verification."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_request(headers: dict | None = None) -> MagicMock:
    """Create a mock FastAPI Request with given headers."""
    req = MagicMock()
    header_dict = headers or {}
    req.headers.get = MagicMock(side_effect=lambda key, default=None: header_dict.get(key, default))
    return req


class TestGetCurrentUser:
    """Tests for auth.get_current_user."""

    def test_valid_hs256_jwt_returns_decoded_token(self):
        """Should return decoded token for HS256 JWT."""
        with patch("auth.verify_jwt") as mock_verify:
            mock_verify.return_value = {"sub": "user-uuid", "email": "test@test.com"}
            from auth import get_current_user

            req = _make_request({"Authorization": "Bearer valid.jwt.token"})
            result = get_current_user(req)

            assert result == {"sub": "user-uuid", "email": "test@test.com"}
            mock_verify.assert_called_once_with("valid.jwt.token")

    def test_missing_authorization_header_returns_401(self):
        """Should raise 401 when no Authorization header present."""
        from auth import get_current_user

        req = _make_request({})
        with pytest.raises(HTTPException) as exc:
            get_current_user(req)
        assert exc.value.status_code == 401

    def test_malformed_header_without_bearer_returns_401(self):
        """Should raise 401 when Authorization header lacks Bearer prefix."""
        from auth import get_current_user

        req = _make_request({"authorization": "Basic some_token"})
        with pytest.raises(HTTPException) as exc:
            get_current_user(req)
        assert exc.value.status_code == 401

    def test_empty_bearer_token_returns_401(self):
        """Should raise 401 when Bearer token is empty string."""
        from auth import get_current_user

        req = _make_request({"authorization": "Bearer "})
        with pytest.raises(HTTPException) as exc:
            get_current_user(req)
        assert exc.value.status_code == 401

    def test_verify_jwt_failure_returns_401(self):
        """Should raise 401 when JWT verification fails."""
        with patch("auth.verify_jwt") as mock_verify:
            mock_verify.side_effect = HTTPException(status_code=401, detail="Invalid or expired token")
            from auth import get_current_user

            req = _make_request({"Authorization": "Bearer invalid.token"})
            with pytest.raises(HTTPException) as exc:
                get_current_user(req)
            assert exc.value.status_code == 401

    def test_x_verified_uid_no_longer_accepted(self):
        """X-Verified-UID header should no longer be a valid auth path."""
        from auth import get_current_user

        req = _make_request({"x-verified-uid": "user123"})
        with pytest.raises(HTTPException) as exc:
            get_current_user(req)
        assert exc.value.status_code == 401
        assert "Missing or invalid" in exc.value.detail


class TestVerifyJwt:
    """Tests for auth.verify_jwt."""

    def test_hs256_token_uses_secret(self):
        """Should verify HS256 token using SUPABASE_JWT_SECRET."""
        mock_decode = MagicMock(return_value={"sub": "user-uuid", "email": "test@test.com"})
        with patch.multiple(
            "auth",
            get_unverified_header=MagicMock(return_value={"alg": "HS256", "kid": "test-kid"}),
            jwt_decode=mock_decode,
        ):
            from auth import verify_jwt
            result = verify_jwt("hs256.token.here")
            assert result == {"sub": "user-uuid", "email": "test@test.com"}
            kwargs = mock_decode.call_args.kwargs
            assert kwargs["algorithms"] == ["HS256"]
            assert kwargs["audience"] == "authenticated"

    def test_rs256_token_uses_jwks(self):
        """Should verify RS256 token using JWKS public key."""
        mock_decode = MagicMock(return_value={"sub": "user-uuid"})
        mock_get_key = MagicMock(return_value="mock-public-key")
        with patch.multiple(
            "auth",
            get_unverified_header=MagicMock(return_value={"alg": "RS256", "kid": "rsa-kid"}),
            jwt_decode=mock_decode,
            _get_public_key=mock_get_key,
        ):
            from auth import verify_jwt
            result = verify_jwt("rs256.token.here")
            assert result == {"sub": "user-uuid"}
            mock_get_key.assert_called_once_with("rsa-kid")
            kwargs = mock_decode.call_args.kwargs
            assert kwargs["algorithms"] == ["RS256"]

    def test_unsupported_algorithm_returns_401(self):
        """Should raise 401 for a genuinely unsupported JWT algorithm.

        ES256 became supported in commit 3be122eb (alongside HS256/RS256),
        so it no longer exercises this branch — use PS256 instead.
        """
        with patch("auth.get_unverified_header", return_value={"alg": "PS256"}):
            from auth import verify_jwt
            with pytest.raises(HTTPException) as exc:
                verify_jwt("bad-alg.token")
            assert exc.value.status_code == 401
            assert "Unsupported token algorithm" in exc.value.detail

    def test_invalid_header_returns_401(self):
        """Should raise 401 when JWT header cannot be decoded."""
        with patch("auth.get_unverified_header", side_effect=Exception("bad header")):
            from auth import verify_jwt
            with pytest.raises(HTTPException) as exc:
                verify_jwt("bad.token")
            assert exc.value.status_code == 401
            assert "Invalid token format" in exc.value.detail

    def test_signature_failure_returns_401(self):
        """Should raise 401 when JWT signature verification fails."""
        with patch.multiple(
            "auth",
            get_unverified_header=MagicMock(return_value={"alg": "HS256"}),
            jwt_decode=MagicMock(side_effect=Exception("Signature verification failed")),
        ):
            from auth import verify_jwt
            with pytest.raises(HTTPException) as exc:
                verify_jwt("bad-sig.token")
            assert exc.value.status_code == 401

    def test_rs256_unknown_kid_returns_401(self):
        """Should raise 401 when JWKS has no matching kid for RS256."""
        with (
            patch.multiple(
                "auth",
                get_unverified_header=MagicMock(return_value={"alg": "RS256", "kid": "unknown-kid"}),
            ),
            patch("auth._get_public_key") as mock_key,
        ):
            mock_key.side_effect = HTTPException(status_code=401, detail="Invalid token: unknown key ID")
            from auth import verify_jwt
            with pytest.raises(HTTPException) as exc:
                verify_jwt("unknown-kid.token")
            assert exc.value.status_code == 401


class TestGetPublicKey:
    """Tests for auth._get_public_key."""

    def test_jwks_fetch_failure_without_cache_returns_502(self):
        """Should raise 502 when JWKS fetch fails and no cached keys."""
        with patch("auth.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            from auth import _get_public_key, _jwks
            _jwks["keys"] = None
            _jwks["fetched"] = 0

            with pytest.raises(HTTPException) as exc:
                _get_public_key("any-kid")
            assert exc.value.status_code == 502
            assert "Authentication service unavailable" in exc.value.detail

    def test_jwks_fetch_with_stale_cache_succeeds(self):
        """Should fall back to stale JWKS when fetch fails and cache exists."""
        from auth import _get_public_key, _jwks

        _jwks["keys"] = [{"kid": "other-kid"}]
        _jwks["fetched"] = 0

        with patch("auth.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            with pytest.raises(HTTPException) as exc:
                _get_public_key("any-kid")
            assert exc.value.status_code == 401
            assert "unknown key ID" in exc.value.detail
