from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import app.auth as auth_module
from app.auth import AuthStore, auth_store, session_store, utc_now
from app.main import app
from app.models import AccountStatus, OrganizationRole


def setup_function() -> None:
    auth_store.reset()
    if hasattr(session_store, "sessions"):
        session_store.sessions.clear()


def register_client(email: str, role: OrganizationRole | None = None) -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@")[0].title(),
            "password": "correct horse battery staple",
            "organization_name": f"{email.split('@')[0].title()} Cloud Team",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    profile = response.json()
    if role is not None:
        membership_id = profile["membership"]["id"]
        membership = auth_store.memberships[__import__("uuid").UUID(membership_id)]
        auth_store.memberships[membership.id] = membership.model_copy(update={"role": role, "approval_permission_enabled": role == OrganizationRole.reviewer})
        profile = client.get("/api/auth/me").json()
    return client, profile


def test_register_creates_owner_workspace_and_safe_session_cookie() -> None:
    client, profile = register_client("owner@example.com")

    assert profile["authenticated"] is True
    assert profile["role_label"] == "Owner"
    assert profile["membership"]["role"] == "OWNER"
    assert profile["organization"]["name"] == "Owner Cloud Team"
    assert "password" not in str(profile).lower()
    cookie = client.cookies.get(auth_module.settings.session_cookie_name)
    assert cookie


def test_registered_credentials_survive_auth_store_restart(tmp_path: Path) -> None:
    persistence_path = tmp_path / "auth-store.json"
    first_store = AuthStore(persistence_path)
    user, organization, _ = first_store.register_owner(
        "persistent@example.com", "Persistent User", "correct horse battery staple", "Persistent Workspace", "UTC"
    )

    restarted_store = AuthStore(persistence_path)
    restored_user, restored_org, _ = restarted_store.authenticate("PERSISTENT@example.com", "correct horse battery staple")

    assert restored_user.id == user.id
    assert restored_org.id == organization.id


def test_login_logout_invalid_disabled_and_expired_session_behaviors() -> None:
    client, profile = register_client("reviewer@example.com")
    csrf = profile["csrf_token"]
    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}, json={})
    assert logout.status_code == 200
    assert client.get("/api/auth/me").json()["demo_mode"] is True

    bad = client.post("/api/auth/login", json={"email": "reviewer@example.com", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid email or password."

    login = client.post("/api/auth/login", json={"email": "reviewer@example.com", "password": "correct horse battery staple"})
    assert login.status_code == 200
    user_id = __import__("uuid").UUID(login.json()["user"]["id"])
    disabled_user = auth_store.users_by_id[user_id].model_copy(update={"status": AccountStatus.disabled})
    auth_store.users_by_id[user_id] = disabled_user
    auth_store.users_by_email[disabled_user.email] = disabled_user
    disabled = client.post("/api/auth/login", json={"email": "reviewer@example.com", "password": "correct horse battery staple"})
    assert disabled.status_code == 403

    active_user = auth_store.users_by_id[user_id].model_copy(update={"status": AccountStatus.active})
    auth_store.users_by_id[user_id] = active_user
    auth_store.users_by_email[active_user.email] = active_user
    expired_client = TestClient(app)
    relogin = expired_client.post("/api/auth/login", json={"email": "reviewer@example.com", "password": "correct horse battery staple"}).json()
    session_id = expired_client.cookies.get(auth_module.settings.session_cookie_name)
    session_store.sessions[session_id]["expires_at"] = (utc_now() - timedelta(seconds=1)).isoformat()
    assert expired_client.get("/api/auth/me").json()["demo_mode"] is True
    assert relogin["authenticated"] is True


def test_organization_isolation_blocks_guessed_run_ids() -> None:
    client_a, profile_a = register_client("alpha@example.com")
    client_b, _ = register_client("beta@example.com")
    csrf_a = profile_a["csrf_token"]

    created = client_a.post(
        "/api/runs",
        headers={"X-CSRF-Token": csrf_a},
        json={"goal": "reduce cost", "scenario_name": "safe"},
    )
    assert created.status_code == 201
    run_id = created.json()["id"]

    assert client_a.get("/api/runs").json()[0]["id"] == run_id
    assert client_b.get(f"/api/runs/{run_id}").status_code == 404
    assert client_b.get("/api/runs").json() == []


def test_reviewer_identity_is_derived_from_session_not_browser_payload() -> None:
    client, profile = register_client("varshan@example.com", role=OrganizationRole.reviewer)
    csrf = profile["csrf_token"]
    run = client.post(
        "/api/runs",
        headers={"X-CSRF-Token": csrf},
        json={"goal": "reduce cost", "scenario_name": "safe"},
    ).json()

    approved = client.post(
        f"/api/runs/{run['id']}/review",
        headers={"X-CSRF-Token": csrf},
        json={"action": "approve", "reviewer": "spoofed-admin@example.com", "expected_version": run["version"], "idempotency_key": "spoof-proof-approve"},
    )

    assert approved.status_code == 201
    review = approved.json()["human_reviews"][-1]
    assert review["reviewer"] == "Varshan"
    assert review["reviewer_email"] == "varshan@example.com"
    assert review["reviewer_role"] == "REVIEWER"
    assert review["organization_id"] == profile["organization"]["id"]


def test_viewer_cannot_call_hidden_approval_action_directly() -> None:
    owner_client, owner = register_client("owner2@example.com")
    viewer_client, _ = register_client("viewer@example.com", role=OrganizationRole.viewer)
    run = owner_client.post(
        "/api/runs",
        headers={"X-CSRF-Token": owner["csrf_token"]},
        json={"goal": "reduce cost", "scenario_name": "safe"},
    ).json()

    blocked = viewer_client.post(
        f"/api/runs/{run['id']}/review",
        headers={"X-CSRF-Token": viewer_client.get("/api/auth/me").json()["csrf_token"]},
        json={"action": "approve", "expected_version": run["version"], "idempotency_key": "viewer-blocked"},
    )

    assert blocked.status_code in {403, 404}


def test_owner_can_start_cloud_hunt() -> None:
    client, profile = register_client("cloud-owner@example.com")
    response = client.post("/api/cloud/hunts", headers={"X-CSRF-Token": profile["csrf_token"]}, json={"provider_scope": "aws", "inventory_source": "fixtures"})
    assert response.status_code == 200
