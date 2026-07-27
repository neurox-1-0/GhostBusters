"""FastAPI application entrypoint for GhostBusters."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import (
    AskGhostBustersRequest, AskGhostBustersResponse,
    ChangeMemberRoleRequest, CloudHuntRequest, CurrentUserResponse, HealthResponse,
    HumanReviewRequest, InviteMemberRequest, LoginRequest, RegisterRequest, ReviewCaseActionRequest,
    ReviewCase, StartRunRequest, WorkflowRun,
)
from app.settings import settings
from app.auth import (
    APPROVALS_DECIDE,
    APPROVALS_READ,
    AUDIT_READ,
    CLOUD_HUNTS_READ,
    CLOUD_HUNTS_RUN,
    MEMBERS_INVITE,
    MEMBERS_READ,
    MEMBERS_MANAGE_ROLES,
    PR_REVIEWS_READ,
    WORKSPACE_READ,
    Principal,
    auth_store,
    clear_session_cookies,
    csrf_protect,
    current_principal,
    require_permission,
    session_store,
    set_session_cookies,
    utc_now,
)
from core.run_store import RunNotFoundError
from core.storage_factory import build_webhook_deduplicator
from core.workflow_service import (
    ScenarioNotFoundError,
    WorkflowConflictError,
    list_scenarios,
    workflow_service,
)
from core.cloud_hunt_service import CloudHuntConflictError, CloudHuntNotFoundError, cloud_hunt_service
from core.assistant_service import AssistantValidationError, assistant_service
from integrations.github_client import GitHubAPIError
from integrations.github_webhook import repository_allowed, verify_signature
from integrations.terraform_runner import TerraformAnalysisError, parse_github_terraform_change, select_terraform_files


app = FastAPI(title="GhostBusters", version="0.1.0")
static_path = Path(__file__).resolve().parent.parent / settings.static_dir
webhook_deduplicator = build_webhook_deduplicator()
app.mount("/static", StaticFiles(directory=static_path), name="static")
cloud_hunt_service.workflow_service = workflow_service
assistant_service.workflow = workflow_service
assistant_service.cloud_hunt = cloud_hunt_service


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@app.get("/")
def home() -> FileResponse:
    index_path = static_path / "index.html"
    return FileResponse(index_path)


@app.get("/api/scenarios")
def api_scenarios() -> dict[str, list[str]]:
    return {"scenarios": list_scenarios()}


def principal_dependency(request: Request) -> Principal:
    principal = current_principal(request)
    csrf_protect(request, principal)
    return principal


@app.post("/api/auth/register", response_model=CurrentUserResponse, status_code=201)
def register(request: RegisterRequest, response: Response) -> CurrentUserResponse:
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


@app.post("/api/invitations", status_code=201)
def invite_member(request: InviteMemberRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_INVITE)
    invitation = auth_store.invite(principal, request.email, request.role, request.approval_permission_enabled)
    return {"invitation": invitation, "development_invitation_link": f"/api/invitations/{invitation.id}/accept?token=development-only"}


@app.patch("/api/members/{membership_id}")
def change_member_role(membership_id: UUID, request: ChangeMemberRoleRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, MEMBERS_MANAGE_ROLES)
    return auth_store.change_role(principal, membership_id, request.role, request.approval_permission_enabled)


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
    return run


@app.get("/api/runs", response_model=list[WorkflowRun])
def list_runs(principal: Principal = Depends(principal_dependency)) -> list[WorkflowRun]:
    require_permission(principal, PR_REVIEWS_READ)
    return workflow_service.list_runs(principal.organization_id)


@app.get("/api/runs/{run_id}", response_model=WorkflowRun)
def get_run(run_id: UUID, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, PR_REVIEWS_READ)
    try:
        return workflow_service.get_run(run_id, principal.organization_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/review", response_model=WorkflowRun)
def review_run(run_id: UUID, request: HumanReviewRequest, response: Response, principal: Principal = Depends(principal_dependency)) -> WorkflowRun:
    require_permission(principal, APPROVALS_DECIDE)
    reviewer = principal.reviewer_name if principal.authenticated else request.reviewer
    secured_request = request.model_copy(update={"reviewer": reviewer})
    try:
        run, maybe_pr_created = workflow_service.review_run(
            run_id,
            secured_request,
            principal.organization_id,
            principal.user.id if principal.user else None,
            principal.user.email if principal.user else None,
            principal.membership.role,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if maybe_pr_created and (run.mock_pr is not None or run.real_pr is not None):
        response.status_code = 201
    return run


@app.post("/api/reset")
def reset_runs() -> dict[str, str]:
    result = workflow_service.reset()
    cloud_hunt_service.reset()
    return result


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


@app.get("/api/cloud/hunt/fixtures")
def cloud_hunt_fixtures(provider_scope: str = Query("multi_cloud"), principal: Principal = Depends(principal_dependency)) -> list[object]:
    require_permission(principal, CLOUD_HUNTS_READ)
    return cloud_hunt_service.fixtures(provider_scope)


@app.post("/api/cloud/hunts")
def start_cloud_hunt(request: CloudHuntRequest, principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_RUN)
    try:
        return cloud_hunt_service.start_hunt(request, principal.organization_id)
    except CloudHuntConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/cloud/hunts")
def list_cloud_hunts(principal: Principal = Depends(principal_dependency)):
    require_permission(principal, CLOUD_HUNTS_READ)
    return cloud_hunt_service.list_hunts(principal.organization_id)


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


@app.post("/api/reviews/{review_id}/action", response_model=ReviewCase)
def act_on_review_case(review_id: UUID, request: ReviewCaseActionRequest, principal: Principal = Depends(principal_dependency)) -> ReviewCase:
    require_permission(principal, APPROVALS_DECIDE)
    reviewer = principal.reviewer_name if principal.authenticated else request.reviewer
    secured_request = request.model_copy(update={"reviewer": reviewer})
    try:
        return cloud_hunt_service.act_on_case(
            review_id,
            secured_request,
            principal.organization_id,
            principal.user.id if principal.user else None,
            principal.user.email if principal.user else None,
            principal.membership.role,
        )
    except CloudHuntNotFoundError:
        if secured_request.action == "waive":
            raise HTTPException(status_code=404, detail="Cloud Hunt review case not found.")
        try:
            run_request = HumanReviewRequest(
                action=secured_request.action, reviewer=secured_request.reviewer, comment=secured_request.comment,
                requested_sources=secured_request.requested_sources, modified_action=secured_request.modified_action, human_context=secured_request.human_context,
            )
            workflow_service.review_run(review_id, run_request, principal.organization_id, principal.user.id if principal.user else None, principal.user.email if principal.user else None, principal.membership.role)
            return next(case for case in cloud_hunt_service.list_cases(principal.organization_id) if case.id == review_id)
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
    if not x_github_delivery:
        raise HTTPException(status_code=422, detail="X-GitHub-Delivery header is required.")
    raw_body = await request.body()
    if settings.github_integration_enabled and not verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Unsupported event: {x_github_event}"}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook JSON.") from exc
    action = payload.get("action")
    if action not in {"opened", "reopened", "synchronize"}:
        return {"status": "ignored", "reason": f"Unsupported pull_request action: {action}"}
    repository_delivery = bool(payload.get("repository") or payload.get("pull_request"))
    cached_run_id = webhook_deduplicator.get_run_id(x_github_delivery)
    if cached_run_id is not None:
        try:
            cached_run = workflow_service.get_run(cached_run_id)
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
    durable = workflow_service.find_run_by_idempotency(x_github_delivery)
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
        if not repository_allowed(repository, settings.github_allowed_repositories):
            raise HTTPException(status_code=403, detail="Repository is not allowed for GitHub integration.")
        client = workflow_service.github_client
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
            run, created = workflow_service.start_github_run(source, x_github_delivery)
        except (GitHubAPIError, TerraformAnalysisError, ValueError, KeyError) as exc:
            detail = str(exc) if isinstance(exc, TerraformAnalysisError) else "GitHub integration failed safely."
            raise HTTPException(status_code=422, detail=detail) from exc
        webhook_deduplicator.remember(x_github_delivery, run.id)
        response.status_code = 201 if created else 200
        return {"status": "created" if created else "duplicate", "run": run}
    if repository_delivery:
        raise HTTPException(
            status_code=503,
            detail="GitHub integration is disabled. Enable it and restart the API before delivering repository webhooks.",
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
