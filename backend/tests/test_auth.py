from tests.conftest import auth


def test_login_success_returns_role(client):
    r = client.post("/auth/login", json={"email": "reviewer@loantrust.demo", "password": "reviewer123"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "reviewer"
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_bad_password(client):
    r = client.post("/auth/login", json={"email": "reviewer@loantrust.demo", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/auth/login", json={"email": "nobody@loantrust.demo", "password": "x"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_token(client, login):
    token = login(client, "consumer@loantrust.demo", "consumer123")
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["role"] == "data_consumer"


def test_invalid_token_rejected(client):
    r = client.get("/auth/me", headers=auth("not-a-real-token"))
    assert r.status_code == 401
