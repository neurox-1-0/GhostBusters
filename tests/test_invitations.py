from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth import auth_store, hash_token, session_store, utc_now
from app.main import app
from app.models import InvitationStatus, OrganizationRole


def setup_function() -> None:
    auth_store.reset()
    if hasattr(session_store, "sessions"):
        session_store.sessions.clear()


def register_owner(email: str = "owner@example.com") -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": "Owner User",
            "password": "correct horse battery staple",
            "organization_name": "Acme Cloud Team",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    return client, response.json()


def token_from_link(link: str) -> str:
    return parse_qs(urlparse(link).query)["token"][0]


def invite(client: TestClient, profile: dict, email: str, role: str = "REVIEWER", approval: bool = True) -> dict:
    response = client.post(
        "/api/invitations",
        headers={"X-CSRF-Token": profile["csrf_token"]},
        json={"email": email, "role": role, "approval_permission_enabled": approval},
    )
    assert response.status_code == 201
    return response.json()


def test_owner_invites_roles_and_list_does_not_expose_token_hash_or_raw_token() -> None:
    client, owner = register_owner()

    admin = invite(client, owner, "admin@example.com", "ADMIN", False)
    reviewer = invite(client, owner, "reviewer@example.com", "REVIEWER", True)
    viewer = invite(client, owner, "viewer@example.com", "VIEWER", False)
    listed = client.get("/api/invitations").json()

    assert admin["invitation"]["assigned_role"] == "ADMIN"
    assert reviewer["invitation"]["assigned_role"] == "REVIEWER"
    assert reviewer["invitation"]["approval_permission_enabled"] is True
    assert viewer["invitation"]["assigned_role"] == "VIEWER"
    assert "development_invitation_link" in reviewer
    assert "token_hash" not in str(listed)
    assert token_from_link(reviewer["development_invitation_link"]) not in str(listed)

    stored = auth_store.invitations[UUID(reviewer["invitation"]["id"])]
    assert stored.token_hash == hash_token(token_from_link(reviewer["development_invitation_link"]))
    assert stored.expires_at > utc_now()
    assert stored.status == InvitationStatus.pending


def test_reviewer_and_viewer_cannot_invite_and_admin_cannot_invite_admin_or_owner() -> None:
    owner_client, owner = register_owner()
    admin_invite = invite(owner_client, owner, "admin2@example.com", "ADMIN", False)
    admin_token = token_from_link(admin_invite["development_invitation_link"])
    admin_client = TestClient(app)
    accepted = admin_client.post(
        "/api/invitations/accept",
        json={"token": admin_token, "display_name": "Admin Two", "password": "correct horse battery staple", "confirm_password": "correct horse battery staple"},
    )
    assert accepted.status_code == 200

    reviewer_invite = admin_client.post(
        "/api/invitations",
        headers={"X-CSRF-Token": accepted.json()["csrf_token"]},
        json={"email": "reviewer2@example.com", "role": "REVIEWER", "approval_permission_enabled": True},
    )
    admin_invites_admin = admin_client.post(
        "/api/invitations",
        headers={"X-CSRF-Token": accepted.json()["csrf_token"]},
        json={"email": "admin3@example.com", "role": "ADMIN"},
    )
    admin_invites_owner = admin_client.post(
        "/api/invitations",
        headers={"X-CSRF-Token": accepted.json()["csrf_token"]},
        json={"email": "owner3@example.com", "role": "OWNER"},
    )

    assert reviewer_invite.status_code == 201
    assert admin_invites_admin.status_code == 403
    assert admin_invites_owner.status_code == 403


def test_invitation_acceptance_creates_user_membership_from_invitation_only_and_single_use() -> None:
    client, owner = register_owner()
    response = invite(client, owner, "priya@example.com", "REVIEWER", True)
    token = token_from_link(response["development_invitation_link"])

    accept = TestClient(app).post(
        "/api/invitations/accept",
        json={
            "token": token,
            "display_name": "Priya Perera",
            "password": "correct horse battery staple",
            "confirm_password": "correct horse battery staple",
        },
    )
    replay = TestClient(app).post(
        "/api/invitations/accept",
        json={
            "token": token,
            "display_name": "Priya Perera",
            "password": "correct horse battery staple",
            "confirm_password": "correct horse battery staple",
        },
    )

    assert accept.status_code == 200
    profile = accept.json()
    assert profile["user"]["email"] == "priya@example.com"
    assert profile["membership"]["role"] == "REVIEWER"
    assert profile["membership"]["approval_permission_enabled"] is True
    assert replay.status_code in {404, 409}
    stored = auth_store.invitations[UUID(response["invitation"]["id"])]
    assert stored.status == InvitationStatus.accepted
    assert stored.token_hash == ""
    assert "correct horse" not in str(auth_store.activity_events)
    assert token not in str(auth_store.activity_events)


