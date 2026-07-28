"""Read-only GitHub context and safe CODEOWNERS resolution."""

from __future__ import annotations

import fnmatch
from datetime import datetime, timedelta, timezone
from typing import Any

from integrations.github_client import GitHubAPIError, GitHubClient


def split_repository(repository: str) -> tuple[str, str]:
    parts = repository.strip().split("/", 1)
    if len(parts) != 2 or not all(parts): raise ValueError("Repository must be owner/name.")
    return parts[0], parts[1]


def parse_codeowners(content: str) -> list[tuple[str, list[str]]]:
    rules = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"): continue
        fields = line.split()
        if len(fields) >= 2: rules.append((fields[0], fields[1:]))
    return rules


def resolve_codeowners(content: str | None, paths: list[str]) -> list[dict[str, Any]]:
    if not content: return [{"path": path, "owner_type": "unknown", "owners": [], "matched_pattern": None, "owner_source": "CODEOWNERS unavailable"} for path in paths]
    rules = parse_codeowners(content)
    results = []
    for path in paths:
        match = None
        for pattern, owners in rules:
            normalized = pattern.lstrip("/")
            if fnmatch.fnmatch(path.lstrip("/"), normalized) or fnmatch.fnmatch(path.lstrip("/"), f"*/{normalized}"):
                match = (pattern, owners)
        if match:
            results.append({"path": path, "owner_type": "explicit", "owners": match[1], "matched_pattern": match[0], "owner_source": "CODEOWNERS"})
        else:
            results.append({"path": path, "owner_type": "unknown", "owners": [], "matched_pattern": None, "owner_source": "No matching CODEOWNERS rule"})
    return results


class GitHubContextAdapter:
    def __init__(self, client: GitHubClient, allowed_repositories: list[str] | tuple[str, ...] = (), source_mode: str = "real_github") -> None:
        self.client = client
        self.allowed_repositories = {item.strip().lower() for item in allowed_repositories}
        self.source_mode = source_mode

    def _allowed(self, repository: str) -> None:
        if self.allowed_repositories and repository.lower() not in self.allowed_repositories: raise GitHubAPIError("authorization", "Repository is outside the organization allowlist.")

    def validate(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        try:
            identity = self.client.get_authenticated_user()
            repositories = self.client.list_repositories()
            accessible = [str(item.get("full_name")) for item in repositories if item.get("full_name")]
            allowed = [item for item in accessible if not self.allowed_repositories or item.lower() in self.allowed_repositories]
            return {"connected": True, "account_identity": identity.get("login") or identity.get("id"), "accessible_repositories": allowed, "permission_warnings": [], "missing_permissions": [], "checked_at": checked_at}
        except GitHubAPIError as exc:
            return {"connected": False, "account_identity": None, "accessible_repositories": [], "permission_warnings": [], "missing_permissions": [exc.category], "checked_at": checked_at}

    def collect_pr_context(self, repository: str, number: int, correlation_id: str | None = None) -> dict[str, Any]:
        self._allowed(repository)
        owner, repo = split_repository(repository)
        pr = self.client.get_pull_request(owner, repo, number)
        files = self.client.list_pull_request_files(owner, repo, number)
        repository_info = self.client.get_repository(owner, repo)
        head_sha = ((pr.get("head") or {}).get("sha") or "")
        codeowners = None
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                codeowners = self.client.get_file_content(owner, repo, path, head_sha).get("content")
                if codeowners is not None: break
            except GitHubAPIError:
                continue
        changed_paths = [str(item.get("filename")) for item in files if item.get("filename")]
        ownership = resolve_codeowners(codeowners, changed_paths)
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        commits = self.client.list_commits(owner, repo, since=since)
        reviews = self.client.list_pull_request_reviews(owner, repo, number)
        return {
            "repository": repository, "pull_request_number": number, "source_type": "github_pull_request", "source_mode": self.source_mode,
            "correlation_id": correlation_id, "repository_default_branch": (repository_info.get("default_branch") or "main"),
            "pr": {"title": pr.get("title"), "body": pr.get("body"), "author": (pr.get("user") or {}).get("login"), "head_branch": (pr.get("head") or {}).get("ref"), "base_branch": (pr.get("base") or {}).get("ref"), "state": pr.get("state"), "labels": [item.get("name") for item in pr.get("labels", [])], "html_url": pr.get("html_url")},
            "changed_files": [{"path": item.get("filename"), "status": item.get("status"), "additions": item.get("additions", 0), "deletions": item.get("deletions", 0)} for item in files],
            "commit_activity": {"recent_commit_count": len(commits), "last_commit": ((commits[0].get("commit") or {}).get("author") or {}).get("date") if commits else None, "lookback_days": 30},
            "reviews": [{"author": (item.get("user") or {}).get("login"), "state": item.get("state"), "submitted_at": item.get("submitted_at")} for item in reviews],
            "ownership": ownership,
            "codeowners_available": codeowners is not None,
            "collected_at": datetime.now(timezone.utc),
        }
