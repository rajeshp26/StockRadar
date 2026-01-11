
import asyncio
import httpx
import time
import json
import sys
import os

# Ensure the backend directory is in the path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import supabase

# --- Configuration ---
BASE_URL = "http://127.0.0.1:8001" 
TEST_FIREBASE_UID = "rGjlsCk0babAUMmtksTJyXfiZh62" 
TEST_EMAIL = "rajeshp01@gmail.com"
TEST_TICKER = "TSLA" 

async def run_functional_test():
    print(f"\n[1/4] Ensuring test user exists: {TEST_FIREBASE_UID}")
    async with httpx.AsyncClient() as client:
        # Sync user
        sync_res = await client.post(f"{BASE_URL}/users/sync", json={
            "firebase_uid": TEST_FIREBASE_UID,
            "email": TEST_EMAIL,
            "display_name": "Rajesh"
        })
        if sync_res.status_code != 200:
            print(f"Failed to sync user: {sync_res.text}")
            return
        
        # Get default watchlist
        watchlist_res = await client.post(f"{BASE_URL}/watchlists/default-with-items", json={
            "firebase_uid": TEST_FIREBASE_UID
        })
        
        if watchlist_res.status_code != 200:
            print(f"Failed to get watchlist: {watchlist_res.status_code} - {watchlist_res.text}")
            return
            
        res_json = watchlist_res.json()
        
        if "watchlist_id" not in res_json:
            print("ERROR: 'watchlist_id' not found in response!")
            return
            
        watchlist_id = res_json["watchlist_id"]
        print(f"Using Watchlist ID: {watchlist_id}")

        print(f"\n[2/4] Adding stock {TEST_TICKER} (Triggering Deep Sync)...")
        add_res = await client.post(f"{BASE_URL}/watchlist-items", json={
            "firebase_uid": TEST_FIREBASE_UID,
            "watchlist_id": watchlist_id,
            "symbol": TEST_TICKER,
            "target_buy": 150.0,
            "target_sell": 250.0
        })
        
        if add_res.status_code != 201:
            print(f"Failed to add stock: {add_res.status_code} - {add_res.text}")
            return
        
        data = add_res.json()
        company_id = data["watchlist_item"]["company_id"]
        print(f"Success! Stock added. Internal Company ID: {company_id}")

        print(f"\n[3/4] Polling for Deep Sync data (max 30s)...")
        start_time = time.time()
        success = False
        
        tables_to_check = ['income_statements', 'balance_sheets', 'statistics', 'dividend_history']
        
        while time.time() - start_time < 30:
            results = {}
            for table in tables_to_check:
                try:
                    res = supabase.table(table).select("count", count="exact").eq("company_id", company_id).execute()
                    results[table] = res.count if res.count else 0
                except Exception as e:
                    results[table] = f"Error: {e}"
            
            print(f"  - Progress: {results}")
            
            if isinstance(results['income_statements'], int) and results['income_statements'] > 0 and \
               isinstance(results['statistics'], int) and results['statistics'] > 0:
                print("\n[4/4] TEST PASSED: Deep Sync data detected in Supabase!")
                success = True
                break
            
            await asyncio.sleep(3)
        
        if not success:
            print("\n[!] TEST FAILED: Background sync did not complete within 30 seconds.")

if __name__ == "__main__":
    try:
        asyncio.run(run_functional_test())
    except Exception as e:
        print(f"Test Execution Error: {e}")
