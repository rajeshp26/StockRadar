# Testing & Quality Engineering Guidelines

## 1. Core Testing Principle

Tests exist to provide evidence that the software behaves correctly.

Tests must NOT exist primarily to increase code coverage.

A test is valuable only when it verifies meaningful behavior, a business rule, a contract, an important edge case, an error condition, or protection against a realistic regression.

High coverage with meaningless tests is not considered high-quality testing.

## 2. Never Modify Production Code Merely to Pass Tests

NEVER change production code solely to make an existing test pass unless the existing implementation is objectively incorrect.

When a test fails:

- Determine why it fails.
- Determine whether the production behavior is correct.
- Determine whether the test expectation is correct.
- Verify the original requirement.
- Check whether the failure indicates a regression.
- Only then modify production code or the test.

Never optimize implementation behavior around the current test suite.

Tests are evidence, not the specification by themselves.

## 3. Never Modify Tests to Hide a Regression

Do not:

- Weaken assertions
- Remove assertions
- Change expected values merely to match new code
- Delete failing tests
- Skip tests
- Increase timeouts without justification
- Mock away the behavior being tested
- Reduce test scope to make the suite pass

Unless there is a documented and technically justified reason.

If behavior intentionally changes, update the test to reflect the new requirement and explain the behavioral change.

## 4. Every Test Must Have a Purpose

Before creating a test, identify what behavior it protects.

Each meaningful test should answer:

**What defect would this test catch?**

If there is no clear answer, do not create the test.

Good test purposes include:

- Business rule validation
- API contract verification
- Permission enforcement
- Error handling
- Boundary conditions
- State transitions
- Data integrity
- Regression prevention
- Integration behavior
- User workflow verification

## 5. Do Not Write Tests Solely for Coverage

Coverage percentage is a metric, not the objective.

Do NOT create meaningless tests such as:

- Calling a function without meaningful assertions
- Testing trivial getters/setters purely for coverage
- Testing implementation details that users do not care about
- Creating tests that simply execute every branch without verifying behavior
- Excessive snapshot tests without meaningful validation

Prefer fewer strong tests over many meaningless tests.

## 6. Test the Contract, Not the Implementation

Tests should generally verify observable behavior.

Avoid tightly coupling tests to internal implementation details unless the internal behavior itself is a contractual requirement.

For example, prefer:

```
Given valid input
When the user submits the request
Then the expected result is returned
```

Over:

```
Verify private method A calls private method B exactly once
```

Unless that interaction is architecturally important.

## 7. Test Pyramid

Use the appropriate level of testing.

**Unit Tests**

Test:

- Business rules
- Pure functions
- Algorithms
- Validation
- Important transformations

**Integration Tests**

Test:

- Service interactions
- Database integration
- API layers
- External integrations
- Component boundaries

**End-to-End Tests**

Test critical user workflows.

Do not duplicate every unit test as an E2E test.

## 8. Test Risk, Not Just Code

Prioritize testing based on risk.

**High priority:**

- Authentication
- Authorization
- Payments/financial logic
- Data modification
- User permissions
- Core business logic
- API contracts
- Critical workflows
- Error recovery
- State transitions
- Data migrations

**Lower priority:**

- Trivial wrappers
- Framework-generated code
- Simple pass-through functions
- Purely presentational code with no meaningful behavior

## 9. Positive and Negative Cases

For meaningful functionality consider:

**Happy path:**
- Does valid input produce the correct result?

**Invalid input:**
- Does invalid input fail correctly?

**Boundary conditions:**

What happens at:

- Minimum values
- Maximum values
- Empty values
- Null values
- Large inputs
- Unexpected combinations

**Failure conditions:**

What happens when:

- Database fails?
- API fails?
- External service fails?
- Network fails?
- Authentication expires?
- Resource is unavailable?

## 10. Regression Testing

For every bug fix:

