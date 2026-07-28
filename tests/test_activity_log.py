from __future__ import annotations

from uuid import UUID

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
        membership_id = UUID(profile["membership"]["id"])
        membership = auth_store.memberships[membership_id]
        auth_store.memberships[membership_id] = membership.model_copy(update={"role": role})
    return client, profile


def test_activity_is_organization_scoped_and_permission_enforced() -> None:
    owner, profile = register("owner@example.com")
    other, _ = register("other@example.com")
    auth_store.record_activity(UUID(profile["organization"]["id"]), "member_tested", UUID(profile["user"]["id"]), {"summary": "Visible event"}, category="Members")

    response = owner.get("/api/activity")
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert all(item["organization_id"] == profile["organization"]["id"] for item in response.json()["items"])
    other_response = other.get("/api/activity")
    assert other_response.status_code == 200
    assert all(item["organization_id"] != profile["organization"]["id"] for item in other_response.json()["items"])


def test_activity_filters_pagination_sorting_and_secret_redaction() -> None:
    client, profile = register("owner@example.com")
    organization_id = UUID(profile["organization"]["id"])
    user_id = UUID(profile["user"]["id"])
    for index in range(30):
        auth_store.record_activity(organization_id, "policy_changed", user_id, {"summary": f"policy-{index}", "token": "never-return-this"}, category="Policies", target_type="policy", target_id=f"p-{index}")

    page = client.get("/api/activity", params={"category": "Policies", "search": "policy-2", "page_size": 25, "sort": "created_at_asc"})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] >= 1
    assert body["items"][0]["category"] == "Policies"
    assert body["items"][0]["metadata"]["token"] == "[REDACTED]"
    assert body["timezone"] == "Asia/Colombo"


def test_activity_events_are_append_only_and_decision_correlation_is_represented_once() -> None:
    client, profile = register("owner@example.com")
    run = client.post("/api/runs", headers={"X-CSRF-Token": profile["csrf_token"]}, json={"goal": "reduce cost", "scenario_name": "safe"}).json()
    decision = client.post(f"/api/runs/{run['id']}/review", headers={"X-CSRF-Token": profile["csrf_token"]}, json={"action": "reject", "comment": "Keep the current shape.", "expected_version": run["version"], "idempotency_key": "activity-decision"})
    assert decision.status_code == 200
    activity = client.get("/api/activity", params={"category": "Human Decisions", "search": decision.json()["correlation_id"]}).json()
    assert activity["total"] == 1
    assert not hasattr(auth_store, "delete_activity")
    assert client.get("/api/activity", params={"category": "Human Decisions", "search": decision.json()["correlation_id"]}).json()["total"] == 1
