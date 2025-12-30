from fastapi import Header, HTTPException
import firebase_admin.auth

def get_user_id_from_header(authorization: str = Header(None)) -> str:
    """
    Dependency to get user_id from the Firebase JWT in the Authorization header.
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
        uid = decoded_token['uid']
        return uid
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"Invalid Firebase token: {e}")