1. Reproduce the bug.
2. Create a regression test that fails before the fix.
3. Implement the fix.
4. Verify the regression test passes.
5. Run relevant existing tests.
6. Perform impact analysis for related functionality.

A bug fix without a meaningful regression test should require explicit justification.

## 11. React Testing

Test user-observable behavior.

Prefer:

- React Testing Library
- Vitest
- Playwright

Examples of meaningful tests:

- User interaction produces expected UI state.
- Invalid input displays correct validation.
- API failure produces correct error state.
- Authentication redirects correctly.
- Important workflows complete successfully.

Avoid testing implementation details unnecessarily.

## 12. Python Testing

Use pytest.

Test:

- Business rules
- Service behavior
- API contracts
- Validation
- Database interactions where appropriate
- Error handling
- Important edge cases

Use mocks only when they provide a meaningful isolation boundary.

Do not mock everything.

Excessive mocking can produce tests that pass while the actual system is broken.

## 13. API Testing

For each important API verify:

- Request validation
- Successful response
- Response schema
- Authentication
- Authorization
- Error responses
- Boundary conditions
- Data persistence
- Relevant side effects

Where appropriate, use contract testing to ensure frontend and backend remain compatible.

## 14. End-to-End Testing

E2E tests should represent important real user workflows.

Examples:

```
Login
→ Navigate
→ Perform action
→ Save
→ Refresh
→ Verify persisted result
```

Do not create E2E tests for every minor UI detail.

Focus on workflows where a regression would materially affect users.

## 15. Test Isolation

Tests must be:

- Deterministic
- Repeatable
- Independent
- Reproducible

Avoid:

- Hidden test dependencies
- Execution-order dependencies
- Shared mutable state
- Random behavior without controlled seeds
- Reliance on external services unless the test specifically validates that integration

## 16. Test Data

Use realistic but minimal test data.

Do not create unnecessarily large fixtures.

Test data should clearly communicate the behavior being tested.

Avoid meaningless random data unless randomness itself is part of the test objective.

## 17. Assertions

Assertions must be meaningful.

Avoid tests where the primary assertion is simply:

```javascript
expect(result).toBeDefined()
```

When the expected value or behavior can be verified.

Prefer precise assertions that prove the intended behavior.

## 18. Coverage

Track coverage, but do not optimize blindly for a percentage.

If coverage increases because meaningful behavior is now tested, that is good.

If coverage increases through meaningless tests, that is not considered an improvement.

Coverage gaps should be evaluated based on risk and behavior.

## 19. Test Failure Investigation

When tests fail, follow this sequence:

1. Reproduce the failure.
2. Read the failing test.
3. Read the implementation.
4. Understand the intended behavior.
5. Determine whether the implementation or test is incorrect.
6. Check recent changes.
7. Perform impact analysis.
8. Fix the root cause.
9. Run the targeted test.
10. Run related tests.
11. Run the full relevant test suite.

Never blindly change code until the test becomes green.

## 20. Test Quality Review

Before considering testing complete, ask:

- Does every new test have a clear purpose?
- Would the test catch a realistic defect?
- Are assertions meaningful?
- Are important negative cases covered?
- Are important boundaries covered?
- Are critical workflows covered?
- Are tests testing behavior rather than implementation details?
- Are mocks hiding real integration problems?
- Did any production code change only to satisfy a test?
- Did any existing test get weakened?
- Are existing tests still meaningful?
- Did the tests actually validate the requirement?

If the answer to any of these is concerning, improve the test strategy.

## 21. Definition of Done

A feature is not considered complete merely because:

- The code compiles.
- Tests pass.
- Coverage increased.

A feature is complete when:

- Requirements are satisfied.
- Design has been reviewed.
- Impact analysis has been performed.
- Implementation follows project architecture.
- Meaningful unit tests exist.
- Appropriate integration tests exist.
- Critical E2E behavior is covered.
- Existing functionality remains intact.
- Static analysis passes.
- No unnecessary code or duplication was introduced.
- Tests provide meaningful evidence of correctness.
