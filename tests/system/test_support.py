"""Black-box helpers for the system tests: authentication over HTTP and a small JSON client.

No application imports and no mocks. Every call goes to the running stack through its public
interfaces, which is what makes a green run evidence about the system rather than about a
fixture. Credentials come from the environment because the harness passes the caller's
environment through to the runner; a missing value raises, because a configuration gap must
never read as a skip.

Why this file is named `test_support.py`: the harness freezes and hashes every `test_*.py` under
the test directory. A `conftest.py` would not be hashed, so its contents could change after the
freeze and the suite would still verify. Keeping the helpers in a frozen file closes that gap.

Why the client is a cached module function rather than a pytest fixture: a fixture defined here
is only visible to the test module if the test module imports it by name, which an unused import
checker reports as dead code, and the alternative -- a `conftest.py` -- is exactly the file the
freeze cannot see. A cached session is neither.
"""
from __future__ import annotations

import os

import requests

BASE_URL = os.environ.get("SYSTEM_TEST_BASE_URL", "").rstrip("/")

_SESSION = None


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            "%s is not set; these tests drive the real stack and cannot run without it" % name)
    return value


def _base():
    if not BASE_URL:
        raise RuntimeError("SYSTEM_TEST_BASE_URL is not set; these tests drive the real stack")
    return BASE_URL


def access_token():
    """Log in through Supabase Auth exactly as the product's client does."""
    url = _required("SYSTEM_TEST_SUPABASE_URL").rstrip("/")
    resp = requests.post(
        url + "/auth/v1/token?grant_type=password",
        headers={"apikey": _required("SYSTEM_TEST_SUPABASE_ANON_KEY"),
                 "Content-Type": "application/json"},
        json={"email": _required("SYSTEM_TEST_EMAIL"),
              "password": _required("SYSTEM_TEST_PASSWORD")},
        timeout=30,
    )
    assert resp.status_code == 200, (
        "supabase auth answered %d: %s" % (resp.status_code, resp.text[:200]))
    token = resp.json().get("access_token")
    assert token, "supabase auth returned no access_token"
    return token


def session():
    """One authenticated HTTP session for the whole run."""
    global _SESSION
    if _SESSION is None:
        client = requests.Session()
        client.headers["Authorization"] = "Bearer " + access_token()
        _SESSION = client
    return _SESSION


def get(path, **params):
    return session().get(_base() + path, params=params, timeout=60)


def series(period):
    """The performance payload for a period, with the transport-level guarantees asserted."""
    resp = get("/portfolio/performance", period=period)
    assert resp.status_code == 200, (
        "period=%s answered %d: %s" % (period, resp.status_code, resp.text[:200]))
    body = resp.json()
    assert body.get("success") is True, (
        "period=%s reported failure: %s" % (period, body.get("error")))
    return body
