"""Optional, structured AI provider boundary.

The provider can propose typed data, but it never receives executable tools and
never performs workflow mutations itself.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.models import (
    AgentNextAction,
    AskGhostBustersResponse,
    GeminiInvestigationPlan,
    GeminiGoalPlan,
    GeminiGoalPlanStep,
    GeminiGoalValidation,
    GeminiRecommendationExplanation,
    ObjectiveInterpretation,
)
from app.settings import Settings, settings
from core.redaction import redact_model_payload


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Sanitized provider failure with a stable category."""

    def __init__(self, category: str, safe_message: str, *, model: str | None = None) -> None:
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message
        self.model = model


@dataclass(frozen=True, slots=True)
class AICallResult:
    value: BaseModel
    model: str
    planning_mode: str
    latency_ms: int
    usage_metadata: dict[str, Any]


class StructuredAIClient(Protocol):
    def validate_goal(self, payload: dict[str, Any]) -> AICallResult: ...
    def plan_goal(self, payload: dict[str, Any]) -> AICallResult: ...
    def interpret_objective(self, payload: dict[str, Any]) -> AICallResult: ...

    def propose_next_action(self, payload: dict[str, Any]) -> AICallResult: ...

    def propose_investigation_plan(self, payload: dict[str, Any]) -> AICallResult: ...

    def explain_recommendation(self, payload: dict[str, Any]) -> AICallResult: ...

    def answer_assistant_question(self, payload: dict[str, Any]) -> AICallResult: ...


