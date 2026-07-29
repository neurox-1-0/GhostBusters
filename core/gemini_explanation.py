"""Optional Gemini recommendation explanations constrained to recorded facts."""

from __future__ import annotations

import re
from typing import Any

from app.models import DecisionRecord, GeminiRecommendationExplanation
from app.settings import Settings, settings
from core.ai_client import AIClientError, StructuredAIClient, build_ai_client
from core.redaction import redact_model_payload


PROHIBITED_EXPLANATION_TERMS = (
    "terraform apply", "merge the pull request", "approved automatically",
    "resource was changed", "cloud resource was modified",
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def deterministic_explanation(decision: DecisionRecord) -> GeminiRecommendationExplanation:
    evidence_points = [f"{item.source}: {item.claim}" for item in decision.evidence[:5]]
    uncertainty_points = [item.impact for item in decision.missing_evidence[:3]]
    safety_points = [
        "Verifier checks and policy evaluation remain deterministic.",
        "Human approval is required before a remediation pull request.",
    ]
    if not decision.policy_result.allowed:
        safety_points.append("Policy currently blocks or requires more context.")
    return GeminiRecommendationExplanation(
        headline=f"Recommendation: {decision.preferred_action}",
        summary=decision.final_summary,
        evidence_points=evidence_points,
        uncertainty_points=uncertainty_points,
        safety_points=safety_points[:3],
        next_step="Use Human Review controls to approve, reject, add context, or request more evidence.",
    )


def add_gemini_explanation(
    decision: DecisionRecord,
    *,
    configuration: Settings = settings,
    client: StructuredAIClient | None = None,
) -> tuple[DecisionRecord, dict[str, Any]]:
    fallback = deterministic_explanation(decision)
    if not configuration.gemini_enabled:
        return decision.model_copy(update={"gemini_explanation": fallback}), {
            "event_type": "gemini_explanation_fallback",
            "summary": "Gemini explanation is disabled; deterministic explanation used.",
            "details": {"fallback_used": True, "provider": "disabled"},
        }
    selected_client = client if client is not None else build_ai_client(configuration)
    if selected_client is None:
        return decision.model_copy(update={"gemini_explanation": fallback}), {
            "event_type": "gemini_explanation_fallback",
            "summary": "Gemini explanation provider unavailable; deterministic explanation used.",
            "details": {"fallback_used": True, "provider": "disabled"},
        }
    payload = redact_model_payload({
        "final_summary": decision.final_summary,
        "preferred_action": decision.preferred_action,
        "confidence": decision.confidence.final_confidence,
        "policy_status": decision.policy_result.status,
        "policy_allowed": decision.policy_result.allowed,
        "blocking_reasons": decision.policy_result.blocking_reasons,
        "verifier_findings": [item.model_dump(mode="json") for item in decision.verifier_findings],
        "evidence_points": [f"{item.source}: {item.claim} = {item.value}" for item in decision.evidence[:8]],
        "uncertainty_points": [item.model_dump(mode="json") for item in decision.missing_evidence[:5]],
        "real_pr_url": None,
        "pricing_policy": "Do not introduce currency or monetary values. Explain only pricing values present in verified live or verified_cached pricing evidence; otherwise state that pricing is unavailable.",
        "pricing_available": any(item.source == "pricing" and item.source_mode in {"live", "verified_cached"} and item.freshness_status != "unavailable" for item in decision.evidence),
        "safety_boundaries": [
            "No cloud resource has been changed by GhostBusters.",
            "Terraform apply and pull-request merge are outside GhostBusters automation.",
        ],
    })
    try:
        call = selected_client.explain_recommendation(payload)
        explanation = call.value
        if not isinstance(explanation, GeminiRecommendationExplanation):
            raise AIClientError("schema_validation_failed", "Gemini explanation schema was invalid.")
        validate_explanation(explanation, decision, payload)
        return decision.model_copy(update={"gemini_explanation": explanation}), {
            "event_type": "gemini_explanation_completed",
            "summary": "Gemini generated a validated recommendation explanation.",
            "details": {
                "provider": "gemini" if call.planning_mode != "mock_gemini" else "mock",
                "model": call.model,
                "latency_ms": call.latency_ms,
                "fallback_used": False,
                "retry_count": call.usage_metadata.get("retry_count", 0),
            },
        }
    except Exception as exc:
        category = exc.category if isinstance(exc, AIClientError) else "schema_validation_failed"
        return decision.model_copy(update={"gemini_explanation": fallback}), {
            "event_type": "gemini_explanation_fallback",
            "summary": "Deterministic explanation used after Gemini explanation failure.",
            "details": {"fallback_used": True, "error_category": category},
        }


def validate_explanation(explanation: GeminiRecommendationExplanation, decision: DecisionRecord, payload: dict[str, Any]) -> None:
    text = " ".join([
        explanation.headline, explanation.summary, explanation.next_step,
        *explanation.evidence_points, *explanation.uncertainty_points, *explanation.safety_points,
    ]).lower()
    if any(term in text for term in PROHIBITED_EXPLANATION_TERMS):
        raise AIClientError("unsafe_action_rejected", "Gemini explanation suggested a prohibited action.")
    if "pull request" in text and "http" in text and not payload.get("real_pr_url"):
        raise AIClientError("unsupported_claim", "Gemini claimed a real PR without a confirmed URL.")
    if not payload.get("pricing_available") and re.search(r"(?:\$|\bUSD\b|\bEUR\b|\bGBP\b)\s*\d", text, re.IGNORECASE):
        raise AIClientError("unsupported_claim", "Gemini introduced a monetary claim without verified pricing evidence.")
    allowed_numbers = {str(number) for number in NUMBER_PATTERN.findall(str(payload))}
    for number in NUMBER_PATTERN.findall(text):
        if number not in allowed_numbers and number not in {"1", "2", "3", "4", "5"}:
            raise AIClientError("unsupported_claim", "Gemini explanation included an unsupported numerical claim.")
