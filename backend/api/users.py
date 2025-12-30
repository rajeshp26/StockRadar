
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

        # Upsert the user and immediately select the record to get the user_id
        # FIXED: Added 'preferred_currency' to satisfy the NOT NULL constraint in the database.
        user_upsert_res = supabase.table('users').upsert({
            'firebase_uid': firebase_uid,
            'email': email,
            'username': user_record.display_name or email.split('@')[0],
            'preferred_currency': 'USD',
        }, on_conflict='firebase_uid').select('user_id, email, username').single().execute()

        if user_upsert_res.error:
            print(f"Supabase Error: {user_upsert_res.error}")
            raise HTTPException(status_code=500, detail=user_upsert_res.error.message)
        
        db_user = user_upsert_res.data
        db_user_id = db_user['user_id']

        # Ensure a default watchlist exists for the user
        watchlist_check_res = supabase.table('watchlists').select('id', count='exact').eq('user_id', db_user_id).eq('is_default', True).execute()
        
        default_watchlist_id = None
        # Check if a default watchlist exists by looking at the count
        if watchlist_check_res.count == 0:
            # If no default watchlist, create one
            new_watchlist_res = supabase.table('watchlists').insert({
                'user_id': db_user_id, 
                'watchlist_name': 'My Watchlist', 
                'is_default': True
            }).select('id').single().execute()
            if new_watchlist_res.error:
                 raise HTTPException(status_code=500, detail="Failed to create default watchlist.")
            default_watchlist_id = new_watchlist_res.data['id']
        else:
            # If it exists, get the id from the first result
            watchlist_data = supabase.table('watchlists').select('id').eq('user_id', db_user_id).eq('is_default', True).limit(1).single().execute()
            default_watchlist_id = watchlist_data.data['id']


        return {
            "user_id": db_user_id,
            "email": db_user['email'],
            "username": db_user['username'],
            "default_watchlist_id": default_watchlist_id
        }

    except Exception as e:
        print(f"[ERROR] Python Backend Crash in /users/sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

