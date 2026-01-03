
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from database import supabase
from dependencies import verify_firebase_token, limiter

router = APIRouter()

class UserSyncRequest(BaseModel):
    email: str
    display_name: str | None = None

@router.post("/users/sync", status_code=200, tags=["Users"])
@limiter.limit("5/minute")
def sync_user(
    request: Request,
    sync_request: UserSyncRequest,
    user_token: dict = Depends(verify_firebase_token)
):
    """
    Synchronizes a Firebase user with the Supabase database.
    Rate limited to 5 requests per minute.
    """
    firebase_uid = user_token["uid"]
    
    try:
        response = supabase.table('users').upsert({
            'firebase_uid': firebase_uid,
            'email': sync_request.email,
            'username': sync_request.display_name or sync_request.email.split('@')[0],
            'preferred_currency': 'USD',
        }, on_conflict='firebase_uid').execute()

        if not response.data:
            raise Exception("No data returned from database")

        db_user = response.data[0]
        return {
            "user_id": db_user.get('user_id'),
            "email": db_user.get('email'),
            "username": db_user.get('username'),
        }

    except Exception as e:
        print(f"[ERROR] /users/sync: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync user profile")
