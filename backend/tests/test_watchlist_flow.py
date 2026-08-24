
import pytest
from fastapi.testclient import TestClient

# We need to adjust the python path to import the main app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app 
from dependencies import get_current_user_dep

# Mock user ID for all tests
TEST_USER_ID = "test-user-123"

@pytest.fixture
def client():
    # Use a TestClient that re-routes the dependency
    # to use our mock user ID instead of a real header.
    def override_get_current_user():
        return {"sub": TEST_USER_ID}

    app.dependency_overrides[get_current_user_dep] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_add_stock_to_watchlist(client: TestClient):
    # 1. Create a new watchlist to get a valid ID
    watchlist_name = "Tech Stocks"
    response = client.post("/watchlists", json={"name": watchlist_name})
    
    assert response.status_code == 201
    watchlist_data = response.json()
    assert watchlist_data["name"] == watchlist_name
    watchlist_id = watchlist_data["id"]

    # 2. Add a stock to the newly created watchlist
    # This is the core of our test. It will fail if yfinance is not installed
    # or if the provider logic is broken.
    ticker = "AAPL"
    add_item_response = client.post(
        "/watchlist-items",
        json={
            "watchlist_id": watchlist_id,
            "ticker_symbol": ticker,
            "target_buy": 400.0,
            "target_sell": 500.0,
            "position": 1
        }
    )

    # 3. Verify the outcome
    assert add_item_response.status_code == 201
    item_data = add_item_response.json()[0]
    assert item_data["watchlist_id"] == watchlist_id

    # The database query joins the company name, let's check it
    # We need to read the dependencies file to mock it
    # For now let's just check the id
    assert item_data["company_id"] is not None