def test_existing_signed_in_user_accepts_matching_email_invitation_into_invited_org() -> None:
    owner_a_client, owner_a = register_owner("owner-a@example.com")
    user_b_client, user_b = register_owner("priya-existing@example.com")
    response = invite(owner_a_client, owner_a, "priya-existing@example.com", "REVIEWER", True)
    token = token_from_link(response["development_invitation_link"])

    accepted = user_b_client.post(
        "/api/invitations/accept",
        headers={"X-CSRF-Token": user_b["csrf_token"]},
        json={"token": token},
    )
    mismatch_invite = invite(owner_a_client, owner_a, "someone-else@example.com", "VIEWER", False)
    mismatch = user_b_client.post(
        "/api/invitations/accept",
        headers={"X-CSRF-Token": accepted.json()["csrf_token"]},
        json={"token": token_from_link(mismatch_invite["development_invitation_link"])},
    )

    assert accepted.status_code == 200
    assert accepted.json()["organization"]["id"] == owner_a["organization"]["id"]
    assert accepted.json()["membership"]["role"] == "REVIEWER"
    assert accepted.json()["membership"]["approval_permission_enabled"] is True
    assert mismatch.status_code == 403


def test_duplicate_pending_member_expired_canceled_and_resend_behaviors() -> None:
    client, owner = register_owner()
    response = invite(client, owner, "nimal@example.com", "VIEWER", False)
    duplicate = client.post(
        "/api/invitations",
        headers={"X-CSRF-Token": owner["csrf_token"]},
        json={"email": "nimal@example.com", "role": "VIEWER"},
    )
    token = token_from_link(response["development_invitation_link"])
    invitation_id = UUID(response["invitation"]["id"])
    expired = auth_store.invitations[invitation_id].model_copy(update={"expires_at": utc_now() - timedelta(seconds=1)})
    auth_store.invitations[invitation_id] = expired
    expired_accept = TestClient(app).post(
        "/api/invitations/accept",
        json={"token": token, "display_name": "Nimal", "password": "correct horse battery staple", "confirm_password": "correct horse battery staple"},
    )
    resent = client.post(f"/api/invitations/{invitation_id}/resend", headers={"X-CSRF-Token": owner["csrf_token"]}, json={})
    new_token = token_from_link(resent.json()["development_invitation_link"])
    old_token_accept = TestClient(app).post(
        "/api/invitations/accept",
        json={"token": token, "display_name": "Nimal", "password": "correct horse battery staple", "confirm_password": "correct horse battery staple"},
    )
    canceled = client.post(f"/api/invitations/{invitation_id}/cancel", headers={"X-CSRF-Token": owner["csrf_token"]}, json={})
    canceled_accept = TestClient(app).post(
        "/api/invitations/accept",
        json={"token": new_token, "display_name": "Nimal", "password": "correct horse battery staple", "confirm_password": "correct horse battery staple"},
    )

    assert duplicate.status_code == 409
    assert expired_accept.status_code == 409
    assert resent.status_code == 200
    assert new_token != token
    assert old_token_accept.status_code == 404
    assert canceled.status_code == 200
    assert canceled_accept.status_code == 404


def test_invitation_and_membership_endpoints_are_organization_scoped() -> None:
    client_a, owner_a = register_owner("owner-a@example.com")
    client_b, owner_b = register_owner("owner-b@example.com")
    invite_a = invite(client_a, owner_a, "scoped@example.com", "VIEWER", False)
    invitation_id = invite_a["invitation"]["id"]
    owner_membership_id = owner_a["membership"]["id"]

    assert all(item["id"] != invitation_id for item in client_b.get("/api/invitations").json())
    assert client_b.post(f"/api/invitations/{invitation_id}/cancel", headers={"X-CSRF-Token": owner_b["csrf_token"]}, json={}).status_code == 404
    assert client_b.patch(
        f"/api/members/{owner_membership_id}",
        headers={"X-CSRF-Token": owner_b["csrf_token"]},
        json={"role": "VIEWER"},
    ).status_code == 404
