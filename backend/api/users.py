from fastapi import APIRouter, Depends, HTTPException, Request
from database import supabase
import firebase_admin.auth
from dependencies import get_user_id_from_header

router = APIRouter()

@router.post("/users/sync", status_code=200, tags=["Users"])
def sync_user(request: Request, firebase_uid: str = Depends(get_user_id_from_header)):
    # DEBUG LOG
    print(f"[DEBUG] Python Backend: Received sync request for Firebase UID: {firebase_uid}")
    
    try:
        try:
            user_record = firebase_admin.auth.get_user(firebase_uid)
            email = user_record.email
        except Exception as e:
            print(f"Firebase Auth Error: {e}")
            raise HTTPException(status_code=403, detail=f"Invalid Firebase token: {e}")

        user_upsert_res = supabase.table('users').upsert({
            'firebase_uid': firebase_uid,
            'email': email,
            'username': user_record.display_name or email.split('@')[0],
        }, on_conflict='firebase_uid').select().execute()

        if user_upsert_res.error:
            print(f"Supabase Error: {user_upsert_res.error}")
            raise HTTPException(status_code=500, detail=user_upsert_res.error.message)
        
        db_user_id = user_upsert_res.data[0]['user_id']

        # Ensure default watchlist
        watchlist_check = supabase.table('watchlists').select('id').eq('user_id', db_user_id).eq('is_default', True).execute()
        if not watchlist_check.data:
            supabase.table('watchlists').insert({'user_id': db_user_id, 'watchlist_name': 'My Watchlist', 'is_default': True}).execute()

        # Fetch profile
        profile = supabase.table('users').select('user_id, email, username, watchlists!inner(id)').eq('user_id', db_user_id).eq('watchlists.is_default', True).single().execute()

        return {
            "user_id": profile.data['user_id'],
            "email": profile.data['email'],
            "username": profile.data['username'],
            "default_watchlist_id": profile.data['watchlists'][0]['id']
        }

    except Exception as e:
        print(f"[ERROR] Python Backend Crash: {e}")
        raise HTTPException(status_code=500, detail=str(e))
