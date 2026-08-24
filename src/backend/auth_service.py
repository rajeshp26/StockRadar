"""Reference implementation for contract API-004.

Deliberately minimal. It exists so G1 has something real to validate against on first run,
and so contract drift is demonstrable rather than theoretical.

The request schema is enforced at the boundary using the contract itself as the source of
truth — the pattern the python skill mandates.
"""
from pathlib import Path

from framework.contracts.validator import load_contract, validate_instance

_CONTRACT = load_contract(Path(".planning/contracts/api-004.openapi.yaml"))
_OP = ("/auth/refresh", "post")

# Stand-in for a token store. Real implementations inject this.
_KNOWN_DEVICES = {None, "web-1", "ios-1"}


def _error(code: str, message: str):
    return {"code": code, "message": message}


def handle_refresh(body: dict):
    """Return (status, payload) conforming to contract API-004."""
    schema = _CONTRACT.request_schema(*_OP)
    errs = validate_instance(body, schema, _CONTRACT.doc)
    if errs:
        return 400, _error("invalid_request", "; ".join(errs)[:200])

    if body.get("device_id") not in _KNOWN_DEVICES:
        return 401, _error("invalid_grant", "refresh token is not valid for this device")

    return 200, {
        "access_token": "a" * 40,
        "expires_in": 3600,
        "token_type": "Bearer",
        "refresh_token": body["refresh_token"],
    }
