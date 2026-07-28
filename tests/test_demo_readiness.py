from fastapi.testclient import TestClient

from app.auth import auth_store, session_store
from app.main import app
from app.models import OrganizationRole


def setup_function():
    auth_store.reset()
    if hasattr(session_store, "sessions"):
        session_store.sessions.clear()


def register(email: str):
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": "Demo Judge", "password": "correct horse battery staple", "organization_name": "Demo Org", "timezone": "UTC"},
    )
    assert response.status_code == 201
    return client, response.json()


def test_readiness_is_authenticated_and_does_not_expose_secrets():
    client, _ = register("readiness@example.com")
    response = client.get("/api/demo/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["authentication"]["authenticated"] is True
    assert "known_warnings" in payload
    assert "password" not in response.text.lower()
    assert "token" not in response.text.lower()
    assert client.get("/live").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_demo_reset_requires_confirmation_and_is_permission_protected():
    client, profile = register("reset@example.com")
    csrf = client.cookies.get("ghostbusters_csrf")
    assert client.post("/api/demo/reset", headers={"X-CSRF-Token": csrf}, json={}).status_code == 422
    reset = client.post("/api/demo/reset", headers={"X-CSRF-Token": csrf}, json={"confirm": True})
    assert reset.status_code == 200
    assert "preserved" in reset.json()["message"]

    membership_id = __import__("uuid").UUID(profile["membership"]["id"])
    auth_store.memberships[membership_id] = auth_store.memberships[membership_id].model_copy(update={"role": OrganizationRole.viewer})
    assert client.post("/api/demo/reset", headers={"X-CSRF-Token": csrf}, json={"confirm": True}).status_code == 403
