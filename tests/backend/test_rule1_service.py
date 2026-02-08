import pytest
from application.services.valuation_service import ValuationService
from domain.models.valuation_rule1 import Rule1RequestOverrides

class StubRepo:
    # Implement minimal stubs for each repo method used by the service
    ...

@pytest.mark.asyncio
async def test_rule1_basic_flow():
    repo = StubRepo(
        trailing_eps=6.0,
        eps_forecast_growth=0.12,
        industry_pe=22.0,
        sector="Information Technology",
        industry="Software",
    )
    svc = ValuationService(repo)
    resp = await svc.compute_rule1_with_diagnostics("MSFT", user_id=1, overrides=Rule1RequestOverrides())

    assert resp.valuation.eps0 == 6.0
    assert 0.11 <= resp.valuation.growth <= 0.12
    assert resp.valuation.futurePE == 22.0  # used industry since it's lower than 2*g
    assert resp.applicability.score >= 75
    assert resp.applicability.category in ("Good", "Caution")