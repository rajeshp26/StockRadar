
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
    try:
        print(f"[DEBUG] Python Backend: Received sync request for Firebase UID: {sync_request.firebase_uid}")

        # Upsert the user into the Supabase 'users' table.
        user_upsert_res = supabase.table('users').upsert({
            'firebase_uid': sync_request.firebase_uid,
            'email': sync_request.email,
            'username': sync_request.display_name or sync_request.email.split('@')[0],
            'preferred_currency': 'USD',
        }, on_conflict='firebase_uid').select('user_id, email, username').single().execute()

        # Handle potential database errors
        if user_upsert_res.error:
            print(f"Supabase Error: {user_upsert_res.error}")
            raise HTTPException(status_code=500, detail=user_upsert_res.error.message)
        
        db_user = user_upsert_res.data

        # Return the user's database profile.
        return {
            "user_id": db_user.get('user_id'),
            "email": db_user.get('email'),
            "username": db_user.get('username'),
        }

    except HTTPException as http_exc:
        # If it's already an HTTPException, just re-raise it.
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors and return a clean 500.
        print(f"[ERROR] Python Backend Crash in /users/sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
