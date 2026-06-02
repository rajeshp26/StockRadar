import os
import sys
from dotenv import load_dotenv

def generate_supabase_token(email: str):
    """
    Generates a Supabase access token for the given email using the
    Supabase service role key. Signs in with email/password.
    """
    try:
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
        load_dotenv(dotenv_path=dotenv_path)

        supabase_url = os.environ.get("SUPABASE_URL")
        anon_key = os.environ.get("SUPABASE_ANON_KEY")

        if not supabase_url or not anon_key:
            print("\033[91mError: SUPABASE_URL and SUPABASE_ANON_KEY must be set in backend/.env\033[0m")
            sys.exit(1)

        from supabase import create_client
        client = create_client(supabase_url, anon_key)

        password = os.environ.get("E2E_TEST_PASSWORD", "StockerPro123!")
        result = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })

        print("\n\033[92mSupabase access token successfully generated!\033[0m")
        print("-" * 70)
        print(f"Email: {email}")
        print(f"User ID: {result.user.id}")
        print(f"\n\033[1mAccess Token:\033[0m")
        print(f"\033[1m{result.session.access_token}\033[0m")
        print("-" * 70)
        print("\nUse the token as: Authorization: Bearer <token>")

    except ImportError:
        print("\033[91mError: supabase package not installed. Run: pip install supabase\033[0m")
        sys.exit(1)
    except Exception as e:
        print(f"\033[91mAn error occurred: {e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_test_token.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    generate_supabase_token(email)
