"""Server-side RBAC matrix: each role reaches only its own dashboard summary."""
import pytest

from tests.conftest import auth

CREDS = {
    "data_operator": ("operator@loantrust.demo", "operator123"),
    "reviewer": ("reviewer@loantrust.demo", "reviewer123"),
    "data_consumer": ("consumer@loantrust.demo", "consumer123"),
}
ROUTE_OWNER = {
    "/operator/summary": "data_operator",
    "/reviewer/summary": "reviewer",
    "/consumer/summary": "data_consumer",
}


@pytest.mark.parametrize("route,owner", ROUTE_OWNER.items())
@pytest.mark.parametrize("role", CREDS.keys())
def test_rbac_matrix(client, login, route, owner, role):
    token = login(client, *CREDS[role])
    r = client.get(route, headers=auth(token))
    if role == owner:
        assert r.status_code == 200, r.text
        assert r.json()["role"] == owner
    else:
        assert r.status_code == 403, r.text


def test_dashboard_requires_auth(client):
    assert client.get("/operator/summary").status_code == 401
