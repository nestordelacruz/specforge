"""Real pytest suite for CI. Covers the same ground as smoke_test.py (auth,
unit-dependent range validation, enum rejection, cross-user permissions) but
as proper test functions with assertions, so CI can actually gate on it."""
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import User


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
def admin_headers(client):
    """Register a user, promote it to admin directly in the DB (there is no
    API to mint an admin), and return its auth header."""
    email = "admin@x.com"
    client.post("/auth/register", json={"email": email, "password": "password123"})
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.role = "admin"
        db.commit()
    finally:
        db.close()
    tok = client.post(
        "/auth/token", data={"username": email, "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


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


def test_auth_me_returns_current_user(client, auth_headers):
    resp = client.get("/auth/me", headers=auth_headers["a"])
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@x.com"


def test_get_nonexistent_reading_404(client, auth_headers):
    resp = client.get("/readings/999999", headers=auth_headers["a"])
    assert resp.status_code == 404


def test_note_over_length_rejected(client, auth_headers):
    resp = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={
            "value": 120,
            "unit": "mg/dL",
            "trend": "steady",
            "note": "x" * 281,
        },
    )
    assert resp.status_code == 422


def test_admin_can_access_and_list_others_readings(client, auth_headers, admin_headers):
    # A regular user (a) owns a reading.
    created = client.post(
        "/readings",
        headers=auth_headers["a"],
        json={"value": 111, "unit": "mg/dL", "trend": "steady"},
    )
    assert created.status_code == 201
    rid = created.json()["id"]

    # Admin can read a reading it does not own (ownership override in
    # _get_owned_or_404).
    assert client.get(f"/readings/{rid}", headers=admin_headers).status_code == 200

    # Admin's list is not scoped to the caller — it includes others' readings.
    admin_list = client.get("/readings", headers=admin_headers).json()
    assert any(item["id"] == rid for item in admin_list)
