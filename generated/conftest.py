"""Fixtures for the generated suite. Rendered by specforge — do not edit.

The suite talks HTTP to a running target rather than importing it. That keeps
the tool independent of the target's dependencies: specforge never needs
fastapi installed to test a FastAPI service, and the same suite would run
against the service deployed anywhere.
"""
import json
import os
import pathlib
import time

import httpx
import pytest

BASE_URL = os.environ.get("SPECFORGE_BASE_URL", "http://127.0.0.1:8000")
RESULTS_PATH = os.environ.get("SPECFORGE_RESULTS")

USER = ("specforge_user@example.com", "password123")
OTHER_USER = ("specforge_other@example.com", "password123")
# Registration always assigns the "user" role, so the admin cannot be created
# over the API. This account comes from the target's own seed data.
ADMIN = ("admin@specforge.dev", "password123")


def _token(email, password):
    """Register (ignoring "already exists") and exchange credentials for a token."""
    httpx.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password})
    resp = httpx.post(
        f"{BASE_URL}/auth/token", data={"username": email, "password": password}
    )
    if resp.status_code != 200:
        raise RuntimeError(f"could not authenticate {email}: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def clients():
    """One HTTP client per identity, each with its auth header preset.

    Tests refer to identities by role, never by credential, so the executor
    owns how a role becomes a token.
    """
    built = {"none": httpx.Client(base_url=BASE_URL, timeout=10.0)}
    for role, (email, password) in (
        ("user", USER),
        ("other_user", OTHER_USER),
        ("admin", ADMIN),
    ):
        token = _token(email, password)
        built[role] = httpx.Client(
            base_url=BASE_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {token}"},
        )
    yield built
    for client in built.values():
        client.close()


def pytest_runtest_logreport(report):
    """Append one JSON line per test outcome.

    A tiny hook rather than a reporting plugin: it keeps the tool's dependency
    list to what it actually needs, and gives the executor a stable format to
    parse across the repeated runs Phase 4 will do.
    """
    if RESULTS_PATH is None or report.when != "call":
        return
    line = {
        "test_id": report.nodeid.rsplit("::", 1)[-1],
        "outcome": report.outcome,
        "duration": round(report.duration, 4),
        "longrepr": str(report.longrepr)[:2000] if report.failed else None,
        "recorded_at": time.time(),
    }
    with pathlib.Path(RESULTS_PATH).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
