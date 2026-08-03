"""Seed demo data: one admin, two regular users, a few readings each.
Run after the DB is up:  python -m db.seed
"""
from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models import Reading, User
from app.security import hash_password

Base.metadata.create_all(bind=engine)

DEMO = [
    ("admin@specforge.dev", "password123", "admin"),
    ("alice@specforge.dev", "password123", "user"),
    ("bob@specforge.dev", "password123", "user"),
]


def run():
    db = SessionLocal()
    try:
        if db.query(User).first():
            print("Data already present; skipping seed.")
            return
        users = []
        for email, pw, role in DEMO:
            u = User(email=email, hashed_password=hash_password(pw), role=role)
            db.add(u)
            users.append(u)
        db.commit()

        now = datetime.now(timezone.utc)
        for u in users[1:]:  # readings for the two regular users
            for i, (val, unit, trend) in enumerate([
                (95, "mg/dL", "steady"),
                (142, "mg/dL", "rising"),
                (6.1, "mmol/L", "falling"),
            ]):
                db.add(Reading(
                    user_id=u.id, value=val, unit=unit, trend=trend,
                    taken_at=now - timedelta(hours=i),
                ))
        db.commit()
        print(f"Seeded {len(users)} users and readings.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
