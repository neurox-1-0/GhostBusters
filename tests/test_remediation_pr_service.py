from __future__ import annotations

import pytest

from app.models import HumanReviewRecord
from app.settings import Settings
from core.run_store import InMemoryRunStore
from core.workflow_service import WorkflowService
from integrations.base import utc_now
from integrations.github_client import GitHubAPIError
from integrations.remediation_pr_service import RemediationPRService, RemediationValidationError
from tests.test_real_pr_workflow import source


class WriteRecordingGitHub:
    def __init__(self, content: str = 'resource "aws_instance" "app" {\n  instance_type = "m5.xlarge"\n}\n') -> None:
        self.content = content
        self.branch_source = None
        self.updated = None
        self.pr_calls = 0
        self.pr_request = None
        self.compare_calls = 0
        self.compare_result = {
            "status": "ahead",
            "ahead_by": 1,
            "behind_by": 0,
            "files": [{"filename": "infra/main.tf", "patch": "@@ -1 +1 @@\n-instance_type = \"m5.xlarge\"\n+instance_type = \"m5.large\""}],
        }
    def get_file_content(self, owner, repo, path, ref):
        return {"content": self.content, "sha": "file-sha"}
    def list_open_pull_requests(self, owner, repo, head):
        return []
    def get_branch(self, owner, repo, branch):
        raise GitHubAPIError("not_found", "not found")
    def create_branch(self, owner, repo, new_branch, source_sha):
        self.branch_source = source_sha
        return {}
    def update_or_create_file(self, owner, repo, branch, path, content, message, existing_sha):
        self.updated = (path, content)
        return {}
    def create_pull_request(self, owner, repo, title, body, head, base):
        self.pr_calls += 1
        self.pr_request = {"title": title, "body": body, "head": head, "base": base}
        return {"number": 77, "html_url": "https://github.test/demo/infra/pull/77"}
    def compare_branches(self, owner, repo, base, head):
        self.compare_calls += 1
        return self.compare_result


def prepared_run():
    service = WorkflowService(InMemoryRunStore(), configuration=Settings(ai_enabled=False))
    run, _ = service.start_github_run(source(), "delivery-remediation")
    return run


def test_real_remediation_writes_only_analysed_file_and_creates_pr() -> None:
    client = WriteRecordingGitHub()
    result = RemediationPRService(client, Settings(github_remediation_branch_prefix="ghostbusters/remediation")).create(prepared_run(), HumanReviewRecord(reviewer="judge", action="approve", created_at=utc_now()))
    assert result.url.endswith("/77")
    assert client.branch_source == "head"
    assert client.updated[0] == "infra/main.tf"
    assert 'instance_type = "m5.large"' in client.updated[1]
    assert client.pr_calls == 1
    assert client.pr_request is not None
    assert client.pr_request["base"] == "resize"
    assert client.compare_calls == 1


def test_empty_remediation_pr_is_rejected_before_creation() -> None:
    client = WriteRecordingGitHub()
    client.compare_result = {"status": "identical", "ahead_by": 0, "behind_by": 0, "files": []}
    with pytest.raises(RemediationValidationError, match="no diff"):
        RemediationPRService(client, Settings(github_remediation_branch_prefix="ghostbusters/remediation")).create(prepared_run(), HumanReviewRecord(reviewer="judge", action="approve", created_at=utc_now()))
    assert client.pr_calls == 0


def test_reused_open_remediation_pr_is_not_recreated() -> None:
    client = WriteRecordingGitHub()
    client.list_open_pull_requests = lambda owner, repo, head: [{"number": 88, "html_url": "https://github.test/demo/infra/pull/88", "title": "GhostBusters remediation"}]
    result = RemediationPRService(client, Settings(github_remediation_branch_prefix="ghostbusters/remediation")).create(prepared_run(), HumanReviewRecord(reviewer="judge", action="approve", created_at=utc_now()))
    assert result.reused is True
    assert result.number == 88
    assert result.base_branch == "resize"
    assert client.pr_calls == 0


def test_stale_old_value_blocks_all_writes() -> None:
    client = WriteRecordingGitHub('resource "aws_instance" "app" {\n  instance_type = "m6.large"\n}\n')
    with pytest.raises(RemediationValidationError, match="stale"):
        RemediationPRService(client).create(prepared_run(), HumanReviewRecord(reviewer="judge", action="approve", created_at=utc_now()))
    assert client.branch_source is None
    assert client.updated is None
