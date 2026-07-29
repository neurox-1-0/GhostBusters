from uuid import uuid4

import pytest

from core.aws_onboarding import AWSOnboardingState


def test_signed_aws_onboarding_state_is_bound_to_the_organization() -> None:
    organization_id = uuid4()
    state = AWSOnboardingState("a" * 32, 900)

    token, correlation_id = state.create(organization_id, None)

    payload = state.consume(token)
    assert payload["organization_id"] == str(organization_id)
    assert payload["correlation_id"] == correlation_id
    assert state.external_id(organization_id) == state.external_id(organization_id)
    assert state.external_id(organization_id) != state.external_id(uuid4())


def test_tampered_aws_onboarding_state_is_rejected() -> None:
    state = AWSOnboardingState("a" * 32, 900)
    token, _ = state.create(uuid4(), None)

    with pytest.raises(ValueError):
        state.consume(token[:-1] + ("a" if token[-1] != "a" else "b"))
