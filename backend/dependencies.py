from fastapi import Header, HTTPException

def get_user_id_from_header(user_id: str = Header(..., alias="X-User-Id")) -> str:
    """
    Dependency to get user_id from a request header.
    In a real app, this would involve decoding a JWT token.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")
    return user_id
