"""
Portfolio API Latency Test

Hits the LIVE backend API endpoints with a generated JWT and measures
end-to-end HTTP response times.  Fails if any endpoint exceeds its threshold.

Usage:
    python -m pytest tests/test_portfolio_api_latency.py -v -s
    python -m pytest tests/test_portfolio_api_latency.py -v -s -k "dashboard"

WARNING: Requires backend at BACKEND_ORIGIN to be running.
"""

import os
import sys
import time
from pathlib import Path

# Load real env vars before conftest.py overrides them
_env_file = Path(__file__).resolve().parent.parent / ".env"
_SUPABASE_URL = "https://viqdqgxcumcdhqxooplw.supabase.co"
_SUPABASE_KEY = "sb_secret_NxN3ywf1RrMektnf-rq9hg_FxKFOVoG"
if _env_file.exists():
    import dotenv
    _env_vars = dotenv.dotenv_values(_env_file)
    _SUPABASE_URL = _env_vars.get("SUPABASE_URL") or _SUPABASE_URL
    _SUPABASE_KEY = _env_vars.get("SUPABASE_SERVICE_ROLE_KEY") or _SUPABASE_KEY

from datetime import datetime, timedelta

import httpx
import jwt as pyjwt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Config ────────────────────────────────────────────────────────────────────

BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://172.19.86.61:8001")
JWT_SECRET = None
_env_secret_path = Path(__file__).resolve().parent.parent / ".env"
if _env_secret_path.exists():
    import dotenv
    _env = dotenv.dotenv_values(_env_secret_path)
    JWT_SECRET = _env.get("SUPABASE_JWT_SECRET")

AUTH_ID = "59a7ced9-aa7c-4f34-b77e-266fc8a8e796"
TIMEOUT_SECONDS = 60


# ── Thresholds (ms) ───────────────────────────────────────────────────────────
# These are the MAX acceptable times for each endpoint.
# They should be tightened as optimisations land.

ENDPOINT_THRESHOLDS = {
    "Dashboard Bundle": 15000,
    "Overview": 5000,
    "Accounts": 5000,
    "Holdings": 5000,
    "Performance 1Y": 15000,
    "Performance 1M": 3000,
    "Performance 3M": 3000,
    "Brokerages": 1500,
    "Benchmarks": 1500,
    "Allocation": 5000,
}

