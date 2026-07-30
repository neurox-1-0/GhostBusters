from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app import main
from app.models import AWSIntegrationConfig, CloudResource


def test_connected_goal_aws_collector_records_read_only_cpu_evidence(monkeypatch) -> None:
    organization_id = uuid4()
    now = datetime.now(timezone.utc)
    config = AWSIntegrationConfig(
        organization_id=organization_id,
        enabled=True,
        connection_status="connected",
        account_id="026870877875",
        role_arn="arn:aws:iam::026870877875:role/GhostBustersReadOnlyRole",
        created_at=now,
        updated_at=now,
    )
    resource = CloudResource(
        provider="aws",
        account_or_subscription_id="026870877875",
        region_or_location="ap-south-1",
        resource_id="i-demo",
        resource_name="demo non-production instance",
        provider_resource_type="virtual_machine",
        normalized_resource_type="virtual_machine",
        status="running",
        metadata={
            "utilization": {"available": True, "average_cpu_pct": 4.2, "lookback_days": 14},
            "pricing": {"available": True, "source_mode": "live", "estimated_monthly_cost_usd": 7.592},
        },
    )

    class Adapter:
        def validate(self):
            return {"connected": True, "account_id": "026870877875"}

        def list_resources(self):
            return [resource]

    monkeypatch.setattr(main.aws_integration_store, "get", lambda _: config)
    monkeypatch.setattr(main.aws_integration_store, "mark_collection", lambda *args, **kwargs: config)
    monkeypatch.setattr(main, "aws_adapter_for_config", lambda _: Adapter())
    monkeypatch.setattr(main.auth_store, "record_activity", lambda *args, **kwargs: None)

    result = main.aws_goal_evidence_collector(organization_id, None)(
        SimpleNamespace(id=uuid4(), goal="Reduce non-production AWS spending.", correlation_id="correlation-1")
    )

    assert result["evidence"][0]["source"] == "AWS"
    assert result["evidence"][0]["status"] == "verified"
    assert "4.2%" in result["evidence"][0]["summary"]
    assert "Verified AWS on-demand estimate" in result["evidence"][0]["summary"]
    assert "Verified pricing" not in result["missing_evidence"]
