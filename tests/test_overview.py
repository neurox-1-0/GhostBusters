from fastapi.testclient import TestClient

from app.auth import auth_store, session_store
from app.main import app
from app.models import OrganizationRole


def setup_function():
    auth_store.reset()
    if hasattr(session_store, "sessions"): session_store.sessions.clear()


def register(email: str):
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"email": email, "display_name": email.split("@")[0], "password": "correct horse battery staple", "organization_name": email.split("@")[0], "timezone": "UTC"})
    assert response.status_code == 201
    return client, response.json()


def test_overview_empty_workspace_is_scoped_and_readable():
    client, profile = register("overview@example.com")
    response = client.get("/api/overview?date_range=30d")
    assert response.status_code == 200
    data = response.json()
    assert data["partial_data"] is False
    assert data["metrics"]["pending_approvals"] == 0
    assert data["metrics"]["predicted_monthly_savings"] == 0
    assert data["timezone"] == "UTC"
    assert "generated_at" in data


def test_overview_permission_and_organization_isolation():
    owner, profile = register("owner-overview@example.com")
    membership = auth_store.memberships[__import__("uuid").UUID(profile["membership"]["id"])]
    auth_store.memberships[membership.id] = membership.model_copy(update={"role": OrganizationRole.viewer})
    assert owner.get("/api/overview").status_code == 200
    other, _ = register("other-overview@example.com")
    assert other.get("/api/overview").status_code == 200
    first = owner.get("/api/overview").json(); second = other.get("/api/overview").json()
    assert first["metrics"]["pending_approvals"] == second["metrics"]["pending_approvals"] == 0


def test_overview_refresh_is_read_only():
    client, _ = register("refresh-overview@example.com")
    before = client.get("/api/cloud/hunts").json()
    response = client.get("/api/overview")
    after = client.get("/api/cloud/hunts").json()
    assert response.status_code == 200
    assert len(before) == len(after) == 0
