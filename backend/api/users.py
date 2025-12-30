
from fastapi import APIRouter, Depends, HTTPException, Request
from database import supabase
import firebase_admin.auth
from dependencies import get_user_id_from_header

router = APIRouter()

@router.post("/users/sync", status_code=200, tags=["Users"])
def sync_user(request: Request, firebase_uid: str = Depends(get_user_id_from_header)):
    """
    Synchronizes a Firebase user with the Supabase database.
    This endpoint's sole responsibility is to create or update a user profile.
    It does NOT handle watchlist creation.
    """
    print(f"[DEBUG] Python Backend: Received sync request for Firebase UID: {firebase_uid}")
    
    try:
        try:
            # 1. Get user details from Firebase Admin SDK
            user_record = firebase_admin.auth.get_user(firebase_uid)
            email = user_record.email
        except Exception as e:
            print(f"Firebase Auth Error: {e}")
            raise HTTPException(status_code=403, detail=f"Invalid Firebase token: {e}")

        # 2. Upsert the user into the Supabase 'users' table.
        # This will create a new user or update an existing one based on firebase_uid.
        user_upsert_res = supabase.table('users').upsert({
            'firebase_uid': firebase_uid,
            'email': email,
            'username': user_record.display_name or email.split('@')[0],
            'preferred_currency': 'USD', # Default value as per schema
        }, on_conflict='firebase_uid').select('user_id, email, username').single().execute()

        # 3. Handle potential database errors
        if user_upsert_res.error:
            print(f"Supabase Error: {user_upsert_res.error}")
            raise HTTPException(status_code=500, detail=user_upsert_res.error.message)
        
        db_user = user_upsert_res.data

        # 4. Return the user's database profile.
        return {
            "user_id": db_user['user_id'],
            "email": db_user['email'],
            "username": db_user['username'],
        }

    except Exception as e:
        print(f"[ERROR] Python Backend Crash in /users/sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
