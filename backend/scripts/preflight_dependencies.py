"""Preflight: fail loudly when the installed environment drifts from the pins.

WHY THIS EXISTS
---------------
The price pipeline was dead for ~6 weeks and nothing said so. The cause was not a
code bug and not missing data: ``requirements.txt`` correctly declared
``defeatbeta-api==0.0.61`` and ``duckdb==1.5.3`` (``requirements.txt:70``, ``:80``)
while the *installed* environment was ``0.0.50`` / ``1.4.3``. ``defeatbeta-api``
0.0.50 pins ``duckdb==1.4.3``, and the ``cache_httpfs`` extension it loads at
connection time does not exist for 1.4.3 -- a direct probe of
community-extensions.duckdb.org returns HTTP 404 for v1.4.3 and HTTP 206 for
v1.5.3. Every price fetch therefore died at DuckDBClient initialisation.

The failure was invisible because each symbol's fetch degraded to a per-symbol
warning; the scheduler recorded ``consecutive_price_failures`` and moved on, so
``price_history`` emptied out silently instead of anything erroring at startup.

This check turns that silent class of outage into an explicit, immediate error.

SCOPE
-----
Only the *pinned* (``==``) entries in ``requirements.txt`` are checked, and only
for packages that are actually installed -- an uninstalled package is reported as
missing rather than crashing the parse. Non-pinned (``>=``) entries are ignored:
they are ranges, not contracts, and drift within a range is not what this guards.

Usage::

    python backend/scripts/preflight_dependencies.py            # check
    python backend/scripts/preflight_dependencies.py --quiet    # only on failure

Exit codes:
    0  installed environment matches every pinned requirement
    1  drift detected (names each mismatch) -- DO NOT TRUST PRICE DATA
    2  the check itself could not run (missing/unreadable requirements.txt)
"""
from __future__ import annotations

import argparse
import re
import sys
from importlib import metadata
from pathlib import Path

REQ_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"

# Packages whose drift starves the price pipeline. Checked FIRST and reported as
# FATAL so the specific outage this script was written for is unmistakable.
PIPELINE_CRITICAL = ("defeatbeta-api", "duckdb")


