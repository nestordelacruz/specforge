"""Bring up the target service on a clean, seeded database.

Deliberately outside the `specforge` package: starting the service needs
uvicorn and the target's own dependencies, and the tool is supposed to need
neither. specforge only ever talks HTTP to a base URL.

    python scripts/run_target.py            # serve until interrupted
    python scripts/run_target.py --reset-only   # rebuild the DB and exit

Run it from the repo root, with target_api's requirements installed.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_ROOT / "target_api"
DB_PATH = TARGET_DIR / "specforge_run.db"
DB_URL = f"sqlite:///{DB_PATH}"


def reset_and_seed() -> None:
    """Recreate the database from scratch and seed it.

    Seeding matters for one specific reason: registration always assigns the
    'user' role, so there is no way to create an admin over the API. The seed
    provides admin@specforge.dev, which the generated suite logs in as. The
    seed also short-circuits if any user already exists, so the delete is not
    optional — without it a re-run silently keeps stale data.
    """
    DB_PATH.unlink(missing_ok=True)
    env = {**os.environ, "DATABASE_URL": DB_URL}
    proc = subprocess.run(
        [sys.executable, "-m", "db.seed"],
        cwd=TARGET_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        raise SystemExit(f"seeding failed (exit {proc.returncode})")
    print(f"database reset and seeded: {DB_PATH.name}")


def serve(host: str, port: int) -> int:
    env = {**os.environ, "DATABASE_URL": DB_URL}
    print(f"serving http://{host}:{port}  (ctrl-c to stop)")
    return subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
        cwd=TARGET_DIR,
        env=env,
        check=False,
    ).returncode


def wait_for_health(base_url: str, timeout: float = 30.0) -> bool:
    """Poll /health until the service answers. Used by CI, which backgrounds the server."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=2.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reset-only", action="store_true", help="Seed the DB and exit")
    parser.add_argument("--wait", metavar="BASE_URL", help="Poll BASE_URL/health and exit")
    args = parser.parse_args(argv)

    if args.wait:
        ok = wait_for_health(args.wait)
        print("target is up" if ok else "target did not become healthy", file=sys.stderr)
        return 0 if ok else 1

    reset_and_seed()
    if args.reset_only:
        return 0
    return serve(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
