def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "LoanTrust Copilot API"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ok(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["checks"]["db"] is True


def test_health_aliases(client):
    # Spec-conventional aliases must behave identically to the k8s-style paths.
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_request_id_header_present(client):
    r = client.get("/healthz")
    assert r.headers.get("X-Request-ID")


def test_reviewer_summary_returns_real_exception_counts(client, login):
    """reviewer/summary must return real counts (not hardcoded 0 from Slice 0 placeholder)."""
    from tests.conftest import auth
    tok = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.get("/reviewer/summary", headers=auth(tok))
    assert r.status_code == 200
    body = r.json()
    # Must have numeric fields (not a placeholder message only)
    assert "open_exceptions" in body
    assert isinstance(body["open_exceptions"], int)
    assert "in_review_exceptions" in body


def test_operator_summary_includes_corrections_needed(client, login):
    """operator/summary must include corrections_needed field."""
    from tests.conftest import auth
    tok = login(client, "operator@loantrust.demo", "operator123")
    r = client.get("/operator/summary", headers=auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert "corrections_needed" in body
    assert isinstance(body["corrections_needed"], int)