def _canonical(name: str) -> str:
    """PEP 503 canonical name: runs of ``-_.`` collapse to ``-``, lowercased."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_pins(path: Path) -> dict[str, str]:
    """Return {canonical_name: version} for every ``name[extras]==version`` line.

    requirements.txt mixes pinned (``==``) and ranged (``>=``) entries and carries
    ``# via ...`` provenance comments; only exact pins are contracts we can fail on.

    Two details matter for a *trustworthy* comparator (I11):
      * extras (``httpx[http2]==...``, ``coverage[toml]==...``) must still be read --
        the old regex ignored them, so drift in those packages was invisible;
      * names are canonicalised (PEP 503) so a declared alias resolves to the same
        distribution ``importlib.metadata`` reports, avoiding false "NOT INSTALLED".
    """
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)(?:\[[^\]]+\])?\s*==\s*([^\s;]+)", line)
        if not m:
            continue
        pins[_canonical(m.group(1))] = m.group(2)
    return pins


def _installed(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check() -> list[tuple[str, str, str | None]]:
    """Return drift as [(name, declared, installed_or_None), ...]; [] means clean.

    Importable form of the check, so startup hooks can call it without spawning a
    subprocess or parsing stdout. `installed is None` means the package is missing.
    Also returns [] (never raises) when requirements.txt cannot be read -- callers
    that need to distinguish "clean" from "unreadable" should use main()'s exit
    codes instead.
    """
    try:
        pins = _parse_pins(REQ_FILE)
    except OSError:
        return []
    if not pins:
        return []
    drift: list[tuple[str, str, str | None]] = []
    for name, want in sorted(pins.items()):
        have = _installed(name)
        if have != want:
            drift.append((name, want, have))
    return drift


def startup_check(logger=None) -> bool:
    """Run the drift check at process startup. Returns True when the env is clean.

    Deliberately non-fatal by default: silently starving price_history is the
    failure this catches, and a hard crash at startup would take unrelated
    schedulers down with it. The drift is logged as a LOUD CLS-style banner so it
    is visible in the worker log rather than discovered six weeks later.

    Set PRICE_PREFLIGHT_FATAL=1 to make drift fatal instead (recommended for
    price-only deployments / CI).
    """
    import os
    drift = check()
    if not drift:
        if logger:
            logger.info("Dependency preflight OK: installed environment matches "
                        "requirements.txt")
        return True

    critical = {n for n, _, _ in drift} & set(PIPELINE_CRITICAL)
    lines = [
        "=" * 68,
        "DEPENDENCY DRIFT DETECTED - installed environment != requirements.txt",
        "=" * 68,
    ]
    if critical:
        lines += [
            "",
            "!! FATAL: price-pipeline dependency is wrong.",
            "!! The provider cannot initialise, every fetch degrades to a warning,",
            "!! and price_history is starved without any error surfacing.",
            "!! PRICE DATA WRITTEN BY THIS PROCESS IS NOT TRUSTWORTHY.",
        ]
    for name, want, have in drift:
        tag = "  <-- PIPELINE CRITICAL" if name in PIPELINE_CRITICAL else ""
        shown = have if have is not None else "NOT INSTALLED"
        lines.append(f"  DRIFT {name}: declared {want}, installed {shown}{tag}")
    lines += ["", "Fix: python -m pip install -r backend/requirements.txt", ""]
    msg = "\n".join(lines)

    if logger:
        logger.error(msg)
    else:
        print(msg, file=sys.stderr)

    # Fail fast on critical dependency drift by default.
    if critical:
        raise RuntimeError(
            "PRICE_PREFLIGHT_FATAL: pipeline-critical dependency drift detected: "
            + ", ".join(sorted(critical))
        )
    # With the explicit opt-in, ALL drift is fatal -- not just pipeline-critical.
    # (The previous nested `if critical` here was unreachable: critical already
    # raised above, so PRICE_PREFLIGHT_FATAL did nothing. I11.)
    if os.environ.get("PRICE_PREFLIGHT_FATAL", "").strip() in ("1", "true", "yes"):
        raise RuntimeError(
            "PRICE_PREFLIGHT_FATAL: dependency drift detected: "
            + ", ".join(sorted(n for n, _, _ in drift))
        )
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing unless drift is found")
    args = ap.parse_args()

    if not REQ_FILE.exists():
        print(f"PREFLIGHT_ERROR: {REQ_FILE} not found", file=sys.stderr)
        return 2
    try:
        pins = _parse_pins(REQ_FILE)
    except OSError as exc:
        print(f"PREFLIGHT_ERROR: cannot read {REQ_FILE}: {exc}", file=sys.stderr)
        return 2
    if not pins:
        # An unreadable or reformatted file must not read as "all good".
        print(f"PREFLIGHT_ERROR: no pinned (==) requirements parsed from {REQ_FILE}",
              file=sys.stderr)
        return 2

    drift: list[tuple[str, str, str | None]] = []
    missing: list[str] = []
    for name, want in sorted(pins.items()):
        have = _installed(name)
        if have is None:
            missing.append(name)
        elif have != want:
            drift.append((name, want, have))

    if not drift and not missing:
        if not args.quiet:
            print(f"PREFLIGHT OK: {len(pins)} pinned requirements match the "
                  f"installed environment")
        return 0

    critical = {n for n, *_ in drift} & set(PIPELINE_CRITICAL) | (
        set(missing) & set(PIPELINE_CRITICAL))

    print("=" * 68)
    print("PREFLIGHT FAILED: installed environment has drifted from requirements.txt")
    print("=" * 68)
    if critical:
        print()
        print("!! FATAL: a price-pipeline dependency is wrong.")
        print("!! This is the exact condition that empties price_history: the")
        print("!! provider cannot initialise, every fetch degrades to a warning,")
        print("!! and the scheduler records failures instead of rows.")
        print("!! PRICE DATA WRITTEN IN THIS ENVIRONMENT IS NOT TRUSTWORTHY.")
    for name, want, have in drift:
        tag = "  <-- PIPELINE CRITICAL" if name in PIPELINE_CRITICAL else ""
        print(f"  MISMATCH {name}: declared {want}, installed {have}{tag}")
    for name in missing:
        tag = "  <-- PIPELINE CRITICAL" if name in PIPELINE_CRITICAL else ""
        print(f"  MISSING  {name}: declared {pins[name]}, not installed{tag}")
    print()
    print("Fix:  python -m pip install -r backend/requirements.txt")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
