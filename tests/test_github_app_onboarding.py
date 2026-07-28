from dataclasses import replace
from uuid import uuid4

import pytest

from app.models import GitHubIntegrationConfigRequest
from app.settings import Settings
from core.github_integration import GitHubIntegrationStore
from integrations.github_app import GitHubAppState


def test_github_app_state_is_signed_one_time_and_expiring() -> None:
    configuration = Settings(secret_key="s" * 48, github_app_state_ttl_seconds=60)
    state_store = GitHubAppState()
    state = state_store.create(str(uuid4()), str(uuid4()), configuration)
    payload = state_store.consume(state, configuration)
    assert payload["organization_id"]
    with pytest.raises(ValueError, match="already used"):
        state_store.consume(state, configuration)

    expired = state_store.create(str(uuid4()), str(uuid4()), replace(configuration, github_app_state_ttl_seconds=-1))
    with pytest.raises(ValueError, match="expired"):
        state_store.consume(expired, configuration)


def test_installation_metadata_contains_no_secret_material(tmp_path) -> None:
    organization_id = uuid4()
    store = GitHubIntegrationStore(Settings(github_integration_config_path=tmp_path / "github.json"))
    config = store.update_installation(organization_id, installation_id=42, account_login="acme", account_type="Organization", repositories=[{"full_name": "acme/infra", "private": True, "default_branch": "main", "installation_access": "available", "token": "must-not-persist"}])
    serialized = str(config.model_dump())
    assert config.installation_id == 42
    assert "must-not-persist" not in serialized
    assert "token" not in serialized.lower()


def test_manual_config_update_supports_optimistic_version(tmp_path) -> None:
    organization_id = uuid4()
    store = GitHubIntegrationStore(Settings(github_integration_config_path=tmp_path / "github.json"))
    current = store.get(organization_id)
    updated = store.update(organization_id, GitHubIntegrationConfigRequest(enabled=True, expected_version=current.version))
    assert updated.version == current.version + 1
    with pytest.raises(ValueError, match="stale"):
        store.update(organization_id, GitHubIntegrationConfigRequest(enabled=False, expected_version=current.version))
