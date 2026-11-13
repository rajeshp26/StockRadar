# StockerPro testing guide

How the product is tested, layer by layer, and how to run each layer.

## Layers

| Path | Layer | Runs against |
|---|---|---|
| `backend/tests/` (loose `test_*.py`) | unit / integration | mocks, or the Supabase CLI stack |
| `backend/tests/unit/` | unit | nothing |
| `backend/tests/integration/` | integration | a real repository / the local Supabase stack |
| `backend/tests/e2e/` | end-to-end | the real stack over HTTP (`RUN_E2E=true`) |
| `backend/tests/system/` | system, black-box, frozen | the running stack (`SYSTEM_TEST_BASE_URL`) |
| `web/e2e/` | browser | Playwright against the running web app |

Unit, integration and end-to-end tests are written by the team and belong to the code they
cover. System tests are written by the framework verifier from the requirements, frozen before
implementation, and then left alone (DID-017) - a failing frozen test is a defect report, not a
test to edit.

## Running

From the repository root:

```bash
pytest backend/tests
```

`backend/tests/system/` is deliberately excluded from that run (`norecursedirs` in
`pyproject.toml`): it needs a live stack and the harness owns its red and green runs.

```bash
RUN_E2E=true pytest backend/tests/e2e
```

System tests - always through the harness, which freezes, hashes and runs the suite:

```bash
python3 framework/testing/run_system_tests.py freeze --plan <plan>
python3 framework/testing/run_system_tests.py run --plan <plan> --phase green
```

The backend runs inside its Nix environment:
`nix-shell backend/shell.nix --run 'bash backend/start.sh'`.
