from datetime import datetime, timezone
import json

from integrations.cloud_adapters import RealAWSCloudAdapter
from fastapi.testclient import TestClient
from app.main import app


class FakeClient:
    def __init__(self, kind: str, calls: list[tuple[str, str]]) -> None:
        self.kind = kind
        self.calls = calls

    def get_caller_identity(self):
        self.calls.append((self.kind, "get_caller_identity"))
        return {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:role/test"}

    def describe_regions(self, **kwargs):
        self.calls.append((self.kind, "describe_regions"))
        return {"Regions": [{"RegionName": "us-east-1"}]}

    def list_metrics(self, **kwargs):
        self.calls.append((self.kind, "list_metrics"))
        return {"Metrics": []}

    def describe_instances(self, **kwargs):
        self.calls.append((self.kind, "describe_instances"))
        return {"Reservations": [{"Instances": [{"InstanceId": "i-1", "InstanceType": "t3.micro", "State": {"Name": "running"}, "LaunchTime": datetime.now(timezone.utc), "Tags": [{"Key": "Environment", "Value": "staging"}, {"Key": "Owner", "Value": "finops"}]}]}]}

    def describe_volumes(self, **kwargs):
        self.calls.append((self.kind, "describe_volumes"))
        return {"Volumes": [{"VolumeId": "vol-1", "CreateTime": datetime.now(timezone.utc), "Size": 20, "VolumeType": "gp3", "Attachments": [], "Tags": []}]}

    def describe_addresses(self, **kwargs):
        self.calls.append((self.kind, "describe_addresses"))
        return {"Addresses": [{"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10"}]}

    def get_metric_statistics(self, **kwargs):
        self.calls.append((self.kind, "get_metric_statistics"))
        return {"Datapoints": []}


class FakeSession:
    region_name = "us-east-1"

    def __init__(self, calls): self.calls = calls

    def client(self, name, region_name=None):
        return FakeClient(name, self.calls)


def test_aws_validation_and_read_only_collection() -> None:
    calls: list[tuple[str, str]] = []
    adapter = RealAWSCloudAdapter(["us-east-1"], session_factory=lambda: FakeSession(calls))
    result = adapter.validate()
    assert result["connected"] is True
    assert result["account_id"] == "123456789012"
    resources = adapter.list_resources()
    assert {item.resource_id for item in resources} == {"i-1", "vol-1", "eipalloc-1"}
    assert all(item.metadata["source_mode"] == "real_aws" for item in resources)
    assert any(item.metadata["utilization"]["available"] is False for item in resources)
    assert not any(method in {"terminate_instances", "delete_volume", "release_address", "create_tags"} for _, method in calls)


def test_aws_missing_credentials_fails_validation_without_fallback() -> None:
    class BrokenSession:
        def client(self, name, region_name=None):
            raise RuntimeError("invalid credentials")

    adapter = RealAWSCloudAdapter(["us-east-1"], session_factory=BrokenSession)
    result = adapter.validate()
    assert result["connected"] is False
    assert "sts:GetCallerIdentity" in result["missing_permissions"][0]


def test_aws_partial_region_failure_is_recorded() -> None:
    calls: list[tuple[str, str]] = []

    class PartialSession(FakeSession):
        def client(self, name, region_name=None):
            if name == "ec2" and region_name == "eu-west-1":
                raise RuntimeError("throttling")
            return FakeClient(name, calls)

    adapter = RealAWSCloudAdapter(["us-east-1", "eu-west-1"], session_factory=lambda: PartialSession(calls))
    resources = adapter.list_resources()
    assert resources
    assert any("eu-west-1" in warning for warning in adapter.collection_warnings)


def test_real_aws_mode_never_silently_falls_back_to_fixtures() -> None:
    client = TestClient(app)
    client.post("/api/demo/reset", json={"confirm": True})
    assert client.patch("/api/integrations/aws/config", json={"enabled": True, "regions": ["us-east-1"]}).status_code == 200
    response = client.post("/api/cloud/hunts", json={"provider_scope": "aws", "inventory_source": "real_aws"})
    assert response.status_code == 409
    assert "did not fall back" in response.json()["detail"]


def test_real_aws_collection_records_live_ec2_and_ebs_pricing_without_mutation() -> None:
    calls: list[tuple[str, str]] = []

    class PricingClient(FakeClient):
        def get_products(self, **kwargs):
            self.calls.append((self.kind, "get_products"))
            fields = {item["Field"]: item["Value"] for item in kwargs["Filters"]}
            if fields["productFamily"] == "Compute Instance":
                price = {"product": {"sku": "ec2-sku"}, "terms": {"OnDemand": {"term": {"priceDimensions": {"hour": {"unit": "Hrs", "pricePerUnit": {"USD": "0.0123"}}}}}}}
            else:
                price = {"product": {"sku": "ebs-sku"}, "terms": {"OnDemand": {"term": {"priceDimensions": {"storage": {"unit": "GB-Mo", "pricePerUnit": {"USD": "0.10"}}}}}}}
            return {"PriceList": [json.dumps(price)]}

    class PricingSession(FakeSession):
        def client(self, name, region_name=None):
            if name == "pricing":
                return PricingClient(name, calls)
            return FakeClient(name, calls)

    resources = RealAWSCloudAdapter(["us-east-1"], session_factory=lambda: PricingSession(calls)).list_resources()
    by_id = {item.resource_id: item for item in resources}

    assert by_id["i-1"].metadata["pricing"] == {
        "available": True,
        "source": "AWS Pricing API",
        "source_mode": "live",
        "service": "AmazonEC2",
        "resource_type": "EC2",
        "instance_type": "t3.micro",
        "rate_per_hour_usd": 0.0123,
        "estimated_monthly_cost_usd": 8.979,
        "currency": "USD",
        "assumption": "On-demand Linux shared tenancy, 730 hours per month.",
        "sku": "ec2-sku",
        "pricing_region": "us-east-1",
        "retrieved_at": by_id["i-1"].metadata["pricing"]["retrieved_at"],
    }
    assert by_id["vol-1"].metadata["pricing"]["estimated_monthly_cost_usd"] == 2.0
    assert ("pricing", "get_products") in calls
    assert not any(method in {"terminate_instances", "delete_volume", "release_address", "create_tags"} for _, method in calls)
