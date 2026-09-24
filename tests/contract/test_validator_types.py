"""Contract-validator type matrix: bool must never satisfy integer or number.

Regression for the subset-mode gap where `{"type": "number"}` accepted True
because `bool` is an `int` subclass. Assertions are mode-agnostic: they check
rejection, not the exact message, so the gate behaves identically under
jsonschema and subset mode. Runs standalone, matching tests/contract convention.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.contracts.validator import validate_instance

DOC = {}


def test_bool_rejected_as_integer():
    assert validate_instance(True, {"type": "integer"}, DOC)


def test_bool_rejected_as_number():
    assert validate_instance(False, {"type": "number"}, DOC)


def test_real_integer_and_float_still_accepted():
    assert not validate_instance(3, {"type": "integer"}, DOC)
    assert not validate_instance(3.5, {"type": "number"}, DOC)


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