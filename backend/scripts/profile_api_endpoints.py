import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
import dotenv
import jwt
from datetime import datetime, timedelta
import httpx

env = dotenv.dotenv_values(Path(__file__).resolve().parent.parent / ".env")
JWT_SECRET = env["SUPABASE_JWT_SECRET"]
AUTH_ID = "59a7ced9-aa7c-4f34-b77e-266fc8a8e796"

payload = {
    "sub": AUTH_ID,
    "aud": "authenticated",
    "role": "authenticated",
    "iat": int(datetime.now().timestamp()),
    "exp": int((datetime.now() + timedelta(hours=1)).timestamp()),
    "email": "rajeshp01@gmail.com",
}
token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
print(f"Token: {token[:50]}...\n")

BASE = "http://172.19.86.61:8001"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-id-token": token,
}

endpoints = [
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

results = []
for method, path, label in endpoints:
    url = f"{BASE}{path}"
    start = time.perf_counter()
    try:
        resp = httpx.get(url, headers=headers, timeout=60.0, follow_redirects=False)
        elapsed = (time.perf_counter() - start) * 1000
        size = len(resp.content)
        results.append({"label": label, "status": resp.status_code, "ms": elapsed, "size_kb": size/1024})
        icon = "OK" if resp.status_code == 200 else "FAIL"
        print(f"  {icon:4s} {elapsed:>8.0f}ms  {resp.status_code:3d}  {size/1024:>7.1f}KB  {label}")
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        results.append({"label": label, "status": 0, "ms": elapsed, "size_kb": 0})
        print(f"  FAIL {elapsed:>8.0f}ms  ---  {label}  ERROR: {str(e)[:60]}")

print()
total = sum(r["ms"] for r in results)
print(f"  TOTAL API TIME: {total:.0f}ms ({total/1000:.1f}s)")
print()
print(f"  Slowest endpoints:")
for r in sorted(results, key=lambda x: x["ms"], reverse=True)[:5]:
    print(f"    {r['ms']:>8.0f}ms  {r['status']}  {r['size_kb']:>6.1f}KB  {r['label']}")
