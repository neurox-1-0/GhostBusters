import pytest
from pydantic import ValidationError

from app.models import GeminiGoalValidation
from core.ai_client import GeminiAIClient


def parse(text: str) -> GeminiGoalValidation:
    raw = GeminiAIClient._parse_json_text(text)
    return GeminiGoalValidation.model_validate(GeminiAIClient._normalize_structured_payload(GeminiGoalValidation, raw))


def test_plain_and_fenced_goal_validation_json_are_accepted() -> None:
    payload = '{"status":"accepted","reason":"Relevant","normalized_goal":"Review cloud cost","category":"cost","risk_level":"medium"}'
    assert parse(payload).status == "accepted"
    assert parse(f"```json\n{payload}\n```").normalized_goal == "Review cloud cost"


def test_optional_arrays_normalize_from_null() -> None:
    result = parse('{"status":"needs_revision","reason":"Need scope","normalized_goal":"Review cost","category":"cost","missing_fields":null,"clarifying_questions":null,"constraints":null,"success_criteria":null,"stop_conditions":null,"suggested_capabilities":null,"risk_level":"medium"}')
    assert result.missing_fields == []
    assert result.suggested_capabilities == []


def test_invalid_status_and_malformed_json_are_rejected() -> None:
    with pytest.raises(ValidationError):
        parse('{"status":"maybe","reason":"x","normalized_goal":"x","category":"x","risk_level":"medium"}')
    with pytest.raises(ValueError):
        GeminiAIClient._parse_json_text("not-json")
    with pytest.raises(ValueError):
        GeminiAIClient._parse_json_text("")
