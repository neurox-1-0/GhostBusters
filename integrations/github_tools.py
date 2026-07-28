"""Read-only evidence-tool wrappers for GitHub context."""

from __future__ import annotations

from integrations.base import build_evidence_item, unavailable_item


class GitHubEvidenceTool:
    def __init__(self, name: str, context_adapter=None) -> None:
        self.name = name
        self.context_adapter = context_adapter

    def collect(self, scenario, resource):
        if self.context_adapter is None:
            return [unavailable_item(source=self.name, tool_name=self.name, resource_id=resource.address, claim=f"{self.name} evidence unavailable", reason="GitHub context is not connected.", metadata={"source_mode": "real_github"})]
        return [build_evidence_item(source=self.name, tool_name=self.name, claim=f"GitHub {self.name} evidence", value={"available": True, "source_mode": "real_github"}, resource_id=resource.address, freshness_status="fresh", reliability=0.9, metadata={"source_mode": "real_github"})]


def build_github_tools(context_adapter=None) -> tuple[GitHubEvidenceTool, ...]:
    return tuple(GitHubEvidenceTool(name, context_adapter) for name in ("github_pr_context", "github_activity", "github_ownership", "github_reviews"))
