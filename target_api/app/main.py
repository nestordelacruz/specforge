from fastapi import FastAPI

from .database import Base, engine
from .routers import auth, readings
from .database import Base, engine, wait_for_db

wait_for_db()
# For a demo target service we create tables on startup. In a real system this
# would be an Alembic migration — noted as a deliberate simplification.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SpecForge Target API",
    version="0.1.0",
    description="Controlled system under test: auth + glucose readings CRUD.",
)

app.include_router(auth.router)
app.include_router(readings.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
