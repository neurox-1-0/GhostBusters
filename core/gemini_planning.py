"""Gemini-assisted investigation plan proposals with deterministic merge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import (
    AIDecisionRecord,
    GeminiInvestigationPlan,
    InvestigationPlan,
    InvestigationQuestion,
    ScenarioDefinition,
    TerraformResourceChange,
)
from app.settings import Settings, settings
from core.ai_client import AIClientError, StructuredAIClient, build_ai_client
from core.redaction import redact_model_payload
from integrations.base import utc_now
from integrations.registry import ToolRegistry


PROHIBITED_PLAN_TERMS = (
    "terraform apply", "merge pull", "approve", "delete resource", "stop resource",
    "resize resource", "modify cloud", "write github", "create pull request",
)


@dataclass(frozen=True, slots=True)
class GeminiPlanMergeResult:
    plan: InvestigationPlan
    decisions: list[AIDecisionRecord] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "deterministic"
    fallback_used: bool = False


def build_planning_context(
    goal: str,
    scenario: ScenarioDefinition,
    resource: TerraformResourceChange,
    base_plan: InvestigationPlan,
    tool_registry: ToolRegistry,
) -> dict[str, Any]:
    return redact_model_payload({
        "objective": goal,
        "scenario_name": scenario.name,
        "provider": _provider_from_resource(resource),
        "resource_type": resource.resource_type,
        "resource_address": resource.address,
        "before": resource.before,
        "after": resource.after,
        "environment": resource.environment,
        "action_type": resource.actions,
        "tags": resource.tags,
        "available_read_only_tools": list(tool_registry.names()),
        "known_evidence_categories": ["pricing", "utilization", "jira", "git_activity", "dependencies"],
        "current_missing_fields": [question.id for question in base_plan.questions if question.status == "unresolved"],
        "deterministic_required_tools": base_plan.selected_tools,
        "safety_boundaries": [
            "Gemini cannot approve, mutate infrastructure, run Terraform, or write to GitHub.",
            "Deterministic policy, verifier, and human approval remain authoritative.",
        ],
    })


def merge_gemini_plan(
    goal: str,
    scenario: ScenarioDefinition,
    resource: TerraformResourceChange,
    base_plan: InvestigationPlan,
    tool_registry: ToolRegistry,
    *,
    configuration: Settings = settings,
    client: StructuredAIClient | None = None,
) -> GeminiPlanMergeResult:
    if not configuration.gemini_assisted_planning_enabled:
        return GeminiPlanMergeResult(
            plan=base_plan,
            fallback_used=True,
            audit_events=[_audit("gemini_planning_fallback", "Gemini assisted planning is disabled.", {"provider": "disabled", "fallback_used": True})],
        )
    selected_client = client if client is not None else build_ai_client(configuration)
    if selected_client is None:
        return GeminiPlanMergeResult(
            plan=base_plan,
            fallback_used=True,
            audit_events=[_audit("gemini_planning_fallback", "Gemini provider unavailable; deterministic plan used.", {"provider": "disabled", "fallback_used": True})],
        )

    audit = [_audit("gemini_planning_started", "Gemini assisted planning started.", {"provider": configuration.ai_provider, "model": configuration.gemini_model})]
    decisions: list[AIDecisionRecord] = []
    context = build_planning_context(goal, scenario, resource, base_plan, tool_registry)
    try:
        call = selected_client.propose_investigation_plan(context)
        proposal = call.value
        if not isinstance(proposal, GeminiInvestigationPlan):
            raise AIClientError("schema_validation_failed", "Gemini investigation plan schema was invalid.")
        validated, validation_notes = validate_gemini_plan(proposal, set(tool_registry.names()))
        merged = _merge(base_plan, validated)
        decisions.append(_decision(call, "Accepted Gemini investigation plan after deterministic validation."))
        audit.append(_audit("gemini_planning_completed", "Gemini assisted planning returned a valid proposal.", _metadata(call, False, validation_notes)))
        audit.append(_audit("gemini_plan_merged", "Validated Gemini questions were merged into the deterministic plan.", {"selected_tools": merged.selected_tools, "fallback_used": False}))
        return GeminiPlanMergeResult(plan=merged, decisions=decisions, audit_events=audit, provider=call.planning_mode, fallback_used=False)
    except AIClientError as exc:
        audit.append(_audit("gemini_planning_failed", exc.safe_message, {"provider": configuration.ai_provider, "error_category": exc.category}))
        audit.append(_audit("gemini_planning_fallback", "Deterministic investigation plan used after Gemini failure.", {"fallback_used": True, "reason": exc.category}))
        return GeminiPlanMergeResult(plan=base_plan, decisions=decisions, audit_events=audit, provider="deterministic", fallback_used=True)
    except Exception:
        audit.append(_audit("gemini_planning_failed", "Gemini planning response was malformed.", {"provider": configuration.ai_provider, "error_category": "schema_validation_failed"}))
        audit.append(_audit("gemini_planning_fallback", "Deterministic investigation plan used after malformed Gemini response.", {"fallback_used": True}))
        return GeminiPlanMergeResult(plan=base_plan, decisions=decisions, audit_events=audit, provider="deterministic", fallback_used=True)


def validate_gemini_plan(plan: GeminiInvestigationPlan, allowed_tools: set[str]) -> tuple[GeminiInvestigationPlan, list[str]]:
    notes: list[str] = []
    all_text = " ".join(
        [plan.summary, *plan.planning_notes, *plan.uncertainties]
        + [question.question + " " + question.reason for question in plan.questions]
    ).lower()
    if any(term in all_text for term in PROHIBITED_PLAN_TERMS):
        raise AIClientError("unsafe_action_rejected", "Gemini proposed a prohibited action.")
    selected = _valid_tools(plan.selected_tools, allowed_tools, notes)
    skipped = _valid_tools(plan.skipped_tools, allowed_tools, notes)
    questions: list[Any] = []
    seen_questions: set[str] = set()
    for question in plan.questions[:6]:
        sources = _valid_tools(question.required_evidence_sources, allowed_tools, notes)
        if not sources:
            notes.append(f"question_without_valid_sources:{question.id}")
            continue
        question_id = question.id.strip()[:64]
        if not question_id or question_id in seen_questions:
            continue
        seen_questions.add(question_id)
        questions.append(question.model_copy(update={"id": question_id, "required_evidence_sources": sources}))
    if not questions:
        raise AIClientError("schema_validation_failed", "Gemini plan contained no valid questions.")
    return plan.model_copy(update={"questions": questions, "selected_tools": selected, "skipped_tools": skipped}), notes


def _valid_tools(tools: list[str], allowed_tools: set[str], notes: list[str]) -> list[str]:
    output: list[str] = []
    for tool in tools:
        if tool not in allowed_tools:
            notes.append(f"unknown_tool_rejected:{tool}")
            continue
        if tool not in output:
            output.append(tool)
    return output


def _merge(base_plan: InvestigationPlan, proposal: GeminiInvestigationPlan) -> InvestigationPlan:
    selected = list(dict.fromkeys([*base_plan.selected_tools, *proposal.selected_tools]))
    for question in proposal.questions:
        for source in question.required_evidence_sources:
            if source not in selected:
                selected.append(source)
    questions = list(base_plan.questions)
    existing = {question.id for question in questions}
    for question in proposal.questions:
        question_id = question.id if question.id not in existing else f"gemini_{question.id}"[:64]
        if question_id in existing:
            continue
        existing.add(question_id)
        questions.append(InvestigationQuestion(
            id=question_id,
            question=question.question,
            required_evidence_sources=question.required_evidence_sources,
        ))
    skipped = [tool for tool in base_plan.skipped_tools if tool not in selected]
    return base_plan.model_copy(deep=True, update={
        "questions": questions,
        "selected_tools": selected,
        "skipped_tools": skipped,
        "planning_notes": [
            *base_plan.planning_notes,
            f"Gemini assistance summary: {proposal.summary}",
            *[f"Gemini note: {note}" for note in proposal.planning_notes],
            *[f"Gemini uncertainty: {item}" for item in proposal.uncertainties],
        ],
    })


def _decision(call: Any, validation_result: str) -> AIDecisionRecord:
    return AIDecisionRecord(
        sequence_number=1,
        model=call.model,
        planning_mode=call.planning_mode,
        purpose="choose_next_tool",
        input_summary="Minimized redacted investigation planning context.",
        proposed_action=None,
        accepted=True,
        validation_result=validation_result,
        fallback_used=False,
        latency_ms=call.latency_ms,
        created_at=utc_now(),
        usage_metadata=call.usage_metadata,
    )


def _audit(event_type: str, summary: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"event_type": event_type, "summary": summary, "details": redact_model_payload(details)}


def _metadata(call: Any, fallback: bool, validation_notes: list[str]) -> dict[str, Any]:
    return {
        "provider": "gemini" if call.planning_mode != "mock_gemini" else "mock",
        "model": call.model,
        "request_purpose": "investigation_planning",
        "latency_ms": call.latency_ms,
        "success": True,
        "fallback_used": fallback,
        "validation_errors": validation_notes,
        "retry_count": call.usage_metadata.get("retry_count", 0),
    }


def _provider_from_resource(resource: TerraformResourceChange) -> str | None:
    if resource.resource_type.startswith("aws_"):
        return "aws"
    if resource.resource_type.startswith("azurerm_"):
        return "azure"
    if resource.resource_type.startswith("google_"):
        return "gcp"
    return None
