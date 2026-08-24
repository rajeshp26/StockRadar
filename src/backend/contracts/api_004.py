# GENERATED from api-004.openapi.yaml — do not edit by hand. Regenerate: framework/contracts/gen_types.py
from typing import TypedDict, Literal, NotRequired

class RefreshRequest(TypedDict):
    refresh_token: str
    device_id: NotRequired[str]

class RefreshResponse(TypedDict):
    access_token: str
    expires_in: int
    token_type: Literal['Bearer']
    refresh_token: NotRequired[str]

class Error(TypedDict):
    code: str
    message: str

