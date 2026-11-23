"""Unit tests for the single security valuation kernel (AC-3)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_mixed_direct_and_cdr_lots_are_valued_independently():
    from domain.valuation import value_lots, value_security

    cdr = value_security(
        security={
            "security_id": 9001,
            "symbol": "META",
            "exchange": "NEO",
            "kind": "CDR",
            "currency": "CAD",
            "cdr_ratio": 10,
        },
        quantity=25,
        price=100.0,
        fx_rate=1.0,
    )
    direct = value_security(
        security={
            "security_id": 9002,
            "symbol": "META",
            "exchange": "NMS",
            "kind": "COMMON",
            "currency": "USD",
            "cdr_ratio": None,
        },
        quantity=2,
        price=100.0,
        fx_rate=1.0,
    )

    assert cdr.effective_price == 10.0
    assert cdr.cdr_ratio_applied == 10.0
    assert direct.effective_price == 100.0
    assert direct.cdr_ratio_applied is None
    assert cdr.reporting_value + direct.reporting_value == 450.0
    assert value_lots([cdr, direct]).reporting_value == 450.0


def test_cdr_without_ratio_is_rejected():
    from domain.valuation import ValuationError, value_security

    try:
        value_security(
            security={"security_id": 1, "kind": "CDR", "currency": "CAD", "cdr_ratio": None},
            quantity=1,
            price=10.0,
        )
    except ValuationError as exc:
        assert exc.code == "MISSING_CDR_RATIO"
    else:
        raise AssertionError("a CDR with no ratio was priced")


def test_fx_is_applied_once_after_ratio():
    from domain.valuation import value_security

    result = value_security(
        security={"security_id": 2, "kind": "COMMON", "currency": "USD", "cdr_ratio": None},
        quantity=3,
        price=20.0,
        fx_rate=1.25,
    )
    assert result.native_value == 60.0
    assert result.reporting_value == 75.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc!r}")
    raise SystemExit(1 if failed else 0)
