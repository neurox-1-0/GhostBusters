from __future__ import annotations

from dataclasses import replace

import pytest

from app.models import AgentNextAction, ObjectiveInterpretation
from app.settings import settings
from core.ai_client import AICallResult, AIClientError, GeminiAIClient, MockGeminiClient


def _interpretation() -> ObjectiveInterpretation:
    return ObjectiveInterpretation(
        original_objective="reduce cost safely",
        objective_type="cost_optimization",
        normalized_goal="Reduce cost safely",
        plain_language_summary="Cost optimization review.",
    )


class FallbackGeminiClient(GeminiAIClient):
    def _load_client(self) -> None:
        self._client = object()
        self._types = object()

    def _generate(self, model, schema, prompt):  # type: ignore[no-untyped-def]
        if model == self.configuration.gemini_model:
            raise AIClientError("model_unavailable", "Gemini model is unavailable.", model=model)
        value = _interpretation() if schema is ObjectiveInterpretation else AgentNextAction(
            action="finish_investigation", reason="Evidence is complete.", question_being_answered="Is it complete?", expected_information="Complete evidence.", confidence=0.8
        )
        return AICallResult(value=value, model=model, planning_mode="gemini_fallback_model", latency_ms=2, usage_metadata={})


class BothUnavailableClient(FallbackGeminiClient):
    def _generate(self, model, schema, prompt):  # type: ignore[no-untyped-def]
        raise AIClientError("model_unavailable", "Gemini model is unavailable.", model=model)


class PrimaryGeminiClient(FallbackGeminiClient):
    def _generate(self, model, schema, prompt):  # type: ignore[no-untyped-def]
        return AICallResult(value=_interpretation(), model=model, planning_mode="gemini_primary", latency_ms=1, usage_metadata={"tokens": 3})


class SequencedGeminiClient(GeminiAIClient):
    def __init__(self, configuration, outcomes):  # type: ignore[no-untyped-def]
        super().__init__(configuration)
        self.outcomes = {model: list(values) for model, values in outcomes.items()}
        self.calls: list[str] = []

    def _generate(self, model, schema, prompt):  # type: ignore[no-untyped-def]
        self.calls.append(model)
        outcome = self.outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return AICallResult(
            value=outcome,
            model=model,
            planning_mode="gemini_primary" if model == self.configuration.gemini_model else "gemini_fallback_model",
            latency_ms=1,
            usage_metadata={},
        )


def _failure(category: str, model: str) -> AIClientError:
    return AIClientError(category, "safe provider failure", model=model)


def test_missing_key_is_classified_without_exposing_a_secret() -> None:
    client = GeminiAIClient(replace(settings, gemini_api_key=None))
    with pytest.raises(AIClientError) as error:
        client.interpret_objective({"objective": "safe"})
    assert error.value.category == "missing_api_key"
    assert "local-test-key" not in error.value.safe_message


def test_primary_model_unavailable_uses_configured_fallback_model() -> None:
    client = FallbackGeminiClient(replace(settings, gemini_api_key="local-test-key"))
    result = client.interpret_objective({"objective": "reduce cost safely"})
    assert result.planning_mode == "gemini_fallback_model"
    assert result.model == settings.gemini_fallback_model


def test_primary_model_success_records_primary_mode() -> None:
    client = PrimaryGeminiClient(replace(settings, gemini_api_key="local-test-key"))
    result = client.interpret_objective({"objective": "reduce cost safely"})
    assert result.planning_mode == "gemini_primary"
    assert result.model == settings.gemini_model


def test_both_models_unavailable_are_reported_as_safe_provider_failure() -> None:
    client = BothUnavailableClient(replace(settings, gemini_api_key="local-test-key"))
    with pytest.raises(AIClientError) as error:
        client.interpret_objective({"objective": "reduce cost safely"})
    assert error.value.category == "model_unavailable"
    assert error.value.model == settings.gemini_fallback_model


@pytest.mark.parametrize("category", ["provider_error", "rate_limited", "timeout"])
def test_transient_primary_failure_retries_then_uses_fallback(category: str) -> None:
    configuration = replace(settings, gemini_api_key="local-test-key", gemini_max_retries=1)
    client = SequencedGeminiClient(
        configuration,
        {
            configuration.gemini_model: [_failure(category, configuration.gemini_model)] * 2,
            configuration.gemini_fallback_model: [_interpretation()],
        },
    )

    result = client.interpret_objective({"objective": "reduce cost safely"})

    assert client.calls == [configuration.gemini_model, configuration.gemini_model, configuration.gemini_fallback_model]
    assert result.model == configuration.gemini_fallback_model
    assert result.planning_mode == "gemini_fallback_model"


def test_schema_validation_failure_does_not_use_fallback() -> None:
    configuration = replace(settings, gemini_api_key="local-test-key")
    client = SequencedGeminiClient(
        configuration,
        {
            configuration.gemini_model: [_failure("schema_validation_failed", configuration.gemini_model)],
            configuration.gemini_fallback_model: [_interpretation()],
        },
    )

    with pytest.raises(AIClientError, match="safe provider failure"):
        client.interpret_objective({"objective": "reduce cost safely"})
    assert client.calls == [configuration.gemini_model]


def test_missing_api_key_error_does_not_use_fallback() -> None:
    configuration = replace(settings, gemini_api_key="local-test-key")
    client = SequencedGeminiClient(
        configuration,
        {
            configuration.gemini_model: [_failure("missing_api_key", configuration.gemini_model)],
            configuration.gemini_fallback_model: [_interpretation()],
        },
    )

    with pytest.raises(AIClientError, match="safe provider failure"):
        client.interpret_objective({"objective": "reduce cost safely"})
    assert client.calls == [configuration.gemini_model]


def test_fallback_failure_returns_its_final_safe_error() -> None:
    configuration = replace(settings, gemini_api_key="local-test-key", gemini_max_retries=0)
    client = SequencedGeminiClient(
        configuration,
        {
            configuration.gemini_model: [_failure("provider_error", configuration.gemini_model)],
            configuration.gemini_fallback_model: [_failure("provider_error", configuration.gemini_fallback_model)],
        },
    )

    with pytest.raises(AIClientError) as error:
        client.interpret_objective({"objective": "reduce cost safely"})
    assert error.value.category == "provider_error"
    assert error.value.model == configuration.gemini_fallback_model


def test_transient_active_primary_failure_still_uses_fallback() -> None:
    configuration = replace(settings, gemini_api_key="local-test-key", gemini_max_retries=0)
    client = SequencedGeminiClient(
        configuration,
        {
            configuration.gemini_model: [_failure("provider_error", configuration.gemini_model)],
            configuration.gemini_fallback_model: [_interpretation()],
        },
    )
    client.active_model = configuration.gemini_model

    result = client.interpret_objective({"objective": "reduce cost safely"})

    assert client.calls == [configuration.gemini_model, configuration.gemini_fallback_model]
    assert result.planning_mode == "gemini_fallback_model"


def test_mock_provider_is_structured_and_offline() -> None:
    client = MockGeminiClient()
    result = client.interpret_objective({"objective": "reduce cost safely"})
    assert result.planning_mode == "mock_gemini"
    assert result.model == "mock-gemini"
    assert isinstance(result.value, ObjectiveInterpretation)
