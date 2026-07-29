"""Workflow execution service for GhostBusters runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.models import (
    Alternative,
    DecisionRecord,
    EvidenceItem,
    HumanReviewRecord,
    HumanReviewRequest,
    InvestigationPlan,
    MissingEvidenceRecord,
    PolicyResult,
    RunStatus,
    ScenarioDefinition,
    DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
    OrganizationRole,
    StartRunRequest,
    TerraformResourceChange,
    ToolExecutionRecord,
    WorkflowRun,
    GitHubTerraformChange,
)
from app.settings import Settings, settings
from core.alternative_generator import generate_alternatives
from core.audit import append_audit_event
from core.confidence import calculate_confidence
from core.conftest_policy import ConftestPolicyEvaluator, default_policy_evaluator
from core.conflict_detector import detect_conflicts
from core.human_review import (
    HumanReviewError,
    ensure_can_add_context,
    ensure_can_approve,
    ensure_can_modify,
    ensure_can_reject,
    ensure_can_request_evidence,
)
from core.investigator import CRITICAL_SOURCES, collect_evidence
from core.mock_pr import create_mock_pull_request
from core.policy_engine import evaluate_policy
from core.reasoning_engine import _final_status, _select_preferred, analyze_resource
from core.retry import RetryExecutor, default_retry_executor
from core.run_store import DuplicateIdempotencyKeyError, RunNotFoundError, RunStore
from core.storage_factory import build_run_store
from core.verifier import run_verifier
from integrations.base import utc_now
from integrations.registry import ToolRegistry, default_registry
from integrations.terraform_parser import parse_terraform_plan
from integrations.github_client import GitHubClient
from integrations.remediation_pr_service import RemediationPRService, RemediationValidationError


REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = REPO_ROOT / "fixtures" / "scenarios"


class ScenarioNotFoundError(Exception):
    """Raised when a requested scenario fixture is missing."""


class WorkflowConflictError(Exception):
    """Raised for unsafe or invalid workflow transitions."""


class WorkflowValidationError(Exception):
    """Raised for invalid user supplied workflow data."""


def list_scenarios() -> list[str]:
    return sorted(path.stem for path in SCENARIO_DIR.glob("*.json"))


def load_scenario(name: str) -> ScenarioDefinition:
    path = SCENARIO_DIR / f"{name}.json"
    if not path.exists():
        raise ScenarioNotFoundError(f"Unknown scenario: {name}")
    return ScenarioDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))


def map_final_status(final_status: str) -> RunStatus:
    return {
        "recommendation_ready": RunStatus.pending_human_review,
        "blocked": RunStatus.blocked,
        "abstained": RunStatus.abstained,
        "keep": RunStatus.keep,
        "needs_human_context": RunStatus.needs_more_evidence,
    }[final_status]


class WorkflowService:
    def __init__(
        self,
        store: RunStore | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_evaluator: ConftestPolicyEvaluator | None = None,
        retry_executor: RetryExecutor | None = None,
        configuration: Settings = settings,
        ai_client=None,
        github_client: GitHubClient | None = None,
    ) -> None:
        self.store = store or build_run_store()
        self.tool_registry = tool_registry or default_registry
        self.policy_evaluator = policy_evaluator or default_policy_evaluator
        self.retry_executor = retry_executor or default_retry_executor
        self.configuration = configuration
        self.ai_client = ai_client
        self.github_client = github_client or (GitHubClient(configuration.github_token, configuration.github_api_base_url, configuration.github_request_timeout_seconds) if configuration.github_integration_enabled and configuration.github_token else None)

    def start_run(
        self,
        request: StartRunRequest,
        organization_id: UUID = DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
        creator_user_id: UUID | None = None,
        creator_display_name: str | None = None,
    ) -> tuple[WorkflowRun, bool]:
        if request.idempotency_key:
            existing = self.store.find_by_idempotency_key(request.idempotency_key, organization_id)
            if existing is not None:
                return existing, False

        scenario = load_scenario(request.scenario_name)
        now = utc_now()
        run = WorkflowRun(
            id=uuid4(),
            organization_id=organization_id,
            goal=request.goal,
            scenario_name=request.scenario_name,
            status=RunStatus.created,
            created_at=now,
            updated_at=now,
            idempotency_key=request.idempotency_key,
            scope=request.scope,
            constraints=request.constraints,
            success_criteria=request.success_criteria,
            stop_conditions=request.stop_conditions,
            creator_user_id=creator_user_id,
            creator_display_name=creator_display_name,
            data_source_mode=request.data_source_mode,
        )
        append_audit_event(run, event_type="run_created", actor="system", summary="Run created.")
        append_audit_event(run, event_type="goal_received", actor="agent", summary=request.goal, details={"constraints": request.constraints})
        try:
            run = self.store.create(run)
        except DuplicateIdempotencyKeyError:
            if request.idempotency_key:
                existing = self.store.find_by_idempotency_key(request.idempotency_key, organization_id)
                if existing is not None:
                    return existing, False
            raise

        def execute(current: WorkflowRun) -> WorkflowRun:
            try:
                current.status = RunStatus.planning
                resource = parse_terraform_plan(scenario.terraform_plan_file)[0]
                append_audit_event(current, event_type="terraform_parsed", actor="agent", summary="Terraform fixture parsed.", details={"resource_id": resource.address})
                current.status = RunStatus.investigating
                decision = analyze_resource(
                    request.goal,
                    scenario,
                    resource,
                    self.tool_registry,
                    self.policy_evaluator,
                    current.id,
                    self.retry_executor,
                    configuration=self.configuration,
                    ai_client=self.ai_client,
                )
                if request.human_context:
                    decision = self._add_context_to_decision(
                        decision,
                        resource,
                        request.human_context,
                        "starter",
                        current.id,
                        current.scenario_name,
                    )
                current.decision_record = decision
                self._capture_goal_state(current, decision)
                current.status = map_final_status(decision.final_status)
                self._copy_decision_audit(current, decision)
                if current.status == RunStatus.pending_human_review:
                    append_audit_event(current, event_type="human_review_required", actor="agent", summary="Human approval is required before any remediation step.", stage="human_review", status="waiting", decision_impact="Execution paused for authenticated human review.")
                else:
                    append_audit_event(current, event_type="goal_completed", actor="agent", summary="Goal execution completed safely.", stage="completed", status="completed", decision_impact=decision.final_summary)
                current.stop_reason = decision.termination_reason
                current.final_outcome = decision.final_status
            except Exception as exc:
                current.status = RunStatus.failed_safely
                current.error = str(exc)
                append_audit_event(current, event_type="failure_handled_safely", actor="system", summary=str(exc))
            current.updated_at = utc_now()
            return current

        return self.store.update(run.id, execute, organization_id), True

    def start_connected_goal(
        self,
        request: StartRunRequest,
        organization_id: UUID,
        creator_user_id: UUID | None = None,
        creator_display_name: str | None = None,
        connected_sources: list[str] | None = None,
        reference_run: WorkflowRun | None = None,
        linked_pr_review_id: UUID | None = None,
        linked_cloud_hunt_id: UUID | None = None,
        linked_approval_id: UUID | None = None,
    ) -> tuple[WorkflowRun, bool]:
        """Create a truthful production goal without falling back to a scenario fixture.

        A free-form goal has no safe resource target until connected evidence is
        collected.  It is therefore persisted and surfaced as needing evidence,
        rather than pretending a Terraform fixture or pricing result was real.
        """
        if request.idempotency_key:
            existing = self.store.find_by_idempotency_key(request.idempotency_key, organization_id)
            if existing is not None:
                return existing, False

        now = utc_now()
        sources = list(dict.fromkeys(connected_sources or []))
        if reference_run is not None:
            sources.append("Recorded PR Review")
            sources = list(dict.fromkeys(sources))
        run = WorkflowRun(
            id=uuid4(),
            organization_id=organization_id,
            goal=request.goal,
            scenario_name="connected_goal",
            source_type="autonomous_goal",
            status=RunStatus.planning,
            created_at=now,
            updated_at=now,
            idempotency_key=request.idempotency_key,
            scope=request.scope,
            constraints=request.constraints,
            success_criteria=request.success_criteria,
            stop_conditions=request.stop_conditions,
            creator_user_id=creator_user_id,
            creator_display_name=creator_display_name,
            data_source_mode="Connected evidence" if sources else "Not connected",
            execution_mode="connected_read_only",
            current_step="scope_resolved",
            selected_tools=sources,
            linked_pr_review_id=linked_pr_review_id,
            linked_cloud_hunt_id=linked_cloud_hunt_id,
            linked_approval_id=linked_approval_id,
        )
        append_audit_event(run, event_type="run_created", actor="system", summary="Autonomous goal created.", stage="goal", status="completed")
        append_audit_event(run, event_type="goal_received", actor="agent", summary="Goal received and scoped for read-only investigation.", stage="goal", status="completed")
        append_audit_event(
            run,
            event_type="investigation_plan_created",
            actor="agent",
            summary="Connected evidence sources selected without infrastructure mutation.",
            stage="planning",
            status="completed",
            details={"connected_sources": sources},
        )
        try:
            run = self.store.create(run)
        except DuplicateIdempotencyKeyError:
            if request.idempotency_key:
                existing = self.store.find_by_idempotency_key(request.idempotency_key, organization_id)
                if existing is not None:
                    return existing, False
            raise

        def await_evidence(current: WorkflowRun) -> WorkflowRun:
            if reference_run is not None and reference_run.decision_record is not None:
                current.decision_record = reference_run.decision_record.model_copy(deep=True)
                current.original_plan = reference_run.original_plan
                current.plan_revisions = list(reference_run.plan_revisions)
                current.completed_steps = list(reference_run.completed_steps)
                current.current_step = reference_run.current_step or "recommendation"
                current.selected_tools = list(reference_run.selected_tools)
                current.skipped_tools = dict(reference_run.skipped_tools)
                current.tool_attempts = list(reference_run.tool_attempts)
                current.evidence_summaries = list(reference_run.evidence_summaries)
                current.decision_impacts = list(reference_run.decision_impacts)
                current.status = reference_run.status
                current.stop_reason = reference_run.stop_reason
                current.final_outcome = reference_run.final_outcome
                append_audit_event(
                    current,
                    event_type="existing_pr_evidence_linked",
                    actor="agent",
                    summary="Verified evidence and recommendation from the linked PR Review were added to this goal.",
                    stage="evidence",
                    status="completed",
                    details={"linked_pr_review_id": str(reference_run.id)},
                    decision_impact="No additional infrastructure mutation was performed.",
                )
                current.updated_at = utc_now()
                return current
            current.status = RunStatus.needs_more_evidence
            current.current_step = "collect_evidence"
            current.completed_steps = ["scope_resolved", "plan_created"]
            current.stop_reason = (
                "No verified resource-level evidence has been collected yet. "
                "GhostBusters will not fabricate a finding, savings estimate, or remediation recommendation."
            )
            current.final_outcome = "needs_human_context"
            append_audit_event(
                current,
                event_type="evidence_collection_pending",
                actor="agent",
                summary="Waiting for verified connected evidence before producing a recommendation.",
                stage="evidence",
                status="waiting",
                decision_impact="No infrastructure mutation was performed.",
            )
            current.updated_at = utc_now()
            return current

        return self.store.update(run.id, await_evidence, organization_id), True

    def cancel_goal(self, run_id: UUID, organization_id: UUID = DEFAULT_DEVELOPMENT_ORGANIZATION_ID) -> WorkflowRun:
        def cancel(current: WorkflowRun) -> WorkflowRun:
            if current.status in {RunStatus.approved, RunStatus.pr_created, RunStatus.remediation_pr_created}:
                raise WorkflowConflictError("Completed remediation decisions cannot be canceled.")
            current.status = RunStatus.canceled
            current.stop_reason = "Canceled by an authenticated user before any infrastructure mutation."
            current.final_outcome = "canceled_safely"
            append_audit_event(current, event_type="failed_safely", actor="system", summary="Goal canceled safely; no infrastructure mutation was performed.", stage="canceled", status="canceled", decision_impact="No Terraform apply, merge, or cloud mutation was performed.")
            return current
        return self.store.update(run_id, cancel, organization_id)

    @staticmethod
    def _capture_goal_state(run: WorkflowRun, decision: DecisionRecord) -> None:
        plan = decision.investigation_plan
        run.original_plan = plan.model_dump(mode="json")
        run.selected_tools = list(plan.selected_tools)
        run.skipped_tools = {
            tool: next((note.split(": ", 1)[1] for note in plan.planning_notes if note.startswith(f"Skipped {tool}:")), "Not relevant to this investigation.")
            for tool in plan.skipped_tools
        }
        run.completed_steps = ["scope_resolved", "plan_created", "evidence_collected", "policy_evaluated"]
        run.current_step = "human_review" if decision.final_status == "recommendation_ready" else "completed"
        run.tool_attempts = [record.model_dump(mode="json") for record in decision.tool_executions]
        run.evidence_summaries = [
            {"source": item.source, "claim": item.claim, "value_summary": str(item.value)[:500], "freshness": item.freshness_status, "reliability": item.reliability, "collected_at": item.collected_at, "effect_on_decision": "Used in deterministic recommendation evaluation."}
            for item in decision.evidence
        ]
        run.decision_impacts = [item.explanation for item in decision.verifier_findings if item.status != "passed"] or [decision.final_summary]

    def start_run_request(self, scenario_name: str, goal: str | None = None) -> tuple[WorkflowRun, bool]:
        scenario = load_scenario(scenario_name)
        return self.start_run(StartRunRequest(goal=goal or scenario.goal, scenario_name=scenario_name))

    def start_github_run(self, source: GitHubTerraformChange, delivery_id: str, goal: str | None = None, organization_id: UUID = DEFAULT_DEVELOPMENT_ORGANIZATION_ID) -> tuple[WorkflowRun, bool]:
        existing = self.store.find_by_idempotency_key(delivery_id, organization_id)
        if existing is not None and (
            existing.source_type != "manual_demo" or existing.github_source is not None
        ):
            return existing, False
        scenario = load_scenario("safe")
        now = utc_now()
        run = WorkflowRun(
            id=existing.id if existing else uuid4(),
            organization_id=organization_id,
            goal=goal or "Analyze a GitHub Terraform pull request for safe FinOps remediation.",
            scenario_name="safe", status=RunStatus.created,
            created_at=existing.created_at if existing else now, updated_at=now,
            idempotency_key=delivery_id, source_type="terraform_pr", github_source=source,
        )
        if existing is not None:
            append_audit_event(
                run,
                event_type="github_legacy_run_reclassified",
                actor="system",
                summary="Reclassified a legacy webhook run after authenticated redelivery.",
            )
        append_audit_event(run, event_type="github_webhook_received", actor="system", summary="Validated GitHub pull-request webhook received.", details={"repository": source.repository, "pull_request": source.pull_request_number})
        append_audit_event(run, event_type="github_signature_validated", actor="system", summary="Webhook HMAC SHA-256 signature validated.", details={"repository": source.repository})
        append_audit_event(run, event_type="github_repository_allowed", actor="system", summary="Repository matched the explicit allowlist.", details={"repository": source.repository})
        append_audit_event(run, event_type="github_pr_loaded", actor="tool", summary="GitHub pull-request metadata loaded.", details={"repository": source.repository, "pull_request": source.pull_request_number, "head_sha": source.head_sha})
        append_audit_event(run, event_type="github_pr_files_loaded", actor="tool", summary="Changed files loaded from GitHub.", details={"files": source.changed_files})
        append_audit_event(run, event_type="terraform_files_selected", actor="agent", summary=f"Selected {len(source.terraform_files)} Terraform file(s).", details={"selected": source.terraform_files, "skipped": source.unsupported_changes})
        run = self.store.update(existing.id, run, organization_id) if existing is not None else self.store.create(run)

        def execute(current: WorkflowRun) -> WorkflowRun:
            if not source.resource_changes:
                current.status = RunStatus.keep
                append_audit_event(current, event_type="terraform_analysis_skipped", actor="agent", summary="No Terraform resource changes required investigation.")
                return current
            change = source.resource_changes[0]
            current_value = next(((change.after or {}).get(key) for key in ("instance_type", "machine_type", "size") if (change.after or {}).get(key)), None)
            prior_value = next(((change.before or {}).get(key) for key in ("instance_type", "machine_type", "size") if (change.before or {}).get(key)), None)
            resource = TerraformResourceChange(
                address=change.address, resource_type=change.resource_type, actions=change.actions,
                before=change.before, after=change.after, environment=source.environment,
                current_instance_type=current_value, proposed_instance_type=prior_value,
                destructive=change.destructive or change.replacement, tags=None,
            )
            append_audit_event(current, event_type="terraform_change_parsed", actor="agent", summary="Controlled GitHub diff parsed.", details={"resource": change.address, "provider": change.provider, "destructive": resource.destructive})
            try:
                current.status = RunStatus.investigating
                decision = analyze_resource(current.goal, scenario, resource, self.tool_registry, self.policy_evaluator, current.id, self.retry_executor, configuration=self.configuration, ai_client=self.ai_client)
                current.decision_record = decision
                current.status = map_final_status(decision.final_status)
                self._copy_decision_audit(current, decision)
                append_audit_event(current, event_type="github_investigation_created", actor="agent", summary="GitHub Terraform investigation completed.", details={"status": current.status})
            except Exception as exc:
                current.status, current.error = RunStatus.failed_safely, str(exc)
                append_audit_event(current, event_type="github_integration_failed", actor="system", summary="GitHub investigation failed safely.")
            current.updated_at = utc_now()
            return current
        return self.store.update(run.id, execute, organization_id), existing is None

    def get_run(self, run_id: UUID, organization_id: UUID | None = None) -> WorkflowRun:
        return self.store.get(run_id, organization_id)

    def find_run_by_idempotency(self, key: str, organization_id: UUID | None = None) -> WorkflowRun | None:
        return self.store.find_by_idempotency_key(key, organization_id)

    def list_runs(self, organization_id: UUID | None = None) -> list[WorkflowRun]:
        return self.store.list(organization_id)

    def reset(self) -> dict[str, str]:
        self.store.delete_all()
        return {"status": "ok"}

    def reset_demo(self, organization_id: UUID) -> dict[str, str]:
        delete_fixture_runs = getattr(self.store, "delete_fixture_runs", None)
        if delete_fixture_runs is not None:
            delete_fixture_runs(organization_id)
        return {"status": "ok"}

    def review_run(
        self,
        run_id: UUID,
        request: HumanReviewRequest,
        organization_id: UUID = DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
        reviewer_user_id: UUID | None = None,
        reviewer_email: str | None = None,
        reviewer_role: OrganizationRole | None = None,
        expected_version: int | None = None,
    ) -> tuple[WorkflowRun, bool]:
        try:
            existing = self.store.get(run_id, organization_id)
        except RunNotFoundError:
            raise
        if request.action == "approve" and existing.status == RunStatus.pr_created:
            return existing, False

        def update(current: WorkflowRun) -> WorkflowRun:
            if expected_version is not None and current.version != expected_version:
                raise WorkflowConflictError("Case version is stale. Refresh and try again.")
            record = self._review_record(request, organization_id, reviewer_user_id, reviewer_email, reviewer_role)
            if request.action == "approve":
                self._approve(current, record)
            elif request.action == "reject":
                ensure_can_reject(current)
                current.human_reviews.append(record)
                append_audit_event(current, event_type="human_review_received", actor="human", summary="Run rejected.", details=record.model_dump(mode="json"))
                current.status = RunStatus.rejected
            elif request.action == "request_evidence":
                self._request_evidence(current, request, record)
            elif request.action == "add_context":
                self._add_context(current, request, record)
            elif request.action == "modify":
                self._modify(current, request, record)
            elif request.action == "revoke_approval":
                self._revoke_approval(current, record)
            elif request.action == "reopen_case":
                self._reopen_case(current, record)
            elif request.action == "add_follow_up_context":
                follow_up = request.model_copy(update={"action": "add_context"})
                self._add_context(current, follow_up, record)
            current.updated_at = utc_now()
            return current

        try:
            return self.store.update(run_id, update, organization_id), request.action == "approve"
        except HumanReviewError as exc:
            raise WorkflowConflictError(str(exc)) from exc

    def _approve(self, run: WorkflowRun, record: HumanReviewRecord) -> None:
        decision = ensure_can_approve(run)
        resource = self._resource_for_run(run)
        run.human_reviews.append(record)
        append_audit_event(run, event_type="human_review_received", actor="human", summary="Approval received.", details=record.model_dump(mode="json"))
        run.status = RunStatus.approved
        if run.github_source and self.configuration.github_create_real_pr and self.configuration.github_integration_enabled and self.github_client:
            append_audit_event(run, event_type="remediation_validation_started", actor="agent", summary="Validating real GitHub remediation proposal.")
            try:
                run.real_pr = RemediationPRService(self.github_client, self.configuration).create(run, record)
                run.status = RunStatus.pr_created
                if run.real_pr.reused:
                    append_audit_event(run, event_type="github_remediation_pr_reused", actor="agent", summary="Existing open remediation pull request reused.", details={"url": run.real_pr.url, "branch": run.real_pr.branch})
                else:
                    append_audit_event(run, event_type="github_branch_created", actor="tool", summary="Dedicated remediation branch created.", details={"branch": run.real_pr.branch})
                    append_audit_event(run, event_type="github_file_updated", actor="tool", summary="Validated Terraform file committed to remediation branch.", details={"resource": decision.resource_id})
                    append_audit_event(run, event_type="github_remediation_pr_created", actor="agent", summary="GitHub confirmed remediation pull request creation.", details={"url": run.real_pr.url, "branch": run.real_pr.branch})
                return
            except RemediationValidationError as exc:
                run.status, run.error = RunStatus.failed_safely, str(exc)
                append_audit_event(run, event_type="remediation_validation_failed", actor="agent", summary=str(exc))
                return
        run.mock_pr = create_mock_pull_request(
            pr_number=len(self.store.list()) + 100,
            goal=run.goal,
            decision=decision,
            resource=resource,
            approval=record,
        )
        run.status = RunStatus.pr_created
        append_audit_event(run, event_type="mock_pr_created", actor="agent", summary="Simulated remediation PR created.", details={"branch": run.mock_pr.branch})

    def _revoke_approval(self, run: WorkflowRun, record: HumanReviewRecord) -> None:
        if run.status not in {RunStatus.approved, RunStatus.pr_created}:
            raise HumanReviewError("Only approved cases can have approval revoked.")
        run.human_reviews.append(record)
        run.status = RunStatus.approval_revoked
        append_audit_event(
            run,
            event_type="approval_revoked",
            actor="human",
            summary="Approval revoked. No rollback, Terraform apply, or GitHub pull-request closure was performed.",
            details=record.model_dump(mode="json"),
        )

    def _reopen_case(self, run: WorkflowRun, record: HumanReviewRecord) -> None:
        if run.status not in {RunStatus.rejected, RunStatus.approval_revoked, RunStatus.pr_created, RunStatus.approved}:
            raise HumanReviewError("Only rejected, revoked, approved, or PR-created cases can be reopened.")
        run.human_reviews.append(record)
        run.status = RunStatus.reopened
        append_audit_event(
            run,
            event_type="case_reopened",
            actor="human",
            summary="Case reopened for human review.",
            details=record.model_dump(mode="json"),
        )

    def _resource_for_run(self, run: WorkflowRun) -> TerraformResourceChange:
        if run.github_source and run.github_source.resource_changes:
            change = run.github_source.resource_changes[0]
            current = next(((change.after or {}).get(key) for key in ("instance_type", "machine_type", "size") if (change.after or {}).get(key)), None)
            proposed = next(((change.before or {}).get(key) for key in ("instance_type", "machine_type", "size") if (change.before or {}).get(key)), None)
            return TerraformResourceChange(address=change.address, resource_type=change.resource_type, actions=change.actions, before=change.before, after=change.after, environment=run.github_source.environment, current_instance_type=current, proposed_instance_type=proposed, destructive=change.destructive or change.replacement, tags=None)
        scenario = load_scenario(run.scenario_name)
        return parse_terraform_plan(scenario.terraform_plan_file)[0]

    def _request_evidence(self, run: WorkflowRun, request: HumanReviewRequest, record: HumanReviewRecord) -> None:
        decision = ensure_can_request_evidence(run)
        if not request.requested_sources:
            raise HumanReviewError("requested_sources is required.")
        unknown = sorted(set(request.requested_sources) - set(self.tool_registry.names()))
        if unknown:
            raise HumanReviewError(f"Unknown evidence source(s): {', '.join(unknown)}")
        scenario = load_scenario(run.scenario_name)
        resource = self._resource_for_run(run)
        run.human_reviews.append(record)
        append_audit_event(run, event_type="additional_evidence_requested", actor="human", summary="Additional evidence requested.", details={"sources": request.requested_sources})
        run.plan_revisions.append({"reason": "Human requested additional evidence.", "added_steps": request.requested_sources, "removed_steps": [], "created_at": utc_now()})
        append_audit_event(run, event_type="plan_revised", actor="agent", summary="Plan revised to collect requested evidence.", stage="replanning", status="completed", reason="Human evidence request.")
        plan = InvestigationPlan(
            goal=run.goal,
            resource_id=resource.address,
            selected_tools=list(request.requested_sources),
            planning_notes=[f"Selected {source}: requested by human reviewer." for source in request.requested_sources],
        )
        evidence, records, _ = collect_evidence(
            plan,
            scenario,
            resource,
            self.tool_registry,
            self.retry_executor,
        )
        for record_item in records:
            self._append_tool_execution_audit(run, record_item)
        merged_evidence = [item for item in decision.evidence if item.source not in set(request.requested_sources)] + evidence
        run.decision_record = self._recalculate_decision(
            decision,
            resource,
            merged_evidence,
            decision.tool_executions + records,
            run.id,
            run.scenario_name,
        )
        run.status = map_final_status(run.decision_record.final_status)
        self._append_policy_audit(run, run.decision_record.policy_result)
        append_audit_event(run, event_type="workflow_resumed", actor="agent", summary="Workflow resumed after evidence request.", details={"status": run.status})

    def _add_context(self, run: WorkflowRun, request: HumanReviewRequest, record: HumanReviewRecord) -> None:
        decision = ensure_can_add_context(run, request)
        resource = self._resource_for_run(run)
        run.human_reviews.append(record)
        context = EvidenceItem(
            source="human_review",
            tool_name="human_context",
            claim="human supplied context",
            value=request.human_context,
            resource_id=resource.address,
            collected_at=utc_now(),
            freshness_status="fresh",
            reliability=1.0,
            metadata={"reviewer": request.reviewer, "timestamp": record.created_at.isoformat()},
        )
        evidence = decision.evidence + [context]
        run.plan_revisions.append({"reason": "Human context arrived.", "added_steps": ["human_context"], "removed_steps": [], "created_at": utc_now()})
        run.decision_record = self._recalculate_decision(
            decision,
            resource,
            evidence,
            decision.tool_executions,
            run.id,
            run.scenario_name,
        )
        run.status = map_final_status(run.decision_record.final_status)
        self._append_policy_audit(run, run.decision_record.policy_result)
        append_audit_event(run, event_type="human_context_added", actor="human", summary="Human context added.", details={"reviewer": request.reviewer})
        append_audit_event(run, event_type="plan_revised", actor="agent", summary="Plan revised after human context arrived.", stage="replanning", status="completed", reason="Authenticated human context.")
        append_audit_event(run, event_type="workflow_resumed", actor="agent", summary="Workflow resumed after human context.", details={"status": run.status})

    def _modify(self, run: WorkflowRun, request: HumanReviewRequest, record: HumanReviewRecord) -> None:
        decision = ensure_can_modify(run, request)
        alternative = next((item for item in decision.alternatives if item.action == request.modified_action), None)
        if alternative is None:
            raise HumanReviewError("Requested action is not in generated alternatives.")
        if not alternative.eligible:
            raise HumanReviewError("Requested alternative is not eligible.")
        if request.modified_action in {"request_evidence", "abstain", "keep"}:
            raise HumanReviewError("Only remediation alternatives can be modified for approval.")
        resource = self._resource_for_run(run)
        revised = decision.model_copy(deep=True)
        revised.preferred_action = str(request.modified_action)
        verifier = run_verifier(resource, revised.evidence, revised.conflicts, alternative)
        python_policy = evaluate_policy(
            resource,
            revised.evidence,
            revised.missing_evidence,
            alternative,
            verifier,
            revised.conflicts,
        )
        provisional_confidence = calculate_confidence(
            revised.evidence,
            revised.missing_evidence,
            revised.conflicts,
            python_policy,
            revised.investigation_plan.selected_tools,
        )
        policy = self.policy_evaluator.evaluate(
            resource,
            revised.evidence,
            revised.missing_evidence,
            alternative,
            verifier,
            revised.conflicts,
            provisional_confidence,
            run_id=run.id,
            scenario_name=run.scenario_name,
        )
        if not policy.allowed:
            raise HumanReviewError("Policy does not allow the modified action.")
        revised.verifier_findings = verifier
        revised.policy_result = policy
        revised.confidence = calculate_confidence(revised.evidence, revised.missing_evidence, revised.conflicts, policy, revised.investigation_plan.selected_tools)
        revised.final_status = _final_status(alternative, policy)  # type: ignore[assignment]
        revised.final_summary = f"Preferred action modified to {alternative.action}. Policy status is {policy.status}."
        run.decision_record = revised
        run.human_reviews.append(record)
        run.status = RunStatus.pending_human_review
        self._append_policy_audit(run, policy)
        append_audit_event(run, event_type="preferred_action_modified", actor="human", summary=f"Preferred action modified to {alternative.action}.", details=record.model_dump(mode="json"))

    def _add_context_to_decision(
        self,
        decision: DecisionRecord,
        resource: TerraformResourceChange,
        context: str,
        reviewer: str,
        run_id: UUID | None = None,
        scenario_name: str | None = None,
    ) -> DecisionRecord:
        item = EvidenceItem(
            source="human_review",
            tool_name="human_context",
            claim="human supplied context",
            value=context,
            resource_id=resource.address,
            collected_at=utc_now(),
            freshness_status="fresh",
            reliability=1.0,
            metadata={"reviewer": reviewer},
        )
        return self._recalculate_decision(
            decision,
            resource,
            decision.evidence + [item],
            decision.tool_executions,
            run_id,
            scenario_name,
        )

    def _recalculate_decision(
        self,
        prior: DecisionRecord,
        resource: TerraformResourceChange,
        evidence: list[EvidenceItem],
        executions: list[ToolExecutionRecord],
        run_id: UUID | None = None,
        scenario_name: str | None = None,
    ) -> DecisionRecord:
        missing = self._missing_from_evidence(evidence)
        conflicts = detect_conflicts(evidence)
        alternatives = generate_alternatives(resource, evidence, missing, conflicts)
        hard_block = resource.destructive and prior.preferred_action != "request_evidence" or (resource.environment or "").lower() == "production"
        preferred = _select_preferred(alternatives, hard_block)
        verifier = run_verifier(resource, evidence, conflicts, preferred)
        python_policy = evaluate_policy(resource, evidence, missing, preferred, verifier, conflicts)
        provisional_confidence = calculate_confidence(
            evidence, missing, conflicts, python_policy, prior.investigation_plan.selected_tools
        )
        policy = self.policy_evaluator.evaluate(
            resource,
            evidence,
            missing,
            preferred,
            verifier,
            conflicts,
            provisional_confidence,
            run_id=run_id,
            scenario_name=scenario_name,
        )
        confidence = calculate_confidence(evidence, missing, conflicts, policy, prior.investigation_plan.selected_tools)
        final_status = _final_status(preferred, policy)
        return prior.model_copy(
            deep=True,
            update={
                "tool_executions": executions,
                "evidence": evidence,
                "conflicts": conflicts,
                "missing_evidence": missing,
                "alternatives": alternatives,
                "preferred_action": preferred.action,
                "confidence": confidence,
                "verifier_findings": verifier,
                "policy_result": policy,
                "final_status": final_status,
                "final_summary": f"Preferred action is {preferred.action}. Policy status is {policy.status}. Confidence is {confidence.final_confidence:.2f}.",
                "human_question": None,
                "termination_reason": "deterministic_re_evaluation_after_human_input",
            },
        )

    def _missing_from_evidence(self, evidence: list[EvidenceItem]) -> list[MissingEvidenceRecord]:
        missing: list[MissingEvidenceRecord] = []
        for item in evidence:
            if item.freshness_status == "unavailable":
                missing.append(
                    MissingEvidenceRecord(
                        source=item.source,
                        claim_needed=item.claim,
                        critical=item.source in CRITICAL_SOURCES,
                        impact="Critical evidence is unavailable." if item.source in CRITICAL_SOURCES else "Context is incomplete.",
                    )
                )
        return missing

    def _copy_decision_audit(self, run: WorkflowRun, decision: DecisionRecord) -> None:
        for event in decision.gemini_audit_events:
            append_audit_event(
                run,
                event_type=event.get("event_type", "gemini_event"),
                actor="agent",
                summary=event.get("summary", "Gemini event recorded."),
                details=event.get("details", {}),
            )
        self._append_ai_audit(run, decision)
        append_audit_event(run, event_type="scope_resolved", actor="agent", summary="Investigation scope resolved from the authenticated goal.", stage="scope", status="completed", input_summary=run.scope or "Workspace scope", decision_impact="The plan is constrained to the recorded scope.")
        append_audit_event(run, event_type="step_started", actor="agent", summary="Dynamic investigation plan started.", stage="planning", status="running")
        append_audit_event(run, event_type="investigation_plan_created", actor="agent", summary="Investigation plan created.", details={"selected_tools": decision.investigation_plan.selected_tools})
        append_audit_event(run, event_type="plan_created", actor="agent", summary="Dynamic investigation plan created.", stage="planning", status="completed", output_summary=f"{len(decision.investigation_plan.selected_tools)} tools selected.")
        for tool in decision.investigation_plan.selected_tools:
            reason = next((note for note in decision.investigation_plan.planning_notes if note.startswith(f"Selected {tool}:")), "Selected by the dynamic plan.")
            append_audit_event(run, event_type="tool_selected", actor="agent", summary=f"Selected {tool}.", tool=tool, reason=reason)
        for tool in decision.investigation_plan.skipped_tools:
            reason = next((note for note in decision.investigation_plan.planning_notes if note.startswith(f"Skipped {tool}:")), "Not relevant to this investigation.")
            append_audit_event(run, event_type="step_skipped", actor="agent", summary=f"Skipped {tool}.", tool=tool, reason=reason, status="skipped")
        for record in decision.tool_executions:
            self._append_tool_execution_audit(run, record)
            append_audit_event(run, event_type="evidence_recorded", actor="agent", summary=f"Evidence recorded from {record.tool_name}.", tool=record.tool_name, output_summary=record.output_summary, status=record.status)
        append_audit_event(run, event_type="conflicts_detected", actor="agent", summary=f"{len(decision.conflicts)} conflict(s) detected.")
        if decision.conflicts:
            append_audit_event(run, event_type="conflict_detected", actor="agent", summary="Evidence conflict detected; the recommendation remains safety constrained.", stage="reasoning", status="warning", decision_impact="Human context or additional evidence may be required.")
        append_audit_event(run, event_type="alternatives_generated", actor="agent", summary=f"{len(decision.alternatives)} alternative(s) generated.")
        if decision.preferred_action:
            append_audit_event(run, event_type="alternative_selected", actor="agent", summary=f"Selected alternative: {decision.preferred_action}.", decision_impact=decision.final_summary)
        append_audit_event(run, event_type="verifier_completed", actor="agent", summary="Verifier checks completed.")
        self._append_policy_audit(run, decision.policy_result)
        append_audit_event(run, event_type="policy_evaluated", actor="policy", summary=f"Policy evaluated: {decision.policy_result.status}.", stage="safety", status=decision.policy_result.status, decision_impact="Mandatory human approval remains authoritative.")
        append_audit_event(run, event_type="recommendation_produced", actor="agent", summary=decision.final_summary)

    def _append_ai_audit(self, run: WorkflowRun, decision: DecisionRecord) -> None:
        if decision.objective_interpretation is None:
            return
        mode = decision.planning_mode
        append_audit_event(
            run,
            event_type="ai_planning_started",
            actor="agent",
            summary=f"AI planning mode: {mode}.",
            details={"planning_mode": mode, "model": decision.ai_decisions[0].model if decision.ai_decisions else "deterministic-planner"},
        )
        if mode == "gemini_primary":
            append_audit_event(run, event_type="ai_primary_model_selected", actor="agent", summary="Gemini primary model selected.", details={"planning_mode": mode})
        elif mode == "gemini_fallback_model":
            append_audit_event(run, event_type="ai_fallback_model_selected", actor="agent", summary="Gemini fallback model selected.", details={"planning_mode": mode})
        elif mode == "mock_gemini":
            append_audit_event(run, event_type="ai_primary_model_selected", actor="agent", summary="Mock Gemini planner selected.", details={"planning_mode": mode, "provider": "mock"})
        else:
            append_audit_event(run, event_type="deterministic_planner_fallback", actor="agent", summary="Deterministic planner handled the investigation.", details={"planning_mode": mode, "reason": decision.termination_reason})

        append_audit_event(
            run,
            event_type="ai_goal_interpreted",
            actor="agent",
            summary=decision.objective_interpretation.plain_language_summary,
            details={"objective_type": decision.objective_interpretation.objective_type, "normalized_goal": decision.objective_interpretation.normalized_goal, "planning_mode": mode},
        )
        for ai_decision in decision.ai_decisions:
            action = ai_decision.proposed_action
            details = {
                "sequence_number": ai_decision.sequence_number,
                "model": ai_decision.model,
                "planning_mode": ai_decision.planning_mode,
                "purpose": ai_decision.purpose,
                "proposed_action": action.action if action else None,
                "tool_name": action.tool_name if action else None,
                "reason": action.reason if action else ai_decision.validation_result,
                "question_being_answered": action.question_being_answered if action else None,
                "expected_information": action.expected_information if action else None,
                "accepted": ai_decision.accepted,
                "validation_result": ai_decision.validation_result,
                "fallback_used": ai_decision.fallback_used,
                "fallback_reason": ai_decision.fallback_reason,
                "latency_ms": ai_decision.latency_ms,
                "error_category": ai_decision.error_category,
            }
            if ai_decision.purpose == "interpret_evidence":
                append_audit_event(run, event_type="ai_evidence_interpreted", actor="agent", summary="AI received summarized evidence for next-step planning.", details=details)
            else:
                append_audit_event(run, event_type="ai_next_action_proposed", actor="agent", summary="AI proposed the next investigation step.", details=details)
            append_audit_event(
                run,
                event_type="ai_action_validated" if ai_decision.accepted else "ai_action_rejected",
                actor="agent",
                summary=ai_decision.validation_result,
                details=details,
            )
            if action and action.action == "call_tool" and ai_decision.accepted:
                append_audit_event(run, event_type="ai_tool_selected", actor="agent", summary=f"AI selected {action.tool_name} after validation.", details=details)
            if action and action.action == "request_human_context" and ai_decision.accepted:
                append_audit_event(run, event_type="ai_human_context_requested", actor="agent", summary=action.human_question or "Human context requested.", details=details)
        append_audit_event(
            run,
            event_type="ai_planning_completed" if mode in {"gemini_primary", "gemini_fallback_model", "mock_gemini"} else "ai_planning_failed",
            actor="agent",
            summary=f"Planning completed with mode {mode}.",
            details={"planning_mode": mode, "termination_reason": decision.termination_reason, "fallback_reason": next((item.fallback_reason for item in decision.ai_decisions if item.fallback_reason), None)},
        )

    def _append_tool_execution_audit(
        self,
        run: WorkflowRun,
        record: ToolExecutionRecord,
    ) -> None:
        append_audit_event(
            run,
            event_type="tool_started",
            actor="tool",
            summary=f"{record.tool_name} started.",
        )
        if record.external_call:
            for event in record.external_call.events:
                details = {
                    "run_id": str(run.id),
                    "tool_name": record.tool_name,
                    "attempt": event.attempt,
                    "maximum_attempts": event.maximum_attempts,
                    "failure_category": event.failure_category,
                    "retryable": event.retryable,
                    "retry_delay_seconds": event.retry_delay_seconds,
                    "elapsed_ms": event.elapsed_ms,
                    **event.details,
                }
                summary = {
                    "external_call_started": f"{record.tool_name} external call attempt {event.attempt} started.",
                    "external_call_succeeded": f"{record.tool_name} external call succeeded.",
                    "external_call_retry_scheduled": f"{record.tool_name} retry scheduled.",
                    "external_call_failed": f"{record.tool_name} external call attempt {event.attempt} failed safely.",
                    "external_call_exhausted": f"{record.tool_name} external call attempts exhausted.",
                    "alternative_evidence_selected": "Alternative Git activity evidence selected for unavailable Jira context.",
                }[event.event_type]
                append_audit_event(
                    run,
                    event_type=event.event_type,
                    actor="tool",
                    summary=summary,
                    details=details,
                )
        append_audit_event(
            run,
            event_type=f"tool_{record.status}",
            actor="tool",
            summary=f"{record.tool_name} {record.status}.",
            details={
                "tool_name": record.tool_name,
                "status": record.status,
                "attempts": record.external_call.attempts if record.external_call else 1,
                "failure_category": (
                    record.external_call.failure_category if record.external_call else None
                ),
            },
        )

    def _append_policy_audit(self, run: WorkflowRun, policy: PolicyResult) -> None:
        details = {
            "engine": policy.engine,
            "policy_version": policy.policy_version,
            "allowed": policy.allowed,
            "violation_codes": [item.code for item in policy.violations],
        }
        append_audit_event(
            run,
            event_type="policy_evaluation_started",
            actor="policy",
            summary="Policy evaluation started.",
        )
        append_audit_event(
            run,
            event_type="policy_engine_selected",
            actor="policy",
            summary=f"Policy engine selected: {policy.engine}.",
            details={"engine": policy.engine},
        )
        if policy.fallback_reason:
            append_audit_event(
                run,
                event_type="policy_fallback_used",
                actor="policy",
                summary="Deterministic Python policy fallback used.",
                details={"reason": policy.fallback_reason},
            )
        append_audit_event(
            run,
            event_type="policy_evaluation_completed",
            actor="policy",
            summary=f"Policy {'allowed' if policy.allowed else 'denied'} the recommendation.",
            details=details,
        )
        append_audit_event(
            run,
            event_type="policy_evaluated",
            actor="policy",
            summary=f"Policy status: {policy.status}.",
            details=details,
        )

    def _review_record(
        self,
        request: HumanReviewRequest,
        organization_id: UUID = DEFAULT_DEVELOPMENT_ORGANIZATION_ID,
        reviewer_user_id: UUID | None = None,
        reviewer_email: str | None = None,
        reviewer_role: OrganizationRole | None = None,
    ) -> HumanReviewRecord:
        return HumanReviewRecord(
            reviewer=request.reviewer,
            reviewer_user_id=reviewer_user_id,
            reviewer_email=reviewer_email,
            reviewer_role=reviewer_role,
            organization_id=organization_id,
            action=request.action,
            comment=request.comment,
            requested_sources=request.requested_sources,
            modified_action=request.modified_action,
            human_context=request.human_context,
            created_at=utc_now(),
        )


workflow_service = WorkflowService()
