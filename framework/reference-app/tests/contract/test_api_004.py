"""Contract tests for API-004 (/auth/refresh).

The gate. Runs under pytest when available, and standalone via
`python3 tests/contract/test_api_004.py` when not — a contract gate must not depend on an
optional toolchain install.

These assert the IMPLEMENTATION against the SCHEMA. They are not unit tests of business logic.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()


def _find(relative: str) -> Path | None:
    """Nearest ancestor that contains ``relative``."""
    for parent in _HERE.parents:
        if (parent / relative).exists():
            return parent
    return None


# Two layouts, one test, resolved instead of pinned. As a CONSUMER (staged by `framework init`
# or installed as a wheel) the app root is two levels up and the contract lives in the
# documented `.planning/contracts/`. Inside the framework's own checkout the fixture is NOT the
# app root: its `contracts/` and `src/` sit under `framework/reference-app/`. Pinning either
# layout made the test runnable in exactly one of them -- and the one it could not run in is
# where `framework validate` executes it.
APP_ROOT = _find("src/backend/auth_service.py")
if APP_ROOT is None:  # pragma: no cover - structural failure, not a test failure
    raise SystemExit("cannot locate the reference application root from " + str(_HERE))
sys.path.insert(0, str(APP_ROOT))

# `framework` is a dependency of the app, never a copy of it: in the framework's checkout it
# is the sibling source tree; in a carved app it is the installed wheel on sys.path.
_FW_ROOT = _find("framework/contracts/validator.py")
if _FW_ROOT is not None:
    sys.path.insert(0, str(_FW_ROOT))

# The imports below MUST follow the sys.path setup above: the app root and the framework root
# are discovered at runtime, so hoisting them would import from whatever the caller's path
# happens to contain.
from framework.contracts.validator import validate_instance, load_contract  # noqa: E402
from src.backend.auth_service import handle_refresh  # noqa: E402

# Consumer layout first (the documented one), fixture layout as the fallback.
SCHEMA = next((p for p in (APP_ROOT / ".planning/contracts/api-004.openapi.yaml",
                           APP_ROOT / "contracts/api-004.openapi.yaml") if p.exists()), None)
if SCHEMA is None:  # pragma: no cover - structural failure, not a test failure
    raise SystemExit("cannot locate api-004.openapi.yaml under " + str(APP_ROOT))
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
            failed.append((t.__name__, str(e)))
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"  ERROR {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} contract tests passed")
    sys.exit(1 if failed else 0)
