with open(r'C:\Project\StockerPro\StockerPro\backend\infrastructure\repositories\financial_repository.py', 'r') as f:
    content = f.read()

old = '''    async def get_financial_candidates(self) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table("companies")
                .select(
                    "company_id, first_financial_data_loaded_at, status, security_type, loaded"
                )
                .eq("loaded", True)
                .in_("status", ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"])
                .neq("security_type", "delisted")
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("Failed to fetch financial candidates")
            return []'''

new = '''    async def get_financial_candidates(self) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table("companies")
                .select(
                    "company_id, ticker_symbol, first_financial_data_loaded_at, status, security_type, loaded"
                )
                .eq("loaded", True)
                .in_("status", ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"])
                .neq("security_type", "delisted")
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("Failed to fetch financial candidates")
            return []'''

if old not in content:
    print('NOT FOUND')
else:
    content = content.replace(old, new)
    with open(r'C:\Project\StockerPro\StockerPro\backend\infrastructure\repositories\financial_repository.py', 'w') as f:
        f.write(content)
    print('DONE')
