
import os
import sys
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv

def generate_custom_token(uid: str):
    """
    Generates a Firebase Custom Token for the given UID using the Admin SDK.
    This method uses the service account credentials (google_credentials.json)
    and does not require a Web API Key.
    """
    try:
        # --- Load Environment & Config ---
        # The script is run from the root, so paths are relative to the root.
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
        load_dotenv(dotenv_path=dotenv_path)

        # The credential path is relative to the root directory
        cred_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'google_credentials.json')
        project_id = os.environ.get("FIREBASE_PROJECT_ID")

        if not os.path.exists(cred_path):
            print(f"\033[91mError: Service account file not found at '{cred_path}'\033[0m")
            print("Please follow the 'ENVIRONMENT_SETUP_GUIDE.md' to download it.")
            sys.exit(1)
        
        if not project_id:
            print("\033[91mError: FIREBASE_PROJECT_ID must be set in backend/.env\033[0m")
            sys.exit(1)

        # --- Initialize Firebase Admin SDK ---
        # Check if the app is already initialized to prevent errors on re-runs.
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {'projectId': project_id})
        
        # --- Generate Custom Token ---
        custom_token = auth.create_custom_token(uid)

        print("\n\033[92mFirebase Custom Token successfully generated!\033[0m")
        print("This is a CUSTOM token, used for server-side testing or to sign in a client SDK.")
        print("-" * 70)
        # The token is bytes, decode for printing
        print(f"\033[1m{custom_token.decode('utf-8')}\033[0m")
        print("-" * 70)

    except Exception as e:
        print(f"\033[91mAn error occurred: {e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_test_token.py <uid_or_email> [password_is_ignored]")
        sys.exit(1)
    
    # The UID for which to generate a token. We use the email argument for this.
    # The password argument is ignored but kept for compatibility with the old script's signature.
    user_uid = sys.argv[1]
    generate_custom_token(user_uid)
