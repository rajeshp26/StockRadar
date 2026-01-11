from fastapi import Request, HTTPException
from firebase_admin import auth, credentials
import firebase_admin
from config import settings
from shared.constants import AUTHORIZATION_HEADER, BEARER_PREFIX
import logging
import os

logger = logging.getLogger(__name__)

# Path to the service account key file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service-account.json")

def initialize_firebase_app():
    """
    Initializes the Firebase Admin SDK using the service account key.
    Logs a critical error and raises an exception if initialization fails.
    """
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred, {
                'projectId': settings.FIREBASE_PROJECT_ID,
            })
            logger.info("Firebase Admin SDK initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Firebase Admin SDK: {e}")
            raise

def get_current_user(request: Request):
    """
    Dependency that verifies the Firebase ID token from the Authorization header
    and returns the user's data.
    """
    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        logger.warning("Missing or invalid Authorization header.")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(BEARER_PREFIX)[1]
    
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
