"""Quick end-to-end smoke test against SQLite. Not the real suite — just proof
the service boots and the four endpoint types behave."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
results = []


def check(name, cond):
    results.append((name, cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


# health
check("health ok", client.get("/health").json() == {"status": "ok"})

# register + token (auth endpoint)
client.post("/auth/register", json={"email": "a@x.com", "password": "password123"})
client.post("/auth/register", json={"email": "b@x.com", "password": "password123"})
tok_a = client.post(
    "/auth/token", data={"username": "a@x.com", "password": "password123"}
).json()["access_token"]
tok_b = client.post(
    "/auth/token", data={"username": "b@x.com", "password": "password123"}
).json()["access_token"]
ha = {"Authorization": f"Bearer {tok_a}"}
hb = {"Authorization": f"Bearer {tok_b}"}

check("bad password rejected", client.post(
    "/auth/token", data={"username": "a@x.com", "password": "wrong"}
).status_code == 401)

# unauth create blocked
check("unauth create 401", client.post("/readings", json={
    "value": 100, "unit": "mg/dL", "trend": "steady"}).status_code == 401)

# valid create (positive)
r = client.post("/readings", headers=ha, json={
    "value": 120, "unit": "mg/dL", "trend": "rising"})
check("valid create 201", r.status_code == 201)
rid = r.json()["id"]

# tricky validation: out-of-range for unit (boundary/negative)
check("mg/dL over-range 422", client.post("/readings", headers=ha, json={
    "value": 700, "unit": "mg/dL", "trend": "steady"}).status_code == 422)
check("mmol/L in-range 201", client.post("/readings", headers=ha, json={
    "value": 6.5, "unit": "mmol/L", "trend": "steady"}).status_code == 201)
check("mmol/L over-range 422", client.post("/readings", headers=ha, json={
    "value": 40, "unit": "mmol/L", "trend": "steady"}).status_code == 422)
check("bad enum 422", client.post("/readings", headers=ha, json={
    "value": 120, "unit": "mg/dL", "trend": "sideways"}).status_code == 422)

# permission: user B cannot read user A's reading
check("cross-user read 403",
      client.get(f"/readings/{rid}", headers=hb).status_code == 403)
check("owner read 200",
      client.get(f"/readings/{rid}", headers=ha).status_code == 200)

# list is scoped
check("B sees none", client.get("/readings", headers=hb).json() == [])
check("A sees own", len(client.get("/readings", headers=ha).json()) >= 1)

# update + delete
check("owner update 200", client.put(f"/readings/{rid}", headers=ha, json={
    "value": 130, "unit": "mg/dL", "trend": "falling"}).status_code == 200)
check("cross-user delete 403",
      client.delete(f"/readings/{rid}", headers=hb).status_code == 403)
check("owner delete 204",
      client.delete(f"/readings/{rid}", headers=ha).status_code == 204)

# openapi spec exports
spec = client.get("/openapi.json").json()
check("openapi has paths", "/readings" in spec["paths"])

print("\n" + ("ALL PASSED" if all(c for _, c in results)
              else f"{sum(1 for _, c in results if not c)} FAILED"))