def _safe_category(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    message = str(exc).lower()
    if status == 429 or "rate limit" in message or "resource exhausted" in message:
        return "rate_limited"
    if status in {401, 403} or "permission" in message or "forbidden" in message:
        return "permission_denied"
    if status == 404 or "not found" in message or "unsupported model" in message:
        return "model_unavailable"
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if isinstance(exc, (ValidationError, ValueError, TypeError, json.JSONDecodeError)):
        return "schema_validation_failed"
    return "provider_error"


class GeminiAIClient:
    """Thin official google-genai client with model fallback."""

    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self._client: Any | None = None
        self._types: Any | None = None
        self.active_model: str | None = None
        self.active_mode: str | None = None

    def _load_client(self) -> None:
        if self._client is not None:
            return
        if not self.configuration.gemini_api_key:
            raise AIClientError("missing_api_key", "Gemini API key is not configured.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise AIClientError("sdk_unavailable", "The google-genai SDK is unavailable.") from exc
        try:
            self._client = genai.Client(
                api_key=self.configuration.gemini_api_key,
                http_options=types.HttpOptions(
                    api_version=self.configuration.gemini_api_version,
                    timeout=int(self.configuration.gemini_timeout_seconds * 1000),
                ),
            )
            self._types = types
        except Exception as exc:
            raise AIClientError(_safe_category(exc), "Gemini client configuration failed.") from exc

    def _generate(self, model: str, schema: type[T], prompt: str) -> AICallResult:
        self._load_client()
        assert self._client is not None and self._types is not None
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=self.configuration.gemini_temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            parsed = getattr(response, "parsed", None)
            text = getattr(response, "text", None)
            finish_reason = None
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = str(getattr(candidates[0], "finish_reason", "") or "")
            logger.info("gemini_structured_response endpoint=generate model=%s schema=%s parsed_present=%s text_length=%s candidates=%s finish_reason=%s", model, schema.__name__, parsed is not None, len(text or ""), len(candidates), finish_reason or "unknown")
            raw = parsed if parsed is not None else self._parse_json_text(text)
            value = schema.model_validate(self._normalize_structured_payload(schema, raw))
        except Exception as exc:
            category = _safe_category(exc)
            fields = []
            if isinstance(exc, ValidationError): fields = [".".join(str(part) for part in item.get("loc", ())) for item in exc.errors()]
            logger.warning("gemini_structured_response_failed endpoint=generate model=%s schema=%s parse_stage=structured_validation exception_class=%s validation_fields=%s", model, schema.__name__, type(exc).__name__, fields)
            message = "Gemini response did not match the goal-validation schema." if schema is GeminiGoalValidation else "Gemini returned an unusable response."
            raise AIClientError(category, message, model=model) from exc
        return AICallResult(
            value=value,
            model=model,
            planning_mode="gemini_primary" if model == self.configuration.gemini_model else "gemini_fallback_model",
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            usage_metadata={},
        )

    @staticmethod
    def _parse_json_text(text: Any) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty structured response")
        cleaned = text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            raise ValueError("structured response was not an object")
        return value

    @staticmethod
    def _normalize_structured_payload(schema: type[T], raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        if schema is not GeminiGoalValidation:
            return raw
        normalized = dict(raw)
        for field in ("missing_fields", "clarifying_questions", "constraints", "success_criteria", "stop_conditions", "suggested_capabilities"):
            if normalized.get(field) is None:
                normalized[field] = []
        for field in ("reason", "normalized_goal", "category"):
            if normalized.get(field) is None:
                normalized[field] = ""
        if normalized.get("suggested_goal") is None:
            normalized["suggested_goal"] = None
        return normalized

    def _call(self, schema: type[T], prompt: str) -> AICallResult:
        models = [self.active_model] if self.active_model else [self.configuration.gemini_model]
        if not self.active_model:
            models.append(self.configuration.gemini_fallback_model)
        last_error: AIClientError | None = None
        for index, model in enumerate(dict.fromkeys(models)):
            if not model:
                continue
            for attempt in range(max(1, self.configuration.gemini_max_retries + 1)):
                try:
                    result = self._generate(model, schema, prompt)
                    result.usage_metadata["retry_count"] = attempt
                    self.active_model = result.model
                    self.active_mode = result.planning_mode
                    return result
                except AIClientError as exc:
                    last_error = exc
                    can_try_fallback = exc.category in {"model_unavailable", "permission_denied"}
                    retryable = exc.category in {"timeout", "rate_limited", "provider_error"}
                    if retryable and attempt < self.configuration.gemini_max_retries:
                        time.sleep(min(0.25 * (2 ** attempt), 2.0))
                        continue
                    if index == 0 and can_try_fallback:
                        break
                    raise
        raise last_error or AIClientError("model_unavailable", "No Gemini model is configured.")

    def interpret_objective(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({"task": "interpret_objective", "input": redact_model_payload(payload)}, sort_keys=True)
        return self._call(ObjectiveInterpretation, prompt)

    def validate_goal(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({"task": "validate_cloud_cost_goal", "instructions": "Return only the schema. Assess relevance and ambiguity; do not authorize mutation, invent facts, tools, or permissions.", "input": redact_model_payload(payload)}, sort_keys=True)
        return self._call(GeminiGoalValidation, prompt)

    def plan_goal(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({"task": "plan_cloud_cost_goal", "instructions": "Select only capabilities listed in allowed_capabilities. Plan read-only evidence collection and policy checks; never request arbitrary code or mutation.", "input": redact_model_payload(payload)}, sort_keys=True)
        return self._call(GeminiGoalPlan, prompt)

    def propose_next_action(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({"task": "propose_next_action", "input": redact_model_payload(payload)}, sort_keys=True)
        return self._call(AgentNextAction, prompt)

    def propose_investigation_plan(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({
            "task": "propose_investigation_plan",
            "instructions": "Return only a safe investigation plan. Do not authorize actions or request mutation.",
            "input": redact_model_payload(payload),
        }, sort_keys=True)
        return self._call(GeminiInvestigationPlan, prompt)

    def explain_recommendation(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({
            "task": "explain_recommendation",
            "instructions": "Explain only recorded facts, interpretation, missing context, and human next step.",
            "input": redact_model_payload(payload),
        }, sort_keys=True)
        return self._call(GeminiRecommendationExplanation, prompt)

    def answer_assistant_question(self, payload: dict[str, Any]) -> AICallResult:
        prompt = json.dumps({
            "task": "ask_ghostbusters",
            "instructions": "Answer only from supplied read-only tool results and product help. Decline actions.",
            "input": redact_model_payload(payload),
        }, sort_keys=True)
        return self._call(AskGhostBustersResponse, prompt)


class MockGeminiClient:
    """Offline provider for demonstrations and tests; never claims real Gemini."""

    def _result(self, value: BaseModel, purpose: str) -> AICallResult:
        return AICallResult(value=value, model="mock-gemini", planning_mode="mock_gemini", latency_ms=0, usage_metadata={"provider": "mock", "purpose": purpose})

    def interpret_objective(self, payload: dict[str, Any]) -> AICallResult:
        objective = str(payload.get("objective", "")).strip()
        lowered = objective.lower()
        if any(term in lowered for term in ("safe", "risk", "production", "protect")):
            objective_type = "safety_review"
        elif any(term in lowered for term in ("refresh", "current", "recent")):
            objective_type = "evidence_refresh"
        elif any(term in lowered for term in ("explain", "understand")):
            objective_type = "explain_change"
        elif any(term in lowered for term in ("cost", "save", "rightsize", "spend")):
            objective_type = "cost_optimization"
        else:
            objective_type = "unsupported"
        return self._result(
            ObjectiveInterpretation(
                original_objective=objective,
                objective_type=objective_type,
                normalized_goal=objective or "Review this infrastructure change safely.",
                constraints=["No direct infrastructure mutation", "Human approval is required for remediation"],
                assumptions=["Prepared Terraform fixture is authoritative for the demo"],
                ambiguities=[],
                plain_language_summary=f"Mock Gemini classified this as a {objective_type.replace('_', ' ')} investigation.",
            ),
            "interpret_objective",
        )

    def validate_goal(self, payload: dict[str, Any]) -> AICallResult:
        goal = str(payload.get("goal", "")).strip()
        lowered = goal.lower()
        ambiguous = "15%" in lowered and not any(term in lowered for term in ("spend", "waste", "cost reduction"))
        status = "needs_revision" if ambiguous else "accepted"
        return self._result(GeminiGoalValidation(status=status, reason="The percentage target needs a spending baseline and environment." if ambiguous else "The goal is relevant to cloud-cost investigation.", normalized_goal=goal, category="cost_optimization", missing_fields=["Spending baseline", "Environment"] if ambiguous else [], clarifying_questions=["Should the 15% target apply to spend or waste?", "Which environment is in scope?"] if ambiguous else [], suggested_goal="Identify safe opportunities to reduce non-production AWS spending by 15%, while protecting production and requiring approval before changes." if ambiguous else goal, constraints=["No direct infrastructure mutation", "Human approval required"], success_criteria=["Produce evidence-grounded opportunities or a safe abstention"], stop_conditions=["Evidence is insufficient", "Human approval is required"], suggested_capabilities=["inspect_github_repository", "load_cloud_hunt_evidence", "evaluate_policy"], risk_level="medium"), "validate_goal")

    def plan_goal(self, payload: dict[str, Any]) -> AICallResult:
        allowed = set(payload.get("allowed_capabilities", []))
        steps = [
            ("inspect_github_repository", "Repository context can establish ownership and infrastructure change context.", "Repository metadata and recent activity."),
            ("load_cloud_hunt_evidence", "Cloud Hunt can provide organization-scoped resource signals.", "Eligible resource evidence and limitations."),
            ("evaluate_evidence_sufficiency", "Evidence gaps must be identified before recommendation.", "Verified evidence threshold and missing inputs."),
            ("evaluate_policy", "Production protection and approval rules remain mandatory.", "Policy outcome and approval requirement."),
        ]
        selected = [GeminiGoalPlanStep(capability=name, reason=reason, expected_evidence=expected) for name, reason, expected in steps if name in allowed]
        return self._result(GeminiGoalPlan(decision_summary="Read-only evidence will be collected before any recommendation is considered.", selected_capabilities=selected or [GeminiGoalPlanStep(capability="evaluate_policy", reason="Safety policy must be evaluated.", expected_evidence="Policy result.")]), "plan_goal")

    def propose_next_action(self, payload: dict[str, Any]) -> AICallResult:
        available = list(payload.get("available_tools", []))
        executed = set(payload.get("executed_tools", []))
        mandatory = list(payload.get("mandatory_tools", []))
        objective_type = payload.get("objective_type")
        preferred_order = {
            "cost_optimization": ["pricing", "utilization", "dependencies", "jira", "git_activity"],
            "safety_review": ["dependencies", "utilization", "jira", "git_activity", "pricing"],
            "evidence_refresh": ["utilization", "pricing", "dependencies", "jira", "git_activity"],
            "explain_change": ["jira", "git_activity", "pricing", "utilization", "dependencies"],
        }.get(objective_type, mandatory or available)
        candidates = [name for name in preferred_order if name in available and name not in executed]
        if candidates:
            tool = candidates[0]
            reasons = {
                "pricing": "Cost impact needs authoritative pricing evidence.",
                "utilization": "Rightsizing needs historical utilization evidence.",
                "dependencies": "Remediation safety requires downstream dependency evidence.",
                "jira": "Project purpose and delivery status need business context.",
                "git_activity": "Recent repository activity can validate project status.",
            }
            return self._result(AgentNextAction(action="call_tool", tool_name=tool, reason=reasons.get(tool, "This registered evidence source is relevant."), question_being_answered=f"What can {tool} tell us?", expected_information=f"Usable {tool} evidence." , confidence=0.9), "propose_next_action")
        if payload.get("conflicts") or payload.get("unresolved_questions"):
            return self._result(AgentNextAction(action="request_human_context", reason="Evidence is complete enough to expose a genuine ambiguity for review.", question_being_answered="Is the proposed change safe in the current business context?", expected_information="Owner context that resolves the remaining ambiguity.", human_question="Can the owner confirm the workload context and whether this change is safe to apply?", confidence=0.76), "propose_next_action")
        return self._result(AgentNextAction(action="finish_investigation", reason="The mandatory evidence sources have been checked.", question_being_answered="Is evidence collection complete?", expected_information="No further mandatory evidence is missing.", confidence=0.88), "propose_next_action")

    def propose_investigation_plan(self, payload: dict[str, Any]) -> AICallResult:
        available = payload.get("available_read_only_tools", payload.get("available_tools", []))
        tools = [tool for tool in available if tool in {"pricing", "utilization", "jira", "git_activity", "dependencies"}]
        selected = tools[:3] or tools
        questions = [
            {
                "id": f"gemini_{tool}",
                "question": f"What does {tool} evidence say about the recommendation?",
                "required_evidence_sources": [tool],
                "reason": f"{tool} is a registered read-only evidence source.",
            }
            for tool in selected
        ]
        return self._result(
            GeminiInvestigationPlan(
                summary="Mock Gemini suggested supplemental evidence questions.",
                questions=questions,
                selected_tools=selected,
                skipped_tools=[],
                planning_notes=["Deterministic required tools remain authoritative."],
                uncertainties=["Business context may still need human review."],
            ),
            "propose_investigation_plan",
        )

    def explain_recommendation(self, payload: dict[str, Any]) -> AICallResult:
        return self._result(
            GeminiRecommendationExplanation(
                headline="Recorded recommendation explained",
                summary=str(payload.get("final_summary") or "GhostBusters completed a deterministic review."),
                evidence_points=[str(item)[:180] for item in payload.get("evidence_points", [])[:5]],
                uncertainty_points=[str(item)[:180] for item in payload.get("uncertainty_points", [])[:3]],
                safety_points=["Human approval remains required before any remediation pull request."],
                next_step="Use the Human Review controls for approval or request more evidence.",
            ),
            "explain_recommendation",
        )

    def answer_assistant_question(self, payload: dict[str, Any]) -> AICallResult:
        fallback = payload.get("fallback_answer") or {}
        return self._result(
            AskGhostBustersResponse(
                answer=str(fallback.get("answer") or "That information is not available in the current case."),
                answer_type=fallback.get("answer_type") or "unavailable",
                supporting_sections=list(fallback.get("supporting_sections") or []),
                evidence_sources=list(fallback.get("evidence_sources") or []),
                limitations=list(fallback.get("limitations") or []),
                provider="mock",
                fallback_used=False,
            ),
            "answer_assistant_question",
        )


def build_ai_client(configuration: Settings = settings) -> StructuredAIClient | None:
    if not (configuration.ai_enabled or configuration.gemini_enabled):
        return None
    if configuration.ai_provider.lower() == "mock":
        return MockGeminiClient()
    if configuration.ai_provider.lower() == "gemini":
        return GeminiAIClient(configuration)
    return None
