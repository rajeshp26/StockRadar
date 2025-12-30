
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from database import supabase

router = APIRouter()

class UserSyncRequest(BaseModel):
    firebase_uid: str
    email: str
    display_name: str | None = None

@router.post("/users/sync", status_code=200, tags=["Users"])
def sync_user(sync_request: UserSyncRequest):
    """
    Synchronizes a Firebase user with the Supabase database.
    This endpoint's sole responsibility is to create or update a user profile.
    It does NOT handle watchlist creation. It trusts the firebase_uid provided by the frontend.
    """
    print(">>> DEBUG: SYNC REQUEST RECEIVED")
    try:
        print(f"[DEBUG] Python Backend: Received sync request for Firebase UID: {sync_request.firebase_uid}")

        print("[DEBUG] Python Backend: Attempting Supabase upsert...")
        # 1. Perform the upsert. .execute() returns the data if successful.
        # Note: In Python, we don't chain .select() after .upsert()
        response = supabase.table('users').upsert({
            'firebase_uid': sync_request.firebase_uid,
            'email': sync_request.email,
            'username': sync_request.display_name or sync_request.email.split('@')[0],
            'preferred_currency': 'USD',
        }, on_conflict='firebase_uid').execute()
        print("[DEBUG] Python Backend: Supabase upsert executed.")

        # 2. In Python, the data is in the .data attribute (which is a list)
        if not response.data:
            raise Exception("No data returned from database")

        db_user = response.data[0] # Get the first (and likely only) returned row
        print(f"[DEBUG] Python Backend: User data retrieved: {db_user}")

        # Return the user's database profile.
        return {
            "user_id": db_user.get('user_id'),
            "email": db_user.get('email'),
            "username": db_user.get('username'),
        }

    except Exception as e:
        # This catches database errors, connection issues, etc.
        print(f"[ERROR] Python Backend Crash in /users/sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
