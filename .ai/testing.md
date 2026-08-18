# Testing Rules

## Test Pyramid

1. **Unit Tests** (base): Isolated, no DB/network. Mock all dependencies.
2. **Integration Tests** (middle): API + DB, use test database or mocks.
3. **E2E Tests** (top): Full user flows with Playwright.

## Backend (pytest)

### Running Tests
```bash
# All tests
nix-shell --run "python -m pytest backend/tests"

# Specific file
nix-shell --run "python -m pytest backend/tests/test_watchlist_service_unit.py"

# With coverage
nix-shell --run "python -m pytest backend/tests --cov=backend --cov-report=html"
```

### Writing Tests
- Unit test files: `test_<feature>_unit.py`
- Integration test files: `test_<feature>_integration.py`
- Use `@pytest.fixture` for setup
- Mock external services with `unittest.mock.MagicMock`
- Test both success AND failure paths
- Name tests descriptively: `test_<action>_<scenario>_<expected>`

### Example
```python
@pytest.fixture
def mock_repo():
    return MagicMock(spec=WatchlistRepository)

@pytest.fixture
def service(mock_repo):
    return WatchlistService(
        user_repo=MagicMock(),
        watchlist_repo=mock_repo,
        stock_provider=MagicMock()
    )

def test_get_watchlist_success(service, mock_repo):
    mock_repo.get_by_id.return_value = Watchlist(id="1", name="Test")
    result = service.get_watchlist("1")
    assert result.name == "Test"
```

## Frontend

- Co-located test files: `Component.test.tsx`
- Use React Testing Library
- Test user interactions, not implementation details

## Mobile

```bash
cd mobile
flutter test
flutter analyze
```

## CI Requirement

- All tests must pass before merge
- No skipped/flaky tests without ticket reference
