import pytest
from pydantic import ValidationError

from app.models import GeminiGoalValidation, ObjectiveInterpretation
from app.settings import settings
from core.ai_client import AIClientError, GeminiAIClient


def parse(text: str) -> GeminiGoalValidation:
    raw = GeminiAIClient._parse_json_text(text)
    return GeminiGoalValidation.model_validate(GeminiAIClient._normalize_structured_payload(GeminiGoalValidation, raw))


def test_plain_and_fenced_goal_validation_json_are_accepted() -> None:
    payload = '{"status":"accepted","reason":"Relevant","normalized_goal":"Review cloud cost","category":"cost","risk_level":"medium"}'
    assert parse(payload).status == "accepted"
    assert parse(f"```json\n{payload}\n```").normalized_goal == "Review cloud cost"
    assert parse(f" \n {payload} \n ").status == "accepted"


def test_optional_arrays_normalize_from_null() -> None:
    result = parse('{"status":"needs_revision","reason":"Need scope","normalized_goal":"Review cost","category":"cost","missing_fields":null,"clarifying_questions":null,"constraints":null,"success_criteria":null,"stop_conditions":null,"suggested_capabilities":null,"risk_level":"medium"}')
    assert result.missing_fields == []
    assert result.suggested_capabilities == []


def test_optional_arrays_normalize_when_missing() -> None:
    result = parse('{"status":"accepted","reason":"Relevant","normalized_goal":"Review cost","category":"cost","risk_level":"medium"}')
    assert result.missing_fields == []
    assert result.clarifying_questions == []


def test_invalid_risk_and_non_object_json_are_rejected() -> None:
    with pytest.raises(ValidationError):
        parse('{"status":"accepted","reason":"x","normalized_goal":"x","category":"x","risk_level":"critical"}')
    with pytest.raises(ValueError):
        GeminiAIClient._parse_json_text("[]")


def test_invalid_status_and_malformed_json_are_rejected() -> None:
    with pytest.raises(ValidationError):
        parse('{"status":"maybe","reason":"x","normalized_goal":"x","category":"x","risk_level":"medium"}')
    with pytest.raises(ValueError):
        GeminiAIClient._parse_json_text("not-json")
    with pytest.raises(ValueError):
        GeminiAIClient._parse_json_text("")


class _Config:
    def __init__(self, **values):  # type: ignore[no-untyped-def]
        self.values = values


class _Types:
    GenerateContentConfig = _Config


class _Models:
    def __init__(self, response):  # type: ignore[no-untyped-def]
        self.response = response
        self.config = None

    def generate_content(self, *, model, contents, config):  # type: ignore[no-untyped-def]
        self.config = config
        return self.response


class _Client:
    def __init__(self, response):  # type: ignore[no-untyped-def]
        self.models = _Models(response)


class _Response:
    def __init__(self, *, parsed=None, text=None):  # type: ignore[no-untyped-def]
        self.parsed = parsed
        self.text = text
        self.candidates = []


def _generated(response: _Response):
    client = GeminiAIClient(settings)
    client._client = _Client(response)
    client._types = _Types()
    return client


def test_generate_uses_parsed_dictionary_without_provider_schema() -> None:
    client = _generated(_Response(parsed={
        "original_objective": "Reduce cost", "objective_type": "cost_optimization", "normalized_goal": "Reduce cost",
        "plain_language_summary": "Review cost safely.",
    }))

    result = client._generate("test-model", ObjectiveInterpretation, "prompt")

    assert result.value.normalized_goal == "Reduce cost"
    assert client._client.models.config.values["response_mime_type"] == "application/json"
    assert "response_schema" not in client._client.models.config.values


def test_empty_and_malformed_generation_responses_fail_safely() -> None:
    for response in (_Response(text=""), _Response(text="not-json"), _Response(text="[]")):
        with pytest.raises(AIClientError) as error:
            _generated(response)._generate("test-model", GeminiGoalValidation, "prompt")
        assert error.value.category in {"provider_error", "schema_validation_failed"}


def test_pydantic_validation_still_runs_for_generated_json() -> None:
    with pytest.raises(AIClientError) as error:
        _generated(_Response(text='{"status":"invalid","reason":"x","normalized_goal":"x","category":"x"}'))._generate(
            "test-model", GeminiGoalValidation, "prompt"
        )
    assert error.value.category == "schema_validation_failed"
