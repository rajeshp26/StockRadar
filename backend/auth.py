# backend/auth.py
#
# Cookie-only BFF (Backend for Frontend) authentication.
# All requests arrive via the Next.js proxy, which reads the __session cookie
# and injects it as `Authorization: Bearer <jwt>`.
# The backend verifies the JWT locally using the Supabase JWT secret (HS256)
# or cached JWKS public keys (RS256).
#
import json
import logging
import time

import httpx
from fastapi import HTTPException, Request
from jwt import decode as jwt_decode
from jwt import get_unverified_header
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from config import settings
from shared.constants import AUTHORIZATION_HEADER, BEARER_PREFIX

logger = logging.getLogger(__name__)

JWKS_CACHE_TTL = 86400  # 24 hours — keys rotate infrequently
_jwks = {"keys": None, "fetched": 0}


def _get_public_key(kid: str):
    """Fetch and cache Supabase JWKS, return RSA public key for given kid."""
    now = time.time()
    if not _jwks["keys"] or (now - _jwks["fetched"]) > JWKS_CACHE_TTL:
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        try:
            resp = httpx.get(jwks_url, timeout=5)
            resp.raise_for_status()
            _jwks["keys"] = resp.json()["keys"]
            _jwks["fetched"] = now
            logger.debug("JWKS keys refreshed from Supabase")
        except Exception as e:
            logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
            if not _jwks["keys"]:
                raise HTTPException(
                    status_code=502,
                    detail="Authentication service unavailable"
                )
            logger.warning("Using stale JWKS keys after fetch failure")

    key_data = next((k for k in _jwks["keys"] if k["kid"] == kid), None)
    if not key_data:
        raise HTTPException(status_code=401, detail="Invalid token: unknown key ID")

    kty = key_data.get("kty")
    if kty == "EC":
        return ECAlgorithm.from_jwk(json.dumps(key_data))
    return RSAAlgorithm.from_jwk(json.dumps(key_data))


def _verify_hs256(token: str, options: dict) -> dict:
    """Verify a Supabase JWT signed with HS256 using the project JWT secret."""
    return jwt_decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
        options=options,
    )


def _verify_rs256(token: str, kid: str, options: dict) -> dict:
    """Verify a Supabase JWT signed with RS256 using cached JWKS public keys."""
    public_key = _get_public_key(kid)
    return jwt_decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="authenticated",
        options=options,
    )


def _verify_es256(token: str, kid: str, options: dict) -> dict:
    """Verify a Supabase JWT signed with ES256 using cached JWKS public keys."""
    public_key = _get_public_key(kid)
    return jwt_decode(
        token,
        public_key,
        algorithms=["ES256"],
        audience="authenticated",
        options=options,
    )


def verify_jwt(token: str) -> dict:
    """Verify a Supabase JWT locally.

    Supports HS256 (shared secret), RS256 (JWKS), and ES256 (JWKS) algorithms.
    """
    try:
        unverified = get_unverified_header(token)
    except Exception as e:
        logger.warning(f"Failed to decode JWT header: {e}")
        raise HTTPException(status_code=401, detail="Invalid token format")

    alg = unverified.get("alg")
    kid = unverified.get("kid")
    options = {"require": ["exp", "sub"]}

    try:
        if alg == "HS256":
            decoded = _verify_hs256(token, options)
        elif alg == "RS256":
            if not kid:
                raise HTTPException(status_code=401, detail="Invalid token: missing key ID")
            decoded = _verify_rs256(token, kid, options)
        elif alg == "ES256":
            if not kid:
                raise HTTPException(status_code=401, detail="Invalid token: missing key ID")
            decoded = _verify_es256(token, kid, options)
        else:
            logger.warning(f"Unsupported JWT algorithm: {alg}")
            raise HTTPException(status_code=401, detail=f"Unsupported token algorithm: {alg}")

        logger.debug(f"JWT verified for sub={decoded.get('sub')}")
        return decoded
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(request: Request):
    """
    FastAPI dependency that authenticates the current request.

    The Next.js proxy reads the __session cookie from all incoming requests
    (including EventSource/SSE) and injects it as:
      Authorization: Bearer <jwt>

    This function verifies the JWT locally using the Supabase JWT secret (HS256)
    or cached JWKS keys (RS256). No fallback chain — single verification path.

    Returns the decoded token dict on success.
    Raises HTTPException 401 on failure.
    """
    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        logger.warning("Missing or invalid Authorization header.")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )

    token = auth_header[len(BEARER_PREFIX):]

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )

    return verify_jwt(token)
