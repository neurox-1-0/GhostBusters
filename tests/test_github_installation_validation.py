from pathlib import Path

from integrations.github_app import GitHubAppClient


class InstallationClient(GitHubAppClient):
    def __init__(self):
        pass

    def installation(self):
        return {"account": {"login": "acme", "type": "Organization"}, "permissions": {"metadata": "read", "contents": "read", "pull_requests": "read"}, "repository_selection": "selected"}

    def api_client(self):
        return self

    def list_installation_repositories(self):
        return [{"full_name": "acme/infra", "private": True, "default_branch": "main"}]


class MissingPermissionClient(InstallationClient):
    def installation(self):
        return {"account": {"login": "acme"}, "permissions": {"metadata": "read", "contents": "read"}}


def test_installation_validation_uses_installation_endpoints_and_not_user() -> None:
    result = InstallationClient().validate_installation()
    assert result["account_identity"] == "acme"
    assert [item["full_name"] for item in result["repositories"]] == ["acme/infra"]
    assert result["missing_permissions"] == []


def test_installation_validation_reports_required_permissions() -> None:
    result = MissingPermissionClient().validate_installation()
    assert result["missing_permissions"] == ["pull_requests"]


def test_frontend_keeps_installation_connected_with_validation_warning() -> None:
    script = Path("static/app.js").read_text(encoding="utf-8")
    assert 'config.last_failure_summary' in script
    assert '"Connected with warning"' in script
    assert 'Validation failed; showing last known repository access.' in script
    assert 'state.githubConfig = await api("/api/integrations/github/config")' in script