ENDPOINTS = [
    ("GET", "/portfolio/dashboard", "Dashboard Bundle"),
    ("GET", "/portfolio/overview", "Overview"),
    ("GET", "/portfolio/accounts", "Accounts"),
    ("GET", "/portfolio/holdings", "Holdings"),
    ("GET", "/portfolio/performance?period=1Y", "Performance 1Y"),
    ("GET", "/portfolio/performance?period=1M", "Performance 1M"),
    ("GET", "/portfolio/performance?period=3M", "Performance 3M"),
    ("GET", "/portfolio/brokerages", "Brokerages"),
    ("GET", "/benchmarks", "Benchmarks"),
    ("GET", "/portfolio/allocation", "Allocation"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token() -> str:
    if not JWT_SECRET:
        pytest.skip("SUPABASE_JWT_SECRET not found in .env")
    payload = {
        "sub": AUTH_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(datetime.now().timestamp()),
        "exp": int((datetime.now() + timedelta(hours=1)).timestamp()),
        "email": "rajeshp01@gmail.com",
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-id-token": token,
    }


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    token = _make_token()
    hdrs = _headers(token)
    c = httpx.Client(base_url=BACKEND_ORIGIN, headers=hdrs, timeout=TIMEOUT_SECONDS, follow_redirects=False)
    yield c
    c.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPortfolioApiLatency:
    """Measure real HTTP response times for every portfolio endpoint."""

    @pytest.fixture(autouse=True)
    def _warmup(self, client):
        """One warmup call to prime Supabase connection pool + query cache."""
        try:
            client.get("/portfolio/brokerages")
        except Exception:
            pass
        yield

    def _time_request(self, client, method: str, path: str, label: str) -> dict:
        url = path
        start = time.perf_counter()
        try:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json={})
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "label": label,
                "status": resp.status_code,
                "ms": elapsed,
                "size_kb": len(resp.content) / 1024,
                "ok": resp.status_code == 200,
            }
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "label": label,
                "status": 0,
                "ms": elapsed,
                "size_kb": 0,
                "ok": False,
                "error": str(e),
            }

    def test_dashboard_bundle(self, client):
        r = self._time_request(client, "GET", "/portfolio/dashboard", "Dashboard Bundle")
        thresh = ENDPOINT_THRESHOLDS["Dashboard Bundle"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Dashboard returned {r['status']}"
        assert r["ms"] < thresh, f"Dashboard took {r['ms']:.0f}ms (limit {thresh})"

    def test_overview(self, client):
        r = self._time_request(client, "GET", "/portfolio/overview", "Overview")
        thresh = ENDPOINT_THRESHOLDS["Overview"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Overview returned {r['status']}"
        assert r["ms"] < thresh, f"Overview took {r['ms']:.0f}ms (limit {thresh})"

    def test_accounts(self, client):
        r = self._time_request(client, "GET", "/portfolio/accounts", "Accounts")
        thresh = ENDPOINT_THRESHOLDS["Accounts"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Accounts returned {r['status']}"
        assert r["ms"] < thresh, f"Accounts took {r['ms']:.0f}ms (limit {thresh})"

    def test_holdings(self, client):
        r = self._time_request(client, "GET", "/portfolio/holdings", "Holdings")
        thresh = ENDPOINT_THRESHOLDS["Holdings"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Holdings returned {r['status']}"
        assert r["ms"] < thresh, f"Holdings took {r['ms']:.0f}ms (limit {thresh})"

    def test_performance_1y(self, client):
        r = self._time_request(client, "GET", "/portfolio/performance?period=1Y", "Performance 1Y")
        thresh = ENDPOINT_THRESHOLDS["Performance 1Y"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Performance 1Y returned {r['status']}"
        assert r["ms"] < thresh, f"Performance 1Y took {r['ms']:.0f}ms (limit {thresh})"

    def test_performance_1m(self, client):
        r = self._time_request(client, "GET", "/portfolio/performance?period=1M", "Performance 1M")
        thresh = ENDPOINT_THRESHOLDS["Performance 1M"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Performance 1M returned {r['status']}"
        assert r["ms"] < thresh, f"Performance 1M took {r['ms']:.0f}ms (limit {thresh})"

    def test_performance_3m(self, client):
        r = self._time_request(client, "GET", "/portfolio/performance?period=3M", "Performance 3M")
        thresh = ENDPOINT_THRESHOLDS["Performance 3M"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Performance 3M returned {r['status']}"
        assert r["ms"] < thresh, f"Performance 3M took {r['ms']:.0f}ms (limit {thresh})"

    def test_brokerages(self, client):
        r = self._time_request(client, "GET", "/portfolio/brokerages", "Brokerages")
        thresh = ENDPOINT_THRESHOLDS["Brokerages"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Brokerages returned {r['status']}"
        assert r["ms"] < thresh, f"Brokerages took {r['ms']:.0f}ms (limit {thresh})"

    def test_benchmarks(self, client):
        r = self._time_request(client, "GET", "/benchmarks", "Benchmarks")
        thresh = ENDPOINT_THRESHOLDS["Benchmarks"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Benchmarks returned {r['status']}"
        assert r["ms"] < thresh, f"Benchmarks took {r['ms']:.0f}ms (limit {thresh})"

    def test_allocation(self, client):
        r = self._time_request(client, "GET", "/portfolio/allocation", "Allocation")
        thresh = ENDPOINT_THRESHOLDS["Allocation"]
        print(f"\n    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>7.1f}KB  threshold={thresh}ms")
        assert r["status"] == 200, f"Allocation returned {r['status']}"
        assert r["ms"] < thresh, f"Allocation took {r['ms']:.0f}ms (limit {thresh})"


# ── Waterfall Report ─────────────────────────────────────────────────────────

class TestPortfolioWaterfallReport:
    """Run all endpoints sequentially and print a waterfall chart."""

    @pytest.fixture(autouse=True)
    def _warmup(self, client):
        try:
            client.get("/portfolio/brokerages")
            client.get("/portfolio/accounts")
        except Exception:
            pass
        yield

    def test_waterfall_report(self, client):
        results = []
        for method, path, label in ENDPOINTS:
            url = path
            start = time.perf_counter()
            try:
                resp = client.get(url)
                elapsed = (time.perf_counter() - start) * 1000
                results.append({
                    "label": label,
                    "status": resp.status_code,
                    "ms": elapsed,
                    "size_kb": len(resp.content) / 1024,
                })
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                results.append({
                    "label": label,
                    "status": 0,
                    "ms": elapsed,
                    "size_kb": 0,
                    "error": str(e),
                })

        # Print waterfall
        total_ms = sum(r["ms"] for r in results)
        width = 50
        print()
        print("=" * 100)
        print("  PORTFOLIO API WATERFALL")
        print(f"  Backend: {BACKEND_ORIGIN}")
        print(f"  Total:   {total_ms:.0f}ms ({total_ms/1000:.1f}s)")
        print("=" * 100)
        print()

        for i, r in enumerate(results, 1):
            bar_len = max(1, int(r["ms"] / max(total_ms, 1) * width))
            bar = "#" * bar_len
            status = f"HTTP {r['status']}" if r["status"] else "FAIL"
            thresh = ENDPOINT_THRESHOLDS.get(r["label"], float("inf"))
            ok = r["ms"] < thresh and r["status"] == 200
            icon = "OK" if ok else "SLOW" if r["status"] == 200 else "FAIL"
            print(f"  {i:2d}. {icon:<5s} {r['ms']:>8.0f}ms  {status:<8s} {r['size_kb']:>7.1f}KB  {r['label']:<25s} {bar}")

        print()
        slow = [r for r in results if r["ms"] >= ENDPOINT_THRESHOLDS.get(r["label"], float("inf"))]
        failed = [r for r in results if r["status"] != 200]
        if slow:
            print(f"  SLOW endpoints ({len(slow)}):")
            for r in slow:
                print(f"    {r['ms']:>8.0f}ms  {r['label']} (threshold: {ENDPOINT_THRESHOLDS.get(r['label'], '?')}ms)")
        if failed:
            print(f"  FAILED endpoints ({len(failed)}):")
            for r in failed:
                print(f"    HTTP {r['status']}  {r['label']}")
        print()
