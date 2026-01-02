# 🧪 Backend Testing Guide

This document outlines the strategy, setup, and execution steps for testing the Stock Tracker backend, following the [Software Architecture Guidelines](./GUIDELINES.md).

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

### 1. **Recommended**: Local Virtual Environment (Works Everywhere)
To avoid pathing issues and conflicting dependencies, use a local virtual environment in the `backend` folder.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx
cd ..
```

### 2. Path Configuration
Python needs to know where the `backend` source code is. Always run tests from the project root.
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
```

---

## 🏃 How to Run Tests

### **Primary Command (Using Virtual Env)**
Always use the Python binary inside the `.venv` to ensure all application dependencies (like `pydantic`) are available.

```bash
# Set path
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Run all tests
./backend/.venv/bin/python -m pytest backend/tests

# Run a specific test file
./backend/.venv/bin/python -m pytest backend/tests/test_watchlist_service_unit.py
```

---

## 🏗️ Writing New Tests

### Unit Testing a Service
When testing a service, mock its dependencies (Repositories and Providers) using `@pytest.fixture`.

```python
@pytest.fixture
def mock_repo():
    return MagicMock(spec=WatchlistRepository)

def test_my_service_logic(service, mock_repo):
    # 1. Arrange (Set up mocks)
    mock_repo.find.return_value = {"id": 1}
    
    # 2. Act
    result = service.do_something()
    
    # 3. Assert
    assert result == expected
```

---

## 🚫 Troubleshooting & Common Pitfalls

### 1. `ModuleNotFoundError: No module named 'pydantic'` (or other app deps)
*   **Root Cause**: You are using the system Python or a Nix environment that has `pytest` but not your app's dependencies.
*   **Fix**: Follow the **Local Virtual Environment** setup above and run tests using `./backend/.venv/bin/python -m pytest`.

### 2. `ModuleNotFoundError: No module named 'application'`
*   **Root Cause**: The Python path is not set correctly.
*   **Fix**: Run `export PYTHONPATH=$PYTHONPATH:$(pwd)/backend` from the project root.

### 3. Import Errors in Tests
*   **Fix**: Use absolute imports (e.g., `from application.services...`) and run tests from the project root.
