"""Deterministic seed: load demo users so all three roles can log in.

Idempotent — safe to run repeatedly (skips users that already exist). In Docker,
Alembic creates the schema first; create_all here is a harmless no-op then, and makes
local/SQLite runs work without migrations.
"""
import json
from pathlib import Path

from sqlalchemy import select

from .core.config import get_settings
from .core.db import Base, SessionLocal, engine
from .core.security import hash_password
from .models import User  # noqa: F401  (registers metadata)


def seed() -> dict:
    settings = get_settings()
    Base.metadata.create_all(engine)

    data = json.loads(Path(settings.seed_users_path).read_text())
    db = SessionLocal()
    created = 0
    try:
        for u in data["users"]:
            if db.scalar(select(User).where(User.email == u["email"].lower())):
                continue
            db.add(
                User(
                    id=u["id"],
                    email=u["email"].lower(),
                    name=u["name"],
                    role=u["role"],
                    password_hash=hash_password(u["password"]),
                )
            )
            created += 1
        db.commit()
    finally:
        db.close()
    result = {"seeded_users": created}
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    seed()
