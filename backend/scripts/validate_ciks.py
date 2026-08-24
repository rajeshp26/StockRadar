#!/usr/bin/env python3
"""Validate CIKs against SEC EDGAR to ensure:
1. CIK exists and has recent 13F filings (and other forms)
2. Company name matches expected investor
3. Verify all parameters are correct
"""

from edgar import Company, get_filings, set_identity

set_identity("stockerpro@example.com")

# Updated with VERIFIED CIKs from SEC (May 2026) - 13F-HR Only
INVESTORS = {
    "0001067983": ("Warren Buffett", "Berkshire Hathaway", ["13F-HR"]),
    "0001569205": ("Terry Smith", "Fundsmith LLP", ["13F-HR"]),
    "0001112520": ("Chuck Akre", "Akre Capital", ["13F-HR"]),
    "0001647251": ("Chris Hohn", "TCI Fund", ["13F-HR"]),
    "0001061768": ("Seth Klarman", "Baupost", ["13F-HR"]),
    "0001549575": ("Mohnish Pabrai", "Dalal Street LLC", ["13F-HR"]),  # UPDATED
    "0001079114": ("David Einhorn", "Greenlight", ["13F-HR"]),
    "0001510387": ("Joel Greenblatt", "Gotham", ["13F-HR"]),
    "0000949509": ("Howard Marks", "Oaktree", ["13F-HR"]),
    "0001167483": ("Chase Coleman", "Tiger Global", ["13F-HR"]),
    "0001135730": ("Philippe Laffont", "Coatue", ["13F-HR"]),
    "0001061165": ("Stephen Mandel", "Lone Pine", ["13F-HR"]),
    "0001103804": ("Andreas Halvorsen", "Viking", ["13F-HR"]),
    "0001697748": ("Cathie Wood", "ARK", ["13F-HR"]),
    "0001336528": ("Bill Ackman", "Pershing Square", ["13F-HR"]),
    "0000921669": ("Carl Icahn", "Icahn", ["13F-HR"]),
    "0001040273": ("Dan Loeb", "Third Point", ["13F-HR"]),
    "0001791786": ("Paul Singer", "Elliott", ["13F-HR"]),
    "0001418814": ("Mason Morfit", "ValueAct", ["13F-HR"]),  # UPDATED
    "0000934639": ("Lee Ainslie", "Maverick", ["13F-HR"]),
    "0001263508": ("Julian Baker", "Baker Bros", ["13F-HR"]),
    "0001656456": ("David Tepper", "Appaloosa", ["13F-HR"]),
    "0001553733": ("Glenn Greenberg", "Brave Warrior", ["13F-HR"]),
    "0001406950": ("Bill Nygren", "Harris Associates", ["13F-HR"]),  # UPDATED
}


def validate_cik(cik: str, expected_name: str, expected_firm: str, form_types: list[str]) -> dict:
    """Validate CIK against SEC EDGAR - check company name and filings match."""
    result = {
        "cik": cik,
        "expected": f"{expected_name} ({expected_firm})",
        "sec_name": None,
        "status": "ERROR",
        "filings": 0,
        "last_filing": None,
        "form_breakdown": {},
    }

    try:
        # Get company info from SEC
        company = Company(cik)
        company_name = company.name if company else "UNKNOWN"
        result["sec_name"] = company_name

        # Check for recent filings of ALL specified form types
        all_filings = []
        form_counts = {}

        # Always check 13F-HR as baseline (even if not in form_types)
        check_forms = list(set(form_types + ["13F-HR"]))

        for form_type in check_forms:
            form_counts[form_type] = 0
            for year in [2023, 2024, 2025, 2026]:
                try:
                    filings = get_filings(year=year, form=form_type).filter(cik=cik)
                    if filings:
                        filings_list = list(filings)
                        form_counts[form_type] += len(filings_list)
                        all_filings.extend(filings_list)
                except:
                    pass

        result["form_breakdown"] = {k: v for k, v in form_counts.items() if v > 0}
        result["filings"] = sum(form_counts.values())

        if all_filings:
            all_filings.sort(key=lambda x: x.filing_date, reverse=True)
            result["last_filing"] = str(all_filings[0].filing_date)

        # Determine status
        if not company_name or company_name == "UNKNOWN":
            result["status"] = "CIK_NOT_FOUND"
        elif result["filings"] == 0:
            result["status"] = "NO_FILINGS"
        else:
            # Flexible name matching - check if ANY word from expected name is in SEC name
            # Also check firm name
            all_search_terms = expected_name.split() + expected_firm.split()
            name_match = any(
                term.upper() in company_name.upper()
                for term in all_search_terms
                if len(term) > 3
            )
            if name_match:
                result["status"] = "VALID"
            else:
                result["status"] = f"NAME_MISMATCH ({company_name[:40]})"

    except Exception as e:
        result["status"] = f"ERROR: {str(e)[:50]}"

    return result


def main():
    print("=" * 70)
    print("SEC EDGAR CIK VALIDATION (Updated May 2026)")
    print("=" * 70)

    results = []
    for cik, (name, firm, forms) in INVESTORS.items():
        print(f"Validating {cik} {name}...", end=" ", flush=True)
        r = validate_cik(cik, name, firm, forms)
        results.append(r)
        status_marker = "OK" if r["status"] == "VALID" else "FAIL"
        print(f"[{status_marker}] {r.get('sec_name', 'N/A')[:35]}")
        if r.get('form_breakdown'):
            breakdown = ", ".join(f"{k}:{v}" for k, v in r['form_breakdown'].items())
            print(f"    Forms: {breakdown}")

    print("\n" + "=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    valid = [r for r in results if r["status"] == "VALID"]
    name_mismatch = [r for r in results if "NAME_MISMATCH" in r["status"]]
    no_filings = [r for r in results if r["status"] == "NO_FILINGS"]
    not_found = [r for r in results if r["status"] == "CIK_NOT_FOUND"]
    errors = [r for r in results if r["status"].startswith("ERROR")]

    print(f"\n[VALID] CIKs matching investor name: {len(valid)}")
    for r in valid:
        print(f"  {r['cik']} {r['expected'].split('(')[0]}: {r.get('sec_name', '')[:40]}")

    if name_mismatch:
        print(f"\n[NAME_MISMATCH] CIK exists but name doesn't match: {len(name_mismatch)}")
        for r in name_mismatch:
            print(f"  {r['cik']} Expected: {r['expected']}")
            print(f"    SEC says: {r.get('sec_name', 'N/A')}")

    if no_filings:
        print(f"\n[NO_FILINGS] No filings found: {len(no_filings)}")
        for r in no_filings:
            print(f"  {r['cik']} {r['expected']}")

    if not_found:
        print(f"\n[NOT_FOUND] CIK not in SEC: {len(not_found)}")
        for r in not_found:
            print(f"  {r['cik']} {r['expected']}")

    if errors:
        print(f"\n[ERROR] Other errors: {len(errors)}")
        for r in errors:
            print(f"  {r['cik']} {r['status']}")

    print(f"\nTotal: {len(results)} investors validated")

if __name__ == "__main__":
    main()
