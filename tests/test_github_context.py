from datetime import datetime, timezone

from integrations.github_context import GitHubContextAdapter, resolve_codeowners
from integrations.github_client import GitHubAPIError


class FakeGitHubClient:
    def __init__(self, fail_validation: bool = False) -> None:
        self.fail_validation = fail_validation
        self.calls: list[str] = []

    def get_authenticated_user(self):
        self.calls.append("get_authenticated_user")
        if self.fail_validation: raise GitHubAPIError("permission", "missing permissions")
        return {"login": "owner"}

    def list_repositories(self):
        self.calls.append("list_repositories")
        return [{"full_name": "acme/app"}, {"full_name": "acme/other"}]

    def get_pull_request(self, owner, repo, number):
        self.calls.append("get_pull_request")
        return {"title": "Reduce instance size", "body": "Context", "user": {"login": "author"}, "head": {"ref": "feature", "sha": "abc"}, "base": {"ref": "main"}, "state": "open", "labels": [{"name": "terraform"}], "html_url": "https://github.com/acme/app/pull/7"}

    def list_pull_request_files(self, owner, repo, number):
        self.calls.append("list_pull_request_files")
        return [{"filename": "infra/main.tf", "status": "modified", "additions": 2, "deletions": 1}]

    def get_repository(self, owner, repo):
        self.calls.append("get_repository")
        return {"default_branch": "main"}

    def get_file_content(self, owner, repo, path, ref):
        self.calls.append(f"get_file_content:{path}")
        if path == ".github/CODEOWNERS": raise GitHubAPIError("not_found", "not found")
        return {"content": "*.tf @platform\n", "path": path}

    def list_commits(self, owner, repo, **kwargs):
        self.calls.append("list_commits")
        return [{"commit": {"author": {"date": datetime.now(timezone.utc).isoformat()}}}]

    def list_pull_request_reviews(self, owner, repo, number):
        self.calls.append("list_pull_request_reviews")
        return [{"user": {"login": "reviewer"}, "state": "APPROVED", "submitted_at": "2026-01-01T00:00:00Z"}]


def test_codeowners_explicit_and_unknown_resolution() -> None:
    result = resolve_codeowners("*.tf @platform\nmodules/* @module-team\n", ["infra/main.tf", "docs/readme.md"])
    assert result[0]["owner_type"] == "explicit"
    assert result[0]["owners"] == ["@platform"]
    assert result[1]["owner_type"] == "unknown"
    assert result[1]["owners"] == []


def test_github_validation_and_pr_context_are_read_only() -> None:
    client = FakeGitHubClient()
    adapter = GitHubContextAdapter(client, ["acme/app"])
    validation = adapter.validate()
    assert validation["connected"] is True
    assert validation["accessible_repositories"] == ["acme/app"]
    context = adapter.collect_pr_context("acme/app", 7, "corr-1")
    assert context["pr"]["title"] == "Reduce instance size"
    assert context["changed_files"][0]["path"] == "infra/main.tf"
    assert context["ownership"][0]["owners"] == ["@platform"]
    assert context["correlation_id"] == "corr-1"
    assert "create_pull_request" not in client.calls


def test_github_repository_allowlist_and_validation_failure() -> None:
    blocked = GitHubContextAdapter(FakeGitHubClient(), ["acme/other"])
    try:
        blocked.collect_pr_context("acme/app", 7)
    except Exception as exc:
        assert "allowlist" in str(exc)
    else:
        raise AssertionError("Repository outside organization allowlist was collected")
    failed = GitHubContextAdapter(FakeGitHubClient(fail_validation=True), [])
    result = failed.validate()
    assert result["connected"] is False
    assert result["missing_permissions"]
