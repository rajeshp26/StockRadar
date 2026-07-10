from collections import defaultdict
from typing import Dict, List, Any, Set


def validate_company_id_consistency(account_ids: List[int]) -> List[str]:
    issues: List[str] = []
    from infrastructure.repositories.portfolio_repository import PortfolioRepository
    repo = PortfolioRepository()
    rows = repo.get_symbol_company_mappings(account_ids)

    symbol_to_companies: Dict[str, Set[int]] = defaultdict(set)
    for r in rows:
        sym = r.get("symbol")
        cid = r.get("company_id")
        if sym and cid:
            symbol_to_companies[sym].add(cid)

    for sym, cids in symbol_to_companies.items():
        if len(cids) > 1:
            issues.append(
                f"Symbol {sym} maps to multiple company_ids: {sorted(cids)}. "
                f"This causes FIFO position splitting. Fix data before backfill."
            )
    return issues
