from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings
import time
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

def wait_for_db(max_attempts: int = 15, delay: float = 2.0) -> None:
    """Block until Postgres accepts connections, so startup doesn't race the DB."""
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt == max_attempts:
                raise
            print(f"DB not ready (attempt {attempt}/{max_attempts}); retrying…")
            time.sleep(delay)
# SQLite needs a special flag for use across threads; Postgres does not.
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
