"""Test setup: force a throwaway SQLite DB and seed the three demo roles.

Env is set BEFORE importing the app so cached settings pick it up.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_loantrust.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-minimum-32-bytes!!")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    import app.models  # noqa: F401  register ALL models on Base.metadata
    from app.core.db import Base, SessionLocal, engine
    from app.core.security import hash_password
    from app.models.user import User

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all(
        [
            User(id="u-operator", email="operator@loantrust.demo", name="Olivia",
                 role="data_operator", password_hash=hash_password("operator123")),
            User(id="u-reviewer", email="reviewer@loantrust.demo", name="Rey",
                 role="reviewer", password_hash=hash_password("reviewer123")),
            User(id="u-consumer", email="consumer@loantrust.demo", name="Casey",
                 role="data_consumer", password_hash=hash_password("consumer123")),
        ]
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def login():
    def _login(client, email, password):
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    return _login


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
