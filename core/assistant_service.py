"""Read-only Ask GhostBusters assistant."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models import AskGhostBustersRequest, AskGhostBustersResponse, WorkflowRun
from app.settings import Settings, settings
from core.ai_client import StructuredAIClient, build_ai_client
from core.cloud_hunt_service import CloudHuntService, cloud_hunt_service
from core.redaction import redact_model_payload
from core.run_store import RunNotFoundError
from core.workflow_service import WorkflowService, workflow_service


PRODUCT_HELP = json.loads((Path(__file__).resolve().parent / "product_help.json").read_text(encoding="utf-8"))
ACTION_TERMS = re.compile(r"\b(approve|reject|create|merge|apply|delete|stop|resize|modify|waive|remediate|run terraform|write|commit)\b", re.I)
CASE_TERMS = re.compile(r"\b(recommendation|evidence|conflict|confidence|resource|protected|approve|policy|stage|case|workflow|modified|github|cloud|missing|blocked|verifier)\b", re.I)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AssistantValidationError(Exception):
    pass


class AskGhostBustersService:
    def __init__(
        self,
        workflow: WorkflowService = workflow_service,
        cloud_hunt: CloudHuntService = cloud_hunt_service,
        configuration: Settings = settings,
        ai_client: StructuredAIClient | None = None,
    ) -> None:
        self.workflow = workflow
        self.cloud_hunt = cloud_hunt
        self.configuration = configuration
        self.ai_client = ai_client

    def ask(self, request: AskGhostBustersRequest) -> AskGhostBustersResponse:
        question = sanitize_question(request.question)
        if ACTION_TERMS.search(question) and _is_action_request(question):
            return AskGhostBustersResponse(
                answer="I can explain the recommendation, but approvals and remediation actions must use the Human Review controls.",
                answer_type="action_not_allowed",
                supporting_sections=["safety_boundaries"],
                evidence_sources=[],
                limitations=["Ask GhostBusters is read-only."],
                provider="deterministic",
                fallback_used=True,
            )
        case_required = is_case_question(question, request.context)
        case_data: dict[str, Any] = {}
        if case_required:
            if request.case_id is None:
                raise AssistantValidationError("case_id is required for case-specific questions.")
            case_data = self._case_bundle(request.case_id)
        topic = classify_product_topic(question)
        product_help = get_product_help(topic) if topic else {}
        fallback = deterministic_answer(question, case_data, product_help)
        if not self.configuration.gemini_assistant_enabled or not self.configuration.gemini_enabled:
            return fallback
        client = self.ai_client if self.ai_client is not None else build_ai_client(self.configuration)
        if client is None:
            return fallback.model_copy(update={"fallback_used": True, "provider": "deterministic"})
        try:
            payload = redact_model_payload({
                "question": question,
                "context": request.context,
                "case_data": case_data,
                "product_help": product_help,
                "fallback_answer": fallback.model_dump(mode="json"),
                "allowed_read_tools": list(ALLOWED_READ_TOOLS),
                "tool_call_limit": 4,
                "safety": "Read-only. No web search, SQL generation, code execution, file uploads, or mutations.",
            })
            call = client.answer_assistant_question(payload)
            answer = call.value
            if not isinstance(answer, AskGhostBustersResponse):
                return fallback
            if ACTION_TERMS.search(answer.answer) and answer.answer_type != "action_not_allowed":
                return fallback
            return answer.model_copy(update={
                "provider": "gemini" if call.planning_mode != "mock_gemini" else "mock",
                "fallback_used": False,
            })
        except Exception:
            return fallback.model_copy(update={"fallback_used": True, "provider": "deterministic"})

    def _case_bundle(self, case_id: UUID) -> dict[str, Any]:
        return redact_model_payload({
            "summary": get_current_case_summary(case_id, self.workflow, self.cloud_hunt),
            "evidence": get_case_evidence(case_id, self.workflow, self.cloud_hunt),
            "conflicts": get_case_conflicts(case_id, self.workflow, self.cloud_hunt),
            "policy": get_case_policy_result(case_id, self.workflow, self.cloud_hunt),
            "verifier": get_case_verifier_findings(case_id, self.workflow, self.cloud_hunt),
            "human_review": get_case_human_review_status(case_id, self.workflow, self.cloud_hunt),
            "remediation": get_case_remediation_status(case_id, self.workflow, self.cloud_hunt),
            "audit": get_case_audit_summary(case_id, self.workflow, self.cloud_hunt),
        })


ALLOWED_READ_TOOLS = {
    "get_current_case_summary",
    "get_case_evidence",
    "get_case_conflicts",
    "get_case_policy_result",
    "get_case_verifier_findings",
    "get_case_human_review_status",
    "get_case_remediation_status",
    "get_case_audit_summary",
    "get_product_help",
}


def sanitize_question(question: str) -> str:
    clean = CONTROL_CHARS.sub("", question).strip()
    if not clean:
        raise AssistantValidationError("question is required.")
    if len(clean) > 600:
        raise AssistantValidationError("question is too long.")
    if "http://" in clean.lower() or "https://" in clean.lower():
        raise AssistantValidationError("URLs are not supported by Ask GhostBusters.")
    return clean


def is_case_question(question: str, context: str) -> bool:
    if context == "product_help":
        return False
    return context in {"pr_review", "cloud_hunt", "approvals", "technical_audit"} or bool(CASE_TERMS.search(question))


def _is_action_request(question: str) -> bool:
    lowered = question.lower()
    return any(prefix in lowered for prefix in ("can you", "please", "do it", "approve", "reject", "create", "merge", "apply", "delete", "stop", "resize", "modify", "waive"))


def classify_product_topic(question: str) -> str | None:
    lowered = question.lower()
    topic_terms = {
        "pr_reviews": ["pr reviews", "pull request", "terraform pr"],
        "cloud_hunt": ["cloud hunt"],
        "approvals": ["approvals", "human approval", "review queue"],
        "technical_audit": ["technical audit", "audit"],
        "demo_mode": ["demo mode", "demo"],
        "human_approval": ["human approval", "approve"],
        "remediation_pr": ["remediation pr", "pull request"],
        "real_vs_fixture": ["real and demo", "fixture", "real cases"],
        "safety_boundaries": ["run terraform", "terraform apply", "modify cloud", "change anything", "safety"],
        "github_integration": ["github"],
        "deterministic_fallback": ["fallback", "deterministic"],
        "gemini_assistance": ["gemini", "assistant"],
    }
    for topic, terms in topic_terms.items():
        if any(term in lowered for term in terms):
            return topic
    if any(term in lowered for term in ("what is", "how does", "does ghostbusters")):
        return "overview"
    return None


def get_product_help(topic: str | None) -> dict[str, str]:
    if not topic or topic not in PRODUCT_HELP:
        return {"overview": PRODUCT_HELP["overview"]}
    return {topic: PRODUCT_HELP[topic]}


def deterministic_answer(question: str, case_data: dict[str, Any], product_help: dict[str, str]) -> AskGhostBustersResponse:
    lowered = question.lower()
    if product_help and not case_data:
        topic, text = next(iter(product_help.items()))
        return AskGhostBustersResponse(answer=text, answer_type="product_help", supporting_sections=[topic], evidence_sources=[], limitations=[], provider="deterministic", fallback_used=True)
    summary = case_data.get("summary") or {}
    policy = case_data.get("policy") or {}
    evidence = case_data.get("evidence") or []
    conflicts = case_data.get("conflicts") or []
    missing = [item for item in evidence if item.get("freshness_status") == "unavailable"]
    if "what happens if i approve" in lowered or "after approval" in lowered:
        answer = "Approval creates a remediation pull request only. GhostBusters does not apply Terraform, merge pull requests, or modify cloud resources directly."
        return _case_response(answer, "explanation", ["human_review", "remediation"], [])
    if "did ghostbusters" in lowered and any(term in lowered for term in ("modify", "change", "cloud", "github")):
        remediation = case_data.get("remediation") or {}
        answer = "GhostBusters has not applied Terraform, merged pull requests, or modified cloud resources directly."
        if remediation.get("real_pr_url"):
            answer += f" A remediation pull request is recorded at {remediation['real_pr_url']}."
        elif remediation.get("simulated_pr"):
            answer += " A simulated remediation pull request is recorded for this case."
        return _case_response(answer, "recorded_fact", ["remediation", "safety_boundaries"], [])
    if "protected" in lowered:
        reasons = policy.get("blocking_reasons") or [item.get("explanation") for item in conflicts] or summary.get("protective_signals") or []
        answer = "This resource is protected because " + ("; ".join(map(str, reasons[:3])) if reasons else "the current case contains policy, dependency, production, or activity signals that require human review.")
        return _case_response(answer, "explanation", ["policy", "dependencies"], _evidence_sources(evidence))
    if "conflict" in lowered:
        answer = "No conflicts were detected in the current case." if not conflicts else "Detected conflicts: " + "; ".join(item.get("explanation") or item.get("claim") for item in conflicts[:3])
        return _case_response(answer, "recorded_fact", ["conflicts"], _evidence_sources(evidence))
    if "confidence" in lowered:
        confidence = summary.get("confidence")
        answer = f"The confidence score is {confidence}. It reflects evidence completeness, reliability, freshness, conflict penalties, and policy certainty." if confidence is not None else "That information is not available in the current case."
        return _case_response(answer, "explanation", ["confidence"], _evidence_sources(evidence))
    if "missing" in lowered:
        answer = "No missing evidence is recorded." if not missing else "Missing evidence: " + "; ".join(item.get("source", "unknown") for item in missing[:5])
        return _case_response(answer, "recorded_fact", ["evidence"], _evidence_sources(evidence))
    if "policy" in lowered or "blocked" in lowered:
        reasons = policy.get("blocking_reasons") or policy.get("violations") or []
        answer = f"Policy status is {policy.get('status', 'not recorded')}." + (f" Blocking reasons: {'; '.join(map(str, reasons[:3]))}." if reasons else "")
        return _case_response(answer, "recorded_fact", ["policy"], [])
    if "stage" in lowered or "workflow" in lowered:
        return _case_response(f"The current workflow stage is {summary.get('status', 'not recorded')}.", "recorded_fact", ["workflow"], [])
    if "evidence" in lowered or "recommend" in lowered or "why" in lowered:
        points = [f"{item.get('source')}: {item.get('claim')}" for item in evidence[:5]]
        answer = summary.get("recommendation_reason") or summary.get("final_summary") or "That information is not available in the current case."
        if points:
            answer += " Evidence used: " + "; ".join(points) + "."
        return _case_response(answer, "explanation", ["recommendation", "evidence"], _evidence_sources(evidence))
    if product_help:
        topic, text = next(iter(product_help.items()))
        return AskGhostBustersResponse(answer=text, answer_type="product_help", supporting_sections=[topic], evidence_sources=[], limitations=[], provider="deterministic", fallback_used=True)
    return AskGhostBustersResponse(answer="That information is not available in the current case.", answer_type="unavailable", supporting_sections=[], evidence_sources=[], limitations=["The current case does not contain enough recorded data to answer."], provider="deterministic", fallback_used=True)


def _case_response(answer: str, answer_type: str, sections: list[str], sources: list[str]) -> AskGhostBustersResponse:
    return AskGhostBustersResponse(answer=answer, answer_type=answer_type, supporting_sections=sections, evidence_sources=sources, limitations=[], provider="deterministic", fallback_used=True)


def _evidence_sources(evidence: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(item.get("source")) for item in evidence if item.get("source")))


def get_current_case_summary(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> dict[str, Any]:
    run = _get_run(case_id, workflow)
    if run:
        decision = run.decision_record
        return {
            "case_id": str(run.id),
            "source_type": run.source_type,
            "status": run.status,
            "resource_id": decision.resource_id if decision else None,
            "recommendation": decision.preferred_action if decision else None,
            "recommendation_reason": decision.final_summary if decision else None,
            "confidence": decision.confidence.final_confidence if decision else None,
            "policy_status": decision.policy_result.status if decision else None,
        }
    case = cloud_hunt.get_case(case_id)
    return {
        "case_id": str(case.id),
        "source_type": case.source_type,
        "status": case.status,
        "resource_id": case.resource_id,
        "resource_name": case.resource_name,
        "recommendation": case.recommendation,
        "recommendation_reason": case.recommendation_reason,
        "confidence": case.confidence,
        "policy_status": case.policy_status,
        "protective_signals": [signal.description for signal in getattr(case.candidate, "signals", []) if not signal.supports_ghost_hypothesis],
    }


def get_case_evidence(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> list[dict[str, Any]]:
    run = _get_run(case_id, workflow)
    if run and run.decision_record:
        return [
            {"source": item.source, "claim": item.claim, "value": item.value, "freshness_status": item.freshness_status, "reliability": item.reliability}
            for item in run.decision_record.evidence
        ]
    case = cloud_hunt.get_case(case_id)
    return [
        {"source": signal.evidence_source, "claim": signal.description, "value": signal.value, "freshness_status": "fresh", "reliability": signal.weight}
        for signal in getattr(case.candidate, "signals", [])
    ]


def get_case_conflicts(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> list[dict[str, Any]]:
    run = _get_run(case_id, workflow)
    if run and run.decision_record:
        return [item.model_dump(mode="json") for item in run.decision_record.conflicts]
    return []


def get_case_policy_result(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> dict[str, Any]:
    run = _get_run(case_id, workflow)
    if run and run.decision_record:
        return run.decision_record.policy_result.model_dump(mode="json")
    case = cloud_hunt.get_case(case_id)
    return {"status": case.policy_status, "blocking_reasons": [case.recommendation_reason] if case.policy_status != "passed" else [], "allowed": case.policy_status == "passed"}


def get_case_verifier_findings(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> list[dict[str, Any]]:
    run = _get_run(case_id, workflow)
    if run and run.decision_record:
        return [item.model_dump(mode="json") for item in run.decision_record.verifier_findings]
    return []


def get_case_human_review_status(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> dict[str, Any]:
    run = _get_run(case_id, workflow)
    if run:
        return {"status": run.status, "reviews": [item.model_dump(mode="json") for item in run.human_reviews[-3:]]}
    case = cloud_hunt.get_case(case_id)
    return {"status": case.status, "human_decision": case.human_decision, "required_reviewer_role": case.required_reviewer_role}


def get_case_remediation_status(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> dict[str, Any]:
    run = _get_run(case_id, workflow)
    if run:
        return {"status": run.status, "simulated_pr": bool(run.mock_pr), "real_pr_url": run.real_pr.url if run.real_pr else None}
    case = cloud_hunt.get_case(case_id)
    return {"status": case.status, "simulated_pr": bool(case.simulated_pr), "real_pr_url": None}


def get_case_audit_summary(case_id: UUID, workflow: WorkflowService = workflow_service, cloud_hunt: CloudHuntService = cloud_hunt_service) -> list[dict[str, Any]]:
    run = _get_run(case_id, workflow)
    events = run.audit_events if run else cloud_hunt.get_case(case_id).audit_events
    return [{"event_type": event.event_type, "summary": event.summary, "actor": event.actor} for event in events[-20:]]


def _get_run(case_id: UUID, workflow: WorkflowService) -> WorkflowRun | None:
    try:
        return workflow.get_run(case_id)
    except RunNotFoundError:
        return None


assistant_service = AskGhostBustersService()
