from pathlib import Path

from app.models import HumanReviewRequest, OutcomeCompleteRequest, OutcomeObservationRequest, OutcomeReopenRequest, OutcomeStartRequest
from app.settings import Settings
from core.outcome_verification import OutcomeConflictError, OutcomeStore, OutcomeVerificationService
from core.run_store import InMemoryRunStore
from core.workflow_service import WorkflowService


def _approved(tmp_path: Path):
    workflow = WorkflowService(InMemoryRunStore())
    run, _ = workflow.start_run_request("safe")
    approved, _ = workflow.review_run(run.id, HumanReviewRequest(action="approve", reviewer="reviewer", comment="approved"))
    return approved, OutcomeVerificationService(OutcomeStore(Settings(outcome_verification_config_path=tmp_path / "outcomes.json")))


def test_pr_creation_waits_for_deployment_and_prediction_is_immutable(tmp_path):
    run, service = _approved(tmp_path)
    outcome = service.start(run, OutcomeStartRequest(idempotency_key="start-1"), run.organization_id)
    assert outcome.verification_status == "waiting_for_deployment"
    before = outcome.prediction_snapshot.copy()
    observed = service.observe(outcome, OutcomeObservationRequest(observed_monthly_savings=70, missing_evidence=["deployment_confirmation"], idempotency_key="refresh-1"))
    assert observed.verification_status == "waiting_for_deployment"
    assert observed.prediction_snapshot == before


def test_success_partial_regression_and_insufficient_evidence(tmp_path):
    run, service = _approved(tmp_path)
    outcome = service.start(run, OutcomeStartRequest(), run.organization_id)
    outcome = service.confirm_deployment(outcome, outcome.version, "deploy")
    success = service.complete(outcome, OutcomeCompleteRequest(observed_monthly_savings=70, observed_health_signals={"healthy": True}, expected_version=outcome.version, idempotency_key="complete"))
    assert success.verification_status == "verified_success"
    run2, service2 = _approved(tmp_path / "second"); outcome2 = service2.start(run2, OutcomeStartRequest(), run2.organization_id); outcome2 = service2.confirm_deployment(outcome2, outcome2.version, "deploy-2")
    partial = service2.complete(outcome2, OutcomeCompleteRequest(observed_monthly_savings=10, observed_health_signals={"healthy": True}, expected_version=outcome2.version, idempotency_key="partial"))
    assert partial.verification_status == "verified_partial"
    run3, service3 = _approved(tmp_path / "third"); outcome3 = service3.start(run3, OutcomeStartRequest(), run3.organization_id); outcome3 = service3.confirm_deployment(outcome3, outcome3.version, "deploy-3")
    regression = service3.complete(outcome3, OutcomeCompleteRequest(observed_monthly_savings=70, observed_health_signals={"regression": True}, expected_version=outcome3.version, idempotency_key="regression"))
    assert regression.verification_status == "regression_detected"
    run4, service4 = _approved(tmp_path / "fourth"); outcome4 = service4.start(run4, OutcomeStartRequest(), run4.organization_id); outcome4 = service4.confirm_deployment(outcome4, outcome4.version, "deploy-4")
    insufficient = service4.complete(outcome4, OutcomeCompleteRequest(missing_evidence=["CloudWatch"], expected_version=outcome4.version, idempotency_key="missing"))
    assert insufficient.verification_status == "insufficient_evidence"


def test_idempotency_concurrency_and_reopen_are_safe(tmp_path):
    run, service = _approved(tmp_path)
    outcome = service.start(run, OutcomeStartRequest(idempotency_key="same"), run.organization_id)
    assert service.start(run, OutcomeStartRequest(idempotency_key="same"), run.organization_id).id == outcome.id
    try: service.confirm_deployment(outcome, 999, "bad")
    except OutcomeConflictError: pass
    else: raise AssertionError("stale outcome update was accepted")
    outcome = service.confirm_deployment(outcome, outcome.version, "deployment")
    outcome = service.complete(outcome, OutcomeCompleteRequest(observed_monthly_savings=1, observed_health_signals={"regression": True}, expected_version=outcome.version, idempotency_key="done"))
    reopened = service.reopen(outcome, OutcomeReopenRequest(reason="Review regression", expected_version=outcome.version, idempotency_key="reopen"))
    assert reopened.verification_status == "reopened"
