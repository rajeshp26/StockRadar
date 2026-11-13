#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import supabase
from application.services.portfolio_service import PortfolioService
from infrastructure.repositories.portfolio_value_series_repository import PortfolioValueSeriesRepository
from application.services.portfolio_response_cache import get_response_cache

async def main():
    svc = PortfolioService()
    repo_series = PortfolioValueSeriesRepository()
    cache = get_response_cache()
    cache.clear()
    
    user_id = 1
    try:
        accounts = svc.portfolio_repo.get_user_accounts(user_id)
    except Exception as e:
        print('ERR accounts', e)
        return
    print('accounts:', len(accounts), [a.get('account_id') for a in accounts])
    if not accounts:
        all_acc = supabase.table('portfolio_accounts').select('user_id').limit(10).execute()
        print('all_acc:', all_acc.data)
        return
    account_ids = [a['account_id'] for a in accounts]
    account_key = ','.join(str(a) for a in sorted(account_ids))
    print('account_key:', account_key)
    
    try:
        supabase.table('portfolio_value_series').delete().eq('account_key', account_key).execute()
        print('cleared series')
    except Exception as e:
        print('clear series err:', e)
    
    print('\n=== TEST 1: cold compute 1Y ===')
    r1 = await svc.get_portfolio_performance(user_id, '1Y', account_ids)
    print('success:', r1.get('success'))
    print('data_source:', r1.get('data_source'))
    print('served_from_cache:', r1.get('served_from_cache'))
    print('locf_count:', r1.get('locf_count'), 'spike_detected:', r1.get('spike_detected'))
    print('data_quality_flag:', r1.get('data_quality_flag'))
    print('snaps:', len(r1.get('snapshots', [])))
    if r1.get('snapshots'):
        print('first snap:', r1['snapshots'][0])
        print('last snap:', r1['snapshots'][-1])
    
    try:
        stored = repo_series.get_series(account_key)
        print('stored points:', len(stored.points) if stored else 0)
    except Exception as e:
        print('stored err:', e)
    
    cache.clear()
    print('\n=== TEST 2: warm via series (cache cleared) 1Y ===')
    r2 = await svc.get_portfolio_performance(user_id, '1Y', account_ids)
    print('success:', r2.get('success'))
    print('data_source:', r2.get('data_source'))
    print('served_from_cache:', r2.get('served_from_cache'))
    print('locf_count:', r2.get('locf_count'), 'spike_detected:', r2.get('spike_detected'))
    print('snaps:', len(r2.get('snapshots', [])))
    
    r1_copy = json.loads(json.dumps(r1))
    r2_copy = json.loads(json.dumps(r2))
    r1_copy.pop('served_from_cache', None)
    r2_copy.pop('served_from_cache', None)
    print('EQUAL:', json.dumps(r1_copy, sort_keys=True) == json.dumps(r2_copy, sort_keys=True))
    
    print('\n=== TEST 3: different period 3M (slice) ===')
    r3 = await svc.get_portfolio_performance(user_id, '3M', account_ids)
    print('success:', r3.get('success'))
    print('data_source:', r3.get('data_source'))
    print('served_from_cache:', r3.get('served_from_cache'))
    print('snaps:', len(r3.get('snapshots', [])))
    
    print('\n=== TEST 4: Layer 3 cache hit (no clear) ===')
    r4 = await svc.get_portfolio_performance(user_id, '3M', account_ids)
    print('success:', r4.get('success'))
    print('data_source:', r4.get('data_source'))
    print('served_from_cache:', r4.get('served_from_cache'))
    
    print('\n=== TEST 5: portfolio compare SPY ===')
    try:
        rc = await svc.get_performance_compare(user_id, '1Y', ['SPY'], account_ids)
        print('success:', rc.get('success'))
        print('benchmarks:', len(rc.get('benchmarks', [])))
        if rc.get('benchmarks'):
            b0 = rc['benchmarks'][0]
            print('bench0 keys:', list(b0.keys()))
            print('bench0 len:', len(b0.get('data',[])))
    except Exception as e:
        print('ERR compare:', e)
        import traceback
        traceback.print_exc()
    
    try:
        h = supabase.table('portfolio_holdings').select('symbol').eq('user_id', user_id).limit(1).execute()
        if h.data:
            sym = h.data[0]['symbol']
            print('\n=== TEST 6: holding compare', sym, 'SPY ===')
            rh = await svc.get_holding_performance_compare(user_id, sym, '1Y', ['SPY'])
            print('success:', rh.get('success'))
            print('benchmarks:', len(rh.get('benchmarks', [])))
        else:
            print('\nno holdings for user', user_id)
    except Exception as e:
        print('ERR holding compare:', e)
    
    print('\n=== DONE ===')

asyncio.run(main())
