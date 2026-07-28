import hashlib
import hmac
import json
from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main_module
from app.models import GitHubTerraformChange, GitHubTerraformResourceChange
from app.settings import Settings
from core.run_store import InMemoryRunStore
from core.workflow_service import WorkflowService


def source() -> GitHubTerraformChange:
    return GitHubTerraformChange(
        repository="acme/infra", pull_request_number=7, pull_request_url="https://github.test/acme/infra/pull/7",
        pull_request_title="Resize", author="dev", base_branch="main", base_sha="base", head_branch="resize", head_sha="head",
        changed_files=["infra/main.tf"], terraform_files=["infra/main.tf"], provider="aws", environment="staging",
        resource_changes=[GitHubTerraformResourceChange(address="aws_instance.app", provider="aws", resource_type="aws_instance", resource_name="app", actions=["update"], before={"instance_type": "m5.large"}, after={"instance_type": "m5.xlarge"}, changed_attributes=["instance_type"], destructive=False, source_file="infra/main.tf")],
    )


def test_github_run_uses_connected_organization_and_delivery_id() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    service = WorkflowService(InMemoryRunStore(), configuration=Settings(ai_enabled=False, github_integration_enabled=False))
    run, created = service.start_github_run(source(), "delivery-org-1", organization_id=organization_id)
    assert created is True
    assert run.organization_id == organization_id
    assert run.source_type == "terraform_pr"
    assert run.idempotency_key == "delivery-org-1"
    assert [item.id for item in service.list_runs(organization_id)] == [run.id]
    assert service.list_runs(other_organization_id) == []
    duplicate, duplicate_created = service.start_github_run(source(), "delivery-org-1", organization_id=organization_id)
    assert duplicate_created is False
    assert duplicate.id == run.id


def test_unknown_installation_is_rejected_without_creating_a_run(monkeypatch) -> None:
    secret = "webhook-test-secret"
    monkeypatch.setattr(main_module, "settings", Settings(app_env="production", github_integration_enabled=True, github_webhook_secret=secret))
    monkeypatch.setattr(main_module.github_integration_store, "find_by_installation", lambda installation_id: None)
    payload = {"action": "opened", "number": 7, "repository": {"full_name": "acme/infra"}, "pull_request": {"number": 7}, "installation": {"id": 987654}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = TestClient(main_module.app).post("/webhooks/github", content=body, headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "unknown-installation", "X-Hub-Signature-256": signature})
    assert response.status_code == 403
    assert "not connected" in response.json()["detail"]
