import asyncio
import logging
import sys

sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO)
from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_derived_financial_metrics,
)
from database import supabase


async def backfill():
    is_resp = supabase.table('income_statements').select('company_id').is_('fiscal_quarter', None).execute()
    companies_with_statements = {r['company_id'] for r in (is_resp.data or [])}

    ratios_resp = supabase.table('financial_ratios').select('company_id').execute()
    companies_with_ratios = {r['company_id'] for r in (ratios_resp.data or [])}

    needs_backfill = companies_with_statements - companies_with_ratios
    print(f'Companies needing backfill: {len(needs_backfill)}')

    for company_id in sorted(needs_backfill):
        try:
            result = await compute_and_upsert_derived_financial_metrics(company_id)
            print(f'  company_id={company_id}: {result["rows_changed"]}/{result["count"]} rows written')
        except Exception as e:
            print(f'  company_id={company_id} FAILED: {e}')

    print('Backfill complete')

asyncio.run(backfill())
