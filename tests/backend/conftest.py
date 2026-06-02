import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "http://test.db.local")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "eyJtest_supabase_service_key_for_testing_only_abcd")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("FIREBASE_ADMIN_CLIENT_EMAIL", "test@test.iam.gserviceaccount.com")
os.environ.setdefault("FIREBASE_ADMIN_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMOCK\n-----END PRIVATE KEY-----")

import sys
import warnings
from unittest.mock import MagicMock, patch

_backend = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

# Silence deprecation warnings from dependencies during testing
warnings.filterwarnings("ignore", category=DeprecationWarning)
