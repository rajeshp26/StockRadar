"""I1c -- no credential literals in scripts; credentials come from the environment.

The two local-migration scripts were gitignored solely because they embedded a
Supabase service key, a real account password and user emails. Professional
handling: read every secret from the environment (as ``backup_cloud.py`` already
does), keep no secret in the source, and track the scrubbed scripts.

Contract:

* neither script contains a service key, password or real email literal;
* ``migrate_auth_users.py`` loads the key and the user list from env vars and
  fails loudly (naming the missing vars) when they are absent;
* the two scripts are no longer listed in ``.gitignore`` (scrubbed == trackable).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
SCRIPTS = BACKEND / "scripts"
SECRET_LITERALS = (
    "sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz",
    "StockerPro2026!",
    "TestAuth2026!",
    "rajeshp01@gmail.com",
)


@pytest.mark.parametrize("script", ["import_local.py", "migrate_auth_users.py"])
def test_no_credential_literal_in_script(script):
    source = (SCRIPTS / script).read_text(encoding="utf-8")
    for secret in SECRET_LITERALS:
        assert secret not in source, f"{script} still contains a credential literal"


def test_scripts_no_longer_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for script in ("backend/scripts/import_local.py", "backend/scripts/migrate_auth_users.py"):
        assert script not in gitignore, f"{script} still ignored after scrubbing"


def test_migrate_loads_credentials_from_env(monkeypatch):
    module = importlib.import_module("scripts.migrate_auth_users")
    users = [{"id": "u-1", "email": "someone@example.com", "password": "env-secret"}]
    monkeypatch.setenv("SUPABASE_LOCAL_SERVICE_ROLE_KEY", "env-service-key")
    monkeypatch.setenv("MIGRATE_AUTH_USERS_JSON", json.dumps(users))

    key, loaded = module.require_local_credentials()

    assert key == "env-service-key"
    assert loaded == users


def test_migrate_missing_credentials_fail_loudly(monkeypatch):
    module = importlib.import_module("scripts.migrate_auth_users")
    monkeypatch.delenv("SUPABASE_LOCAL_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("MIGRATE_AUTH_USERS_JSON", raising=False)

    with pytest.raises(SystemExit, match="SUPABASE_LOCAL_SERVICE_ROLE_KEY") as exc:
        module.require_local_credentials()

    assert "MIGRATE_AUTH_USERS_JSON" in str(exc.value)
