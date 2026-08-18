import sys, os, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dotenv, jwt

env = dotenv.dotenv_values(Path(__file__).resolve().parent.parent / ".env")
JWT_SECRET = env["SUPABASE_JWT_SECRET"]
payload = {
    "sub": "59a7ced9-aa7c-4f34-b77e-266fc8a8e796",
    "aud": "authenticated", "role": "authenticated",
    "iat": int(datetime.now().timestamp()),
    "exp": int((datetime.now() + timedelta(hours=1)).timestamp()),
    "email": "rajeshp01@gmail.com",
}
token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

r = subprocess.run(
    ["curl.exe", "-s", "-H", f"Authorization: Bearer {token}", "http://localhost:8001/companies/search?symbol=AAPL"],
    capture_output=True, text=True, timeout=15
)
d = json.loads(r.stdout)
print(json.dumps(d, indent=2, default=str)[:500])
