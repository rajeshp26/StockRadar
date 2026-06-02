
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import supabase
from dependencies import get_current_user_dep
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
    user: dict = Depends(get_current_user_dep)
):
    """
    Synchronizes the authenticated user with the Supabase database.
    This is a robust "upsert" operation.
    - If auth_id exists, UPDATE.
    - If email exists, UPDATE (to link accounts).
    - Otherwise, INSERT.
    IDENTITY: The 'auth_id' (Supabase user UUID) is from the JWT 'sub' claim.
    """
    auth_id = user["sub"]
    email = body.email
    
    try:
        # Prepare the data payload for the upsert operation.
        user_data = {
            'email': email,
            'username': body.username,
            'last_signed_in': datetime.now().isoformat(),
            'auth_id': auth_id,
            'preferred_currency': 'USD'
        }

        # 1. Check if a user exists with this auth_id.
        res_auth = supabase.table('users').select('user_id').eq('auth_id', auth_id).execute()

        if res_auth.data:
            # Case 1: User with this auth_id exists. Update their profile.
            logger.info(f"Sync: Updating existing profile for auth_id: {auth_id}")
            update_res = supabase.table('users').update(user_data).eq('auth_id', auth_id).execute()
            return update_res.data[0]
        else:
            # Case 2: No user with this auth_id. Check if the email is already in use.
            res_email = supabase.table('users').select('user_id').eq('email', email).execute()
            if res_email.data:
                # An account with this email exists. Link it to the new auth_id.
                logger.info(f"Sync: Email {email} exists. Linking new auth_id: {auth_id}")
                update_res = supabase.table('users').update(user_data).eq('email', email).execute()
                return update_res.data[0]
            else:
                # Case 3: No user with this auth_id or email. Create a new record.
                logger.info(f"Sync: Creating new user profile for auth_id: {auth_id}")
                insert_res = supabase.table('users').insert(user_data).execute()
                return insert_res.data[0]

    except Exception as e:
        db_error_details = str(getattr(e, 'message', str(e)))
        logger.error(f"Database sync operation failed for auth_id: {auth_id}. DB Error: {db_error_details}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to sync user profile: {db_error_details}"
        )
