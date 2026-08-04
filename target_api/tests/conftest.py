import os
from pathlib import Path

_TEST_DB = Path(__file__).parent / "test.db"
_TEST_DB.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
