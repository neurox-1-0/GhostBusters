"""Closed-loop remediation outcome verification using read-only observations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from app.models import OutcomeCompleteRequest, OutcomeObservationRequest, OutcomeReopenRequest, OutcomeStartRequest, OutcomeVerification, WorkflowRun
from app.settings import Settings, settings
from core.postgres_json_store import PostgresJsonStore

class OutcomeConflictError(Exception): pass
class OutcomeNotFoundError(Exception): pass

def utc_now() -> datetime: return datetime.now(timezone.utc)
def fingerprint(value) -> str: return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

class OutcomeStore:
    def __init__(self, configuration: Settings = settings) -> None:
        self.path = Path(configuration.outcome_verification_config_path)
        self.database = PostgresJsonStore(configuration.database_url, "outcome_verification") if configuration.database_url else None
        self._items: dict[UUID, OutcomeVerification] = {}
        self._lock = RLock(); self._load()
    def list(self, organization_id: UUID) -> list[OutcomeVerification]:
        with self._lock: return [item.model_copy(deep=True) for item in self._items.values() if item.organization_id == organization_id]
    def get(self, outcome_id: UUID, organization_id: UUID) -> OutcomeVerification:
        with self._lock:
            item = self._items.get(outcome_id)
            if item is None or item.organization_id != organization_id: raise OutcomeNotFoundError(str(outcome_id))
            return item.model_copy(deep=True)
    def find_case(self, case_id: UUID, organization_id: UUID) -> OutcomeVerification | None:
        return next((item for item in self.list(organization_id) if item.case_id == case_id), None)
    def save(self, item: OutcomeVerification) -> OutcomeVerification:
        with self._lock: self._items[item.id] = item.model_copy(deep=True); self._persist(); return item.model_copy(deep=True)
    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            if self.database: self.database.delete_all()
            else:
                try: self.path.unlink(missing_ok=True)
                except OSError: pass
    def _load(self) -> None:
        if self.database:
            for key, value in self.database.load().items():
                try: self._items[key] = OutcomeVerification.model_validate(value)
                except Exception: continue
            return
        try: payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return
        for key, value in payload.items():
            try: self._items[UUID(key)] = OutcomeVerification.model_validate(value)
            except Exception: continue
    def _persist(self) -> None:
        if self.database:
            self.database.replace({key: value.model_dump(mode="json") for key, value in self._items.items()})
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True); temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps({str(k): v.model_dump(mode="json") for k, v in self._items.items()}), encoding="utf-8"); temp.replace(self.path)
        except OSError: pass

class OutcomeVerificationService:
    def __init__(self, store: OutcomeStore | None = None) -> None: self.store = store or OutcomeStore()
    def start(self, run: WorkflowRun, request: OutcomeStartRequest, organization_id: UUID) -> OutcomeVerification:
        if run.organization_id != organization_id: raise OutcomeNotFoundError(str(run.id))
        if not (run.real_pr or run.mock_pr) or run.status not in {"pr_created", "remediation_pr_created", "approved"}:
            raise OutcomeConflictError("Outcome verification requires an approved remediation result. PR creation is waiting for deployment confirmation.")
        existing = self.store.find_case(run.id, organization_id)
        if existing:
            if request.idempotency_key and existing.last_idempotency_key == request.idempotency_key: return existing
            raise OutcomeConflictError("Outcome verification already exists for this case.")
        decision = run.decision_record; preferred = next((item for item in (decision.alternatives if decision else []) if item.action == (decision.preferred_action if decision else "")), None)
        monthly = float(getattr(preferred, "estimated_monthly_savings", 0) or (run.mock_pr.monthly_savings if run.mock_pr else 0))
        annual = float(getattr(preferred, "estimated_annual_savings", monthly * 12) or monthly * 12)
        now = utc_now()
        item = OutcomeVerification(id=uuid4(), organization_id=organization_id, case_id=run.id, source_type=run.source_type, remediation_reference={"real_pr": run.real_pr.model_dump(mode="json") if run.real_pr else None, "mock_pr": bool(run.mock_pr), "deployment_confirmed": False}, prediction_snapshot={"predicted_monthly_savings": monthly, "predicted_annual_savings": annual, "expected_utilization_range": None, "expected_risk": getattr(preferred, "risks", None), "selected_alternative": decision.preferred_action if decision else None, "baseline_evidence_window": "available evidence at approval", "pricing_source": "pricing evidence" if decision and any(e.source == "pricing" for e in decision.evidence) else None, "confidence": decision.confidence.final_confidence if decision else None}, verification_window={"days": request.verification_window_days, "started_at": now, "ends_at": now + timedelta(days=request.verification_window_days)}, verification_status="waiting_for_deployment", created_at=now, updated_at=now, correlation_id=run.correlation_id, last_idempotency_key=request.idempotency_key, last_request_fingerprint=fingerprint(request.model_dump(mode="json")))
        return self.store.save(item)
    def _update(self, item: OutcomeVerification, expected_version: int | None, key: str | None, payload: dict, status: str | None = None) -> OutcomeVerification:
        if key and item.last_idempotency_key == key and item.last_request_fingerprint == fingerprint(payload): return item
        if expected_version is not None and expected_version != item.version: raise OutcomeConflictError("Outcome version is stale. Refresh and try again.")
        updated = item.model_copy(update={**payload, "verification_status": status or item.verification_status, "updated_at": utc_now(), "version": item.version + 1, "last_idempotency_key": key, "last_request_fingerprint": fingerprint(payload)})
        return self.store.save(updated)
    def confirm_deployment(self, item: OutcomeVerification, expected_version: int | None, key: str | None) -> OutcomeVerification:
        return self._update(item, expected_version, key, {"deployment_confirmed_at": utc_now(), "remediation_reference": {**item.remediation_reference, "deployment_confirmed": True}}, "observing")
    def observe(self, item: OutcomeVerification, request: OutcomeObservationRequest) -> OutcomeVerification:
        payload = {"observed_cost": request.observed_cost, "observed_utilization": request.observed_utilization, "observed_health_signals": request.observed_health_signals, "savings_variance": {"observed_monthly_savings": request.observed_monthly_savings, "predicted_monthly_savings": item.prediction_snapshot.get("predicted_monthly_savings"), "exact_value_available": request.observed_monthly_savings is not None}, "conclusion": "Observation refreshed; verification remains open."}
        return self._update(item, request.expected_version, request.idempotency_key, payload, "observing" if item.deployment_confirmed_at else "waiting_for_deployment")
    def complete(self, item: OutcomeVerification, request: OutcomeCompleteRequest) -> OutcomeVerification:
        observed_health = request.observed_health_signals or {}; missing = request.missing_evidence
        if not item.deployment_confirmed_at: status, conclusion = "waiting_for_deployment", "Deployment confirmation is required before verification can complete."
        elif missing or request.observed_monthly_savings is None: status, conclusion = "insufficient_evidence", "Required post-change evidence is incomplete; no exact savings claim was made."
        elif observed_health.get("healthy") is False or observed_health.get("regression") is True: status, conclusion = "regression_detected", "Post-change health evidence indicates material regression; human review is required."
        else:
            predicted = float(item.prediction_snapshot.get("predicted_monthly_savings") or 0); actual = float(request.observed_monthly_savings); status = "verified_success" if predicted == 0 or actual >= predicted * 0.8 else "verified_partial"; conclusion = "Observed savings and health evidence support the recommendation." if status == "verified_success" else "Some predicted savings were observed while health remained acceptable."
        payload = {"observed_cost": request.observed_cost, "observed_utilization": request.observed_utilization, "observed_health_signals": request.observed_health_signals, "savings_variance": {"observed_monthly_savings": request.observed_monthly_savings, "predicted_monthly_savings": item.prediction_snapshot.get("predicted_monthly_savings"), "exact_value_available": request.observed_monthly_savings is not None}, "risk_outcome": "regression" if status == "regression_detected" else "acceptable" if status in {"verified_success", "verified_partial"} else "unknown", "conclusion": conclusion}
        return self._update(item, request.expected_version, request.idempotency_key, payload, status)
    def reopen(self, item: OutcomeVerification, request: OutcomeReopenRequest) -> OutcomeVerification:
        return self._update(item, request.expected_version, request.idempotency_key, {"conclusion": request.reason, "risk_outcome": "human_review_required"}, "reopened")

outcome_store = OutcomeStore()
outcome_verification_service = OutcomeVerificationService(outcome_store)
