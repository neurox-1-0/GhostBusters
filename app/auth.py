"""Authentication, sessions, and authorization for GhostBusters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response
from redis import Redis
from redis.exceptions import RedisError

from app.models import (
    AccountStatus,
    CurrentUserResponse,
    DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
    Invitation,
    InvitationStatus,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
    User,
)
from app.settings import settings


WORKSPACE_READ = "workspace.read"
WORKSPACE_MANAGE = "workspace.manage"
MEMBERS_READ = "members.read"
MEMBERS_INVITE = "members.invite"
MEMBERS_MANAGE_ROLES = "members.manage_roles"
MEMBERS_CANCEL_INVITATION = "members.cancel_invitation"
MEMBERS_DISABLE = "members.disable"
OWNERSHIP_TRANSFER = "ownership.transfer"
INTEGRATIONS_READ = "integrations.read"
INTEGRATIONS_MANAGE = "integrations.manage"
POLICIES_READ = "policies.read"
POLICIES_MANAGE = "policies.manage"
PR_REVIEWS_READ = "pr_reviews.read"
GOALS_READ = "goals.read"
GOALS_RUN = "goals.run"
GOALS_CANCEL = "goals.cancel"
CLOUD_HUNTS_READ = "cloud_hunts.read"
CLOUD_HUNTS_RUN = "cloud_hunts.run"
APPROVALS_READ = "approvals.read"
APPROVALS_DECIDE = "approvals.decide"
APPROVALS_REJECT = "approvals.reject"
APPROVALS_REVOKE = "approvals.revoke"
APPROVALS_REOPEN = "approvals.reopen"
APPROVALS_REQUEST_EVIDENCE = "approvals.request_evidence"
APPROVALS_ADD_CONTEXT = "approvals.add_context"
APPROVALS_MODIFY = "approvals.modify"
AUDIT_READ = "audit.read"
ACTIVITY_READ = "activity.read"
ACTIVITY_EXPORT = "activity.export"
BILLING_READ = "billing.read"
BILLING_MANAGE = "billing.manage"

ROLE_LABELS = {
    OrganizationRole.owner: "Owner",
    OrganizationRole.admin: "Admin",
    OrganizationRole.reviewer: "Reviewer",
    OrganizationRole.viewer: "Viewer",
}

ACTIVITY_CATEGORY_LABELS = {
    "human_decision": "Human Decisions",
    "pr_review": "PR Reviews",
    "cloud_hunt": "Cloud Hunt",
    "member": "Members",
    "roles_access": "Roles and Access",
    "integration": "Integrations",
    "policy": "Policies",
    "authentication": "Authentication",
    "workspace": "Workspace",
    "system": "System",
}


def activity_category(event_type: str) -> str:
    value = event_type.lower()
    if any(token in value for token in ("human_decision", "approval", "rejection", "evidence", "context", "recommendation_modified", "preferred_action")):
        return "Human Decisions"
    if any(token in value for token in ("cloud_hunt", "candidate", "provider_inventory", "resource_normalized")):
        return "Cloud Hunt"
    if any(token in value for token in ("member", "invitation", "user_account")):
        return "Members"
    if any(token in value for token in ("role", "permission")):
        return "Roles and Access"
    if "integration" in value or "github" in value or "terraform" in value:
        return "Integrations"
    if "policy" in value:
        return "Policies"
    if any(token in value for token in ("login", "logout", "authentication")):
        return "Authentication"
    if any(token in value for token in ("workspace", "registered")):
        return "Workspace"
    return "System"


def activity_summary(event_type: str, details: dict[str, object]) -> str:
    if details.get("summary"):
        return str(details["summary"])
    return event_type.replace("_", " ").strip().capitalize()

ROLE_PERMISSIONS = {
    OrganizationRole.owner: {
        WORKSPACE_READ,
        WORKSPACE_MANAGE,
        MEMBERS_READ,
        MEMBERS_INVITE,
        MEMBERS_MANAGE_ROLES,
        MEMBERS_CANCEL_INVITATION,
        MEMBERS_DISABLE,
        OWNERSHIP_TRANSFER,
        INTEGRATIONS_READ,
        INTEGRATIONS_MANAGE,
        POLICIES_READ,
        POLICIES_MANAGE,
        PR_REVIEWS_READ,
        GOALS_READ,
        GOALS_RUN,
        GOALS_CANCEL,
        CLOUD_HUNTS_READ,
        CLOUD_HUNTS_RUN,
        APPROVALS_READ,
        APPROVALS_DECIDE,
        APPROVALS_REJECT,
        APPROVALS_REVOKE,
        APPROVALS_REOPEN,
        APPROVALS_REQUEST_EVIDENCE,
        APPROVALS_ADD_CONTEXT,
        APPROVALS_MODIFY,
        AUDIT_READ,
        ACTIVITY_READ,
        ACTIVITY_EXPORT,
        BILLING_READ,
        BILLING_MANAGE,
    },
    OrganizationRole.admin: {
        WORKSPACE_READ,
        MEMBERS_READ,
        MEMBERS_INVITE,
        MEMBERS_MANAGE_ROLES,
        MEMBERS_CANCEL_INVITATION,
        MEMBERS_DISABLE,
        INTEGRATIONS_READ,
        INTEGRATIONS_MANAGE,
        POLICIES_READ,
        POLICIES_MANAGE,
        PR_REVIEWS_READ,
        GOALS_READ,
        GOALS_RUN,
        GOALS_CANCEL,
        CLOUD_HUNTS_READ,
        CLOUD_HUNTS_RUN,
        APPROVALS_READ,
        APPROVALS_DECIDE,
        APPROVALS_REJECT,
        APPROVALS_REVOKE,
        APPROVALS_REOPEN,
        APPROVALS_REQUEST_EVIDENCE,
        APPROVALS_ADD_CONTEXT,
        APPROVALS_MODIFY,
        AUDIT_READ,
        ACTIVITY_READ,
        ACTIVITY_EXPORT,
    },
    OrganizationRole.reviewer: {
        WORKSPACE_READ,
        PR_REVIEWS_READ,
        GOALS_READ,
        CLOUD_HUNTS_READ,
        APPROVALS_READ,
        APPROVALS_DECIDE,
        APPROVALS_REJECT,
        APPROVALS_REVOKE,
        APPROVALS_REOPEN,
        APPROVALS_REQUEST_EVIDENCE,
        APPROVALS_ADD_CONTEXT,
        APPROVALS_MODIFY,
        AUDIT_READ,
    },
    OrganizationRole.viewer: {
        WORKSPACE_READ,
        PR_REVIEWS_READ,
        CLOUD_HUNTS_READ,
        APPROVALS_READ,
        AUDIT_READ,
    },
}


@dataclass(frozen=True, slots=True)
class Principal:
    user: User | None
    organization: Organization
    membership: OrganizationMembership
    permissions: frozenset[str]
    authenticated: bool
    demo_mode: bool = False
    csrf_token: str | None = None

    @property
    def organization_id(self) -> UUID:
        return self.organization.id

    @property
    def reviewer_name(self) -> str:
        if self.user is None:
            return "Demo Reviewer"
        return self.user.display_name

    def response(self) -> CurrentUserResponse:
        return CurrentUserResponse(
            authenticated=self.authenticated,
            user=self.user,
            organization=self.organization,
            membership=self.membership,
            role_label=ROLE_LABELS[self.membership.role],
            permissions=sorted(self.permissions),
            demo_mode=self.demo_mode,
            csrf_token=self.csrf_token,
        )


class SessionStore(Protocol):
    def create(self, principal_id: UUID, csrf_token: str, expires_at: datetime) -> str: ...
    def get(self, session_id: str) -> dict[str, str] | None: ...
    def revoke(self, session_id: str) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, str]] = {}

    def create(self, principal_id: UUID, csrf_token: str, expires_at: datetime) -> str:
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            "user_id": str(principal_id),
            "csrf_token": csrf_token,
            "expires_at": expires_at.isoformat(),
        }
        return session_id

    def get(self, session_id: str) -> dict[str, str] | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        if datetime.fromisoformat(session["expires_at"]) <= utc_now():
            self.sessions.pop(session_id, None)
            return None
        return dict(session)

    def revoke(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


class RedisSessionStore:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    def create(self, principal_id: UUID, csrf_token: str, expires_at: datetime) -> str:
        session_id = secrets.token_urlsafe(32)
        self.client.hset(
            self._key(session_id),
            mapping={"user_id": str(principal_id), "csrf_token": csrf_token, "expires_at": expires_at.isoformat()},
        )
        self.client.expire(self._key(session_id), self.ttl_seconds)
        return session_id

    def get(self, session_id: str) -> dict[str, str] | None:
        try:
            data = self.client.hgetall(self._key(session_id))
        except RedisError:
            return None
        if not data:
            return None
        if datetime.fromisoformat(data["expires_at"]) <= utc_now():
            self.revoke(session_id)
            return None
        return dict(data)

    def revoke(self, session_id: str) -> None:
        self.client.delete(self._key(session_id))

    @staticmethod
    def _key(session_id: str) -> str:
        return f"ghostbusters:session:{session_id}"


class AuthStore:
    def __init__(self, persistence_path: Path | None = None) -> None:
        self.persistence_path = persistence_path if persistence_path is not None else settings.auth_persistence_path
        self.users_by_id: dict[UUID, User] = {}
        self.users_by_email: dict[str, User] = {}
        self.password_hashes: dict[UUID, str] = {}
        self.organizations: dict[UUID, Organization] = {}
        self.memberships: dict[UUID, OrganizationMembership] = {}
        self.invitations: dict[UUID, Invitation] = {}
        self.activity_events: list[dict[str, object]] = []
        self.login_failures: dict[str, list[datetime]] = {}
        self._ensure_development_workspace()
        self._load_persistent_state()

    def reset(self) -> None:
        try:
            self.persistence_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.__init__(self.persistence_path)

    def _load_persistent_state(self) -> None:
        if not self.persistence_path.exists():
            return
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            for item in payload.get("organizations", []):
                organization = Organization.model_validate(item)
                self.organizations[organization.id] = organization
            for item in payload.get("users", []):
                user = User.model_validate(item)
                self.users_by_id[user.id] = user
                self.users_by_email[user.email] = user
            self.password_hashes.update({UUID(key): value for key, value in payload.get("password_hashes", {}).items()})
            for item in payload.get("memberships", []):
                membership = OrganizationMembership.model_validate(item)
                self.memberships[membership.id] = membership
            for item in payload.get("invitations", []):
                invitation = Invitation.model_validate(item)
                self.invitations[invitation.id] = invitation
            self.activity_events = []
            for raw_event in payload.get("activity_events", []):
                event = dict(raw_event)
                for key in ("id", "organization_id", "actor_user_id"):
                    if event.get(key):
                        try:
                            event[key] = UUID(str(event[key]))
                        except ValueError:
                            pass
                if isinstance(event.get("created_at"), str):
                    event["created_at"] = datetime.fromisoformat(event["created_at"])
                self.activity_events.append(event)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A damaged local snapshot must not prevent the application from booting.
            return

    @staticmethod
    def _json_default(value):
        if isinstance(value, (UUID, datetime)):
            return str(value)
        if hasattr(value, "value"):
            return value.value
        raise TypeError(f"Cannot serialize {type(value).__name__}")

    def _persist(self) -> None:
        payload = {
            "organizations": [item.model_dump(mode="json") for item in self.organizations.values()],
            "users": [item.model_dump(mode="json") for item in self.users_by_id.values()],
            "password_hashes": {str(key): value for key, value in self.password_hashes.items()},
            "memberships": [item.model_dump(mode="json") for item in self.memberships.values()],
            "invitations": [item.model_dump(mode="json") for item in self.invitations.values()],
            "activity_events": self.activity_events,
        }
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.persistence_path.with_suffix(self.persistence_path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, default=self._json_default), encoding="utf-8")
            temporary.replace(self.persistence_path)
        except OSError:
            # Local persistence is best-effort; configured database deployments use
            # their durable auth store and should not fail a request on a file error.
            return

    def register_owner(self, email: str, display_name: str, password: str, organization_name: str, timezone_name: str, slug: str | None = None) -> tuple[User, Organization, OrganizationMembership]:
        normalized = normalize_email(email)
        if normalized in self.users_by_email:
            raise HTTPException(status_code=409, detail="Account already exists.")
        now = utc_now()
        user = User(id=uuid4(), email=normalized, display_name=display_name.strip(), created_at=now, updated_at=now)
        organization = Organization(
            id=uuid4(),
            name=organization_name.strip(),
            slug=slugify(slug or organization_name),
            timezone=timezone_name or "UTC",
            created_at=now,
            updated_at=now,
        )
        membership = OrganizationMembership(
            id=uuid4(),
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationRole.owner,
            approval_permission_enabled=False,
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        self.password_hashes[user.id] = hash_password(password)
        self.organizations[organization.id] = organization
        self.memberships[membership.id] = membership
        self.record_activity(organization.id, "user_registered", user.id, {"email": user.email})
        self.record_activity(organization.id, "workspace_created", user.id, {"name": organization.name})
        return user, organization, membership

    def authenticate(self, email: str, password: str, remote_addr: str = "") -> tuple[User, Organization, OrganizationMembership]:
        key = f"{normalize_email(email)}:{remote_addr}"
        failures = [item for item in self.login_failures.get(key, []) if item > utc_now() - timedelta(seconds=settings.login_rate_limit_window_seconds)]
        self.login_failures[key] = failures
        if len(failures) >= settings.login_rate_limit_attempts:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        user = self.users_by_email.get(normalize_email(email))
        if user is None or not verify_password(password, self.password_hashes.get(user.id, "")):
            failures.append(utc_now())
            self.login_failures[key] = failures
            if user is not None:
                self.record_activity(self.membership_for_user(user.id).organization_id, "login_failed", user.id, {})
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if user.status != AccountStatus.active:
            raise HTTPException(status_code=403, detail="Account is disabled.")
        membership = self.membership_for_user(user.id)
        organization = self.organizations[membership.organization_id]
        user = user.model_copy(update={"last_login_at": utc_now(), "updated_at": utc_now()})
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        self.record_activity(organization.id, "login_succeeded", user.id, {})
        return user, organization, membership

    def membership_for_user(self, user_id: UUID, organization_id: UUID | None = None) -> OrganizationMembership:
        membership = next(
            (
                item
                for item in self.memberships.values()
                if item.user_id == user_id and (organization_id is None or item.organization_id == organization_id)
            ),
            None,
        )
        if membership is None or membership.status != MembershipStatus.active:
            raise HTTPException(status_code=403, detail="Workspace membership is not active.")
        return membership

    def invite(self, principal: Principal, email: str, role: OrganizationRole, approval_permission_enabled: bool, note: str | None = None) -> tuple[Invitation, str]:
        normalized = normalize_email(email)
        if not is_valid_email(normalized):
            raise HTTPException(status_code=422, detail="Enter a valid email address.")
        self._ensure_invitable_role(principal, role)
        if approval_permission_enabled and role == OrganizationRole.viewer:
            raise HTTPException(status_code=422, detail="Approval permission is not available for Viewer.")
        if self._active_membership_for_email(principal.organization_id, normalized):
            raise HTTPException(status_code=409, detail="This email is already an active member.")
        if self._pending_invitation_for_email(principal.organization_id, normalized):
            raise HTTPException(status_code=409, detail="An invitation is already pending for this email.")
        now = utc_now()
        token = new_invitation_token()
        invitation = Invitation(
            id=uuid4(),
            organization_id=principal.organization_id,
            email=normalized,
            normalized_email=normalized,
            role=role,
            approval_permission_enabled=approval_permission_enabled,
            token_hash=hash_token(token),
            status=InvitationStatus.pending,
            expires_at=now + timedelta(hours=settings.invitation_expiry_hours),
            last_sent_at=now,
            invited_by_user_id=principal.user.id if principal.user else principal.membership.user_id,
            invited_by_membership_id=principal.membership.id,
            created_at=now,
            updated_at=now,
            metadata={"note": note} if note else {},
        )
        self.invitations[invitation.id] = invitation
        self.record_activity(principal.organization_id, "invitation_created", principal.user.id if principal.user else None, {"email": invitation.email, "role": ROLE_LABELS[role]})
        self.record_activity(principal.organization_id, "invitation_link_generated_development", principal.user.id if principal.user else None, {"email": invitation.email})
        return invitation, token

    def list_invitations(self, principal: Principal) -> list[Invitation]:
        now = utc_now()
        output = []
        for invitation in self.invitations.values():
            if invitation.organization_id != principal.organization_id:
                continue
            if invitation.status == InvitationStatus.pending and invitation.expires_at <= now:
                invitation = invitation.model_copy(update={"status": InvitationStatus.expired, "updated_at": now})
                self.invitations[invitation.id] = invitation
                self.record_activity(invitation.organization_id, "invitation_expired", None, {"email": invitation.email})
            output.append(invitation)
        return sorted(output, key=lambda item: item.created_at, reverse=True)

    def validate_invitation_token(self, token: str) -> Invitation:
        invitation = self._invitation_for_token(token)
        if invitation is None:
            raise HTTPException(status_code=404, detail="Invitation is invalid.")
        invitation = self._refresh_invitation_status(invitation)
        if invitation.status != InvitationStatus.pending:
            raise HTTPException(status_code=409, detail=f"Invitation is {invitation.status.value.lower()}.")
        return invitation

    def accept_invitation(
        self,
        token: str,
        display_name: str | None = None,
        password: str | None = None,
        confirm_password: str | None = None,
        principal: Principal | None = None,
    ) -> tuple[User, Organization, OrganizationMembership]:
        invitation = self.validate_invitation_token(token)
        now = utc_now()
        user = None
        if principal and principal.authenticated and principal.user:
            if normalize_email(principal.user.email) != invitation.normalized_email:
                raise HTTPException(status_code=403, detail="This invitation was sent to another email address. Sign in with the invited account.")
            user = principal.user
        else:
            user = self.users_by_email.get(invitation.normalized_email)
            if user is None:
                if not display_name:
                    raise HTTPException(status_code=422, detail="Display name is required.")
                if not password or password != confirm_password:
                    raise HTTPException(status_code=422, detail="Passwords do not match.")
                user = User(id=uuid4(), email=invitation.normalized_email, display_name=display_name.strip(), created_at=now, updated_at=now)
                self.users_by_id[user.id] = user
                self.users_by_email[user.email] = user
                self.password_hashes[user.id] = hash_password(password)
                self.record_activity(invitation.organization_id, "user_account_created_through_invitation", user.id, {"email": user.email})
            elif password or display_name:
                # Existing users sign in with their existing password instead of creating a new one.
                raise HTTPException(status_code=409, detail="An account already exists. Sign in instead to accept this invitation.")
        if self._membership_for_user_org(user.id, invitation.organization_id):
            raise HTTPException(status_code=409, detail="This account is already a member of the organization.")
        membership = OrganizationMembership(
            id=uuid4(),
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
            approval_permission_enabled=invitation.approval_permission_enabled,
            status=MembershipStatus.active,
            invited_by_user_id=invitation.invited_by_user_id,
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        self.memberships[membership.id] = membership
        accepted = invitation.model_copy(update={"status": InvitationStatus.accepted, "accepted_at": now, "updated_at": now, "token_hash": ""})
        self.invitations[accepted.id] = accepted
        self.record_activity(invitation.organization_id, "invitation_accepted", user.id, {"email": user.email})
        self.record_activity(invitation.organization_id, "membership_activated", user.id, {"role": ROLE_LABELS[membership.role]})
        return user, self.organizations[invitation.organization_id], membership

    def resend_invitation(self, principal: Principal, invitation_id: UUID) -> tuple[Invitation, str]:
        invitation = self._scoped_invitation(principal, invitation_id)
        if invitation.status not in {InvitationStatus.pending, InvitationStatus.expired}:
            raise HTTPException(status_code=409, detail="Only pending or expired invitations can be resent.")
        self._ensure_invitable_role(principal, invitation.role)
        now = utc_now()
        token = new_invitation_token()
        updated = invitation.model_copy(update={
            "status": InvitationStatus.pending,
            "token_hash": hash_token(token),
            "expires_at": now + timedelta(hours=settings.invitation_expiry_hours),
            "updated_at": now,
            "last_sent_at": now,
            "resend_count": invitation.resend_count + 1,
        })
        self.invitations[updated.id] = updated
        self.record_activity(principal.organization_id, "invitation_resent", principal.user.id if principal.user else None, {"email": updated.email})
        return updated, token

    def cancel_invitation(self, principal: Principal, invitation_id: UUID) -> Invitation:
        invitation = self._scoped_invitation(principal, invitation_id)
        if invitation.status != InvitationStatus.pending:
            raise HTTPException(status_code=409, detail="Only pending invitations can be canceled.")
        now = utc_now()
        updated = invitation.model_copy(update={"status": InvitationStatus.canceled, "canceled_at": now, "updated_at": now, "token_hash": ""})
        self.invitations[updated.id] = updated
        self.record_activity(principal.organization_id, "invitation_canceled", principal.user.id if principal.user else None, {"email": updated.email})
        return updated

    def change_role(self, principal: Principal, membership_id: UUID, role: OrganizationRole, approval_permission_enabled: bool | None) -> OrganizationMembership:
        membership = self.memberships.get(membership_id)
        if membership is None or membership.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Membership not found.")
        if membership.user_id == principal.membership.user_id and role == OrganizationRole.owner and principal.membership.role != OrganizationRole.owner:
            raise HTTPException(status_code=403, detail="Self-elevation is not allowed.")
        if membership.role == OrganizationRole.owner and role != OrganizationRole.owner and self._active_owner_count(principal.organization_id) <= 1:
            raise HTTPException(status_code=409, detail="The last active Owner cannot be changed to another role.")
        if role == OrganizationRole.owner and principal.membership.role != OrganizationRole.owner:
            raise HTTPException(status_code=403, detail="Only an Owner can assign Owner role.")
        updated = membership.model_copy(
            update={
                "role": role,
                "approval_permission_enabled": membership.approval_permission_enabled if approval_permission_enabled is None else approval_permission_enabled,
                "updated_at": utc_now(),
            }
        )
        self.memberships[updated.id] = updated
        self.record_activity(principal.organization_id, "member_role_changed", principal.user.id if principal.user else None, {"membership_id": str(updated.id), "role": role})
        return updated

    def disable_member(self, principal: Principal, membership_id: UUID) -> OrganizationMembership:
        membership = self.memberships.get(membership_id)
        if membership is None or membership.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Membership not found.")
        if membership.role == OrganizationRole.owner and self._active_owner_count(principal.organization_id) <= 1:
            raise HTTPException(status_code=409, detail="The last active Owner cannot be disabled.")
        updated = membership.model_copy(update={"status": MembershipStatus.disabled, "updated_at": utc_now()})
        self.memberships[updated.id] = updated
        self.record_activity(principal.organization_id, "member_disabled", principal.user.id if principal.user else None, {"membership_id": str(updated.id)})
        return updated

    def reactivate_member(self, principal: Principal, membership_id: UUID) -> OrganizationMembership:
        membership = self.memberships.get(membership_id)
        if membership is None or membership.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Membership not found.")
        updated = membership.model_copy(update={"status": MembershipStatus.active, "updated_at": utc_now()})
        self.memberships[updated.id] = updated
        self.record_activity(principal.organization_id, "member_reactivated", principal.user.id if principal.user else None, {"membership_id": str(updated.id)})
        return updated

    def principal_for_user(self, user_id: UUID, csrf_token: str | None = None, organization_id: UUID | None = None) -> Principal:
        user = self.users_by_id.get(user_id)
        if user is None or user.status != AccountStatus.active:
            raise HTTPException(status_code=401, detail="Authentication required.")
        membership = self.membership_for_user(user.id, organization_id)
        organization = self.organizations[membership.organization_id]
        return make_principal(user, organization, membership, csrf_token=csrf_token)

    def demo_principal(self) -> Principal:
        membership = self.membership_for_user(DEMO_USER_ID, DEFAULT_DEVELOPMENT_ORGANIZATION_ID)
        return make_principal(None, self.organizations[DEFAULT_DEVELOPMENT_ORGANIZATION_ID], membership, authenticated=False, demo_mode=True)

    def record_activity(
        self,
        organization_id: UUID,
        event_type: str,
        actor_user_id: UUID | None,
        details: dict[str, object],
        *,
        actor_type: str | None = None,
        category: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | UUID | None = None,
        target_display_name: str | None = None,
        result: str = "success",
        summary: str | None = None,
        correlation_id: str | None = None,
        related_case_id: str | UUID | None = None,
        related_run_id: str | UUID | None = None,
    ) -> None:
        """Append a workspace event with actor and target snapshots.

        This intentionally has no update or delete counterpart. Older producers may
        still pass event_type/details only; those records are normalized here.
        """
        now = utc_now()
        user = self.users_by_id.get(actor_user_id) if actor_user_id else None
        membership = next((item for item in self.memberships.values() if item.user_id == actor_user_id and item.organization_id == organization_id), None) if actor_user_id else None
        inferred_category = category or activity_category(event_type)
        inferred_action = action or event_type
        inferred_target_type = target_type or ("case" if details.get("case_id") else "workspace")
        inferred_target_id = target_id or details.get("case_id") or details.get("run_id")
        inferred_summary = summary or activity_summary(event_type, details)
        self.activity_events.append({
            "id": uuid4(),
            "organization_id": organization_id,
            "actor_type": actor_type or ("User" if actor_user_id else "System"),
            "actor_user_id": actor_user_id,
            "actor_display_name": user.display_name if user else ("System" if not actor_user_id else "Unknown user"),
            "actor_role_snapshot": ROLE_LABELS.get(membership.role) if membership else ("System" if not actor_user_id else None),
            "category": inferred_category,
            "action": inferred_action,
            "target_type": inferred_target_type,
            "target_id": str(inferred_target_id) if inferred_target_id else None,
            "target_display_name": target_display_name or str(details.get("target_display_name") or inferred_target_id or "Workspace"),
            "result": result,
            "summary": inferred_summary,
            "metadata": dict(details),
            "correlation_id": correlation_id or details.get("correlation_id"),
            "related_case_id": str(related_case_id or details.get("case_id")) if (related_case_id or details.get("case_id")) else None,
            "related_run_id": str(related_run_id or details.get("run_id")) if (related_run_id or details.get("run_id")) else None,
            "created_at": now,
            # Compatibility for the existing overview/test producers.
            "event_type": event_type,
            "details": dict(details),
        })
        self._persist()

    def _ensure_development_workspace(self) -> None:
        now = utc_now()
        organization = Organization(
            id=DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
            name="GhostBusters Development",
            slug="ghostbusters-dev",
            status=OrganizationStatus.active,
            timezone="UTC",
            created_at=now,
            updated_at=now,
        )
        user = User(id=DEMO_USER_ID, email="demo@ghostbusters.local", display_name="Demo Reviewer", created_at=now, updated_at=now)
        membership = OrganizationMembership(
            id=DEMO_MEMBERSHIP_ID,
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationRole.reviewer,
            approval_permission_enabled=True,
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        self.organizations[organization.id] = organization
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        self.password_hashes[user.id] = hash_password("development-only-password")
        self.memberships[membership.id] = membership

    def _ensure_invitable_role(self, principal: Principal, role: OrganizationRole) -> None:
        if role == OrganizationRole.owner:
            raise HTTPException(status_code=403, detail="Owner invitations are not supported in this flow.")
        if principal.membership.role == OrganizationRole.admin and role == OrganizationRole.admin:
            raise HTTPException(status_code=403, detail="Admin invitation requires explicit Owner authority.")

    def _active_membership_for_email(self, organization_id: UUID, email: str) -> OrganizationMembership | None:
        user = self.users_by_email.get(email)
        if user is None:
            return None
        membership = self._membership_for_user_org(user.id, organization_id)
        return membership if membership and membership.status == MembershipStatus.active else None

    def _membership_for_user_org(self, user_id: UUID, organization_id: UUID) -> OrganizationMembership | None:
        return next((item for item in self.memberships.values() if item.user_id == user_id and item.organization_id == organization_id), None)

    def _pending_invitation_for_email(self, organization_id: UUID, email: str) -> Invitation | None:
        now = utc_now()
        return next((item for item in self.invitations.values() if item.organization_id == organization_id and item.normalized_email == email and item.status == InvitationStatus.pending and item.expires_at > now), None)

    def _scoped_invitation(self, principal: Principal, invitation_id: UUID) -> Invitation:
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Invitation not found.")
        return self._refresh_invitation_status(invitation)

    def _invitation_for_token(self, token: str) -> Invitation | None:
        token_hash = hash_token(token)
        return next((item for item in self.invitations.values() if item.token_hash and hmac.compare_digest(item.token_hash, token_hash)), None)

    def _refresh_invitation_status(self, invitation: Invitation) -> Invitation:
        if invitation.status == InvitationStatus.pending and invitation.expires_at <= utc_now():
            updated = invitation.model_copy(update={"status": InvitationStatus.expired, "updated_at": utc_now()})
            self.invitations[updated.id] = updated
            self.record_activity(updated.organization_id, "invitation_expired", None, {"email": updated.email})
            return updated
        return invitation

    def _active_owner_count(self, organization_id: UUID) -> int:
        return sum(1 for item in self.memberships.values() if item.organization_id == organization_id and item.role == OrganizationRole.owner and item.status == MembershipStatus.active)


DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
DEMO_MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000003")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"workspace-{secrets.token_hex(3)}"


def new_invitation_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return "scrypt$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(digest).decode("ascii")


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def make_principal(
    user: User | None,
    organization: Organization,
    membership: OrganizationMembership,
    authenticated: bool = True,
    demo_mode: bool = False,
    csrf_token: str | None = None,
) -> Principal:
    permissions = set(ROLE_PERMISSIONS[membership.role])
    if membership.approval_permission_enabled:
        permissions.update({
            APPROVALS_DECIDE,
            APPROVALS_REJECT,
            APPROVALS_REVOKE,
            APPROVALS_REOPEN,
            APPROVALS_REQUEST_EVIDENCE,
            APPROVALS_ADD_CONTEXT,
            APPROVALS_MODIFY,
        })
    if demo_mode:
        permissions.add(CLOUD_HUNTS_RUN)
        permissions.update({GOALS_READ, GOALS_RUN, GOALS_CANCEL})
    return Principal(
        user=user,
        organization=organization,
        membership=membership,
        permissions=frozenset(permissions),
        authenticated=authenticated,
        demo_mode=demo_mode,
        csrf_token=csrf_token,
    )


def build_session_store() -> SessionStore:
    if settings.redis_url:
        return RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)
    return InMemorySessionStore()


auth_store = AuthStore()
session_store = build_session_store()


def set_session_cookies(response: Response, session_id: str, csrf_token: str) -> None:
    secure = settings.auth_required
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(settings.csrf_cookie_name, csrf_token, httponly=False, secure=secure, samesite="lax", max_age=settings.session_ttl_seconds)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)


def current_principal(request: Request) -> Principal:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        session = session_store.get(session_id)
        if session:
            return auth_store.principal_for_user(UUID(session["user_id"]), csrf_token=session.get("csrf_token"))
    if settings.demo_mode_enabled and not settings.auth_required:
        return auth_store.demo_principal()
    raise HTTPException(status_code=401, detail="Authentication required.")


def csrf_protect(request: Request, principal: Principal) -> None:
    if not principal.authenticated or request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = principal.csrf_token
    supplied = request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="CSRF token is missing or invalid.")


def require_permission(principal: Principal, permission: str) -> None:
    if permission in principal.permissions:
        return
    auth_store.record_activity(principal.organization_id, "permission_denied", principal.user.id if principal.user else None, {"permission": permission})
    raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
