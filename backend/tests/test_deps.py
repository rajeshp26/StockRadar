import sys
import importlib

packages = [
    "fastapi",
    "yfinance",
    "stockdex",
    "edgar",
    "supabase",
    "pandas",
    "numpy",
    "pydantic",
    "httpx",
    "requests",
    "slowapi",
    "lxml",
    "firebase_admin",
    "dotenv",
    "uvicorn",
    "pydantic_settings",
]

dotted_tests = [
    "google.generativeai",
]

all_ok = True
for pkg in packages:
    try:
        importlib.import_module(pkg)
        print(f"  OK  {pkg}")
    except Exception as e:
        print(f"FAIL  {pkg}: {e}")
        all_ok = False

for pkg in dotted_tests:
    try:
        importlib.import_module(pkg)
        print(f"  OK  {pkg}")
    except Exception as e:
        print(f"FAIL  {pkg}: {e}")
        all_ok = False

if all_ok:
    print("\nALL IMPORTS PASSED")
else:
    print("\nSOME IMPORTS FAILED")
    sys.exit(1)
