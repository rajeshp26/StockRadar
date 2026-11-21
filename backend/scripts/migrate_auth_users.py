"""Create local Supabase auth users during a migration from cloud to local.

Credentials are read from the environment only; none are stored in this file or
in the repository. This mirrors ``backup_cloud.py``'s credential handling.

Required environment variables (export them or place them in the gitignored
``backend/.env`` before invoking):

* ``SUPABASE_LOCAL_SERVICE_ROLE_KEY`` -- local Supabase service_role key.
* ``MIGRATE_AUTH_USERS_JSON`` -- JSON array of ``{id, email, password}`` objects
  for the users to create. The accounts are environment data, not source data.

Optional:

* ``SUPABASE_LOCAL_URL`` -- local Supabase URL (default ``http://localhost:54321``).

Usage::

    cd backend
    python scripts/migrate_auth_users.py
"""
from __future__ import annotations

import json
import os
import sys

import requests

LOCAL_URL = os.environ.get("SUPABASE_LOCAL_URL", "http://localhost:54321")


def require_local_credentials() -> tuple[str, list[dict[str, str]]]:
    """Return (service key, users) from the environment, or fail loudly."""
    key = os.environ.get("SUPABASE_LOCAL_SERVICE_ROLE_KEY", "")
    raw_users = os.environ.get("MIGRATE_AUTH_USERS_JSON", "")
    missing = [
        name
        for name, value in (
            ("SUPABASE_LOCAL_SERVICE_ROLE_KEY", key),
            ("MIGRATE_AUTH_USERS_JSON", raw_users),
        )
        if not value.strip()
    ]
    if missing:
        raise SystemExit(
            "ERROR: missing required environment variable(s): "
            + ", ".join(missing)
            + "\nSet them before running this script. Credentials are intentionally"
            "\nnot stored in this repository."
        )
    try:
        users = json.loads(raw_users)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: MIGRATE_AUTH_USERS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(users, list) or not all(
        isinstance(u, dict) and all(k in u for k in ("id", "email", "password"))
        for u in users
    ):
        raise SystemExit(
            "ERROR: MIGRATE_AUTH_USERS_JSON must be an array of "
            "{id, email, password} objects."
        )
    return key, users


def main() -> int:
    key, users = require_local_credentials()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    for user in users:
        payload = {
            "id": user["id"],
            "email": user["email"],
            "email_confirmed": True,
            "password": user["password"],
        }
        response = requests.post(
            f"{LOCAL_URL}/auth/v1/admin/users", headers=headers, json=payload
        )
        data = response.json()
        if response.status_code in (200, 201):
            print(f"Created: {user['email']} (id={user['id']})")
        else:
            print(f"Error for {user['email']}: {data}")

    response = requests.get(f"{LOCAL_URL}/auth/v1/admin/users", headers=headers)
    data = response.json()
    print(f"\nTotal auth users: {len(data.get('users', []))}")
    for user in data.get("users", []):
        print(f"  {user['id']} | {user['email']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
