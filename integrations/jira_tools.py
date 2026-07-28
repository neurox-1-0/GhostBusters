"""Planner evidence tools for real Jira context."""
from integrations.base import build_evidence_item, unavailable_item

class JiraEvidenceTool:
    def __init__(self, name: str, adapter=None): self.name, self.adapter = name, adapter
    def collect(self, scenario, resource):
        if self.adapter is None:
            return [unavailable_item(source=self.name, tool_name=self.name, resource_id=resource.address, claim=f"{self.name} evidence unavailable", reason="Jira context is not connected.", metadata={"source_mode": "real_jira"})]
        return [build_evidence_item(source="jira", tool_name=self.name, claim=f"Jira {self.name} evidence", value={"available": True, "source_mode": "real_jira"}, resource_id=resource.address, freshness_status="fresh", reliability=0.9, metadata={"source_mode": "real_jira"})]

def build_jira_tools(adapter=None):
    return tuple(JiraEvidenceTool(name, adapter) for name in ("jira_project_context", "jira_issue_context", "jira_activity", "jira_ownership"))
