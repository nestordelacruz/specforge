"""Real pytest suite for CI. Covers the same ground as smoke_test.py (auth,
unit-dependent range validation, enum rejection, cross-user permissions) but
as proper test functions with assertions, so CI can actually gate on it."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client):
    client.post("/auth/register", json={"email": "a@x.com", "password": "password123"})
    client.post("/auth/register", json={"email": "b@x.com", "password": "password123"})
    tok_a = client.post(
        "/auth/token", data={"username": "a@x.com", "password": "password123"}
    ).json()["access_token"]
    tok_b = client.post(
        "/auth/token", data={"username": "b@x.com", "password": "password123"}
    ).json()["access_token"]
    return {
        "a": {"Authorization": f"Bearer {tok_a}"},
        "b": {"Authorization": f"Bearer {tok_b}"},
    }


@pytest.fixture(scope="module")
def reading_id(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 120, "unit": "mg/dL", "trend": "rising"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_bad_password_rejected(client, auth_headers):
    resp = client.post("/auth/token", data={"username": "a@x.com", "password": "wrong"})
    assert resp.status_code == 401


def test_unauthenticated_create_blocked(client):
    resp = client.post(
        "/readings", json={"value": 100, "unit": "mg/dL", "trend": "steady"}
    )
    assert resp.status_code == 401


def test_mg_dl_over_range_rejected(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 700, "unit": "mg/dL", "trend": "steady"},
    )
    assert resp.status_code == 422


def test_mmol_l_in_range_accepted(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 6.5, "unit": "mmol/L", "trend": "steady"},
    )
    assert resp.status_code == 201


def test_mmol_l_over_range_rejected(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 40, "unit": "mmol/L", "trend": "steady"},
    )
    assert resp.status_code == 422


def test_bad_enum_rejected(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 120, "unit": "mg/dL", "trend": "sideways"},
    )
    assert resp.status_code == 422


def test_cross_user_read_forbidden(client, auth_headers, reading_id):
    resp = client.get(f"/readings/{reading_id}", headers=auth_headers["b"])
    assert resp.status_code == 403


def test_owner_read_ok(client, auth_headers, reading_id):
    resp = client.get(f"/readings/{reading_id}", headers=auth_headers["a"])
    assert resp.status_code == 200


def test_list_scoped_to_owner(client, auth_headers, reading_id):
    assert client.get("/readings", headers=auth_headers["b"]).json() == []
    assert len(client.get("/readings", headers=auth_headers["a"]).json()) >= 1


def test_owner_update_ok(client, auth_headers, reading_id):
    resp = client.put(
        f"/readings/{reading_id}",
        headers=auth_headers["a"],
        json={"value": 130, "unit": "mg/dL", "trend": "falling"},
    )
    assert resp.status_code == 200


def test_cross_user_delete_forbidden(client, auth_headers, reading_id):
    resp = client.delete(f"/readings/{reading_id}", headers=auth_headers["b"])
    assert resp.status_code == 403


def test_owner_delete_ok(client, auth_headers, reading_id):
    resp = client.delete(f"/readings/{reading_id}", headers=auth_headers["a"])
    assert resp.status_code == 204


def test_openapi_has_readings_path(client):
    spec = client.get("/openapi.json").json()
    assert "/readings" in spec["paths"]
