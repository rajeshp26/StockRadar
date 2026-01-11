# StockerPro Testing Guide

This document outlines the testing strategy for the StockerPro application and provides instructions for running the various types of tests.

## Testing Philosophy

We employ a multi-layered testing strategy to ensure the quality and reliability of our application. This includes:

- **Unit Tests**: To verify the functionality of individual components in isolation.
- **Integration Tests**: To ensure that different parts of the system work together as expected.
- **End-to-End (E2E) Tests**: To simulate real user scenarios and validate the complete application workflow.

## Directory Structure

All tests are located in the `tests/` directory, which is organized as follows:

- `tests/backend/`: Contains all tests for the Python backend, including unit and integration tests.
- `tests/e2e/`: Contains end-to-end tests that simulate real user workflows.

## Running Tests

### Backend Tests

To run the backend tests, use the following command from the project root:

```bash
pytest backend/tests/
```

### End-to-End Tests

To run the end-to-end tests, use the following command from the project root:

```bash
python tests/e2e/test_user_sync.py
```
