from dataclasses import replace

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.models import GeminiGoalValidation
from core.ai_client import AICallResult


client = TestClient(app)


def test_goal_validation_accepts_supported_safe_goal() -> None:
    response = client.post("/api/goals/validate", json={
        "goal": "Reduce non-production cloud waste while protecting production workloads.",
        "scope": "Non-production AWS",
        "require_approval": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "run_cloud_hunt" in body["suggested_capabilities"]
    assert "Human approval required" in body["constraints"]


def test_goal_validation_rejects_unsafe_or_unrelated_input() -> None:
    unsafe = client.post("/api/goals/validate", json={"goal": "Delete all AWS servers", "scope": "Production AWS"})
    unrelated = client.post("/api/goals/validate", json={"goal": "Plan a birthday party", "scope": "Home"})

    assert unsafe.status_code == 200
    assert unsafe.json()["status"] == "rejected"
    assert unrelated.status_code == 200
    assert unrelated.json()["status"] == "rejected"


def test_goal_validation_recognizes_ambiguous_cloud_bill_target() -> None:
    response = client.post("/api/goals/validate", json={"goal": "Reduce the cloud bills up to 15%", "scope": "Workspace"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_revision"
    assert body["reason"] == 'The meaning of "up to 15%" is ambiguous.'
    assert body["suggested_goal"] == "Identify safe opportunities to reduce non-production AWS spending by 15%, protect production, and require approval before any change."
    assert body["requested_scope"]["clarifying_questions"] == [
        "Is the target a 15% reduction in current spending?",
        "Which AWS environment or account is in scope?",
        "What time period should be used?",
        "Must production remain protected?",
    ]


def test_goal_validation_recognizes_cloud_cost_language() -> None:
    for goal in ("Lower AWS spending by 10%", "Reduce cloud expenses"):
        response = client.post("/api/goals/validate", json={"goal": goal, "scope": "Non-production AWS"})
        assert response.status_code == 200
        assert response.json()["status"] in {"accepted", "needs_revision"}


def test_gemini_supported_needs_revision_is_preserved(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class GeminiValidationClient:
        def validate_goal(self, payload):  # type: ignore[no-untyped-def]
            return AICallResult(
                value=GeminiGoalValidation(
                    status="needs_revision",
                    reason="Need the target period.",
                    normalized_goal="Reduce cloud bills safely.",
                    category="cost_optimization",
                    clarifying_questions=[{"id": "time_period", "question": "What time period should be used?", "answer_type": "text", "options": [], "placeholder": "Enter a period", "required": True, "why_needed": "The target needs a measurement period."}],
                    risk_level="medium",
                ),
                model="test-gemini",
                planning_mode="gemini_primary",
                latency_ms=0,
                usage_metadata={},
            )

    monkeypatch.setattr(main, "settings", replace(main.settings, app_env="production", ai_enabled=True, gemini_assisted_planning_enabled=True, gemini_api_key="test-key"))
    monkeypatch.setattr(main, "build_ai_client", lambda configuration: GeminiValidationClient())

    response = client.post("/api/goals/validate", json={"goal": "Reduce the cloud bills", "scope": "Workspace"})

    assert response.status_code == 200
    assert response.json()["status"] == "needs_revision"
    assert response.json()["reason"] == "Need the target period."


def test_goal_validation_stops_after_two_clarification_rounds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class GeminiValidationClient:
        def validate_goal(self, payload):  # type: ignore[no-untyped-def]
            return AICallResult(value=GeminiGoalValidation(status="needs_revision", reason="Still need scope.", normalized_goal="Reduce cloud spending.", category="cost_optimization", missing_fields=["Scope"]), model="test-gemini", planning_mode="gemini_primary", latency_ms=0, usage_metadata={})

    monkeypatch.setattr(main, "settings", replace(main.settings, app_env="production", ai_enabled=True, gemini_assisted_planning_enabled=True, gemini_api_key="test-key"))
    monkeypatch.setattr(main, "build_ai_client", lambda configuration: GeminiValidationClient())
    response = client.post("/api/goals/validate", json={"goal": "Reduce cloud spending", "scope": "Workspace", "clarification_round": 2})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "two clarification rounds" in response.json()["reason"]
