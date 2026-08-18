# Design & Implementation Engineering Guidelines

## 1. Core Engineering Principle

All changes must be implemented as if they are going into a professional, production-grade software system.

The objective is NOT merely to make the requested functionality work.

The objective is to produce software that is:

- Correct
- Maintainable
- Modular
- Testable
- Understandable
- Robust
- Secure
- Consistent with the existing architecture
- Free from unnecessary complexity
- Free from redundant or duplicated implementation
- Backward-compatible unless a breaking change is explicitly required

Never optimize for "passing the current tests" at the expense of software quality.

## 2. No Assumptions

Do not make assumptions about the codebase, requirements, APIs, data models, dependencies, framework behavior, configuration, or runtime behavior when the information can be verified.

Before making a design or implementation decision:

- Inspect the relevant source code.
- Inspect related interfaces and contracts.
- Inspect existing implementations of similar functionality.
- Inspect configuration and dependency definitions where relevant.
- Inspect relevant tests.
- Inspect callers and consumers.
- Inspect documentation/specifications when available.
- Use authoritative documentation or source code to fact-check framework/library behavior.
- Clearly identify anything that cannot be verified.

If information is unknown, do not silently assume it.

State:
- What is known
- What was verified
- What remains uncertain
- What decision is being made and why

## 3. Understand Before Changing

NEVER modify code immediately after locating the first apparently relevant file.

Before implementation, build a sufficient understanding of the affected area.

At minimum determine:

- Where the functionality originates
- How it flows through the system
- Which components consume it
- Which components it depends upon
- Relevant interfaces/contracts
- Data flow
- Control flow
- Error handling
- State management
- Persistence implications
- External dependencies
- Configuration dependencies
- Existing tests
- Existing assumptions/invariants

Use the codebase knowledge graph/code intelligence tools where available.

Do not rely solely on filename or keyword matches.

Trace the actual relationships between components.

## 4. Relevant-Code Deep Analysis

For every requested change, identify the complete relevant execution path.

For example:

**Frontend:**

```
User action
→ React component
→ hook
→ state management
→ API client
→ backend endpoint
```

**Backend:**

```
API endpoint
→ validation
→ service
→ business logic
→ repository
→ database/external service
```

Understand the complete path before modifying it.

For cross-cutting changes, inspect both upstream and downstream dependencies.

## 5. Impact Analysis Is Mandatory

Before implementation, perform an explicit impact analysis.

Identify:

**Direct impact:**
- Files modified
- Functions/classes modified
- APIs modified
- Data structures modified
- Database objects modified

**Indirect impact:**
- Callers
- Consumers
- Dependencies
- Shared utilities
- Shared state
- API consumers
- Background jobs
- Configuration
- Persistence
- Caching
- Authentication/authorization
- Error handling

Determine whether the change can affect:

- Existing workflows
- Existing API behavior
- Existing UI behavior
- Data integrity
- Performance
- Concurrency
- Error handling
- Security
- Backward compatibility
- Regression risk

Identify existing functionality that could regress because of the change.

Do not implement until the impact analysis is sufficiently understood.

## 6. Use Existing Architecture Before Creating New Architecture

Before introducing:

- A new class
- A new service
- A new utility
- A new hook
- A new API
- A new abstraction
- A new database table
- A new dependency

Search the existing codebase for equivalent or reusable functionality.

Prefer:

- Reuse existing appropriate functionality.
- Refactor existing functionality if necessary.
- Extend an existing abstraction if architecturally appropriate.
- Create something new only when justified.

Do not create duplicate implementations of functionality that already exists.

## 7. No Snowflake Code

"Sculpted" or unnecessarily unique solutions are prohibited.

Do not introduce a special implementation merely because it is technically possible.

Prefer established patterns already used consistently within the project.

Avoid:

- One-off abstractions
- One-off utilities
- Duplicate helpers
- Duplicate business logic
- Unnecessary wrappers
- Unnecessary indirection
- Clever tricks
- Over-engineering
- Premature optimization
- Framework features that are inconsistent with the existing architecture

A solution should look like it naturally belongs in the existing codebase.

## 8. Modularity

Code must have clear responsibilities.

Each module/class/function should have a well-defined purpose.

Follow appropriate separation of concerns.

Avoid:

- God classes
- God functions
- Excessively large components
- Business logic inside UI components
- Database logic inside API controllers
- Infrastructure logic mixed with business logic
- Duplicated validation logic

Use appropriate architectural patterns such as:

- Separation of concerns
- Dependency inversion
- Single responsibility
- Repository/service patterns where appropriate
- Adapter pattern where appropriate
- Strategy pattern where appropriate
- Factory pattern where appropriate

Do NOT apply design patterns simply to demonstrate that a pattern was used.

Use a design pattern only when it solves a real problem.

## 9. DRY — But Do Not Over-Abbreviate

Avoid duplicated logic.

However, do not force unrelated code into a shared abstraction merely because two pieces currently look similar.

Use abstraction when:

- Behavior is genuinely shared
- The abstraction has a clear responsibility
- It reduces duplication
- It improves maintainability

Do not abstract merely because two functions have similar syntax.

