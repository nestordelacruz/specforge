# SpecForge Target API

The **controlled system under test** for SpecForge (Phase 1). A small FastAPI +
Postgres service with a health-tech shape (glucose readings) chosen because it
produces genuinely tricky, unit-dependent validation — ideal fodder for
boundary and negative test generation.

## Endpoints

| Method | Path | Type | Notes |
|---|---|---|---|
| GET | `/health` | meta | liveness |
| POST | `/auth/register` | auth | create a user |
| POST | `/auth/token` | auth | OAuth2 password → JWT |
| GET | `/auth/me` | auth | current user |
| POST | `/readings` | create | **tricky validation** (see below) |
| GET | `/readings` | list | **scoped to caller** (admin sees all) |
| GET | `/readings/{id}` | read | **permission-checked** |
| PUT | `/readings/{id}` | update | permission-checked |
| DELETE | `/readings/{id}` | delete | permission-checked, 204 |

### The tricky validation (why this API is worth testing)

`value` must fall within a range that **depends on `unit`**:

- `mg/dL` → 20–600
- `mmol/L` → 1.1–33.3

Plus enum constraints on `unit` and `trend`, and a 280-char cap on `note`.
This cross-field rule is exactly the kind of thing manual test authors miss and
where generated boundary tests earn their keep.

### The permission model

A reading belongs to a user. A `user` may only read/update/delete their own;
an `admin` may touch any. `GET /readings` is filtered to the caller. This gives
the generator real authorization cases to cover (403 vs 404 vs 200).

## Run it

With Docker (Postgres-backed), from the repo root:

```bash
docker-compose up --build
# API at http://localhost:8000/docs
```

Quick local run without Docker (SQLite):

```bash
cd target_api
pip install -r requirements.txt
DATABASE_URL="sqlite:///./dev.db" uvicorn app.main:app --reload
```

Seed demo data (admin + two users with readings):

```bash
DATABASE_URL="sqlite:///./dev.db" python -m db.seed
```

Demo credentials (password `password123`): `admin@specforge.dev`,
`alice@specforge.dev`, `bob@specforge.dev`.

## Smoke test

```bash
cd target_api && python smoke_test.py
```

Exercises auth, the unit-dependent range validation, enum rejection, and
cross-user permission denial. Not the real suite — SpecForge generates that —
just proof the service behaves.

## OpenAPI spec

`openapi.json` is exported from the live app and is the contract SpecForge's
generator consumes. Regenerate after changing endpoints:

```bash
DATABASE_URL="sqlite:///./tmp.db" python -c "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi(), indent=2))"
```

## Deliberate simplifications (documented on purpose)

- Tables are created on startup instead of via Alembic migrations — fine for a
  demo target; a production service would use migrations.
- JWT secret defaults are for local dev only.
