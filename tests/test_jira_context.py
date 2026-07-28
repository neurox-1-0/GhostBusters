from datetime import datetime, timezone, timedelta

from core.planner import create_investigation_plan
from integrations.jira_client import JiraAPIError
from integrations.jira_context import JiraContextAdapter, detect_jira_github_conflict
from integrations.jira_tools import build_jira_tools
from integrations.registry import ToolRegistry
from tests.scenario_helpers import load_resource, load_scenario


class FakeJiraClient:
    def __init__(self, fail=False, owner=True, stale=False):
        self.fail, self.owner, self.stale, self.calls = fail, owner, stale, []

    def get_myself(self):
        self.calls.append("myself")
        if self.fail: raise JiraAPIError("authentication", "credentials unavailable")
        return {"displayName": "Jira Service"}

    def list_projects(self):
        self.calls.append("projects")
        return [{"key": "OPS", "name": "Operations"}, {"key": "OTHER"}]

    def get_project(self, key):
        self.calls.append("project")
        return {"key": key, "name": "Operations", "lead": {"displayName": "Platform"} if self.owner else {}}

    def get_issue(self, key):
        self.calls.append("issue")
        updated = datetime.now(timezone.utc) - (timedelta(days=60) if self.stale else timedelta(hours=1))
        return {"key": key, "fields": {"project": {"key": "OPS"}, "summary": "Decommission old resource", "status": {"name": "Done"}, "assignee": {"displayName": "Platform"} if self.owner else {}, "reporter": {}, "labels": ["decommission"], "components": [{"name": "Infra"}], "updated": updated.isoformat().replace("+00:00", "Z")}}


def test_jira_validation_allowlist_and_credentials():
    adapter = JiraContextAdapter(FakeJiraClient(), ["OPS"])
    result = adapter.validate()
    assert result["connected"] and result["accessible_projects"] == ["OPS"]
    failed = JiraContextAdapter(FakeJiraClient(fail=True))
    assert failed.validate()["connected"] is False


def test_jira_issue_context_signals_freshness_and_ownership():
    context = JiraContextAdapter(FakeJiraClient(), ["OPS"]).collect_issue_context("OPS-7", "corr-jira")
    assert context["signals"][0]["type"] == "decommission"
    assert context["ownership"]["owner_type"] == "explicit"
    assert context["correlation_id"] == "corr-jira"
    stale = JiraContextAdapter(FakeJiraClient(stale=True), ["OPS"]).collect_issue_context("OPS-7")
    assert stale["activity"]["stale"] is True and stale["activity"]["reliability"] < 0.9


def test_jira_unknown_owner_conflict_and_read_only_tools():
    context = JiraContextAdapter(FakeJiraClient(owner=False), ["OPS"]).collect_issue_context("OPS-7")
    assert context["ownership"]["owner_type"] == "unknown"
    conflict = detect_jira_github_conflict(context, {"commit_activity": {"recent_commit_count": 2}})
    assert conflict and conflict["type"] == "jira_github_status_conflict"
    client = FakeJiraClient()
    plan = create_investigation_plan("Need Jira business context", load_scenario("safe"), load_resource("safe"), ToolRegistry(build_jira_tools(JiraContextAdapter(client))))
    assert "jira_issue_context" in plan.selected_tools
    assert not any("create" in call for call in client.calls)
