"""FastAPI application entrypoint for GhostBusters."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.models import (
    AskGhostBustersRequest, AskGhostBustersResponse,
    DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
    AuditEvent,
    ChangeMemberRoleRequest, CloudHuntRequest, CurrentUserResponse, HealthResponse,
    GoalContextRequest, GoalCreateRequest, GoalEvidenceRetryRequest,
    AWSIntegrationConfigRequest,
    GitHubIntegrationConfigRequest,
    JiraIntegrationConfigRequest, JiraContextRequest,
    CloudHuntScheduleRequest, CloudHuntScheduleToggleRequest,
    OutcomeStartRequest, OutcomeObservationRequest, OutcomeCompleteRequest, OutcomeReopenRequest,
    OrganizationUpdateRequest,
    DemoResetRequest,
    HumanReviewRequest, InvitationAcceptRequest, InvitationValidateResponse,
    InviteMemberRequest, LoginRequest, RegisterRequest, ReviewCaseActionRequest,
    ReviewCase, StartRunRequest, WorkflowRun,
)
from app.settings import settings, validate_startup_settings
from app.auth import (
    APPROVALS_DECIDE,
    APPROVALS_REJECT,
    APPROVALS_REVOKE,
    APPROVALS_REOPEN,
    APPROVALS_REQUEST_EVIDENCE,
    APPROVALS_ADD_CONTEXT,
    APPROVALS_MODIFY,
    APPROVALS_READ,
    ACTIVITY_READ,
    AUDIT_READ,
    CLOUD_HUNTS_READ,
    CLOUD_HUNTS_RUN,
    CLOUD_HUNTS_SCHEDULE_READ,
    CLOUD_HUNTS_SCHEDULE_MANAGE,
    MEMBERS_INVITE,
    MEMBERS_READ,
    MEMBERS_CANCEL_INVITATION,
    MEMBERS_DISABLE,
    MEMBERS_MANAGE_ROLES,
    PR_REVIEWS_READ,
    GOALS_READ,
    GOALS_RUN,
    GOALS_CANCEL,
    INTEGRATIONS_AWS_READ,
    INTEGRATIONS_AWS_MANAGE,
    INTEGRATIONS_GITHUB_READ,
    INTEGRATIONS_GITHUB_MANAGE,
    INTEGRATIONS_JIRA_READ,
    INTEGRATIONS_JIRA_MANAGE,
    BUSINESS_CONTEXT_READ,
    OUTCOMES_READ, OUTCOMES_START, OUTCOMES_REFRESH, OUTCOMES_COMPLETE, OUTCOMES_REOPEN,
    OVERVIEW_READ,
    WORKSPACE_MANAGE,
    REPOSITORY_CONTEXT_READ,
    WORKSPACE_READ,
    Principal,
    ROLE_LABELS,
    auth_store,
    clear_session_cookies,
    csrf_protect,
    current_principal,
    require_permission,
    session_store,
    set_session_cookies,
    utc_now,
)
from core.audit import append_audit_event
from core.decision_events import decision_event_store, normalized_fingerprint
from core.run_store import RunNotFoundError
from core.storage_factory import build_webhook_deduplicator
from core.workflow_service import (
    ScenarioNotFoundError,
    WorkflowConflictError,
    list_scenarios,
    workflow_service,
)
from core.cloud_hunt_service import CloudHuntConflictError, CloudHuntNotFoundError, cloud_hunt_service
from core.aws_integration import aws_integration_store
from core.github_integration import github_integration_store
from core.jira_integration import jira_integration_store
from core.assistant_service import AssistantValidationError, assistant_service
from integrations.github_client import GitHubAPIError
from integrations.github_app import GitHubAppClient, github_app_state
from integrations.github_webhook import repository_allowed, verify_signature
from integrations.terraform_runner import TerraformAnalysisError, parse_github_terraform_change, select_terraform_files
from integrations.cloud_adapters import RealAWSCloudAdapter
from integrations.cloud_registry import CloudProviderRegistry
from integrations.github_context import GitHubContextAdapter
from integrations.jira_client import JiraAPIError, JiraClient
from integrations.jira_context import JiraContextAdapter, detect_jira_github_conflict
from core.cloud_hunt_scheduler import CloudHuntScheduler, schedule_store
from core.outcome_verification import OutcomeConflictError, OutcomeNotFoundError, outcome_store, outcome_verification_service
from core.rate_limit import rate_limiter
from core.evidence_utils import verified_pricing_item


logger = logging.getLogger(__name__)

app = FastAPI(title="GhostBusters", version="0.1.0")
validate_startup_settings()
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Correlation-ID", "X-GitHub-Event", "X-GitHub-Delivery", "X-Hub-Signature-256"],
    )
static_path = Path(__file__).resolve().parent.parent / settings.static_dir
webhook_deduplicator = build_webhook_deduplicator()
app.mount("/static", StaticFiles(directory=static_path), name="static")
cloud_hunt_service.workflow_service = workflow_service
assistant_service.workflow = workflow_service
assistant_service.cloud_hunt = cloud_hunt_service


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness() -> JSONResponse:
    database = "in_memory"; redis = "not_configured"; errors: list[str] = []
    if settings.app_env == "production" and not settings.database_url:
        errors.append("database_configuration"); database = "unavailable"
    if settings.database_url:
        try:
            import psycopg
            with psycopg.connect(settings.database_url) as connection:
                connection.execute("SELECT 1")
            database = "ready"
        except Exception:
            database = "unavailable"; errors.append("database")
    if settings.app_env == "production" and not settings.redis_url:
        errors.append("redis_configuration"); redis = "unavailable"
    if settings.redis_url:
        try:
            from redis import Redis
            Redis.from_url(settings.redis_url).ping()
            redis = "ready"
        except Exception:
            redis = "unavailable"; errors.append("redis")
    status = "ready" if not errors else "not_ready"
    payload = {"status": status, "database": database, "redis": redis, "errors": errors,
               "scheduled_execution_enabled": settings.cloud_hunt_schedule_enabled,
               "scheduled_execution_message": "Scheduled execution is enabled." if settings.cloud_hunt_schedule_enabled else "Scheduled execution is disabled in this deployment. Manual Run Now remains available."}
    return JSONResponse(status_code=200 if status == "ready" else 503, content=payload)


@app.get("/")
def home() -> FileResponse:
    index_path = static_path / "index.html"
    return FileResponse(index_path)


@app.get("/invitations/accept")
def invitation_accept_page() -> FileResponse:
    index_path = static_path / "index.html"
    return FileResponse(index_path)


@app.get("/api/scenarios")
def api_scenarios() -> dict[str, list[str]]:
    return {"scenarios": list_scenarios() if settings.demo_mode_enabled else []}


def principal_dependency(request: Request) -> Principal:
    principal = current_principal(request)
    csrf_protect(request, principal)
    return principal


@app.post("/api/auth/register", response_model=CurrentUserResponse, status_code=201)
def register(request: RegisterRequest, fastapi_request: Request, response: Response) -> CurrentUserResponse:
    rate_limiter.check(fastapi_request, "authentication", limit=settings.auth_endpoint_rate_limit_attempts, window_seconds=settings.login_rate_limit_window_seconds)
    user, organization, membership = auth_store.register_owner(
        request.email,
        request.display_name,
        request.password,
        request.organization_name,
        request.timezone,
        request.organization_slug,
    )
    csrf_token = secrets.token_urlsafe(32)
    session_id = session_store.create(user.id, csrf_token, utc_now() + timedelta(seconds=settings.session_ttl_seconds))
    set_session_cookies(response, session_id, csrf_token)
    return auth_store.principal_for_user(user.id, csrf_token).response()


@app.post("/api/auth/login", response_model=CurrentUserResponse)
def login(request: LoginRequest, fastapi_request: Request, response: Response) -> CurrentUserResponse:
    rate_limiter.check(fastapi_request, "authentication", limit=settings.auth_endpoint_rate_limit_attempts, window_seconds=settings.login_rate_limit_window_seconds)
    user, _, _ = auth_store.authenticate(request.email, request.password, fastapi_request.client.host if fastapi_request.client else "")
    csrf_token = secrets.token_urlsafe(32)
    session_id = session_store.create(user.id, csrf_token, utc_now() + timedelta(seconds=settings.session_ttl_seconds))
    set_session_cookies(response, session_id, csrf_token)
    return auth_store.principal_for_user(user.id, csrf_token).response()


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    session_id = request.cookies.get(settings.session_cookie_name)
    principal = current_principal(request)
    if principal.authenticated:
        csrf_protect(request, principal)
    if session_id:
        session_store.revoke(session_id)
    clear_session_cookies(response)
    auth_store.record_activity(principal.organization_id, "logout", principal.user.id if principal.user else None, {})
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=CurrentUserResponse)
def me(principal: Principal = Depends(principal_dependency)) -> CurrentUserResponse:
    return principal.response()


ACTIVITY_CATEGORIES = {"Human Decisions", "PR Reviews", "Cloud Hunt", "Members", "Roles and Access", "Integrations", "Policies", "Authentication", "Workspace", "System"}
ACTIVITY_SORTS = {"created_at_desc", "created_at_asc", "newest", "oldest"}
SENSITIVE_ACTIVITY_KEYS = {"password", "token", "token_hash", "csrf_token", "cookie", "secret", "private_key", "access_token", "client_secret"}


def _redact_activity(value):
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if str(key).lower() in SENSITIVE_ACTIVITY_KEYS else _redact_activity(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_activity(item) for item in value]
    return value


def _public_activity_event(event: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(event.get("id")),
        "organization_id": str(event.get("organization_id")),
        "actor_type": event.get("actor_type", "System"),
        "actor_user_id": str(event["actor_user_id"]) if event.get("actor_user_id") else None,
        "actor_display_name": event.get("actor_display_name", "System"),
        "actor_role_snapshot": event.get("actor_role_snapshot"),
        "category": event.get("category", "System"),
        "action": event.get("action", event.get("event_type")),
        "target_type": event.get("target_type", "workspace"),
        "target_id": event.get("target_id"),
        "target_display_name": event.get("target_display_name", "Workspace"),
        "result": event.get("result", "success"),
        "summary": event.get("summary", "Activity recorded."),
        "metadata": _redact_activity(event.get("metadata", event.get("details", {}))),
        "correlation_id": event.get("correlation_id"),
        "related_case_id": event.get("related_case_id"),
        "related_run_id": event.get("related_run_id"),
        "created_at": event.get("created_at"),
    }


@app.get("/api/activity")
def list_activity(
    category: str | None = None,
    actor_type: str | None = None,
    actor_user_id: UUID | None = None,
    action: str | None = None,
    result: str | None = None,
    target_type: str | None = None,
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "created_at_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    principal: Principal = Depends(principal_dependency),
) -> dict[str, object]:
    require_permission(principal, ACTIVITY_READ)
    if category and category not in ACTIVITY_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown activity category.")
    if sort not in ACTIVITY_SORTS:
        raise HTTPException(status_code=422, detail="Unknown activity sort.")
    def aware(value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    start, end = aware(created_from), aware(created_to)
    needle = (search or "").strip().lower()
    events = []
    for event in auth_store.list_activity_events(principal.organization_id):
        created_at = event.get("created_at")
        if not isinstance(created_at, datetime):
            continue
        if category and event.get("category") != category:
            continue
        if actor_type and str(event.get("actor_type", "")).lower() != actor_type.lower():
            continue
        if actor_user_id and event.get("actor_user_id") != actor_user_id:
            continue
        if action and str(event.get("action", event.get("event_type", ""))).lower() != action.lower():
            continue
        if result and str(event.get("result", "")).lower() != result.lower():
            continue
        if target_type and str(event.get("target_type", "")).lower() != target_type.lower():
            continue
        if (start and created_at < start) or (end and created_at > end):
            continue
        if needle:
            searchable = " ".join(str(event.get(key, "")) for key in ("actor_display_name", "actor_role_snapshot", "category", "action", "target_display_name", "summary", "correlation_id", "metadata"))
            if needle not in searchable.lower():
                continue
        events.append(event)
    events.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=sort in {"created_at_desc", "newest"})
    total = len(events)
    start_index = (page - 1) * page_size
    return {"items": [_public_activity_event(event) for event in events[start_index:start_index + page_size]], "total": total, "page": page, "page_size": page_size, "has_next": start_index + page_size < total, "timezone": principal.organization.timezone}


@app.get("/api/activity/{event_id}")
def get_activity(event_id: UUID, principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, ACTIVITY_READ)
    event = auth_store.get_activity_event(principal.organization_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Activity event not found.")
    return _public_activity_event(event)


@app.get("/api/members")
def list_members(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_READ)
    memberships = [
        item
        for item in auth_store.memberships.values()
        if item.organization_id == principal.organization_id
    ]
    users = auth_store.users_by_id
    return [
        {"membership": membership, "user": users.get(membership.user_id)}
        for membership in memberships
    ]


@app.patch("/api/workspace")
def update_workspace(request: OrganizationUpdateRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, WORKSPACE_MANAGE)
    expected = request.expected_version
    if expected is not None and expected != principal.organization.version:
        raise HTTPException(status_code=409, detail="Workspace settings changed elsewhere. Refresh and try again.")
    return auth_store.update_organization(principal, request.name, request.timezone, expected)


@app.get("/api/workspace")
def get_workspace(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, WORKSPACE_READ)
    organization = principal.organization
    return {"organization": organization, "version": organization.version, "display_preferences": {"currency": "USD", "currency_editable": False, "source": "default"}}


def invitation_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/invitations/accept?token={token}"


def public_invitation(invitation, token: str | None = None) -> dict[str, object]:
    inviter = auth_store.users_by_id.get(invitation.invited_by_user_id)
    payload: dict[str, object] = {
        "id": str(invitation.id),
        "organization_id": str(invitation.organization_id),
        "email": invitation.email,
        "assigned_role": invitation.role,
        "role_label": ROLE_LABELS[invitation.role],
        "approval_permission_enabled": invitation.approval_permission_enabled,
        "status": invitation.status,
        "status_label": invitation.status.value.title(),
        "invited_by": inviter.display_name if inviter else "Unknown",
        "invited_by_user_id": str(invitation.invited_by_user_id),
        "created_at": invitation.created_at,
        "updated_at": invitation.updated_at,
        "expires_at": invitation.expires_at,
        "accepted_at": invitation.accepted_at,
        "canceled_at": invitation.canceled_at,
        "last_sent_at": invitation.last_sent_at,
        "resend_count": invitation.resend_count,
    }
    if token and not settings.invitation_email_enabled:
        payload["development_invitation_link"] = invitation_link(token)
    return payload


@app.get("/api/invitations")
def list_invitations(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_READ)
    return [public_invitation(invitation) for invitation in auth_store.list_invitations(principal)]


@app.post("/api/invitations", status_code=201)
def invite_member(request: InviteMemberRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_INVITE)
    invitation, token = auth_store.invite(principal, request.email, request.role, request.approval_permission_enabled, request.note)
    return {"invitation": public_invitation(invitation), "development_invitation_link": invitation_link(token), "email_sent": settings.invitation_email_enabled}


@app.get("/api/invitations/validate", response_model=InvitationValidateResponse)
def validate_invitation(token: str) -> InvitationValidateResponse:
    try:
        invitation = auth_store.validate_invitation_token(token)
    except HTTPException as exc:
        return InvitationValidateResponse(valid=False, status="invalid", message=str(exc.detail))
    organization = auth_store.organizations[invitation.organization_id]
    return InvitationValidateResponse(
        valid=True,
        status=invitation.status,
        organization_name=organization.name,
        email=invitation.email,
        role_label=ROLE_LABELS[invitation.role],
        approval_permission_enabled=invitation.approval_permission_enabled,
        expires_at=invitation.expires_at,
    )


@app.post("/api/invitations/accept", response_model=CurrentUserResponse)
def accept_invitation(request: InvitationAcceptRequest, fastapi_request: Request, response: Response) -> CurrentUserResponse:
    principal = None
    try:
        principal = current_principal(fastapi_request)
        if principal.authenticated:
            csrf_protect(fastapi_request, principal)
        else:
            principal = None
    except HTTPException:
        principal = None
    user, organization, _ = auth_store.accept_invitation(
        request.token,
        request.display_name,
        request.password,
        request.confirm_password,
        principal,
    )
    csrf_token = secrets.token_urlsafe(32)
    session_id = session_store.create(user.id, csrf_token, utc_now() + timedelta(seconds=settings.session_ttl_seconds))
    set_session_cookies(response, session_id, csrf_token)
    return auth_store.principal_for_user(user.id, csrf_token, organization.id).response()


@app.post("/api/invitations/{invitation_id}/resend")
def resend_invitation(invitation_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_INVITE)
    invitation, token = auth_store.resend_invitation(principal, invitation_id)
    return {"invitation": public_invitation(invitation), "development_invitation_link": invitation_link(token), "email_sent": settings.invitation_email_enabled}


@app.post("/api/invitations/{invitation_id}/cancel")
def cancel_invitation(invitation_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_CANCEL_INVITATION)
    return public_invitation(auth_store.cancel_invitation(principal, invitation_id))


@app.patch("/api/members/{membership_id}")
def change_member_role(membership_id: UUID, request: ChangeMemberRoleRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_MANAGE_ROLES)
    return auth_store.change_role(principal, membership_id, request.role, request.approval_permission_enabled)


@app.post("/api/members/{membership_id}/disable")
def disable_member(membership_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_DISABLE)
    return auth_store.disable_member(principal, membership_id)


@app.post("/api/members/{membership_id}/reactivate")
def reactivate_member(membership_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_DISABLE)
    return auth_store.reactivate_member(principal, membership_id)


@app.post("/api/runs", response_model=WorkflowRun, status_code=201)
def create_run(request: StartRunRequest, response: Response, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, PR_REVIEWS_READ)
    try:
        run, created = workflow_service.start_run(request, principal.organization_id)
    except ScenarioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Run failed safely: {exc}") from exc
    if not created:
        response.status_code = 200
    else:
        auth_store.record_activity(principal.organization_id, "pr_review_created", None, {"run_id": str(run.id), "scenario": run.scenario_name}, actor_type="System", category="PR Reviews", target_type="run", target_id=run.id, target_display_name=f"PR review {run.id}", related_run_id=run.id)
    return run


def _pr_review_summary(run: WorkflowRun) -> dict[str, object]:
    decision = run.decision_record
    source = run.github_source
    mock = run.mock_pr
    preferred = next((item for item in (decision.alternatives if decision else []) if item.action == (decision.preferred_action if decision else None)), None)
    latest_review = run.human_reviews[-1] if run.human_reviews else None
    risk_values = []
    if decision:
        risk_values.extend(item.severity for item in decision.conflicts)
        risk_values.extend(item.severity for item in decision.verifier_findings if item.status != "passed")
    risk_order = {"info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
    risk = max(risk_values, key=lambda value: risk_order.get(str(value).lower(), 0), default="low")
    if preferred and preferred.risks and not risk_values:
        risk = "medium"
    resource = None
    if source and source.resource_changes:
        resource = source.resource_changes[0]
    pricing_item = verified_pricing_item(decision.evidence if decision else [])
    demo_pricing = settings.demo_mode_enabled and preferred is not None and pricing_item is None
    if pricing_item is not None:
        pricing_value = pricing_item.value
        pricing = {
            "available": True,
            "source": pricing_item.source,
            "source_mode": pricing_item.source_mode,
            **pricing_value,
        }
        savings = float(preferred.estimated_monthly_savings) if preferred else None
        annual_savings = float(preferred.estimated_annual_savings) if preferred else None
    elif demo_pricing:
        savings = float(preferred.estimated_monthly_savings) if preferred else None
        annual_savings = float(preferred.estimated_annual_savings) if preferred else None
        pricing = {"available": True, "source": "scenario_fixture", "source_mode": "fixture", "reason": "Demo fixture pricing."}
    else:
        savings = None
        annual_savings = None
        pricing = {"available": False, "source": "unavailable", "source_mode": "unavailable", "reason": "Live pricing evidence was not available for this change."}
    return {
        "id": str(run.id), "source_type": run.source_type, "organization_id": str(run.organization_id),
        "repository": source.repository if source else (mock.repository if mock else "Demo review"),
        "pull_request_number": source.pull_request_number if source else (mock.pr_number if mock else None),
        "title": (source.pull_request_title if source else None) or (mock.title if mock else run.goal),
        "branch": source.head_branch if source else (mock.branch if mock else None),
        "base_branch": source.base_branch if source else (mock.base_branch if mock else None),
        "change": resource.address if resource else (decision.resource_id if decision else (mock.resource_id if mock else None)),
        "change_summary": (f"{resource.address}: {', '.join(resource.actions)}" if resource else (mock.terraform_patch_preview if mock else "Terraform review")),
        "recommendation": decision.preferred_action if decision else (mock.chosen_action if mock else None),
        "savings": savings,
        "annual_savings": annual_savings,
        "pricing": pricing,
        "risk": str(risk), "confidence": float(decision.confidence.final_confidence if decision else (mock.confidence if mock else 0)),
        "status": run.status, "reviewer": latest_review.reviewer if latest_review else "Unassigned",
        "received_at": run.created_at, "updated_at": run.updated_at, "version": run.version,
    }


def _pr_review_group(status: str) -> str:
    if status in {"pending_human_review", "needs_more_evidence", "reopened", "abstained", "keep"}: return "needs-attention"
    if status in {"created", "planning", "investigating", "verifying"}: return "in-progress"
    if status in {"approved", "rejected", "approval_revoked", "pr_created", "remediation_pr_created", "remediation_proposal_prepared", "completed"}: return "completed"
    if status in {"blocked", "failed_safely"}: return "blocked"
    return "all"


@app.get("/api/runs")
def list_runs(
    source_type: str | None = None, status: str | None = None, repository: str | None = None,
    reviewer: str | None = None, search: str | None = None, created_from: datetime | None = None,
    created_to: datetime | None = None, sort: str | None = None, group: str | None = None,
    page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100),
    principal: Principal = Depends(principal_dependency),
):
    require_permission(principal, PR_REVIEWS_READ)
    runs = workflow_service.list_runs(principal.organization_id)
    if not any(value is not None for value in (source_type, status, repository, reviewer, search, created_from, created_to, sort, group, page, page_size)):
        return runs
    summaries = [_pr_review_summary(run) for run in runs if source_type is None or run.source_type == source_type]
    needle = (search or "").strip().lower()
    allowed_sorts = {"newest", "oldest", "updated_desc", "last_updated", "savings_desc", "risk_desc", "confidence_desc"}
    if sort and sort not in allowed_sorts:
        raise HTTPException(status_code=422, detail="Unknown PR review sort.")
    def aware(value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    start, end = aware(created_from), aware(created_to)
    filtered = []
    for item in summaries:
        created = item["received_at"]
        haystack = " ".join(str(item.get(key) or "") for key in ("repository", "pull_request_number", "title", "branch", "base_branch", "change", "reviewer"))
        if status and str(item["status"]) != status: continue
        if repository and str(item["repository"]).lower() != repository.lower(): continue
        if reviewer and str(item["reviewer"]).lower() != reviewer.lower(): continue
        if group and group != "all" and _pr_review_group(str(item["status"])) != group: continue
        if needle and needle not in haystack.lower(): continue
        if start and created < start or end and created > end: continue
        filtered.append(item)
    sort_key = sort or "updated_desc"
    risk_order = {"info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
    if sort_key in {"newest", "oldest"}: filtered.sort(key=lambda item: item["received_at"], reverse=sort_key == "newest")
    elif sort_key in {"savings_desc"}: filtered.sort(key=lambda item: item["savings"], reverse=True)
    elif sort_key in {"risk_desc"}: filtered.sort(key=lambda item: risk_order.get(str(item["risk"]).lower(), 0), reverse=True)
    elif sort_key in {"confidence_desc"}: filtered.sort(key=lambda item: item["confidence"], reverse=True)
    else: filtered.sort(key=lambda item: item["updated_at"], reverse=True)
    actual_page = page or 1
    actual_size = page_size or 20
    offset = (actual_page - 1) * actual_size
    return {"items": filtered[offset:offset + actual_size], "total": len(filtered), "page": actual_page, "page_size": actual_size, "has_next": offset + actual_size < len(filtered)}


@app.get("/api/runs/{run_id}", response_model=WorkflowRun)
def get_run(run_id: UUID, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, PR_REVIEWS_READ)
    try:
        return workflow_service.get_run(run_id, principal.organization_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


ACTION_PERMISSIONS = {
    "approve": APPROVALS_DECIDE,
    "reject": APPROVALS_REJECT,
    "revoke_approval": APPROVALS_REVOKE,
    "reopen_case": APPROVALS_REOPEN,
    "request_evidence": APPROVALS_REQUEST_EVIDENCE,
    "add_context": APPROVALS_ADD_CONTEXT,
    "add_follow_up_context": APPROVALS_ADD_CONTEXT,
    "modify": APPROVALS_MODIFY,
}

REASON_REQUIRED_ACTIONS = {"reject", "revoke_approval", "reopen_case", "modify"}
CONTEXT_ACTIONS = {"add_context", "add_follow_up_context"}


def _trim(value: str | None) -> str | None:
    trimmed = (value or "").strip()
    return trimmed or None


def _validate_decision_contract(request: HumanReviewRequest | ReviewCaseActionRequest, valid_sources: set[str] | None = None) -> None:
    if request.expected_version is None:
        raise HTTPException(status_code=422, detail="expected_version is required.")
    if not _trim(request.idempotency_key):
        raise HTTPException(status_code=422, detail="idempotency_key is required.")
    if request.action in REASON_REQUIRED_ACTIONS and not _trim(request.comment):
        raise HTTPException(status_code=422, detail="A reason is required for this action.")
    if request.action in CONTEXT_ACTIONS and not _trim(request.human_context or request.comment):
        raise HTTPException(status_code=422, detail="Meaningful context is required.")
    if request.action == "request_evidence":
        if not request.requested_sources:
            raise HTTPException(status_code=422, detail="requested_sources is required.")
        if valid_sources is not None:
            unknown = sorted(set(request.requested_sources) - valid_sources)
            if unknown:
                raise HTTPException(status_code=422, detail=f"Unknown evidence source(s): {', '.join(unknown)}")


def _decision_payload(case_id: UUID, case_type: str, request: HumanReviewRequest | ReviewCaseActionRequest, principal: Principal) -> dict[str, object]:
    data = request.model_dump(mode="json", exclude={"reviewer"})
    data["case_id"] = str(case_id)
    data["case_type"] = case_type
    data["organization_id"] = str(principal.organization_id)
    data["actor_user_id"] = str(principal.user.id) if principal.user else None
    return data


def _remediation_result(case: dict[str, object]) -> dict[str, object]:
    mock_pr = case.get("mock_pr") or case.get("simulated_pr")
    real_pr = case.get("real_pr")
    if real_pr:
        return {"created": True, "type": "github_pr", "url": real_pr.get("url") if isinstance(real_pr, dict) else None}
    if mock_pr:
        status = str(case.get("status") or "")
        return {"created": status in {"pr_created", "remediation_pr_created"}, "type": "simulated_pr", "proposal_only": status == "remediation_proposal_prepared"}
    return {"created": False, "type": None, "proposal_only": False}


def _record_decision_success(
    *,
    case_id: UUID,
    case_type: str,
    action: str,
    request: HumanReviewRequest | ReviewCaseActionRequest,
    principal: Principal,
    previous_state: dict[str, object],
    resulting: dict[str, object],
    fingerprint: str,
    correlation_id: str,
) -> dict[str, object]:
    base = dict(resulting)
    response_snapshot: dict[str, object] = {
        **base,
        "case_id": str(case_id),
        "status": base.get("status"),
        "new_version": base.get("version"),
        "correlation_id": correlation_id,
        "updated_at": base.get("updated_at"),
        "remediation_result": _remediation_result(base),
        "idempotent_replay": False,
    }
    related = decision_event_store.latest_for_case(principal.organization_id, case_id, "approve") if action == "revoke_approval" else None
    event = decision_event_store.append(
        organization_id=principal.organization_id,
        case_id=case_id,
        case_type=case_type,
        principal=principal,
        action=action,
        reason=_trim(request.comment),
        previous_state=previous_state,
        resulting_state={"status": base.get("status"), "version": base.get("version"), "updated_at": base.get("updated_at")},
        related_event_id=related.id if related else None,
        correlation_id=correlation_id,
        idempotency_key=_trim(request.idempotency_key) or "",
        request_fingerprint=fingerprint,
        response_snapshot=response_snapshot,
    )
    response_snapshot["decision_event_id"] = str(event.id)
    event.response_snapshot["decision_event_id"] = str(event.id)
    auth_store.record_activity(
        principal.organization_id,
        "human_decision_recorded",
        principal.user.id if principal.user else None,
        {"case_id": str(case_id), "action": action, "correlation_id": correlation_id, "decision_event_id": str(event.id), "previous_state": previous_state, "resulting_state": resulting, "reason": _trim(request.comment)},
        actor_type="User" if principal.user else "System",
        target_type="case",
        target_id=case_id,
        target_display_name=f"{case_type} {case_id}",
        correlation_id=correlation_id,
        related_case_id=case_id,
        related_run_id=case_id if case_type == "workflow_run" else None,
    )
    remediation = response_snapshot["remediation_result"]
    if action == "approve" and isinstance(remediation, dict) and remediation.get("created"):
        auth_store.record_activity(
            principal.organization_id,
            "remediation_pr_created",
            None,
            {"case_id": str(case_id), "correlation_id": correlation_id, "remediation": remediation},
            actor_type="Agent",
            category="PR Reviews" if case_type == "workflow_run" else "Cloud Hunt",
            target_type="case",
            target_id=case_id,
            target_display_name=f"{case_type} {case_id}",
            correlation_id=correlation_id,
            related_case_id=case_id,
            related_run_id=case_id if case_type == "workflow_run" else None,
        )
    return response_snapshot


@app.post("/api/runs/{run_id}/review")
def review_run(run_id: UUID, request: HumanReviewRequest, response: Response, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, ACTION_PERMISSIONS[request.action])
    _validate_decision_contract(request, set(workflow_service.tool_registry.names()))
    reviewer = principal.reviewer_name if principal.authenticated else request.reviewer
    secured_request = request.model_copy(update={"reviewer": reviewer, "comment": _trim(request.comment), "human_context": _trim(request.human_context), "idempotency_key": _trim(request.idempotency_key)})
    fingerprint = normalized_fingerprint(_decision_payload(run_id, "workflow_run", secured_request, principal))
    replay = decision_event_store.replay(principal.organization_id, secured_request.idempotency_key or "", fingerprint)
    if replay is not None:
        return replay
    correlation_id = secrets.token_urlsafe(18)
    try:
        previous = workflow_service.get_run(run_id, principal.organization_id).model_dump(mode="json")
        run, maybe_pr_created = workflow_service.review_run(
            run_id,
            secured_request,
            principal.organization_id,
            principal.user.id if principal.user else None,
            principal.user.email if principal.user else None,
            principal.membership.role,
            secured_request.expected_version,
        )
        append_audit_event(run, event_type="human_decision_event_recorded", actor="system", summary="Human decision event recorded.", details={"correlation_id": correlation_id, "action": secured_request.action})
        run = workflow_service.store.update(run.id, run, principal.organization_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if maybe_pr_created and (run.mock_pr is not None or run.real_pr is not None):
        response.status_code = 201
    return _record_decision_success(
        case_id=run_id,
        case_type="workflow_run",
        action=secured_request.action,
        request=secured_request,
        principal=principal,
        previous_state={"status": previous.get("status"), "version": previous.get("version"), "updated_at": previous.get("updated_at")},
        resulting=run.model_dump(mode="json"),
        fingerprint=fingerprint,
        correlation_id=correlation_id,
    )


@app.post("/api/runs/{run_id}/github-context", response_model=WorkflowRun)
def collect_github_context(run_id: UUID, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, REPOSITORY_CONTEXT_READ)
    try:
        run = workflow_service.get_run(run_id, principal.organization_id)
        source = run.github_source
        if source is None or not source.repository or source.pull_request_number is None:
            raise HTTPException(status_code=422, detail="This run has no GitHub pull-request source.")
        config = github_integration_store.get(principal.organization_id)
        client = GitHubAppClient(config.installation_id).api_client() if config.installation_id else (workflow_service.github_client if settings.github_development_token_fallback else None)
        if client is None:
            raise HTTPException(status_code=503, detail="GitHub credentials are unavailable.")
        config = github_integration_store.get(principal.organization_id)
        context = GitHubContextAdapter(client, config.allowed_repositories, config.source_mode).collect_pr_context(source.repository, source.pull_request_number, run.correlation_id)
        def update(current: WorkflowRun) -> WorkflowRun:
            current.github_context = context
            append_audit_event(current, event_type="github_context_collected", actor="tool", summary="Read-only GitHub context collected.", details={"repository": source.repository, "pull_request": source.pull_request_number, "codeowners_available": context["codeowners_available"]})
            if not context["codeowners_available"]:
                append_audit_event(current, event_type="ownership_resolution", actor="tool", summary="CODEOWNERS was unavailable; ownership remains unknown.", stage="ownership", status="warning", reason="No CODEOWNERS file was found.")
            return current
        result = workflow_service.store.update(run_id, update, principal.organization_id)
        github_integration_store.mark_collection(principal.organization_id, True)
        auth_store.record_activity(principal.organization_id, "github_context_collected", principal.user.id if principal.user else None, {"run_id": str(run_id), "repository": source.repository, "pull_request": source.pull_request_number, "correlation_id": run.correlation_id}, actor_type="Integration", category="Integrations", related_run_id=run_id)
        return result
    except HTTPException:
        raise
    except (RunNotFoundError, GitHubAPIError) as exc:
        github_integration_store.mark_collection(principal.organization_id, False, str(exc))
        raise HTTPException(status_code=409 if isinstance(exc, GitHubAPIError) else 404, detail=str(exc)) from exc


@app.post("/api/goals", response_model=WorkflowRun, status_code=201)
def create_goal(request: GoalCreateRequest, fastapi_request: Request, response: Response, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    rate_limiter.check(fastapi_request, "goal_execution", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    require_permission(principal, GOALS_RUN)
    logger.info("goal_request_received organization_id=%s user_id=%s", principal.organization_id, principal.user.id if principal.user else None)
    try:
        start_request = StartRunRequest(goal=request.goal, scenario_name=request.scenario_name, constraints=request.constraints, idempotency_key=request.idempotency_key, scope=request.scope, success_criteria=request.success_criteria, stop_conditions=request.stop_conditions, data_source_mode=request.data_source_mode)
        if settings.demo_mode_enabled:
            run, created = workflow_service.start_run(start_request, principal.organization_id, principal.user.id if principal.user else None, principal.reviewer_name)
        else:
            github = github_integration_store.get(principal.organization_id)
            aws = aws_integration_store.get(principal.organization_id)
            jira = jira_integration_store.get(principal.organization_id)
            connected_sources = [
                name for name, enabled in (("GitHub", github.enabled and bool(github.installation_id)), ("AWS", aws.enabled), ("Jira", jira.enabled and bool(jira.base_url))) if enabled
            ]
            existing_prs = [run for run in workflow_service.list_runs(principal.organization_id) if run.source_type == "terraform_pr"]
            existing_hunts = cloud_hunt_service.list_hunts(principal.organization_id)
            latest_pr = max(existing_prs, key=lambda item: item.updated_at, default=None)
            latest_hunt = max(existing_hunts, key=lambda item: item.completed_at or item.started_at, default=None)
            if latest_pr and latest_pr.data_source_mode in {"Fixture-backed", "fixtures", "demo"}:
                latest_pr = None
            run, created = workflow_service.start_connected_goal(
                start_request,
                principal.organization_id,
                principal.user.id if principal.user else None,
                principal.reviewer_name,
                connected_sources=connected_sources,
                reference_run=latest_pr,
                linked_pr_review_id=latest_pr.id if latest_pr else None,
                linked_cloud_hunt_id=latest_hunt.id if latest_hunt else None,
            )
            if created and run.status == "investigating":
                def github_collector(goal_run: WorkflowRun) -> dict[str, object]:
                    config = github_integration_store.get(principal.organization_id)
                    if not config.enabled or not config.installation_id:
                        raise RuntimeError("GitHub installation is not connected.")
                    client = GitHubAppClient(config.installation_id).api_client()
                    repositories = client.list_installation_repositories()
                    allowed = {item.lower() for item in config.allowed_repositories}
                    repository = next((str(item.get("full_name")) for item in repositories if item.get("full_name") and (not allowed or str(item.get("full_name")).lower() in allowed)), None)
                    if not repository:
                        raise RuntimeError("No allowed GitHub repository is available.")
                    owner, name = repository.split("/", 1)
                    metadata = client.get_repository(owner, name)
                    commits = client.list_commits(owner, name)
                    collected_at = utc_now()
                    context = {"repository": repository, "source_type": "github_repository", "source_mode": config.source_mode, "repository_default_branch": metadata.get("default_branch"), "commit_activity": {"recent_commit_count": len(commits), "last_commit": ((commits[0].get("commit") or {}).get("author") or {}).get("date") if commits else None}, "collected_at": collected_at, "correlation_id": goal_run.correlation_id}
                    evidence = {"source": "GitHub", "source_id": repository, "resource_id": repository, "status": "verified", "summary": f"Repository metadata and {len(commits)} recent commit record(s) were collected.", "provenance": {"organization_id": str(principal.organization_id), "repository": repository, "source_mode": config.source_mode, "collected_at": collected_at}, "limitations": ["GitHub evidence does not establish runtime utilization, sizing safety, or verified savings."], "collected_at": collected_at}
                    return {"github_context": context, "evidence": [evidence], "missing_evidence": ["AWS utilization", "Verified pricing", "Resource-to-repository mapping"], "output_summary": f"GitHub repository context collected for {repository}."}

                def cloud_hunt_collector(goal_run: WorkflowRun) -> dict[str, object]:
                    if not goal_run.linked_cloud_hunt_id:
                        raise RuntimeError("No linked Cloud Hunt run is available.")
                    hunt = cloud_hunt_service.get_hunt(goal_run.linked_cloud_hunt_id, principal.organization_id)
                    if hunt.data_source_mode == "Fixture-backed":
                        raise RuntimeError("Fixture-backed Cloud Hunt evidence is not eligible for production goals.")
                    collected_at = utc_now()
                    evidence = []
                    for candidate in hunt.candidates:
                        resource = candidate.resource
                        evidence.append({"source": "Cloud Hunt", "source_id": str(hunt.id), "resource_id": resource.resource_id, "status": "partial", "summary": f"{resource.resource_name}: {candidate.suspicion_level} suspicion classification from Cloud Hunt.", "provenance": {"organization_id": str(principal.organization_id), "cloud_hunt_id": str(hunt.id), "source_mode": hunt.data_source_mode, "collected_at": collected_at}, "limitations": ["Cloud Hunt classification alone does not verify utilization, savings, or remediation safety."], "collected_at": collected_at})
                    return {"evidence": evidence, "missing_evidence": ["AWS utilization", "Verified pricing", "Resource-to-repository mapping"], "output_summary": f"{len(evidence)} eligible Cloud Hunt record(s) imported."}

                collectors = {"GitHub": github_collector}
                if latest_hunt:
                    collectors["Cloud Hunt"] = cloud_hunt_collector
                    if "Cloud Hunt" not in run.selected_tools:
                        run = workflow_service.store.update(run.id, lambda current: current.model_copy(update={"selected_tools": [*current.selected_tools, "Cloud Hunt"]}), principal.organization_id)
                run = workflow_service.execute_connected_evidence(run.id, principal.organization_id, collectors)
        if not created: response.status_code = 200
        else:
            auth_store.record_activity(principal.organization_id, "goal_created", principal.user.id if principal.user else None, {"goal_id": str(run.id), "correlation_id": run.correlation_id, "execution_mode": run.execution_mode}, actor_type="User", category="System", target_type="goal", target_id=run.id, target_display_name=run.goal[:120], related_run_id=run.id)
        logger.info("goal_created organization_id=%s goal_id=%s status=%s correlation_id=%s", principal.organization_id, run.id, run.status, run.correlation_id)
        return run
    except ScenarioNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("goal_creation_failed organization_id=%s exception_class=%s", principal.organization_id, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Goal failed safely. No infrastructure changes were made.") from exc


@app.get("/api/goals")
def list_goals(principal: Principal = Depends(principal_dependency)) -> list[dict[str, object]]:
    require_permission(principal, GOALS_READ)
    return [{"id": run.id, "goal": run.goal, "scope": run.scope, "status": run.status, "created_at": run.created_at, "updated_at": run.updated_at, "planning_mode": run.decision_record.planning_mode if run.decision_record else "deterministic_only", "data_source_mode": run.data_source_mode, "correlation_id": run.correlation_id} for run in workflow_service.list_runs(principal.organization_id)]


@app.get("/api/goals/{goal_id}", response_model=WorkflowRun)
def get_goal(goal_id: UUID, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, GOALS_READ)
    try: return workflow_service.get_run(goal_id, principal.organization_id)
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/goals/{goal_id}/start", response_model=WorkflowRun)
def start_goal(goal_id: UUID, request: Request, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    rate_limiter.check(request, "goal_execution", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    require_permission(principal, GOALS_RUN)
    try: return workflow_service.get_run(goal_id, principal.organization_id)
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/goals/{goal_id}/continue", response_model=WorkflowRun)
def continue_goal(goal_id: UUID, request: Request, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    rate_limiter.check(request, "goal_execution", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    require_permission(principal, GOALS_RUN)
    try: return workflow_service.get_run(goal_id, principal.organization_id)
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/goals/{goal_id}/retry-evidence", response_model=WorkflowRun)
def retry_goal_evidence(goal_id: UUID, request: GoalEvidenceRetryRequest, fastapi_request: Request, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    rate_limiter.check(fastapi_request, "goal_execution", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    require_permission(principal, GOALS_RUN)
    try:
        run = workflow_service.get_run(goal_id, principal.organization_id)
        if run.last_evidence_retry_key == request.idempotency_key:
            return run
        if run.status != "needs_more_evidence":
            raise HTTPException(status_code=409, detail="Evidence retry is only available for goals paused for evidence.")

        def github_collector(goal_run: WorkflowRun) -> dict[str, object]:
            config = github_integration_store.get(principal.organization_id)
            if not config.enabled or not config.installation_id:
                raise RuntimeError("GitHub installation is not connected.")
            client = GitHubAppClient(config.installation_id).api_client()
            repositories = client.list_installation_repositories()
            allowed = {item.lower() for item in config.allowed_repositories}
            repository = next((str(item.get("full_name")) for item in repositories if item.get("full_name") and (not allowed or str(item.get("full_name")).lower() in allowed)), None)
            if not repository:
                raise RuntimeError("No allowed GitHub repository is available.")
            owner, name = repository.split("/", 1); metadata = client.get_repository(owner, name); commits = client.list_commits(owner, name); collected_at = utc_now()
            return {"github_context": {"repository": repository, "source_type": "github_repository", "source_mode": config.source_mode, "repository_default_branch": metadata.get("default_branch"), "commit_activity": {"recent_commit_count": len(commits)}, "collected_at": collected_at, "correlation_id": goal_run.correlation_id}, "evidence": [{"source": "GitHub", "source_id": repository, "resource_id": repository, "status": "verified", "summary": f"Repository metadata and {len(commits)} recent commit record(s) were collected.", "provenance": {"organization_id": str(principal.organization_id), "repository": repository, "source_mode": config.source_mode, "collected_at": collected_at}, "limitations": ["GitHub evidence does not establish runtime utilization, sizing safety, or verified savings."], "collected_at": collected_at}], "missing_evidence": ["AWS utilization", "Verified pricing", "Resource-to-repository mapping"], "output_summary": f"GitHub repository context collected for {repository}."}

        def cloud_hunt_collector(goal_run: WorkflowRun) -> dict[str, object]:
            if not goal_run.linked_cloud_hunt_id:
                raise RuntimeError("No linked Cloud Hunt run is available.")
            hunt = cloud_hunt_service.get_hunt(goal_run.linked_cloud_hunt_id, principal.organization_id)
            if hunt.data_source_mode == "Fixture-backed":
                raise RuntimeError("Fixture-backed Cloud Hunt evidence is not eligible for production goals.")
            collected_at = utc_now()
            evidence = [{"source": "Cloud Hunt", "source_id": str(hunt.id), "resource_id": candidate.resource.resource_id, "status": "partial", "summary": f"{candidate.resource.resource_name}: {candidate.suspicion_level} suspicion classification from Cloud Hunt.", "provenance": {"organization_id": str(principal.organization_id), "cloud_hunt_id": str(hunt.id), "source_mode": hunt.data_source_mode, "collected_at": collected_at}, "limitations": ["Cloud Hunt classification alone does not verify utilization, savings, or remediation safety."], "collected_at": collected_at} for candidate in hunt.candidates]
            return {"evidence": evidence, "missing_evidence": ["AWS utilization", "Verified pricing", "Resource-to-repository mapping"], "output_summary": f"{len(evidence)} eligible Cloud Hunt record(s) imported."}

        collectors = {"GitHub": github_collector, "Cloud Hunt": cloud_hunt_collector}
        updated = workflow_service.execute_connected_evidence(goal_id, principal.organization_id, collectors, retry_unavailable_only=True)
        updated = workflow_service.store.update(goal_id, lambda current: current.model_copy(update={"last_evidence_retry_key": request.idempotency_key}), principal.organization_id)
        auth_store.record_activity(principal.organization_id, "goal_evidence_retry", principal.user.id if principal.user else None, {"goal_id": str(goal_id), "correlation_id": updated.correlation_id}, actor_type="User", category="System", target_type="goal", target_id=goal_id, target_display_name=updated.goal[:120], related_run_id=goal_id)
        return updated
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Goal not found.") from exc


@app.post("/api/goals/{goal_id}/context", response_model=WorkflowRun)
def add_goal_context(goal_id: UUID, request: GoalContextRequest, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, GOALS_RUN)
    try:
        run, _ = workflow_service.review_run(goal_id, HumanReviewRequest(action="add_context", reviewer=principal.reviewer_name, human_context=request.context, comment=request.context, expected_version=request.expected_version), principal.organization_id, principal.user.id if principal.user else None, principal.user.email if principal.user else None, principal.membership.role, request.expected_version)
        return run
    except (RunNotFoundError, WorkflowConflictError) as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/goals/{goal_id}/cancel", response_model=WorkflowRun)
def cancel_goal(goal_id: UUID, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, GOALS_CANCEL)
    try:
        run = workflow_service.cancel_goal(goal_id, principal.organization_id)
        auth_store.record_activity(principal.organization_id, "goal_canceled", principal.user.id if principal.user else None, {"goal_id": str(goal_id), "correlation_id": run.correlation_id}, actor_type="User", category="System", target_type="goal", target_id=goal_id, target_display_name=run.goal[:120], related_run_id=goal_id)
        return run
    except (RunNotFoundError, WorkflowConflictError) as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/goals/{goal_id}/events", response_model=list[AuditEvent])
def goal_events(goal_id: UUID, since_sequence: int = Query(0, ge=0), principal: Principal = Depends(principal_dependency)) -> list[AuditEvent]:
    require_permission(principal, GOALS_READ)
    try: run = workflow_service.get_run(goal_id, principal.organization_id)
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [event for event in run.audit_events if event.sequence_number > since_sequence]


@app.get("/api/demo/readiness")
def demo_readiness(principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, OVERVIEW_READ)
    runs = workflow_service.list_runs(principal.organization_id)
    hunts = cloud_hunt_service.list_hunts(principal.organization_id)
    cases = cloud_hunt_service.list_cases(principal.organization_id)
    schedules = schedule_store.list(principal.organization_id)
    integrations: dict[str, object] = {}
    for name, store in (("aws", aws_integration_store), ("github", github_integration_store), ("jira", jira_integration_store)):
        try:
            config = store.get(principal.organization_id)
            integrations[name] = {"enabled": config.enabled, "status": "disabled" if not config.enabled else "warning" if config.last_failure_summary else "ready" if getattr(config, "last_validated", None) or getattr(config, "last_successful_collection", None) else "not_checked", "last_checked": getattr(config, "last_validated", None), "last_success": config.last_successful_collection, "source_mode": getattr(config, "source_mode", "real"), "warnings": [config.last_failure_summary] if config.last_failure_summary else []}
        except Exception:
            integrations[name] = {"enabled": False, "status": "unavailable", "warnings": ["Integration status unavailable."]}
    recent = next((run for run in sorted(runs, key=lambda item: item.updated_at, reverse=True) if run.status in {"completed", "pr_created", "remediation_pr_created", "approved"}), None)
    warnings = []
    if not settings.github_webhook_secret: warnings.append("GitHub webhook signature secret is not configured.")
    if not settings.database_url: warnings.append("Using in-memory workflow storage; configure PostgreSQL for production.")
    if not settings.redis_url: warnings.append("Redis is not configured; distributed delivery/scheduler coordination is limited.")
    return {"authentication": {"authenticated": principal.authenticated, "organization": principal.organization.name, "role": principal.membership.role}, "health": {"database": "configured" if settings.database_url else "in_memory", "redis": "configured" if settings.redis_url else "not_configured"}, "github_webhook": {"enabled": settings.github_integration_enabled, "signature_ready": bool(settings.github_webhook_secret), "endpoint": "/webhooks/github"}, "integrations": integrations, "data_modes": {"fixtures_available": settings.demo_mode_enabled, "real_aws_configured": bool(settings.aws_region or settings.aws_allowed_regions), "real_github_configured": bool(settings.github_token), "real_jira_configured": bool(settings.jira_base_url and settings.jira_api_token)}, "scheduler": {"enabled": settings.cloud_hunt_schedule_enabled, "schedule_count": len(schedules), "enabled_schedule_count": sum(item.enabled for item in schedules), "redis_coordination": bool(settings.redis_url)}, "pending_approvals": sum(case.status in {"pending", "pending_human_review", "needs_more_evidence", "reopened"} for case in cases), "recent_successful_run": {"id": recent.id, "updated_at": recent.updated_at, "status": recent.status} if recent else None, "known_warnings": warnings}


@app.post("/api/demo/reset")
def reset_demo_fixtures(request: DemoResetRequest, fastapi_request: Request, principal: Principal = Depends(principal_dependency)) -> dict[str, str]:
    require_permission(principal, WORKSPACE_MANAGE)
    rate_limiter.check(fastapi_request, "demo_reset", principal.user.id if principal.user else None, 5, 300, principal.organization_id)
    if not request.confirm: raise HTTPException(status_code=422, detail="Explicit demo reset confirmation is required.")
    if not settings.demo_mode_enabled: raise HTTPException(status_code=403, detail="Demo reset is disabled in this environment.")
    workflow_service.reset_demo(principal.organization_id)
    cloud_hunt_service.reset_demo(principal.organization_id)
    auth_store.record_activity(principal.organization_id, "demo_fixtures_reset", principal.user.id if principal.user else None, {"summary": "Demo fixtures and demo runs were reset; integration configuration was preserved."}, actor_type="User" if principal.user else "System", category="Workspace", target_type="workspace", target_id=principal.organization_id, target_display_name=principal.organization.name)
    return {"status": "ok", "message": "Demo fixtures reset. Organization settings and integration configuration were preserved."}


@app.get("/api/overview")
def overview_dashboard(
    date_range: str = Query("30d", pattern="^(all|today|7d|30d|custom)$"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    principal: Principal = Depends(principal_dependency),
) -> dict[str, object]:
    require_permission(principal, OVERVIEW_READ)
    now = utc_now(); warnings: list[str] = []; unavailable: list[str] = []
    start = created_from
    if date_range == "today": start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == "7d": start = now - timedelta(days=7)
    elif date_range == "30d": start = now - timedelta(days=30)
    if start and start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
    if created_to and created_to.tzinfo is None: created_to = created_to.replace(tzinfo=timezone.utc)
    def in_range(value: datetime | None) -> bool:
        if value is None: return True
        return (not start or value >= start) and (not created_to or value <= created_to)
    sections: dict[str, object] = {}
    try:
        cases = [case for case in cloud_hunt_service.list_cases(principal.organization_id) if in_range(case.updated_at)]
        active = {"pending", "pending_human_review", "needs_more_evidence", "reopened"}
        terminal = {"rejected", "approval_revoked", "waived", "remediation_pr_created", "pr_created"}
        pr_cases = {case.id: case for case in cases if case.source_type == "terraform_pr"}
        cloud_cases = {case.id: case for case in cases if case.source_type == "cloud_hunt"}
        attention = []
        for case in cases:
            if case.status in active or case.status in {"blocked", "failed_safely"}:
                attention.append({"id": case.id, "source_type": case.source_type, "title": case.resource_name, "status": case.status, "risk": case.risk_level, "link": "/approvals" if case.status in active else "/pr-reviews"})
        sections["needs_attention"] = attention[:12]
        eligible = [case for case in cases if case.status not in terminal and case.status not in {"blocked", "failed_safely"} and case.estimated_monthly_savings is not None and case.estimated_monthly_savings > 0]
        sections["top_opportunities"] = [{"id": case.id, "source_type": case.source_type, "title": case.resource_name, "estimated_monthly_savings": case.estimated_monthly_savings, "risk": case.risk_level, "confidence": case.confidence, "status": case.status, "data_source_mode": "Fixture-backed" if case.source_type == "cloud_hunt" else "Connected repository"} for case in sorted(eligible, key=lambda item: item.estimated_monthly_savings, reverse=True)[:8]]
        predicted = sum(float(case.estimated_monthly_savings or 0) for case in eligible)
        sections["metrics"] = {"pr_reviews_needing_attention": sum(case.status in active for case in pr_cases.values()), "pr_reviews_in_progress": sum(case.status not in terminal and case.status not in active for case in pr_cases.values()), "pending_approvals": sum(case.status in active for case in cases), "active_cloud_hunt_findings": sum(case.status in active for case in cloud_cases.values()), "predicted_monthly_savings": predicted}
    except Exception as exc:
        warnings.append("Some case metrics are temporarily unavailable."); unavailable.extend(["pr_reviews", "cloud_findings", "predicted_savings"]); sections["needs_attention"] = []; sections["top_opportunities"] = []; sections["metrics"] = {}
    try:
        hunts = [hunt for hunt in cloud_hunt_service.list_hunts(principal.organization_id) if in_range(hunt.started_at)]
        sections.setdefault("metrics", {}).update({"cloud_hunt_runs_in_progress": sum(hunt.status in {"created", "scanning"} for hunt in hunts), "failed_safe_runs": sum(hunt.status == "failed" for hunt in hunts)})
    except Exception:
        warnings.append("Cloud Hunt run metrics are temporarily unavailable."); unavailable.append("cloud_hunt_runs")
    if principal.permissions.intersection({OUTCOMES_READ}):
        try:
            outcomes = [item for item in outcome_store.list(principal.organization_id) if in_range(item.updated_at)]
            sections["outcome_summary"] = {"verified_success": sum(item.verification_status == "verified_success" for item in outcomes), "verified_partial": sum(item.verification_status == "verified_partial" for item in outcomes), "pending": sum(item.verification_status in {"pending", "waiting_for_deployment", "observing"} for item in outcomes), "insufficient_evidence": sum(item.verification_status == "insufficient_evidence" for item in outcomes), "regressions": sum(item.verification_status == "regression_detected" for item in outcomes), "verified_monthly_savings": sum(float((item.savings_variance or {}).get("observed_monthly_savings") or 0) for item in outcomes if item.verification_status in {"verified_success", "verified_partial"}), "pending_outcome_verifications": sum(item.verification_status in {"pending", "waiting_for_deployment", "observing"} for item in outcomes)}
            sections["metrics"]["regressions_detected"] = sections["outcome_summary"]["regressions"]
        except Exception:
            warnings.append("Outcome verification metrics are temporarily unavailable."); unavailable.append("outcomes")
    try:
        goals = [run for run in workflow_service.list_runs(principal.organization_id) if run.source_type == "manual_demo" and in_range(run.updated_at)]
        sections["metrics"]["active_goals"] = sum(run.status not in {"completed", "failed_safely", "canceled", "blocked", "approved", "pr_created", "remediation_pr_created"} for run in goals)
    except Exception:
        unavailable.append("goals"); warnings.append("Goal metrics are temporarily unavailable.")
    if principal.permissions.intersection({ACTIVITY_READ}):
        try:
            events = [event for event in auth_store.list_activity_events(principal.organization_id) if in_range(event.get("created_at"))]
            sections["recent_activity"] = [{"actor": event.get("actor_display_name"), "actor_type": event.get("actor_type"), "action": event.get("action"), "target": event.get("target_display_name"), "result": event.get("result"), "created_at": event.get("created_at"), "summary": event.get("summary"), "related_case_id": event.get("related_case_id"), "related_run_id": event.get("related_run_id")} for event in sorted(events, key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:8]]
        except Exception:
            unavailable.append("recent_activity"); warnings.append("Recent activity is temporarily unavailable.")
    if principal.permissions.intersection({CLOUD_HUNTS_SCHEDULE_READ}):
        try:
            schedules = schedule_store.list(principal.organization_id); enabled = [item for item in schedules if item.enabled]
            sections["scheduled_hunts"] = {"next": min((item.next_run for item in enabled), default=None), "last": max((item.last_run for item in schedules if item.last_run), default=None), "enabled": len(enabled), "failed": sum(bool(item.last_failure) for item in schedules), "items": [{"id": item.id, "name": item.name, "next_run": item.next_run, "last_run": item.last_run, "enabled": item.enabled, "last_failure": item.last_failure} for item in schedules[:8]]}
        except Exception:
            unavailable.append("scheduled_hunts"); warnings.append("Schedule metrics are temporarily unavailable.")
    integrations = {}
    for name, store, permission in (("aws", aws_integration_store, INTEGRATIONS_AWS_READ), ("github", github_integration_store, INTEGRATIONS_GITHUB_READ), ("jira", jira_integration_store, INTEGRATIONS_JIRA_READ)):
        if permission not in principal.permissions: continue
        try:
            config = store.get(principal.organization_id); checked = getattr(config, "last_validated", None) or getattr(config, "updated_at", None); failure = bool(config.last_failure_summary); integrations[name] = {"status": "disabled" if not config.enabled else "unavailable" if failure else "connected" if checked else "warning", "last_checked": checked, "last_success": config.last_successful_collection, "permission_warning_count": 1 if failure else 0}
        except Exception:
            integrations[name] = {"status": "unavailable", "last_checked": None, "last_success": None, "permission_warning_count": 0}; warnings.append(f"{name} integration health is temporarily unavailable.")
    sections["integration_health"] = integrations
    sections["metrics"].setdefault("verified_monthly_savings", sections.get("outcome_summary", {}).get("verified_monthly_savings", 0))
    sections["metrics"].setdefault("pending_outcome_verifications", sections.get("outcome_summary", {}).get("pending_outcome_verifications", 0))
    return {"generated_at": now, "timezone": principal.organization.timezone, "partial_data": bool(warnings or unavailable), "warnings": warnings, "unavailable_metrics": sorted(set(unavailable)), **sections}


def _outcome_audit(outcome, event_type: str, summary: str, principal: Principal, result: str = "success") -> None:
    try:
        run = workflow_service.get_run(outcome.case_id, principal.organization_id)
        append_audit_event(run, event_type=event_type, actor="tool", summary=summary, correlation_id=outcome.correlation_id, details={"outcome_id": str(outcome.id), "status": outcome.verification_status})
        workflow_service.store.update(run.id, run, principal.organization_id)
    except RunNotFoundError:
        pass
    auth_store.record_activity(principal.organization_id, event_type, principal.user.id if principal.user else None, {"outcome_id": str(outcome.id), "case_id": str(outcome.case_id), "correlation_id": outcome.correlation_id, "status": outcome.verification_status}, actor_type="User" if principal.user else "System", category="System", result=result, correlation_id=outcome.correlation_id, related_case_id=outcome.case_id)


@app.get("/api/outcomes")
def list_outcomes(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_READ)
    return {"items": outcome_store.list(principal.organization_id), "summary": {"predicted_savings": sum(float(i.prediction_snapshot.get("predicted_monthly_savings") or 0) for i in outcome_store.list(principal.organization_id)), "verified_savings": sum(float((i.savings_variance or {}).get("observed_monthly_savings") or 0) for i in outcome_store.list(principal.organization_id) if i.verification_status in {"verified_success", "verified_partial"}), "pending_verification": sum(i.verification_status in {"pending", "waiting_for_deployment", "observing"} for i in outcome_store.list(principal.organization_id)), "regressions_detected": sum(i.verification_status == "regression_detected" for i in outcome_store.list(principal.organization_id))}}


@app.get("/api/outcomes/{outcome_id}")
def get_outcome(outcome_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_READ)
    try: return outcome_store.get(outcome_id, principal.organization_id)
    except OutcomeNotFoundError as exc: raise HTTPException(status_code=404, detail="Outcome verification not found.") from exc


@app.post("/api/runs/{run_id}/outcome-verification")
def start_outcome_verification(run_id: UUID, request: OutcomeStartRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_START)
    try:
        run = workflow_service.get_run(run_id, principal.organization_id)
        outcome = outcome_verification_service.start(run, request, principal.organization_id)
        _outcome_audit(outcome, "verification_started", "Outcome verification started; deployment confirmation is still required.", principal)
        return outcome
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail="Case not found.") from exc
    except OutcomeConflictError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/outcomes/{outcome_id}/deployment-confirmation")
def confirm_outcome_deployment(outcome_id: UUID, request: OutcomeStartRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_START)
    try:
        current = outcome_store.get(outcome_id, principal.organization_id); outcome = outcome_verification_service.confirm_deployment(current, request.expected_version, request.idempotency_key)
        _outcome_audit(outcome, "deployment_confirmed", "Deployment was confirmed by an authenticated user.", principal); return outcome
    except OutcomeNotFoundError as exc: raise HTTPException(status_code=404, detail="Outcome verification not found.") from exc
    except OutcomeConflictError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/outcomes/{outcome_id}/refresh")
def refresh_outcome(outcome_id: UUID, request: OutcomeObservationRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_REFRESH)
    try:
        current = outcome_store.get(outcome_id, principal.organization_id); outcome = outcome_verification_service.observe(current, request)
        _outcome_audit(outcome, "verification_evidence_collected", "Read-only post-change evidence was refreshed.", principal); return outcome
    except OutcomeNotFoundError as exc: raise HTTPException(status_code=404, detail="Outcome verification not found.") from exc
    except OutcomeConflictError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/outcomes/{outcome_id}/complete")
def complete_outcome(outcome_id: UUID, request: OutcomeCompleteRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_COMPLETE)
    try:
        current = outcome_store.get(outcome_id, principal.organization_id); outcome = outcome_verification_service.complete(current, request)
        _outcome_audit(outcome, "verification_completed" if outcome.verification_status not in {"regression_detected", "insufficient_evidence"} else "verification_result_calculated", "Outcome verification result calculated without infrastructure mutation.", principal)
        if outcome.verification_status == "regression_detected": _outcome_audit(outcome, "regression_detected", "Regression detected; human review is required and no rollback was performed.", principal, "warning")
        return outcome
    except OutcomeNotFoundError as exc: raise HTTPException(status_code=404, detail="Outcome verification not found.") from exc
    except OutcomeConflictError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/outcomes/{outcome_id}/reopen")
def reopen_outcome(outcome_id: UUID, request: OutcomeReopenRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, OUTCOMES_REOPEN)
    try:
        current = outcome_store.get(outcome_id, principal.organization_id); outcome = outcome_verification_service.reopen(current, request)
        _outcome_audit(outcome, "case_reopened", "Outcome was routed to human review; no rollback was performed.", principal, "warning"); return outcome
    except OutcomeNotFoundError as exc: raise HTTPException(status_code=404, detail="Outcome verification not found.") from exc
    except OutcomeConflictError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/assistant/ask", response_model=AskGhostBustersResponse)
def ask_ghostbusters(request: AskGhostBustersRequest, principal: Principal = Depends(principal_dependency)) -> AskGhostBustersResponse:
    require_permission(principal, WORKSPACE_READ)
    try:
        return assistant_service.ask(request)
    except AssistantValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RunNotFoundError, CloudHuntNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {exc}") from exc


@app.get("/api/cloud/providers")
def cloud_providers(principal: Principal = Depends(principal_dependency)) -> list[dict[str, object]]:
    require_permission(principal, CLOUD_HUNTS_READ)
    return cloud_hunt_service.providers()


@app.get("/api/cloud/schedules")
def list_cloud_hunt_schedules(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_READ)
    return schedule_store.list(principal.organization_id)


@app.post("/api/cloud/schedules")
def create_cloud_hunt_schedule(request: CloudHuntScheduleRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    try:
        schedule = schedule_store.create(request, principal.organization_id, principal.user.id if principal.user else None, principal.user.display_name if principal.user else "System")
        auth_store.record_activity(principal.organization_id, "cloud_hunt_schedule_created", principal.user.id if principal.user else None, {"schedule_id": str(schedule.id), "correlation_id": str(schedule.id)}, actor_type="User" if principal.user else "System", category="Cloud Hunt", target_type="schedule", target_id=schedule.id, target_display_name=schedule.name)
        return schedule
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/cloud/schedules/{schedule_id}")
def update_cloud_hunt_schedule(schedule_id: UUID, request: CloudHuntScheduleRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    try: return schedule_store.update(schedule_id, request, principal.organization_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/cloud/schedules/{schedule_id}/enabled")
def toggle_cloud_hunt_schedule(schedule_id: UUID, request: CloudHuntScheduleToggleRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    try: return schedule_store.toggle(schedule_id, request.enabled, principal.organization_id, request.expected_version)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/cloud/schedules/{schedule_id}")
def delete_cloud_hunt_schedule(schedule_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    try: schedule_store.delete(schedule_id, principal.organization_id); return {"status": "deleted"}
    except KeyError as exc: raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/cloud/schedules/{schedule_id}/run-now")
def run_cloud_hunt_schedule_now(schedule_id: UUID, request: Request, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    require_permission(principal, CLOUD_HUNTS_RUN)
    rate_limiter.check(request, "cloud_hunt_run_now", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    try:
        schedule = schedule_store.get(schedule_id, principal.organization_id)
        hunt = CloudHuntScheduler(cloud_hunt_service, schedule_store).trigger(schedule, force=True)
        if hunt is None: raise HTTPException(status_code=409, detail="Schedule is disabled, already running, or already triggered.")
        auth_store.record_activity(principal.organization_id, "cloud_hunt_schedule_run_triggered", principal.user.id if principal.user else None, {"schedule_id": str(schedule_id), "hunt_id": str(hunt.id), "correlation_id": str(schedule_id)}, actor_type="User", category="Cloud Hunt", target_type="schedule", target_id=schedule_id, target_display_name=schedule.name, related_run_id=hunt.id)
        return hunt
    except KeyError as exc: raise HTTPException(status_code=404, detail="Schedule not found.") from exc


@app.get("/api/cloud/schedules/{schedule_id}/history")
def cloud_hunt_schedule_history(schedule_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_READ)
    try: schedule_store.get(schedule_id, principal.organization_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Schedule not found.") from exc
    return [hunt for hunt in cloud_hunt_service.list_hunts(principal.organization_id) if hunt.schedule_id == schedule_id]


@app.post("/api/cloud/schedules/run-due")
def run_due_cloud_hunt_schedules(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_SCHEDULE_MANAGE)
    hunts = CloudHuntScheduler(cloud_hunt_service, schedule_store).run_due(principal.organization_id)
    return {"items": hunts, "count": len(hunts)}


@app.get("/api/integrations/aws/config")
def get_aws_config(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_AWS_READ)
    return aws_integration_store.get(principal.organization_id)


@app.get("/api/integrations/github/config")
def get_github_config(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_GITHUB_READ)
    return github_integration_store.get(principal.organization_id)


@app.patch("/api/integrations/github/config")
def update_github_config(request: GitHubIntegrationConfigRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_GITHUB_MANAGE)
    try: return github_integration_store.update(principal.organization_id, request)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/integrations/github/connect")
def connect_github(principal: Principal = Depends(principal_dependency)) -> RedirectResponse:
    require_permission(principal, INTEGRATIONS_GITHUB_MANAGE)
    if not settings.github_app_name or not settings.github_app_callback_url or not settings.github_app_id:
        raise HTTPException(status_code=503, detail="GitHub App onboarding is not configured.")
    state = github_app_state.create(str(principal.organization_id), str(principal.user.id if principal.user else ""))
    url = f"https://github.com/apps/{settings.github_app_name}/installations/new?state={state}"
    auth_store.record_activity(principal.organization_id, "github_connection_started", principal.user.id if principal.user else None, {"correlation_id": state.split(".", 1)[0]}, actor_type="Integration", category="Integrations")
    return RedirectResponse(url=url, status_code=307)


@app.get("/api/integrations/github/callback")
def github_callback(state: str, installation_id: int | None = None, setup_action: str | None = None) -> RedirectResponse:
    try: payload = github_app_state.consume(state)
    except ValueError as exc: return RedirectResponse(url="/?github=error&reason=invalid_state", status_code=303)
    organization_id = UUID(str(payload["organization_id"]))
    if not installation_id: return RedirectResponse(url="/?github=error&reason=missing_installation", status_code=303)
    stage = "create_client"
    try:
        app_client = GitHubAppClient(installation_id)
        stage = "fetch_installation"
        installation = app_client.installation()
        stage = "create_api_client"
        client = app_client.api_client()
        stage = "list_repositories"
        repositories = client.list_installation_repositories()
        safe = [{"full_name": item.get("full_name"), "private": bool(item.get("private")), "archived": bool(item.get("archived")), "default_branch": (item.get("default_branch") or "main"), "installation_access": "available"} for item in repositories if item.get("full_name")]
        stage = "persist_installation"
        github_integration_store.update_installation(organization_id, installation_id=installation_id, account_login=(installation.get("account") or {}).get("login"), account_type=(installation.get("account") or {}).get("type"), repository_selection=str(installation.get("repository_selection") or "selected"), repositories=safe)
        stage = "record_activity"
        auth_store.record_activity(organization_id, "github_connection_completed", UUID(str(payload["user_id"])) if payload.get("user_id") else None, {"installation_id": installation_id, "repository_count": len(safe), "correlation_id": state.split(".", 1)[0]}, actor_type="Integration", category="Integrations")
        return RedirectResponse(url="/?github=connected", status_code=303)
    except Exception as exc:
        logger.exception("GitHub App callback failed", extra={"stage": stage, "organization_id": str(organization_id), "installation_id": installation_id, "setup_action": setup_action, "exception_class": type(exc).__name__})
        try:
            auth_store.record_activity(organization_id, "github_connection_failed", UUID(str(payload["user_id"])) if payload.get("user_id") else None, {"reason": "GitHub App connection failed safely.", "correlation_id": "github_callback"}, actor_type="Integration", category="Integrations", result="failure")
        except Exception as activity_exc:
            logger.warning("GitHub callback failure activity recording failed", extra={"stage": "record_activity", "organization_id": str(organization_id), "installation_id": installation_id, "exception_class": type(activity_exc).__name__})
        return RedirectResponse(url="/?github=error&reason=connection_failed", status_code=303)


@app.get("/api/integrations/github/repositories")
def github_repositories(principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, INTEGRATIONS_GITHUB_READ)
    config = github_integration_store.get(principal.organization_id)
    if config.installation_id:
        try:
            repositories = GitHubAppClient(config.installation_id).api_client().list_installation_repositories()
            safe = [{"full_name": item.get("full_name"), "private": bool(item.get("private")), "archived": bool(item.get("archived")), "default_branch": item.get("default_branch") or "main", "installation_access": "available"} for item in repositories if item.get("full_name")]
            github_integration_store.update_installation(principal.organization_id, installation_id=config.installation_id, account_login=config.account_login, account_type=config.account_type, repository_selection=config.repository_selection, repositories=safe)
            return {"items": safe, "count": len(safe)}
        except GitHubAPIError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    if settings.github_development_token_fallback and settings.github_token:
        items = GitHubContextAdapter(workflow_service.github_client, config.allowed_repositories, config.source_mode).validate().get("accessible_repositories", []) if workflow_service.github_client else []
        return {"items": [{"full_name": name, "installation_access": "development_token"} for name in items], "count": len(items), "source_mode": "development_token_fallback"}
    return {"items": [], "count": 0, "source_mode": "not_connected"}


@app.post("/api/integrations/github/disconnect")
def disconnect_github(request: Request, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_GITHUB_MANAGE)
    config = github_integration_store.get(principal.organization_id)
    try: updated = github_integration_store.disconnect(principal.organization_id, config.version)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    auth_store.record_activity(principal.organization_id, "github_disconnected", principal.user.id if principal.user else None, {"correlation_id": request.headers.get("X-Correlation-ID")}, actor_type="Integration", category="Integrations")
    return updated


@app.get("/api/integrations/jira/config")
def get_jira_config(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_JIRA_READ)
    return jira_integration_store.get(principal.organization_id)


@app.patch("/api/integrations/jira/config")
def update_jira_config(request: JiraIntegrationConfigRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_JIRA_MANAGE)
    return jira_integration_store.update(principal.organization_id, request)


@app.post("/api/integrations/jira/validate")
def validate_jira_connection(request: Request, principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, INTEGRATIONS_JIRA_READ)
    rate_limiter.check(request, "integration_validation", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    config = jira_integration_store.get(principal.organization_id)
    base_url = config.base_url or settings.jira_base_url
    if not base_url or not settings.jira_api_token:
        result = {"connected": False, "account_identity": None, "accessible_projects": [], "permission_warnings": [], "missing_permissions": ["Jira credentials or base URL are unavailable."], "checked_at": utc_now()}
    else:
        result = JiraContextAdapter(JiraClient(base_url, settings.jira_email, settings.jira_api_token, settings.jira_request_timeout_seconds), config.allowed_projects, config.source_mode).validate()
    jira_integration_store.mark_validation(principal.organization_id, bool(result["connected"]), "; ".join(result["missing_permissions"]))
    auth_store.record_activity(principal.organization_id, "jira_validation_succeeded" if result["connected"] else "jira_validation_failed", principal.user.id if principal.user else None, {"account_identity": result["account_identity"], "missing_permissions": result["missing_permissions"]}, actor_type="Integration", category="Integrations", result="success" if result["connected"] else "failure")
    return result


@app.post("/api/runs/{run_id}/jira-context", response_model=WorkflowRun)
def collect_jira_context(run_id: UUID, request: JiraContextRequest, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, BUSINESS_CONTEXT_READ)
    try:
        run = workflow_service.get_run(run_id)
        if run.organization_id != principal.organization_id: raise RunNotFoundError(str(run_id))
        config = jira_integration_store.get(principal.organization_id)
        base_url = config.base_url or settings.jira_base_url
        if not base_url or not settings.jira_api_token: raise HTTPException(status_code=503, detail="Jira credentials are unavailable.")
        adapter = JiraContextAdapter(JiraClient(base_url, settings.jira_email, settings.jira_api_token, settings.jira_request_timeout_seconds), config.allowed_projects, config.source_mode)
        if not request.issue_key and not request.project_key: raise HTTPException(status_code=422, detail="An issue key or project key is required.")
        context = adapter.collect_issue_context(request.issue_key, run.correlation_id) if request.issue_key else adapter.collect_project_context(request.project_key, run.correlation_id)
        run.jira_context = context
        conflict = detect_jira_github_conflict(context, run.github_context)
        if conflict:
            context["conflict"] = conflict
            append_audit_event(run, event_type="jira_github_conflict", actor="tool", summary=conflict["summary"], details=conflict)
        append_audit_event(run, event_type="jira_context_collected", actor="tool", summary="Read-only Jira business context collected.", details={"project_key": context.get("project_key"), "issue_key": context.get("issue_key")})
        run = workflow_service.store.update(run_id, run, principal.organization_id)
        jira_integration_store.mark_collection(principal.organization_id, True)
        auth_store.record_activity(principal.organization_id, "jira_context_collected", principal.user.id if principal.user else None, {"run_id": str(run_id), "project_key": context.get("project_key"), "issue_key": context.get("issue_key"), "correlation_id": run.correlation_id}, actor_type="Integration", category="Integrations", related_run_id=run_id)
        return run
    except RunNotFoundError as exc: raise HTTPException(status_code=404, detail="Run not found.") from exc
    except JiraAPIError as exc:
        jira_integration_store.mark_collection(principal.organization_id, False, str(exc))
        raise HTTPException(status_code=403 if exc.category == "authorization" else 409, detail=str(exc)) from exc


@app.post("/api/integrations/github/validate")
def validate_github_connection(request: Request, principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, INTEGRATIONS_GITHUB_READ)
    rate_limiter.check(request, "integration_validation", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    config = github_integration_store.get(principal.organization_id)
    if config.installation_id:
        stage = "fetch_installation"
        try:
            app_client = GitHubAppClient(config.installation_id)
            stage = "validate_installation"
            validation = app_client.validate_installation(config.allowed_repositories)
            stage = "persist_installation"
            installation = validation["installation"]
            repositories = validation["repositories"]
            missing_permissions = [f"{name}: read" for name in validation["missing_permissions"]]
            github_integration_store.update_installation(
                principal.organization_id,
                installation_id=config.installation_id,
                account_login=validation["account_identity"],
                account_type=(installation.get("account") or {}).get("type"),
                repository_selection=str(installation.get("repository_selection") or config.repository_selection),
                repositories=repositories,
            )
            result = {"connected": not missing_permissions, "account_identity": validation["account_identity"], "accessible_repositories": [str(item["full_name"]) for item in repositories], "permission_warnings": [f"Missing GitHub App permissions: {', '.join(missing_permissions)}"] if missing_permissions else [], "missing_permissions": missing_permissions, "checked_at": utc_now()}
            if missing_permissions:
                github_integration_store.mark_validation(principal.organization_id, False, "; ".join(missing_permissions))
        except Exception as exc:
            logger.exception("GitHub App validation failed", extra={"organization_id": str(principal.organization_id), "installation_id": config.installation_id, "stage": stage, "exception_class": type(exc).__name__})
            github_integration_store.mark_validation(principal.organization_id, False, "GitHub App installation validation failed safely.")
            result = {"connected": False, "account_identity": config.account_login, "accessible_repositories": [str(item.get("full_name")) for item in config.connected_repositories if item.get("full_name")], "permission_warnings": ["Validation failed; showing last known repository access."], "missing_permissions": ["GitHub App installation access"], "checked_at": utc_now()}
    else:
        github_client = workflow_service.github_client if settings.github_development_token_fallback else None
        if github_client is None:
            result = {"connected": False, "account_identity": None, "accessible_repositories": [], "permission_warnings": [], "missing_permissions": ["GitHub credentials are unavailable."], "checked_at": utc_now()}
        else:
            result = GitHubContextAdapter(github_client, config.allowed_repositories, config.source_mode).validate()
        github_integration_store.mark_validation(principal.organization_id, bool(result["connected"]), "; ".join(result["missing_permissions"]))
    if result["connected"]:
        auth_store.record_activity(principal.organization_id, "github_validation_succeeded", principal.user.id if principal.user else None, {"account_identity": result["account_identity"]}, actor_type="Integration", category="Integrations")
    else:
        auth_store.record_activity(principal.organization_id, "github_validation_failed", principal.user.id if principal.user else None, {"missing_permissions": result["missing_permissions"]}, actor_type="Integration", category="Integrations", result="failure")
    return result


@app.patch("/api/integrations/aws/config")
def update_aws_config(request: AWSIntegrationConfigRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, INTEGRATIONS_AWS_MANAGE)
    return aws_integration_store.update(principal.organization_id, request)


@app.post("/api/integrations/aws/validate")
def validate_aws_connection(request: Request, principal: Principal = Depends(principal_dependency)) -> dict[str, object]:
    require_permission(principal, INTEGRATIONS_AWS_READ)
    rate_limiter.check(request, "integration_validation", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds, principal.organization_id)
    config = aws_integration_store.get(principal.organization_id)
    regions = config.regions or ([settings.aws_region] if settings.aws_region else list(settings.aws_allowed_regions))
    adapter = RealAWSCloudAdapter(regions, config.cloudwatch_lookback_days, config.low_cpu_threshold)
    result = adapter.validate()
    if result["connected"]:
        aws_integration_store.mark_collection(principal.organization_id, True)
    else:
        aws_integration_store.mark_collection(principal.organization_id, False, "; ".join(result["missing_permissions"]))
    return result


@app.get("/api/cloud/hunt/fixtures")
def cloud_hunt_fixtures(provider_scope: str = Query("multi_cloud"), principal: Principal = Depends(principal_dependency)) -> list[object]:
    require_permission(principal, CLOUD_HUNTS_READ)
    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=404, detail="Fixture inventory is disabled.")
    return cloud_hunt_service.fixtures(provider_scope)


@app.post("/api/cloud/hunts")
def start_cloud_hunt(request: CloudHuntRequest, fastapi_request: Request, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_RUN)
    if request.inventory_source == "fixtures" and not settings.demo_mode_enabled:
        raise HTTPException(status_code=503, detail="Fixture-backed Cloud Hunt is disabled. Connect a cloud account for live inventory.")
    rate_limiter.check(fastapi_request, "cloud_hunt_run", principal.user.id if principal.user else None, settings.expensive_rate_limit_attempts, settings.expensive_rate_limit_window_seconds)
    try:
        registry_override = None
        if request.inventory_source == "real_aws":
            config = aws_integration_store.get(principal.organization_id)
            if not config.enabled:
                raise CloudHuntConflictError("Real AWS mode is disabled for this organization.")
            regions = config.regions or ([settings.aws_region] if settings.aws_region else list(settings.aws_allowed_regions))
            adapter = RealAWSCloudAdapter(regions, config.cloudwatch_lookback_days, config.low_cpu_threshold)
            validation = adapter.validate()
            if not validation["connected"]:
                raise CloudHuntConflictError("AWS validation failed safely; real AWS mode did not fall back to fixtures.")
            registry_override = CloudProviderRegistry([adapter])
        hunt = cloud_hunt_service.start_hunt(
            request,
            principal.organization_id,
            principal.user.id if principal.user else None,
            principal.user.display_name if principal.user else None,
            registry_override,
        )
        auth_store.record_activity(principal.organization_id, "cloud_hunt_started", principal.user.id if principal.user else None, {"hunt_id": str(hunt.id), "provider_scope": request.provider_scope}, actor_type="User" if principal.user else "System", category="Cloud Hunt", target_type="hunt", target_id=hunt.id, target_display_name=f"Cloud Hunt {hunt.id}", related_run_id=hunt.id)
        auth_store.record_activity(principal.organization_id, "cloud_hunt_completed", None, {"hunt_id": str(hunt.id), "candidates": hunt.candidates_found}, actor_type="Agent", category="Cloud Hunt", target_type="hunt", target_id=hunt.id, target_display_name=f"Cloud Hunt {hunt.id}", related_run_id=hunt.id)
        return hunt
    except CloudHuntConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/cloud/hunts")
def list_cloud_hunts(
    status: str | None = None,
    provider: str | None = None,
    started_by: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    search: str | None = None,
    sort: str | None = None,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    principal: Principal = Depends(principal_dependency),
):
    require_permission(principal, CLOUD_HUNTS_READ)
    hunts = cloud_hunt_service.list_hunts(principal.organization_id)
    if not any(value is not None for value in (status, provider, started_by, created_from, created_to, search, sort, page, page_size)):
        return hunts
    allowed_sorts = {"newest", "oldest", "highest_waste", "most_candidates", "longest_duration"}
    if sort and sort not in allowed_sorts:
        raise HTTPException(status_code=422, detail="Unknown Cloud Hunt sort.")

    def aware(value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    start, end = aware(created_from), aware(created_to)
    cases = cloud_hunt_service.list_cases(principal.organization_id)
    active_statuses = {"pending", "pending_human_review", "needs_more_evidence", "reopened"}
    case_counts = {
        str(run.id): sum(1 for case in cases if case.source_type == "cloud_hunt" and case.source_reference == str(run.id) and case.status in active_statuses)
        for run in hunts
    }
    filtered = []
    for run in hunts:
        started = run.started_at
        actor = run.started_by_display_name or "System"
        run_number = f"CH-{started.year}-{str(run.id)[:8].upper()}"
        duration = (run.completed_at - started).total_seconds() if run.completed_at else None
        haystack = " ".join((run_number, run.provider_scope, actor, run.inventory_source, run.goal)).lower()
        normalized_status = "failed" if status == "failed" and run.status == "failed" else status
        if normalized_status and run.status != normalized_status:
            continue
        if provider and provider.lower() not in run.provider_scope.lower():
            continue
        if started_by and started_by.lower() not in f"{actor} {run.started_by_user_id or ''}".lower():
            continue
        if (start and started < start) or (end and started > end):
            continue
        if search and search.strip().lower() not in haystack:
            continue
        filtered.append({
            "id": run.id,
            "run_number": run_number,
            "organization_id": run.organization_id,
            "provider_scope": run.provider_scope,
            "started_by_user_id": run.started_by_user_id,
            "started_by": actor,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "duration_seconds": duration,
            "resources_scanned": run.resources_scanned,
            "candidates_found": run.candidates_found,
            "protected_resources": run.protected_resources,
            "pending_reviews": case_counts[str(run.id)],
            "estimated_monthly_waste": run.summary.estimated_monthly_waste,
            "status": run.status,
            "data_source_mode": run.data_source_mode,
            "inventory_source": run.inventory_source,
            "warnings": run.errors,
        })
    sort_key = sort or "newest"
    if sort_key == "oldest":
        filtered.sort(key=lambda item: item["started_at"])
    elif sort_key == "highest_waste":
        filtered.sort(key=lambda item: item["estimated_monthly_waste"], reverse=True)
    elif sort_key == "most_candidates":
        filtered.sort(key=lambda item: item["candidates_found"], reverse=True)
    elif sort_key == "longest_duration":
        filtered.sort(key=lambda item: item["duration_seconds"] or 0, reverse=True)
    else:
        filtered.sort(key=lambda item: item["started_at"], reverse=True)
    actual_page, actual_size = page or 1, page_size or 20
    offset = (actual_page - 1) * actual_size
    return {"items": filtered[offset:offset + actual_size], "total": len(filtered), "page": actual_page, "page_size": actual_size, "has_next": offset + actual_size < len(filtered)}


@app.get("/api/cloud/hunts/{hunt_id}")
def get_cloud_hunt(hunt_id: UUID, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_READ)
    try:
        return cloud_hunt_service.get_hunt(hunt_id, principal.organization_id)
    except CloudHuntNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/reviews", response_model=list[ReviewCase])
def list_review_cases(
    source_type: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    required_role: str | None = None,
    risk: str | None = None,
    principal: Principal = Depends(principal_dependency),
) -> list[ReviewCase]:
    require_permission(principal, APPROVALS_READ)
    cases = cloud_hunt_service.list_cases(principal.organization_id)
    return [case for case in cases if
            (source_type is None or case.source_type == source_type) and
            (provider is None or case.provider == provider) and
            (status is None or case.status == status) and
            (required_role is None or case.required_reviewer_role == required_role) and
            (risk is None or case.risk_level == risk)]


@app.get("/api/reviews/{review_id}", response_model=ReviewCase)
def get_review_case(review_id: UUID, principal: Principal = Depends(principal_dependency)) -> ReviewCase:
    require_permission(principal, APPROVALS_READ)
    try:
        return cloud_hunt_service.get_case(review_id, principal.organization_id)
    except CloudHuntNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/reviews/{review_id}/action")
def act_on_review_case(review_id: UUID, request: ReviewCaseActionRequest, principal: Principal = Depends(principal_dependency)):
    if request.action == "waive":
        require_permission(principal, APPROVALS_DECIDE)
    else:
        require_permission(principal, ACTION_PERMISSIONS[request.action])
        _validate_decision_contract(request, {"pricing", "utilization", "jira", "git_activity", "dependencies", "owner", "cost", "activity"})
    reviewer = principal.reviewer_name if principal.authenticated else request.reviewer
    secured_request = request.model_copy(update={"reviewer": reviewer, "comment": _trim(request.comment), "human_context": _trim(request.human_context), "idempotency_key": _trim(request.idempotency_key)})
    fingerprint = normalized_fingerprint(_decision_payload(review_id, "review_case", secured_request, principal))
    replay = None if request.action == "waive" else decision_event_store.replay(principal.organization_id, secured_request.idempotency_key or "", fingerprint)
    if replay is not None:
        return replay
    correlation_id = secrets.token_urlsafe(18)
    try:
        previous_case = cloud_hunt_service.get_case(review_id, principal.organization_id).model_dump(mode="json")
        case = cloud_hunt_service.act_on_case(
            review_id,
            secured_request,
            principal.organization_id,
            principal.user.id if principal.user else None,
            principal.user.email if principal.user else None,
            principal.membership.role,
        )
        case.audit_events.append(
            AuditEvent(
                sequence_number=len(case.audit_events) + 1,
                timestamp=utc_now(),
                event_type="human_decision_event_recorded",
                actor="system",
                summary="Human decision event recorded.",
                details={"correlation_id": correlation_id, "action": secured_request.action},
            )
        )
        cloud_hunt_service._cases[case.id] = case.model_copy(deep=True)
        if cloud_hunt_service.persistence is not None:
            cloud_hunt_service.persistence.save_case(case)
        case_dict = case.model_dump(mode="json")
        return _record_decision_success(
            case_id=review_id,
            case_type="review_case",
            action=secured_request.action,
            request=secured_request,
            principal=principal,
            previous_state={"status": previous_case.get("status"), "version": previous_case.get("version"), "updated_at": previous_case.get("updated_at")},
            resulting=case_dict,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CloudHuntNotFoundError:
        if secured_request.action == "waive":
            raise HTTPException(status_code=404, detail="Cloud Hunt review case not found.")
        try:
            run_request = HumanReviewRequest(
                action=secured_request.action, reviewer=secured_request.reviewer, comment=secured_request.comment,
                requested_sources=secured_request.requested_sources, modified_action=secured_request.modified_action, human_context=secured_request.human_context,
                expected_version=secured_request.expected_version, idempotency_key=secured_request.idempotency_key,
            )
            previous_run = workflow_service.get_run(review_id, principal.organization_id).model_dump(mode="json")
            run, _ = workflow_service.review_run(review_id, run_request, principal.organization_id, principal.user.id if principal.user else None, principal.user.email if principal.user else None, principal.membership.role, secured_request.expected_version)
            append_audit_event(run, event_type="human_decision_event_recorded", actor="system", summary="Human decision event recorded.", details={"correlation_id": correlation_id, "action": secured_request.action})
            run = workflow_service.store.update(run.id, run, principal.organization_id)
            case = next(case for case in cloud_hunt_service.list_cases(principal.organization_id) if case.id == review_id)
            return _record_decision_success(
                case_id=review_id,
                case_type="workflow_run",
                action=secured_request.action,
                request=secured_request,
                principal=principal,
                previous_state={"status": previous_run.get("status"), "version": previous_run.get("version"), "updated_at": previous_run.get("updated_at")},
                resulting={**case.model_dump(mode="json"), "version": run.version, "status": run.status.value},
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
        except (StopIteration, WorkflowConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CloudHuntConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    response: Response,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, object]:
    rate_limiter.check(request, "github_webhook", limit=settings.expensive_rate_limit_attempts, window_seconds=settings.expensive_rate_limit_window_seconds)
    if not x_github_delivery:
        raise HTTPException(status_code=422, detail="X-GitHub-Delivery header is required.")
    raw_body = await request.body()
    if len(raw_body) > settings.max_request_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds the configured request size limit.")
    if settings.github_integration_enabled and not verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Unsupported event: {x_github_event}"}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook JSON.") from exc
    action = payload.get("action")
    installation_id = int((payload.get("installation") or {}).get("id") or 0)
    if x_github_event in {"installation", "installation_repositories"}:
        association = github_integration_store.find_by_installation(installation_id) if installation_id else None
        if association:
            organization_id, config = association
            if x_github_event == "installation" and action == "deleted":
                github_integration_store.disconnect(organization_id)
                event_name = "github_installation_removed"
            else:
                current = {item.get("full_name"): item for item in config.connected_repositories if item.get("full_name")}
                for item in (payload.get("repositories_added") or []):
                    if item.get("full_name"): current[item["full_name"]] = {"full_name": item.get("full_name"), "private": bool(item.get("private")), "archived": bool(item.get("archived")), "default_branch": item.get("default_branch") or "main", "installation_access": "available"}
                for item in (payload.get("repositories_removed") or []): current.pop(item.get("full_name"), None)
                github_integration_store.update_installation(organization_id, installation_id=installation_id, account_login=config.account_login, account_type=config.account_type, repository_selection=config.repository_selection, repositories=list(current.values()))
                event_name = "github_repositories_changed"
            auth_store.record_activity(organization_id, event_name, None, {"installation_id": installation_id, "action": action, "correlation_id": x_github_delivery}, actor_type="Integration", category="Integrations", correlation_id=x_github_delivery)
        return {"status": "processed" if association else "ignored", "event": x_github_event}
    if action not in {"opened", "reopened", "synchronize"}:
        return {"status": "ignored", "reason": f"Unsupported pull_request action: {action}"}
    repository_delivery = bool(payload.get("repository") or payload.get("pull_request"))
    association = github_integration_store.find_by_installation(installation_id) if installation_id else None
    if installation_id and association is None:
        raise HTTPException(status_code=403, detail="GitHub installation is not connected to an organization.")
    if settings.app_env == "production" and association is None:
        raise HTTPException(status_code=403, detail="GitHub App installation is not connected to an organization.")
    webhook_organization_id = association[0] if association else DEFAULT_DEVELOPMENT_ORGANIZATION_ID
    cached_run_id = webhook_deduplicator.get_run_id(x_github_delivery)
    if cached_run_id is not None:
        try:
            cached_run = workflow_service.get_run(cached_run_id, webhook_organization_id)
            cached_legacy_github_run = (
                settings.github_integration_enabled
                and repository_delivery
                and cached_run.source_type == "manual_demo"
                and cached_run.github_source is None
            )
            if not cached_legacy_github_run:
                return {"status": "duplicate", "run": cached_run}
        except RunNotFoundError:
            pass
    durable = workflow_service.find_run_by_idempotency(x_github_delivery, webhook_organization_id)
    legacy_github_run = (
        durable is not None
        and settings.github_integration_enabled
        and durable.source_type == "manual_demo"
        and durable.github_source is None
        and repository_delivery
    )
    if durable is not None and not legacy_github_run:
        return {"status": "duplicate", "run": durable}
    if settings.github_integration_enabled:
        repository = str((payload.get("repository") or {}).get("full_name") or "")
        installation_id = int((payload.get("installation") or {}).get("id") or 0)
        allowed_repositories = association[1].allowed_repositories if association else settings.github_allowed_repositories
        if not repository_allowed(repository, tuple(allowed_repositories)):
            raise HTTPException(status_code=403, detail="Repository is not allowed for GitHub integration.")
        client = GitHubAppClient(installation_id).api_client() if association else (workflow_service.github_client if settings.github_development_token_fallback else None)
        if client is None:
            raise HTTPException(status_code=503, detail="GitHub integration is enabled but credentials are unavailable.")
        try:
            number = int((payload.get("pull_request") or {}).get("number") or payload.get("number"))
            owner, repo = repository.split("/", 1)
            pr = client.get_pull_request(owner, repo, number)
            files = client.list_pull_request_files(owner, repo, number)
            selected, _ = select_terraform_files(files)
            head_sha = str((pr.get("head") or {}).get("sha") or "")
            fetched = {item["filename"]: client.get_file_content(owner, repo, item["filename"], head_sha)["content"] for item in selected}
            source = parse_github_terraform_change(repository, pr, files, fetched)
            run, created = workflow_service.start_github_run(source, x_github_delivery, organization_id=webhook_organization_id)
            auth_store.record_activity(webhook_organization_id, "github_pr_review_created", None, {"run_id": str(run.id), "repository": repository, "pull_request": number, "delivery_id": x_github_delivery, "correlation_id": run.correlation_id}, actor_type="Integration", category="PR Reviews", target_type="run", target_id=run.id, target_display_name=f"PR #{number} {repository}", related_run_id=run.id, correlation_id=run.correlation_id)
        except (GitHubAPIError, TerraformAnalysisError, ValueError, KeyError) as exc:
            detail = str(exc) if isinstance(exc, TerraformAnalysisError) else "GitHub integration failed safely."
            raise HTTPException(status_code=422, detail=detail) from exc
        webhook_deduplicator.remember(x_github_delivery, run.id)
        response.status_code = 201 if created else 200
        return {"status": "created" if created else "duplicate", "run": run}
    if repository_delivery or not settings.demo_mode_enabled:
        raise HTTPException(
            status_code=503,
            detail="No live GitHub integration is available for this webhook.",
        )
    goal = payload.get("goal") or "Analyze Terraform pull request for safe FinOps remediation."
    scenario_name = payload.get("scenario_name") or "safe"
    try:
        run, created = workflow_service.start_run(
            StartRunRequest(
                goal=goal,
                scenario_name=scenario_name,
                idempotency_key=x_github_delivery,
            )
        )
    except ScenarioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    webhook_deduplicator.remember(x_github_delivery, run.id)
    response.status_code = 201 if created else 200
    return {"status": "created" if created else "duplicate", "run": run}
