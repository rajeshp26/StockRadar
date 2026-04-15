# backend/auth.py
#
# SECURITY CHANGES FROM ORIGINAL:
#  1. Firebase Admin SDK initialization now prefers env vars over service-account.json
#  2. SSE connections can be authenticated via X-Verified-UID header
#     (set by Next.js proxy after verifying a Firebase session cookie)
#  3. X-Verified-UID is only trusted from the local proxy (127.0.0.1/::1)
#
from fastapi import Request, HTTPException
from firebase_admin import auth, credentials
import firebase_admin
from config import settings
from shared.constants import AUTHORIZATION_HEADER, BEARER_PREFIX
import logging
import os

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service-account.json")

# Header injected by the Next.js proxy after verifying a Firebase session cookie.
# Used for SSE connections (EventSource cannot send custom Authorization headers).
VERIFIED_UID_HEADER = "x-verified-uid"

# Only trust X-Verified-UID from these hosts (the local Next.js proxy).
# Prevents external callers from bypassing auth by forging this header.
TRUSTED_PROXY_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _is_trusted_proxy(request: Request) -> bool:
    """Return True only if the request originates from the local Next.js proxy."""
    if not request.client:
        return False
    return request.client.host in TRUSTED_PROXY_HOSTS


def initialize_firebase_app():
    """
    Initialize Firebase Admin SDK.

    Priority:
      1. Environment variables (FIREBASE_ADMIN_CLIENT_EMAIL + FIREBASE_ADMIN_PRIVATE_KEY)
         — required for production deployments.
      2. service-account.json file — development fallback only.

    Logs a critical error and raises if initialization fails.
    """
    if firebase_admin._apps:
        return  # Already initialized

    try:
        project_id = settings.FIREBASE_PROJECT_ID

        client_email = getattr(settings, "FIREBASE_ADMIN_CLIENT_EMAIL", None) or \
                       os.environ.get("FIREBASE_ADMIN_CLIENT_EMAIL")
        private_key_raw = getattr(settings, "FIREBASE_ADMIN_PRIVATE_KEY", None) or \
                          os.environ.get("FIREBASE_ADMIN_PRIVATE_KEY")

        if client_email and private_key_raw:
            # Production path: credentials from environment variables
            private_key = private_key_raw.replace("\\n", "\n")
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            logger.info("Firebase Admin SDK initialized from environment variables.")

        elif os.path.exists(SERVICE_ACCOUNT_FILE):
            # Development fallback: service account JSON file
            if settings.is_production:
                logger.critical(
                    "service-account.json found in production. "
                    "Use FIREBASE_ADMIN_CLIENT_EMAIL and FIREBASE_ADMIN_PRIVATE_KEY env vars instead. "
                    "Remove service-account.json from the repository."
                )
                raise RuntimeError(
                    "service-account.json must not be used in production. "
                    "Set FIREBASE_ADMIN_CLIENT_EMAIL and FIREBASE_ADMIN_PRIVATE_KEY."
                )
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            logger.warning(
                "Firebase Admin SDK initialized from service-account.json (development only). "
                "Set FIREBASE_ADMIN_CLIENT_EMAIL and FIREBASE_ADMIN_PRIVATE_KEY for production."
            )

        else:
            raise FileNotFoundError(
                "Firebase Admin credentials not found. "
                "Set FIREBASE_ADMIN_CLIENT_EMAIL and FIREBASE_ADMIN_PRIVATE_KEY env vars, "
                "or provide service-account.json for development."
            )

        firebase_admin.initialize_app(cred, {"projectId": project_id})

    except Exception as e:
        logger.critical(f"Failed to initialize Firebase Admin SDK: {e}")
        raise


def get_current_user(request: Request):
    """
    FastAPI dependency that authenticates the current request.

    Authentication order:
      1. X-Verified-UID header from trusted local proxy (SSE connections only).
         The proxy verifies Firebase session cookies and injects this header.
      2. Authorization: Bearer <firebase_id_token> header (standard API calls).
         Tries ID token verification first, then falls back to session cookie
         verification for requests forwarded from the Next.js proxy.

    Returns the decoded token dict on success.
    Raises HTTPException 401 on failure.
    """

    # ── Path 1: Proxy-verified UID (SSE) ────────────────────────────────────
    verified_uid = request.headers.get(VERIFIED_UID_HEADER)
    logger.info(f"[AUTH-DEBUG] Headers: auth={bool(request.headers.get('authorization'))}, verified_uid={bool(request.headers.get('x-verified-uid'))}")
    if verified_uid:
        if not _is_trusted_proxy(request):
            # Log this — it means someone is trying to forge the header externally
            logger.warning(
                f"X-Verified-UID header received from untrusted host: {request.client.host if request.client else 'unknown'}. "
                "This may indicate an attack attempt."
            )
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: X-Verified-UID from untrusted source"
            )
        # Return a minimal user dict compatible with how the rest of the app uses decoded tokens
        logger.debug(f"SSE auth via X-Verified-UID for uid={verified_uid}")
        return {"uid": verified_uid, "sub": verified_uid}

    # ── Path 2: Firebase ID token in Authorization header ───────────────────
    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        logger.warning("Missing or invalid Authorization header.")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )

    token = auth_header[len(BEARER_PREFIX):]

    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as id_token_error:
        logger.debug(f"ID token verification failed, trying session cookie: {id_token_error}")

    try:
        decoded_token = auth.verify_session_cookie(token, check_revoked=True)
        logger.debug(f"Session cookie verified for uid={decoded_token.get('uid')}")
        return decoded_token
    except Exception as session_error:
        logger.error(f"Token verification failed (ID token: {id_token_error}, session cookie: {session_error})")
        raise HTTPException(status_code=401, detail="Invalid or expired token")