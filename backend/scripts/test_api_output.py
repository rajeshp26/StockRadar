"""Test API output by hitting the running server with a mock auth override.
Starts a test client with dependency override to bypass real JWT."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

# Override auth BEFORE importing main
from dependencies import get_current_user_dep

MOCK_USER = {"sub": "59a7ced9-aa7c-4f34-b77e-266fc8a8e796", "user_id": 1}

def _mock_current_user():
    return MOCK_USER

# Import app after override
import main

main.app.dependency_overrides[get_current_user_dep] = _mock_current_user

client = TestClient(main.app)

ACCT_NAMES = {7: "Non-registered", 8: "RRSP", 9: "TFSA", 10: "TFSA-2", 11: "RRSP-2", 12: "Margin"}

EXPECTED = {
    7:  {"total": 46984.17, "market": 46662.74, "cost": 10500.17, "holdings": 34},
    8:  {"total": 39861.64, "market": 37253.42, "cost": 22723.49, "holdings": 34},
    9:  {"total": 83149.12, "market": 81647.76, "cost": 44264.87, "holdings": 75},
    10: {"total": 10760.00, "market": 28110.00, "cost": 18790.00, "holdings": 3},
    11: {"total": 16114.50, "market": 40314.50, "cost": 25590.00, "holdings": 3},
    12: {"total": 1301.25,  "market": 5971.25,  "cost": 4737.50,  "holdings": 2},
}

def check(label, actual, expected, tol=0.01):
    if abs(actual - expected) <= tol:
        return f"MATCH (${expected:,.2f})"
    return f"MISMATCH got=${actual:,.2f} expected=${expected:,.2f}"

print("=" * 100)
print("1. DASHBOARD: GET /portfolio/dashboard")
print("=" * 100)
r = client.get("/portfolio/dashboard")
if r.status_code != 200:
    print(f"FAILED: {r.status_code} {r.text[:300]}")
else:
    dj = r.json()
    accounts = dj.get("accounts", [])
    print(f"  Accounts: {len(accounts)}")
    for a in accounts:
        aid = a["account_id"]
        tv = float(a["total_value"])
        tc = float(a["total_cost"])
        gl = float(a["gain_loss"])
        hc = a["holdings_count"]
        exp = EXPECTED[aid]
        t_chk = check("total", tv, exp["total"])
        c_chk = check("cost", tc, exp["cost"])
        print(f"  Acct {aid} ({ACCT_NAMES[aid]}): total={t_chk} cost={c_chk} gain=${gl:,.2f} holdings={hc}")

print()
print("=" * 100)
print("2. ACCOUNT HOLDINGS: GET /portfolio/accounts/{id}/holdings")
print("=" * 100)
all_ok = True
for aid in [7, 8, 9, 10, 11, 12]:
    r = client.get(f"/portfolio/accounts/{aid}/holdings")
    if r.status_code != 200:
        print(f"  Acct {aid}: FAILED ({r.status_code})")
        all_ok = False
        continue
    hj = r.json()
    holdings = hj.get("holdings", [])
    total_val = sum(float(x.get("current_value", 0)) for x in holdings)
    total_cost = sum(float(x.get("total_cost", 0)) for x in holdings)
    n = len(holdings)
    exp = EXPECTED[aid]

    m_chk = check("market_val", total_val, exp["market"])
    c_chk = check("total_cost", total_cost, exp["cost"])
    h_chk = check("holdings_count", n, exp["holdings"])

    ok = "MATCH" in m_chk and "MATCH" in c_chk and "MATCH" in h_chk
    if not ok: all_ok = False
    print(f"  Acct {aid} ({ACCT_NAMES[aid]}): {'OK' if ok else 'FAIL'}")
    print(f"    market_val={m_chk} cost={c_chk} count={h_chk}")
    # Top 3 holdings
    for x in sorted(holdings, key=lambda h: float(h.get("current_value",0)), reverse=True)[:3]:
        sym = x.get("symbol","?")
        qty = float(x.get("quantity",0))
        px = float(x.get("current_price",0))
        val = float(x.get("current_value",0))
        print(f"      {sym:>8} qty={qty:.2f} price=${px:.2f} value=${val:,.2f}")

print()
print("=" * 100)
print("3. ALL HOLDINGS: GET /portfolio/holdings")
print("=" * 100)
r = client.get("/portfolio/holdings")
if r.status_code != 200:
    print(f"FAILED: {r.status_code} {r.text[:200]}")
else:
    ahj = r.json()
    all_h = ahj.get("holdings", [])
    tv = sum(float(x.get("current_value",0)) for x in all_h)
    tc = sum(float(x.get("total_cost",0)) for x in all_h)
    tot_exp = sum(v["total"] for v in EXPECTED.values())
    tc_exp = sum(v["cost"] for v in EXPECTED.values())
    print(f"  Total holdings: {len(all_h)}")
    print(f"  Total market:   ${tv:>10,.2f}  {check('total', tv, tot_exp)}")
    print(f"  Total cost:     ${tc:>10,.2f}  {check('cost', tc, tc_exp)}")

print()
print("=" * 70)
print(f"OVERALL: {'ALL API CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
print("=" * 70)
