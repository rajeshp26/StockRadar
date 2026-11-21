"""Unit tests for Rule1Service core valuation math.

I1d: the original test defined an empty ``StubRepo: ...`` but constructed it
with constructor kwargs, so it raised TypeError and never exercised any
service code. It is rebuilt here against the current async repository
interface. The suitability scorecard and AI summary are separate units with
their own coverage, so they are stubbed at the service boundary.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.rule1_service import Rule1Service
from domain.models.valuation_rule1 import Rule1RequestOverrides


@pytest.mark.asyncio
async def test_rule1_basic_flow():
    repo = AsyncMock()
    repo.get_company_context.return_value = {
        "company_id": 42,
        "currency": "USD",
        "sector": None,
        "industry": None,
    }
    repo.get_method_params.return_value = {}
    repo.get_trailing_eps.return_value = {
        "trailing_eps": 6.0,
        "snapshot_date": None,
    }

    # Pin the two derived inputs so the test targets the valuation math rather
    # than forecast/industry fallback resolution.
    overrides = Rule1RequestOverrides(forceGrowth=0.12, forceFuturePE=22.0)

    with (
        patch(
            "application.services.rule1_service.evaluate_rule1_suitability",
            new=AsyncMock(return_value=(80, "Good", [], {})),
        ),
        patch(
            "application.services.rule1_service.generate_suitability_summary",
            new=AsyncMock(return_value="stubbed summary"),
        ),
    ):
        svc = Rule1Service(repo=repo, guard=MagicMock())
        resp = await svc.compute_rule1_with_diagnostics(
            "MSFT", user_id=1, overrides=overrides
        )

    assert resp.valuation.eps0 == 6.0
    assert resp.valuation.growth == 0.12
    assert resp.valuation.futurePE == 22.0
    assert resp.applicability.score == 80
    assert resp.applicability.category == "Good"
