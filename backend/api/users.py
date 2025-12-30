
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from database import supabase
import firebase_admin.auth

router = APIRouter()

def get_firebase_uid_from_token(authorization: str) -> str:
    """
    Parses the Bearer token and verifies it with Firebase Admin to get the UID.
    This function is now called within the endpoint's main try block.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header not provided")
    
    parts = authorization.split()

    if parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization header must start with Bearer")
    elif len(parts) == 1:
        raise HTTPException(status_code=401, detail="Token not found")
    elif len(parts) > 2:
        raise HTTPException(status_code=401, detail="Authorization header must be Bearer token")

    token = parts[1]
    try:
        decoded_token = firebase_admin.auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        # Re-raise as a standard HTTP Exception that FastAPI can handle gracefully.
        raise HTTPException(status_code=403, detail=f"Invalid Firebase token: {e}")

@router.post("/users/sync", status_code=200, tags=["Users"])
def sync_user(request: Request, authorization: str = Header(None)):
    """
    Synchronizes a Firebase user with the Supabase database.
    This endpoint's sole responsibility is to create or update a user profile.
    It does NOT handle watchlist creation.
    """
    try:
        # 1. Get UID from token. This is now inside the try block.
        firebase_uid = get_firebase_uid_from_token(authorization)
        print(f"[DEBUG] Python Backend: Received sync request for Firebase UID: {firebase_uid}")

        # 2. Get user details from Firebase Admin SDK
        user_record = firebase_admin.auth.get_user(firebase_uid)
        email = user_record.email

        # 3. Upsert the user into the Supabase 'users' table.
        user_upsert_res = supabase.table('users').upsert({
            'firebase_uid': firebase_uid,
            'email': email,
            'username': user_record.display_name or email.split('@')[0],
            'preferred_currency': 'USD',
        }, on_conflict='firebase_uid').select('user_id, email, username').single().execute()

        # 4. Handle potential database errors
        if user_upsert_res.error:
            print(f"Supabase Error: {user_upsert_res.error}")
            raise HTTPException(status_code=500, detail=user_upsert_res.error.message)
        
        db_user = user_upsert_res.data

        # 5. Return the user's database profile.
        return {
            "user_id": db_user.get('user_id'),
            "email": db_user.get('email'),
            "username": db_user.get('username'),
        }

    except HTTPException as http_exc:
        # If it's already an HTTPException (like from our token helper), just re-raise it.
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors and return a clean 500.
        print(f"[ERROR] Python Backend Crash in /users/sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
