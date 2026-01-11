
import os
import sys
import uuid
from dotenv import load_dotenv
import requests
import json

def run_e2e_test():
    """
    Executes an end-to-end test of the /users/sync endpoint.
    1. Simulates a NEW user login -> Expect 201 Created
    2. Simulates an EXISTING user login -> Expect 200 OK
    """
    # Load environment variables from backend/.env
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    # Use a real, but temporary, Firebase auth token for a test user
    # In a real CI/CD pipeline, you would generate this token programmatically
    auth_token = os.environ.get("FIREBASE_TEST_AUTH_TOKEN")
    if not auth_token:
        print("ERROR: FIREBASE_TEST_AUTH_TOKEN must be set in backend/.env for this test.")
        sys.exit(1)

    # The URL for our local development server
    url = "http://127.0.0.1:9002/api/proxy/users/sync"

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    # --- Test Case 1: New User --- #
    # Use a unique email to ensure this user is always new
    new_email = f"testuser_{uuid.uuid4()}@example.com"
    new_user_payload = {
        "email": new_email,
        "username": "E2E Test User"
    }

    print(f"--- Running Test Case 1: NEW USER ({new_email}) ---")
    try:
        response_new = requests.post(url, headers=headers, data=json.dumps(new_user_payload))
        print(f"Response Status Code: {response_new.status_code}")
        print(f"Response Body: {response_new.json()}")

        if response_new.status_code == 201:
            print("\033[92mSUCCESS: New user sync returned 201 Created as expected.\033[0m")
        else:
            print(f"\033[91mFAILURE: Expected 201, but got {response_new.status_code}\033[0m")
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"\033[91mFAILURE: Request failed: {e}\033[0m")
        sys.exit(1)

    # --- Test Case 2: Existing User --- #
    # Use the *same* payload again. The corrected logic should now find the user.
    print(f"\n--- Running Test Case 2: EXISTING USER ({new_email}) ---")
    try:
        response_existing = requests.post(url, headers=headers, data=json.dumps(new_user_payload))
        print(f"Response Status Code: {response_existing.status_code}")
        print(f"Response Body: {response_existing.json()}")

        if response_existing.status_code == 200:
            print("\033[92mSUCCESS: Existing user sync returned 200 OK as expected.\033[0m")
        else:
            print(f"\033[91mFAILURE: Expected 200, but got {response_existing.status_code}\033[0m")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"\033[91mFAILURE: Request failed: {e}\033[0m")
        sys.exit(1)

    print("\n\033[1;92mAll E2E tests passed successfully!\033[0m")

if __name__ == "__main__":
    run_e2e_test()
