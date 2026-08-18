# Coding Rules

## Backend (Python)

### Required
- Python 3.11+, type hints on ALL functions
- Pydantic v2 for ALL request/response models
- FastAPI dependency injection via `Depends()`
- Service layer pattern: API -> Application -> Domain -> Infrastructure
- No business logic in route handlers

### Architecture
- One class = one responsibility (SRP)
- Depend on abstractions (domain interfaces), not concretions
- External providers implement domain interfaces (e.g., `StockPriceProvider`)

### Naming
- snake_case for variables, functions, methods
- PascalCase for classes
- `test_<feature>_<scenario>.py` for test files

## Frontend (TypeScript/React)

### Required
- TypeScript strict mode — NO `any` types
- React Query for server state management
- Feature-based folder structure
- Components must have co-located tests

### Patterns
- Keep components small and focused
- Use custom hooks for shared logic
- API calls through centralized service layer

## Mobile (Flutter)

### Required
- Flutter 3.22+, Dart 3.x
- Riverpod for state management
- Fail-fast initialization (Bootstrap Guard)
- `flutter analyze` must pass with zero warnings

## General

- No `@ts-ignore`, `# type: ignore`, or `noqa` without comment explaining why
- All public functions/methods must have docstrings
- Errors must be handled explicitly — no silent failures
- Commit messages: conventional commits format
