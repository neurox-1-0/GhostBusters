from fastapi.testclient import TestClient

from app.auth import auth_store, session_store
from app.main import app
from app.models import OrganizationRole


def setup_function():
    auth_store.reset()
    if hasattr(session_store, "sessions"): session_store.sessions.clear()


def register(email: str):
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"email": email, "display_name": "Settings User", "password": "correct horse battery staple", "organization_name": "Settings Org", "timezone": "UTC"})
    assert response.status_code == 201
    return client, response.json()


def test_workspace_settings_update_timezone_and_optimistic_concurrency():
    client, _ = register("settings-owner@example.com")
    workspace = client.get("/api/workspace").json()
    csrf = client.cookies.get("ghostbusters_csrf")
    updated = client.patch("/api/workspace", headers={"X-CSRF-Token": csrf}, json={"name": "Renamed Workspace", "timezone": "Asia/Colombo", "expected_version": workspace["version"]})
    assert updated.status_code == 200
    assert updated.json()["timezone"] == "Asia/Colombo"
    stale = client.patch("/api/workspace", headers={"X-CSRF-Token": csrf}, json={"name": "Stale", "expected_version": workspace["version"]})
    assert stale.status_code == 409
    assert any(event.get("event_type") == "workspace_updated" for event in auth_store.activity_events)


def test_viewer_can_read_workspace_but_cannot_edit():
    client, profile = register("settings-viewer@example.com")
    membership_id = __import__("uuid").UUID(profile["membership"]["id"])
    membership = auth_store.memberships[membership_id]
    auth_store.memberships[membership_id] = membership.model_copy(update={"role": OrganizationRole.viewer})
    assert client.get("/api/workspace").status_code == 200
    csrf = client.cookies.get("ghostbusters_csrf")
    assert client.patch("/api/workspace", headers={"X-CSRF-Token": csrf}, json={"name": "Nope"}).status_code == 403


def test_workspace_values_are_organization_scoped():
    first, _ = register("first-settings@example.com")
    second, _ = register("second-settings@example.com")
    first.patch("/api/workspace", headers={"X-CSRF-Token": first.cookies.get("ghostbusters_csrf")}, json={"name": "First Workspace"})
    assert second.get("/api/workspace").json()["organization"]["name"] == "Settings Org"
