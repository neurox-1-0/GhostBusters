from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import auth_store, session_store
from app.main import app
from app.models import OrganizationRole


def setup_function() -> None:
    auth_store.reset()
    if hasattr(session_store, "sessions"):
        session_store.sessions.clear()


def register(email: str, role: OrganizationRole | None = None) -> tuple[TestClient, dict]:
    client = TestClient(app)
    profile = client.post("/api/auth/register", json={
        "email": email, "display_name": email.split("@")[0].title(),
        "password": "correct horse battery staple", "organization_name": email,
        "timezone": "Asia/Colombo",
    }).json()
    if role:
        membership_id = __import__("uuid").UUID(profile["membership"]["id"])
        membership = auth_store.memberships[membership_id]
        auth_store.memberships[membership_id] = membership.model_copy(update={"role": role})
    return client, profile


def create_run(client: TestClient, profile: dict, scenario: str = "safe") -> dict:
    response = client.post("/api/runs", headers={"X-CSRF-Token": profile["csrf_token"]}, json={"goal": f"review {scenario}", "scenario_name": scenario})
    assert response.status_code == 201
    return response.json()


def test_multiple_reviews_are_retained_and_server_pagination_search_sort_work() -> None:
    client, profile = register("owner@example.com")
    first = create_run(client, profile, "safe")
    second = create_run(client, profile, "missing_evidence")

    listed = client.get("/api/runs", params={"page": 1, "page_size": 1, "sort": "oldest"})
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert body["has_next"] is True
    assert body["items"][0]["id"] == first["id"]
    assert "audit_events" not in body["items"][0]
    assert client.get("/api/runs", params={"page": 1, "page_size": 20, "search": "missing_evidence"}).json()["items"][0]["id"] == second["id"]


def test_status_filter_and_review_permission_are_enforced_without_mutating_work() -> None:
    client, profile = register("owner@example.com")
    run = create_run(client, profile)
    before = len(client.get("/api/runs").json())
    filtered = client.get("/api/runs", params={"status": "pending_human_review", "group": "needs-attention", "page": 1, "page_size": 20})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert len(client.get("/api/runs").json()) == before
    assert client.get(f"/api/runs/{run['id']}").json()["id"] == run["id"]

    viewer, _ = register("viewer@example.com", OrganizationRole.viewer)
    assert viewer.get("/api/runs", params={"page": 1, "page_size": 20}).status_code == 200


def test_organization_isolation_keeps_review_history_private() -> None:
    owner, profile = register("owner@example.com")
    other, _ = register("other@example.com")
    run = create_run(owner, profile)
    body = other.get("/api/runs", params={"page": 1, "page_size": 20}).json()
    assert body["total"] == 0
    assert other.get(f"/api/runs/{run['id']}").status_code == 404
