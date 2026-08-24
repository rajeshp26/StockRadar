import requests
import json
import os

# Configuration: Read from environment variable, with a default
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001/users/sync")

# Test payload for user sync
TEST_PAYLOAD = {
    "firebase_uid": "test_firebase_uid_123",
    "email": "test.user@example.com",
    "display_name": "Test User"
}

def debug_user_sync():
    print(f"\nAttempting to send POST request to {BACKEND_URL}")
    print(f"Payload: {json.dumps(TEST_PAYLOAD, indent=2)}")

    try:
        response = requests.post(BACKEND_URL, json=TEST_PAYLOAD, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        print(f"\nBackend Response Status: {response.status_code}")
        print("Backend Response Body:")
        print(json.dumps(response.json(), indent=2))

    except requests.exceptions.Timeout:
        print("\nError: Request timed out. The backend did not respond within 10 seconds.")
    except requests.exceptions.ConnectionError as e:
        print(f"\nError: Could not connect to the backend at {BACKEND_URL}.")
        print("Please ensure your Python backend is running and accessible.")
        print(f"Details: {e}")
    except requests.exceptions.RequestException as e:
        print("\nError: An HTTP request error occurred.")
        print(f"Status Code: {response.status_code if 'response' in locals() else 'N/A'}")
        print(f"Response Body: {response.text if 'response' in locals() else 'N/A'}")
        print(f"Details: {e}")
    except json.JSONDecodeError:
        print("\nError: Could not decode JSON response from backend.")
        print(f"Raw response: {response.text}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    debug_user_sync()
