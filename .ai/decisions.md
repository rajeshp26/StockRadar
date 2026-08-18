# Architecture Decisions

## ADR-001: Supabase over Direct PostgreSQL
**Status**: Accepted
**Context**: Need managed PostgreSQL with auth integration
**Decision**: Use Supabase for DB + auth, with Firebase auth bridged via middleware
**Consequences**: Adds auth bridging complexity, but reduces infra overhead

## ADR-002: Next.js API Routes as Bridge
**Status**: Accepted
**Context**: Browser cannot directly call Python backend (CORS, security)
**Decision**: Next.js API routes proxy all requests to FastAPI
**Consequences**: Extra hop, but eliminates CORS issues and centralizes auth token forwarding

## ADR-003: Hexagonal Architecture for Backend
**Status**: Accepted
**Context**: Need testable, maintainable backend with external dependencies
**Decision**: Follow Clean Architecture with Domain/Infrastructure separation
**Consequences**: More boilerplate, but strong separation of concerns

## ADR-004: Nix for Environment Isolation
**Status**: Accepted
**Context**: C-extension conflicts (NumPy, Pandas) across dev machines
**Decision**: Use Nix shell for reproducible backend environment
**Consequences**: Requires Nix installed, but eliminates "works on my machine" issues

## ADR-005: Flutter for Mobile
**Status**: Accepted
**Context**: Need cross-platform mobile app
**Decision**: Flutter 3.22 with Riverpod state management
**Consequences**: Dart ecosystem dependency, but single codebase for iOS/Android

---

## Add New Decisions

When making a significant architectural decision, add an ADR:

```markdown
## ADR-NNN: [Title]
**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-XXX
**Context**: [What is the issue?]
**Decision**: [What was decided?]
**Consequences**: [What are the trade-offs?]
```
