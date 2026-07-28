"""Evidence-tool wrappers for an explicitly connected AWS adapter."""

from __future__ import annotations

from integrations.base import build_evidence_item, unavailable_item


class AWSEvidenceTool:
    def __init__(self, name: str, adapter) -> None:
        self.name = name
        self.adapter = adapter

    def collect(self, scenario, resource):
        if self.adapter is None:
            return [unavailable_item(source=self.name, tool_name=self.name, resource_id=resource.address, claim=f"{self.name} evidence unavailable", reason="AWS adapter is not connected.", metadata={"source_mode": "real_aws"})]
        if self.name == "aws_inventory":
            value = {"resource_id": resource.address, "provider": "aws", "source_mode": "real_aws"}
        elif self.name == "aws_cloudwatch":
            value = self.adapter.get_utilization_evidence(resource.address)
        elif self.name == "aws_pricing":
            value = self.adapter.get_cost_evidence(resource.address)
        else:
            value = self.adapter.get_ownership_evidence(resource.address)
        return [build_evidence_item(source=self.name, tool_name=self.name, claim=f"AWS {self.name} evidence", value=value, resource_id=resource.address, freshness_status="fresh" if value.get("available", True) else "unavailable", reliability=0.95 if value.get("available", True) else 0.0, metadata={"source_mode": "real_aws"})]


def build_aws_tools(adapter) -> tuple[AWSEvidenceTool, ...]:
    return tuple(AWSEvidenceTool(name, adapter) for name in ("aws_inventory", "aws_cloudwatch", "aws_pricing", "aws_tags"))
