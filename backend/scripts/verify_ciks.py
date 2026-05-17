#!/usr/bin/env python3
"""Verify all Super Investor CIKs against SEC EDGAR API."""
from datetime import datetime
from edgar import get_filings, set_identity

set_identity("stockerpro@example.com")

# Updated with VERIFIED CIKs from SEC (May 2026) - 13F-HR Only
INVESTORS = {
    "0001067983": "Warren Buffett (Berkshire Hathaway)",
    "0001569205": "Terry Smith (Fundsmith LLP)",
    "0001112520": "Chuck Akre (Akre Capital)",
    "0001647251": "Chris Hohn (TCI Fund)",
    "0001061768": "Seth Klarman (Baupost)",
    "0001549575": "Mohnish Pabrai (Dalal Street LLC)",  # UPDATED
    "0001079114": "David Einhorn (Greenlight)",
    "0001510387": "Joel Greenblatt (Gotham)",
    "0000949509": "Howard Marks (Oaktree)",
    "0001167483": "Chase Coleman (Tiger Global)",
    "0001135730": "Philippe Laffont (Coatue)",
    "0001061165": "Stephen Mandel (Lone Pine)",
    "0001103804": "Andreas Halvorsen (Viking)",
    "0001697748": "Cathie Wood (ARK)",
    "0001336528": "Bill Ackman (Pershing Square)",
    "0000921669": "Carl Icahn",
    "0001040273": "Dan Loeb (Third Point)",
    "0001791786": "Paul Singer (Elliott)",
    "0001418814": "Mason Morfit (ValueAct)",  # UPDATED
    "0000934639": "Lee Ainslie (Maverick)",
    "0001263508": "Julian Baker (Baker Bros)",
    "0001656456": "David Tepper (Appaloosa)",
    "0001553733": "Glenn Greenberg (Brave Warrior)",
    "0001406950": "Bill Nygren (Harris Associates)",  # UPDATED
}


def verify_cik(cik, name):
    """Verify a CIK by querying SEC EDGAR for recent 13F filings."""
    result = {"cik": cik, "name": name, "status": "unknown", "filings_found": 0, "last_filing": None, "form_breakdown": {}}
    
    try:
        current_year = datetime.now().year
        years = list(range(current_year - 3, current_year + 1))
        
        all_filings = []
        form_counts = {}
        
        # Check multiple form types
        for form_type in ["13F-HR", "SC 13D", "SC 13D/A", "NPORT-P"]:
            form_counts[form_type] = 0
            for year in years:
                try:
                    filings = get_filings(year=year, form=form_type).filter(cik=cik)
                    if filings:
                        filings_list = list(filings)
                        form_counts[form_type] += len(filings_list)
                        all_filings.extend(filings_list)
                except Exception:
                    continue
        
        result["form_breakdown"] = {k: v for k, v in form_counts.items() if v > 0}
        result["filings_found"] = sum(form_counts.values())
        
        if all_filings:
            result["status"] = "VALID"
            all_filings.sort(key=lambda x: x.filing_date, reverse=True)
            result["last_filing"] = str(all_filings[0].filing_date)
        else:
            result["status"] = "NO_FILINGS"
            
    except Exception as e:
        result["status"] = f"ERROR: {str(e)[:50]}"
    
    return result


def main():
    print("SEC EDGAR CIK VERIFICATION")
    print("=" * 60)
    
    results = []
    for cik, name in INVESTORS.items():
        print(f"Checking {cik} {name}...", end=" ")
        r = verify_cik(cik, name)
        results.append(r)
        print(f"[{r['status']}] ({r['filings_found']} filings)")
        if r.get('form_breakdown'):
            breakdown = ", ".join(f"{k}:{v}" for k, v in r['form_breakdown'].items())
            print(f"    Forms: {breakdown}")
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    valid = [r for r in results if r["status"] == "VALID"]
    no_13f = [r for r in results if r["status"] == "NO_FILINGS"]
    errors = [r for r in results if r["status"].startswith("ERROR")]
    
    print(f"\n[VALID] Valid CIKs: {len(valid)}")
    for r in valid:
        print(f"  {r['cik']} {r['name']}: {r['last_filing']} ({r['filings_found']} filings)")
    
    if no_13f:
        print(f"\n[NO_FILINGS] No filings found: {len(no_13f)}")
        for r in no_13f:
            print(f"  {r['cik']} {r['name']}")
    
    if errors:
        print(f"\n[ERROR] Errors: {len(errors)}")
        for r in errors:
            print(f"  {r['cik']} {r['name']}: {r['status']}")
    
    print(f"\nTotal: {len(results)} investors")

if __name__ == "__main__":
    main()
