from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import supabase
from dependencies import verify_firebase_token, limiter
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class UserSync(BaseModel):
    email: str
    username: str

@router.post("/users/sync", tags=["Users"])
def sync_user(
    body: UserSync,
    user_token: dict = Depends(verify_firebase_token)
):
    """
    Synchronizes the Firebase User with the Supabase database.
    IDENTITY: The 'firebase_uid' is taken from the TOKEN, not the body.
    """
    firebase_uid = user_token["uid"]
    
    try:
        # Check if user already exists
        res = supabase.table('users').select('*').eq('firebase_uid', firebase_uid).execute()
        
        user_data = {
            'email': body.email,
            'username': body.username,
            'last_signed_in': datetime.now().isoformat(),
            'firebase_uid': firebase_uid
        }

        if not res.data:
            # Create new user
            logger.info(f"Sync: Creating new user profile for UID: {firebase_uid}")
            insert_res = supabase.table('users').insert(user_data).execute()
            return insert_res.data[0]
        else:
            # Update existing user
            logger.info(f"Sync: Updating existing profile for UID: {firebase_uid}")
            update_res = supabase.table('users').update(user_data).eq('firebase_uid', firebase_uid).execute()
            return update_res.data[0]

    except Exception as e:
        logger.error(f"Sync Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync user profile")
