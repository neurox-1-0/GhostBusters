from __future__ import annotations

from dataclasses import replace

import pytest

from app.models import GeminiInvestigationPlan, GeminiInvestigationQuestion
from app.settings import settings
from core.gemini_planning import merge_gemini_plan, validate_gemini_plan
from core.ai_client import AICallResult, AIClientError
from integrations.registry import default_registry
from tests.scenario_helpers import load_resource, load_scenario
from core.planner import create_investigation_plan


class PlanClient:
    def __init__(self, plan: GeminiInvestigationPlan) -> None:
        self.plan = plan

    def propose_investigation_plan(self, payload):  # type: ignore[no-untyped-def]
        return AICallResult(self.plan, "mock-gemini", "mock_gemini", 0, {"retry_count": 0})

    def interpret_objective(self, payload):  # type: ignore[no-untyped-def]
        raise AssertionError

    def propose_next_action(self, payload):  # type: ignore[no-untyped-def]
        raise AssertionError

    def explain_recommendation(self, payload):  # type: ignore[no-untyped-def]
        raise AssertionError

    def answer_assistant_question(self, payload):  # type: ignore[no-untyped-def]
        raise AssertionError


def test_valid_gemini_questions_merge_without_removing_required_tools() -> None:
    scenario = load_scenario("safe")
    resource = load_resource("safe")
    base = create_investigation_plan(scenario.goal, scenario, resource, default_registry)
    proposal = GeminiInvestigationPlan(
        summary="Check activity too.",
        questions=[
            GeminiInvestigationQuestion(id="git_check", question="Is Git activity relevant?", required_evidence_sources=["git_activity"], reason="Recent work may affect safety."),
        ],
        selected_tools=["git_activity", "pricing"],
        planning_notes=["Keep deterministic tools."],
    )

    result = merge_gemini_plan(
        scenario.goal,
        scenario,
        resource,
        base,
        default_registry,
        configuration=replace(settings, ai_enabled=True, ai_provider="mock", gemini_assisted_planning_enabled=True),
        client=PlanClient(proposal),
    )

    assert not result.fallback_used
    assert set(base.selected_tools).issubset(set(result.plan.selected_tools))
    assert "git_activity" in result.plan.selected_tools
    assert any(question.id == "git_check" for question in result.plan.questions)
    assert any(event["event_type"] == "gemini_plan_merged" for event in result.audit_events)


def test_unknown_tools_are_rejected_and_empty_plan_fails() -> None:
    proposal = GeminiInvestigationPlan(
        summary="Unknown tool.",
        questions=[
            GeminiInvestigationQuestion(id="bad", question="Use shell?", required_evidence_sources=["shell"], reason="Not allowed."),
        ],
        selected_tools=["shell"],
    )

    with pytest.raises(AIClientError):
        validate_gemini_plan(proposal, {"pricing"})
