"""Authentication, sessions, and authorization for GhostBusters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
INTEGRATIONS_READ = "integrations.read"
INTEGRATIONS_MANAGE = "integrations.manage"
POLICIES_READ = "policies.read"
POLICIES_MANAGE = "policies.manage"
PR_REVIEWS_READ = "pr_reviews.read"
CLOUD_HUNTS_READ = "cloud_hunts.read"
CLOUD_HUNTS_RUN = "cloud_hunts.run"
APPROVALS_READ = "approvals.read"
APPROVALS_DECIDE = "approvals.decide"
AUDIT_READ = "audit.read"
ACTIVITY_READ = "activity.read"
BILLING_READ = "billing.read"
BILLING_MANAGE = "billing.manage"

ROLE_LABELS = {
    OrganizationRole.owner: "Owner",
    OrganizationRole.admin: "Admin",
    OrganizationRole.reviewer: "Reviewer",
    OrganizationRole.viewer: "Viewer",
}

ROLE_PERMISSIONS = {
    OrganizationRole.owner: {
        WORKSPACE_READ,
        WORKSPACE_MANAGE,
        MEMBERS_READ,
        MEMBERS_INVITE,
        MEMBERS_MANAGE_ROLES,
        INTEGRATIONS_READ,
        INTEGRATIONS_MANAGE,
        POLICIES_READ,
        POLICIES_MANAGE,
        PR_REVIEWS_READ,
        CLOUD_HUNTS_READ,
        APPROVALS_READ,
        AUDIT_READ,
        ACTIVITY_READ,
        BILLING_READ,
        BILLING_MANAGE,
    },
    OrganizationRole.admin: {
        WORKSPACE_READ,
        MEMBERS_READ,
        MEMBERS_INVITE,
        MEMBERS_MANAGE_ROLES,
        INTEGRATIONS_READ,
        INTEGRATIONS_MANAGE,
        POLICIES_READ,
        POLICIES_MANAGE,
        PR_REVIEWS_READ,
        CLOUD_HUNTS_READ,
        CLOUD_HUNTS_RUN,
        APPROVALS_READ,
        AUDIT_READ,
        ACTIVITY_READ,
    },
    OrganizationRole.reviewer: {
        WORKSPACE_READ,
        PR_REVIEWS_READ,
        CLOUD_HUNTS_READ,
        APPROVALS_READ,
        APPROVALS_DECIDE,
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
    def __init__(self) -> None:
        self.users_by_id: dict[UUID, User] = {}
        self.users_by_email: dict[str, User] = {}
        self.password_hashes: dict[UUID, str] = {}
        self.organizations: dict[UUID, Organization] = {}
        self.memberships: dict[UUID, OrganizationMembership] = {}
        self.invitations: dict[UUID, Invitation] = {}
        self.activity_events: list[dict[str, object]] = []
        self.login_failures: dict[str, list[datetime]] = {}
        self._ensure_development_workspace()

    def reset(self) -> None:
        self.__init__()

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

    def invite(self, principal: Principal, email: str, role: OrganizationRole, approval_permission_enabled: bool) -> Invitation:
        if role == OrganizationRole.owner and principal.membership.role != OrganizationRole.owner:
            raise HTTPException(status_code=403, detail="Only an Owner can assign Owner role.")
        now = utc_now()
        invitation = Invitation(
            id=uuid4(),
            organization_id=principal.organization_id,
            email=normalize_email(email),
            role=role,
            approval_permission_enabled=approval_permission_enabled,
            expires_at=now + timedelta(days=7),
            invited_by_user_id=principal.user.id if principal.user else principal.membership.user_id,
            created_at=now,
        )
        self.invitations[invitation.id] = invitation
        self.record_activity(principal.organization_id, "user_invited", principal.user.id if principal.user else None, {"email": invitation.email, "role": role})
        return invitation

    def change_role(self, principal: Principal, membership_id: UUID, role: OrganizationRole, approval_permission_enabled: bool | None) -> OrganizationMembership:
        membership = self.memberships.get(membership_id)
        if membership is None or membership.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Membership not found.")
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

    def principal_for_user(self, user_id: UUID, csrf_token: str | None = None) -> Principal:
        user = self.users_by_id.get(user_id)
        if user is None or user.status != AccountStatus.active:
            raise HTTPException(status_code=401, detail="Authentication required.")
        membership = self.membership_for_user(user.id)
        organization = self.organizations[membership.organization_id]
        return make_principal(user, organization, membership, csrf_token=csrf_token)

    def demo_principal(self) -> Principal:
        membership = self.membership_for_user(DEMO_USER_ID, DEFAULT_DEVELOPMENT_ORGANIZATION_ID)
        return make_principal(None, self.organizations[DEFAULT_DEVELOPMENT_ORGANIZATION_ID], membership, authenticated=False, demo_mode=True)

    def record_activity(self, organization_id: UUID, event_type: str, actor_user_id: UUID | None, details: dict[str, object]) -> None:
        self.activity_events.append(
            {
                "organization_id": organization_id,
                "event_type": event_type,
                "actor_user_id": actor_user_id,
                "details": details,
                "created_at": utc_now(),
            }
        )

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


DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
DEMO_MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000003")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"workspace-{secrets.token_hex(3)}"


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
        permissions.add(APPROVALS_DECIDE)
    if demo_mode:
        permissions.add(CLOUD_HUNTS_RUN)
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
