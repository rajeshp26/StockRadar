# 🧪 Backend Testing Guide

This document outlines the strategy, setup, and execution steps for testing the StockerPro backend.

## 🏔️ The Test Pyramid

1.  **Unit Tests (Bottom)**: Test individual components (Services, Utils) in isolation.
    *   **Scope**: No database, no external APIs.
    *   **Tool**: `pytest` + `unittest.mock`.
    *   **Location**: `backend/tests/` (Standardized as `test_*_unit.py`).
2.  **Integration Tests (Middle)**: Test the interaction between components (API -> Service -> Repository).
    *   **Scope**: Uses a test database or mock external services.
    *   **Tool**: `pytest` + `httpx.AsyncClient`.
3.  **End-to-End Tests (Top)**: Test full user journeys.

---

## 🛠️ Environment Setup

The project uses Nix to manage all dependencies, including those for testing. The `backend/shell.nix` file defines the complete environment.

**To run tests, you must use `nix-shell backend/shell.nix`.** This ensures that `pytest`, `httpx`, and all other required packages are available and correctly configured.

---

## 🏃 How to Run Tests

All test commands should be executed from the **project root directory**.

### **Primary Command (Using Nix)**
This command loads the Nix environment and runs the specified test suite.

```bash
# Run all tests in the backend
nix-shell backend/shell.nix --run "python -m pytest backend/tests"

# Run a specific test file
nix-shell backend/shell.nix --run "python -m pytest backend/tests/test_watchlist_service_unit.py"
```

---

## 🏗️ Writing New Tests

### Unit Testing a Service
When testing a service, mock its dependencies (Repositories and Providers) using `@pytest.fixture`.

```python
import pytest
from unittest.mock import MagicMock
from application.services.watchlist_service import WatchlistService
from domain.interfaces.repository import WatchlistRepository

@pytest.fixture
def mock_repo():
    return MagicMock(spec=WatchlistRepository)

@pytest.fixture
def service(mock_repo):
    return WatchlistService(user_repo=MagicMock(), watchlist_repo=mock_repo, stock_provider=MagicMock())

def test_my_service_logic(service, mock_repo):
    # 1. Arrange (Set up mocks)
    mock_repo.find.return_value = {"id": 1, "name": "Default"}
    expected_result = {"id": 1, "name": "Default"}
    
    # 2. Act
    result = service.get_watchlist(1)
    
    # 3. Assert
    assert result == expected_result
    mock_repo.find.assert_called_once_with(1)
```

---

## 🚫 Troubleshooting & Common Pitfalls

### 1. `ModuleNotFoundError` (e.g., `pydantic`, `application`, etc.)
*   **Root Cause**: You are likely not running the test command from within the Nix environment, or you are not in the project's root directory.
*   **Fix**: Ensure you are using the `nix-shell backend/shell.nix --run "..."` command format from the project root. This automatically sets the correct `PYTHONPATH` and makes all dependencies available.

### 2. Test Failures Due to Missing Dependencies
*   **Root Cause**: The required testing packages (like `pytest` or `httpx`) may not be included in the `backend/shell.nix` file.
*   **Fix**: Verify that `pytest` and `httpx` are listed under `buildInputs` in the `backend/shell.nix` file.
