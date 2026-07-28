"""Bounded, read-only Jira REST client. Credentials are never persisted or returned."""
from __future__ import annotations
import base64
from typing import Any
import httpx

class JiraAPIError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category

class JiraClient:
    def __init__(self, base_url: str, email: str | None, api_token: str, timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        auth = None
        headers = {"Accept": "application/json"}
        if email:
            auth = (email, api_token)
        else:
            headers["Authorization"] = f"Bearer {api_token}"
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers, auth=auth)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise JiraAPIError("network", "Jira connection failed safely.") from exc
        if response.status_code in (401, 403):
            raise JiraAPIError("authentication" if response.status_code == 401 else "permission", "Jira credentials or permissions are insufficient.")
        if response.status_code >= 400:
            raise JiraAPIError("jira_error", "Jira returned an error while collecting read-only context.")
        try: return response.json()
        except ValueError as exc: raise JiraAPIError("invalid_response", "Jira returned an invalid response.") from exc

    def get_myself(self) -> dict[str, Any]: return self._get("/rest/api/3/myself")
    def list_projects(self) -> list[dict[str, Any]]: return self._get("/rest/api/3/project/search", {"maxResults": 100}).get("values", [])
    def get_project(self, key: str) -> dict[str, Any]: return self._get(f"/rest/api/3/project/{key}")
    def get_issue(self, key: str) -> dict[str, Any]:
        return self._get(f"/rest/api/3/issue/{key}", {"fields": "summary,status,assignee,reporter,labels,components,project,description,issuelinks,updated,created"})
    def search_issues(self, jql: str, max_results: int = 25) -> list[dict[str, Any]]:
        return self._get("/rest/api/3/search", {"jql": jql, "maxResults": min(max_results, 100), "fields": "summary,status,assignee,reporter,labels,project,updated"}).get("issues", [])

