
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import supabase
from dependencies import get_current_user_dep
from shared.time_utils import now_iso
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class UserSync(BaseModel):
    email: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_currency: Optional[str] = None


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    preferred_currency: Optional[str] = None

@router.post("/users/sync", tags=["Users"])
def sync_user(
    body: UserSync,
    user: dict = Depends(get_current_user_dep)
):
    """
    Synchronizes the authenticated user with the Supabase database.
    Uses DB-level UNIQUE constraints on auth_id and email for race-condition-safe upsert.
    """
    auth_id = user["sub"]
    email = body.email

    try:
        user_data = {
            'email': email,
            'username': body.username,
            'last_signed_in': now_iso(),
            'auth_id': auth_id,
            'first_name': body.first_name,
            'last_name': body.last_name,
            'avatar_url': body.avatar_url,
        }
        user_data['preferred_currency'] = body.preferred_currency or 'USD'

        result = supabase.table('users').upsert(
            user_data,
            on_conflict='auth_id'
        ).execute()

        if result.data:
            return result.data[0]

        raise HTTPException(status_code=500, detail="Upsert returned no data")

    except Exception as e:
        db_error_details = str(getattr(e, 'message', str(e)))
        logger.error(f"Database sync failed for auth_id {auth_id}: {db_error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync user profile: {db_error_details}"
        )


@router.get("/users/me", tags=["Users"])
def get_current_user_profile(
    user: dict = Depends(get_current_user_dep)
):
    """
    Returns the authenticated user's profile from the `users` table.
    Read-only — does not update last_signed_in.
    """
    auth_id = user["sub"]

    try:
        result = supabase.table('users').select(
            'user_id', 'auth_id', 'email', 'username',
            'first_name', 'last_name', 'avatar_url',
            'preferred_currency', 'last_signed_in'
        ).eq('auth_id', auth_id).maybe_single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User profile not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        db_error_details = str(getattr(e, 'message', str(e)))
        logger.error(f"Failed to fetch profile for auth_id {auth_id}: {db_error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user profile: {db_error_details}"
        )


@router.patch("/users/me", tags=["Users"])
def update_current_user_profile(
    body: UserProfileUpdate,
    user: dict = Depends(get_current_user_dep)
):
    """
    Updates the authenticated user's profile fields.
    Only includes fields that are explicitly provided (not None).
    Never changes auth_id or last_signed_in via this endpoint.
    """
    auth_id = user["sub"]

    try:
        patch_data = {k: v for k, v in body.model_dump().items() if v is not None}

        if not patch_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = supabase.table('users').update(patch_data).eq('auth_id', auth_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User profile not found")

        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        db_error_details = str(getattr(e, 'message', str(e)))
        logger.error(f"Failed to update profile for auth_id {auth_id}: {db_error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update user profile: {db_error_details}"
        )