Prefer clear, maintainable code over excessive abstraction.

## 10. Design Principles

Apply appropriate principles including:

- SOLID
- DRY
- KISS
- YAGNI
- Separation of concerns
- Least privilege
- Dependency inversion
- Composition over inheritance where appropriate
- Explicit contracts
- Fail-fast validation where appropriate

These are engineering principles, not checkboxes.

The agent must explain why a principle or pattern is relevant when it materially affects the design.

## 11. Architecture Consistency

Before introducing a new architectural approach, determine how the existing system is structured.

Do not mix architectural styles without justification.

Maintain consistency in:

- Naming
- Module boundaries
- Error handling
- API design
- State management
- Data access
- Logging
- Configuration
- Dependency injection
- Testing

If the existing architecture is flawed and the requested change exposes the problem, identify the problem explicitly rather than silently introducing another inconsistent pattern.

## 12. React-Specific Requirements

For React code:

- Prefer TypeScript.
- Avoid unnecessary `any`.
- Keep components focused.
- Keep business logic outside presentation components where appropriate.
- Avoid unnecessary state.
- Avoid unnecessary re-renders.
- Follow established state-management conventions.
- Reuse existing hooks/utilities where appropriate.
- Keep API interaction separated from presentation.
- Do not duplicate API models or business rules unnecessarily.
- Preserve existing user behavior unless the requirement explicitly changes it.

Before modifying a shared component or hook, inspect all consumers.

## 13. Python-Specific Requirements

For Python:

- Use explicit typing where appropriate.
- Maintain clear module boundaries.
- Keep business logic independent from transport/infrastructure concerns.
- Avoid excessive global state.
- Reuse existing services/utilities where appropriate.
- Preserve existing exception and error-handling conventions.
- Avoid unnecessary dependencies.
- Follow the project's established async/sync model.
- Do not introduce blocking operations into asynchronous execution paths.

## 14. API and Contract Changes

Before modifying an API, inspect:

- Backend implementation
- OpenAPI specification
- Frontend API client
- All known consumers
- Tests
- Authentication/authorization
- Error responses
- Request/response models

Determine whether the change is:

- Backward compatible
- Additive
- Behavioral
- Breaking

Do not make breaking changes without explicitly identifying them.

## 15. Database Changes

Before changing the database, inspect:

- Existing schema
- Models
- Repositories
- Queries
- Migrations
- API consumers
- Existing data assumptions

Consider:

- Existing records
- Migration safety
- Rollback
- Indexes
- Constraints
- Referential integrity
- Performance
- Backward compatibility

Never change a database schema simply to make implementation easier without evaluating the broader impact.

## 16. Dependency Changes

Before adding a dependency, determine whether existing dependencies already provide the required functionality.

For every new dependency evaluate:

- Necessity
- Maintenance status
- License
- Security
- Size
- Compatibility
- Existing alternatives

Avoid introducing dependencies for trivial functionality.

## 17. Fact Checking

For framework/library behavior that is not obvious from the codebase, verify against authoritative sources.

Preferred sources:

- Official documentation
- Official source repository
- Official specifications
- Existing verified project implementation
- Trusted technical documentation

Do not treat an LLM's prior knowledge as authoritative.

When behavior is version-dependent, verify the exact installed version.

## 18. Design Review Before Implementation

For non-trivial changes, produce:

- **Problem**: What problem is being solved?
- **Current behavior**: How does the existing system work?
- **Proposed design**: What will change?
- **Alternatives considered**: What alternatives were considered and rejected?
- **Impact analysis**: What existing functionality could be affected?
- **Risks**: What can go wrong?
- **Testing strategy**: How will correctness and regression safety be demonstrated?

Do not begin implementation until the design is sufficiently understood.

## 19. Implementation Discipline

Implement the smallest clean change that satisfies the requirement.

Do not:

- Refactor unrelated code
- Rename unrelated variables
- Reformat unrelated files
- Upgrade dependencies unnecessarily
- Change architecture unnecessarily
- "Clean up" unrelated code
- Introduce speculative functionality

Keep the change focused.

However, if the existing architecture prevents a safe implementation, stop and explain the architectural issue rather than creating a workaround that damages the design.

## 20. Final Implementation Review

After implementation, perform another review.

Verify:

- Requirement satisfied
- Architecture consistency
- No unnecessary code
- No duplication
- No unused code
- No dead code
- No unintended API changes
- No unintended behavior changes
- No obvious performance regressions
- No security regressions
- Tests cover meaningful behavior
- Existing tests remain valid

The implementation is not complete until this review passes.

## MANDATORY: Pre-Implementation Analysis

For any non-trivial change, produce the following before implementation:

```
UNDERSTANDING
- Existing behavior:
- Relevant components:
- Data flow:
- Control flow:

FACT CHECK
- Verified facts:
- Sources:
- Unknowns:

IMPACT ANALYSIS
- Direct impact:
- Indirect impact:
- Potential regressions:

DESIGN
- Proposed solution:
- Alternatives:
- Design principles/patterns:
- Why this approach:

IMPLEMENTATION PLAN
- Files to modify:
- Files not to modify:
- Tests required:
```

Only after this analysis should implementation begin.
