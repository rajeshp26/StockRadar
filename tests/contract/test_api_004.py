"""Contract tests for API-004 (/auth/refresh).

The gate. Runs under pytest when available, and standalone via
`python3 tests/contract/test_api_004.py` when not — a contract gate must not depend on an
optional toolchain install.

These assert the IMPLEMENTATION against the SCHEMA. They are not unit tests of business logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from framework.contracts.validator import validate_instance, load_contract
from src.backend.auth_service import handle_refresh

SCHEMA = Path(".planning/contracts/api-004.openapi.yaml")
CONTRACT = load_contract(SCHEMA)
OP = ("/auth/refresh", "post")

VALID_TOKEN = "r" * 32


def _call(body):
    """Invoke the implementation the way a consumer would."""
    status, payload = handle_refresh(body)
    return status, payload


def _assert_response(status, payload, expected_status):
    assert status == expected_status, f"expected {expected_status}, got {status}"
    declared = CONTRACT.response_schema(*OP, str(status))
    assert declared is not None, f"status {status} is not declared in the contract"
    errs = validate_instance(payload, declared, CONTRACT.doc)
    assert not errs, f"response violates contract: {errs}"


def test_declared_statuses_are_exactly_implemented():
    """An undocumented status code is a contract violation."""
    declared = set(CONTRACT.statuses(*OP))
    assert declared == {"200", "400", "401"}, f"contract declares {declared}"


def test_success_returns_contract_shaped_response():
    status, payload = _call({"refresh_token": VALID_TOKEN})
    _assert_response(status, payload, 200)
    assert payload["token_type"] == "Bearer"
    assert payload["expires_in"] >= 1


def test_missing_required_field_returns_400():
    status, payload = _call({})
    _assert_response(status, payload, 400)


def test_additional_properties_rejected():
    """`additionalProperties: false` in the request schema must be enforced."""
    status, payload = _call({"refresh_token": VALID_TOKEN, "unexpected": 1})
    _assert_response(status, payload, 400)


def test_short_token_violates_min_length_returns_400():
    status, payload = _call({"refresh_token": "tooshort"})
    _assert_response(status, payload, 400)


def test_invalid_token_returns_401_not_500():
    status, payload = _call({"refresh_token": "x" * 32, "device_id": "unknown-device"})
    _assert_response(status, payload, 401)


def test_error_responses_carry_contract_error_shape():
    for body, expected in (({}, 400), ({"refresh_token": "x" * 32,
                                        "device_id": "unknown-device"}, 401)):
        status, payload = _call(body)
        assert status == expected
        assert set(payload) >= {"code", "message"}, f"error payload missing keys: {payload}"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = []
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, str(e))); print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e))); print(f"  ERROR {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} contract tests passed")
    sys.exit(1 if failed else 0)
