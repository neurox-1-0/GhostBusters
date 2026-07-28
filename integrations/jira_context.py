"""Safe normalization of read-only Jira business context."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from integrations.jira_client import JiraAPIError, JiraClient

def _now() -> datetime: return datetime.now(timezone.utc)
def _person(value: Any) -> str | None:
    return (value or {}).get("displayName") or (value or {}).get("accountId")

def _signals(issue: dict[str, Any]) -> list[dict[str, str]]:
    fields = issue.get("fields") or {}
    text = " ".join(str(fields.get(key) or "") for key in ("summary", "description", "labels")).lower()
    found = []
    for kind, terms in (("decommission", ("decommission", "retire", "sunset")), ("migration", ("migration", "migrate")), ("shutdown", ("shutdown", "shut down"))):
        if any(term in text for term in terms): found.append({"type": kind, "strength": "strong"})
    return found

class JiraContextAdapter:
    def __init__(self, client: JiraClient, allowed_projects=(), source_mode: str = "real_jira") -> None:
        self.client = client
        self.allowed_projects = {str(item).strip().upper() for item in allowed_projects if str(item).strip()}
        self.source_mode = source_mode

    def _allowed(self, project: str) -> None:
        if self.allowed_projects and project.upper() not in self.allowed_projects: raise JiraAPIError("authorization", "Jira project is outside the organization allowlist.")

    def validate(self) -> dict[str, Any]:
        checked_at = _now()
        try:
            identity = self.client.get_myself()
            projects = self.client.list_projects()
            accessible = [p.get("key") for p in projects if p.get("key") and (not self.allowed_projects or p.get("key", "").upper() in self.allowed_projects)]
            return {"connected": True, "account_identity": identity.get("displayName") or identity.get("accountId") or identity.get("emailAddress"), "accessible_projects": accessible, "permission_warnings": [], "missing_permissions": [], "checked_at": checked_at}
        except JiraAPIError as exc:
            return {"connected": False, "account_identity": None, "accessible_projects": [], "permission_warnings": [], "missing_permissions": [exc.category], "checked_at": checked_at}

    def collect_issue_context(self, issue_key: str, correlation_id: str | None = None) -> dict[str, Any]:
        issue = self.client.get_issue(issue_key)
        fields = issue.get("fields") or {}
        project = (fields.get("project") or {}).get("key") or issue_key.split("-", 1)[0]
        self._allowed(project)
        updated = fields.get("updated")
        stale = False
        if updated:
            try: stale = _now() - datetime.fromisoformat(updated.replace("Z", "+00:00")) > timedelta(days=30)
            except ValueError: stale = True
        owner = _person(fields.get("assignee")) or _person(fields.get("reporter"))
        return {"project_key": project, "issue_key": issue.get("key", issue_key), "source_type": "jira_issue", "source_mode": self.source_mode, "correlation_id": correlation_id, "collected_at": _now(), "issue": {"title": fields.get("summary"), "status": (fields.get("status") or {}).get("name"), "assignee": _person(fields.get("assignee")), "reporter": _person(fields.get("reporter")), "labels": fields.get("labels", []), "components": [c.get("name") for c in fields.get("components", [])], "updated": updated}, "ownership": {"owner": owner, "owner_type": "explicit" if fields.get("assignee") else ("inferred" if fields.get("reporter") else "unknown"), "owner_source": "assignee" if fields.get("assignee") else ("reporter" if fields.get("reporter") else None)}, "activity": {"last_activity": updated, "stale": stale, "reliability": 0.55 if stale else 0.9}, "signals": _signals(issue)}

    def collect_project_context(self, project_key: str, correlation_id: str | None = None) -> dict[str, Any]:
        self._allowed(project_key)
        project = self.client.get_project(project_key)
        return {"project_key": project_key, "source_type": "jira_project", "source_mode": self.source_mode, "correlation_id": correlation_id, "collected_at": _now(), "project": {"name": project.get("name"), "description": project.get("description"), "lead": _person(project.get("lead")), "url": project.get("self")}, "ownership": {"owner": _person(project.get("lead")), "owner_type": "explicit" if project.get("lead") else "unknown", "owner_source": "project lead" if project.get("lead") else None}}

def detect_jira_github_conflict(jira_context: dict[str, Any], github_context: dict[str, Any] | None) -> dict[str, Any] | None:
    status = str((jira_context.get("issue") or {}).get("status") or "").lower()
    commits = int((github_context or {}).get("commit_activity", {}).get("recent_commit_count", 0))
    if status in {"done", "completed", "closed", "resolved"} and commits > 0:
        return {"type": "jira_github_status_conflict", "summary": "Jira is complete but recent Git activity exists.", "severity": "medium"}
    return None
