"""Fixture-backed, read-only cloud provider adapters for Cloud Hunt Mode."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from app.models import CloudProvider, CloudResource


class CloudProviderAdapter(ABC):
    provider: CloudProvider
    display_name: str
    fixture_backed = True

    @abstractmethod
    def list_resources(self) -> list[CloudResource]:
        """Return normalized resources from the controlled inventory fixture."""

    def get_resource_details(self, resource_id: str) -> CloudResource | None:
        return next((item for item in self.list_resources() if item.resource_id == resource_id), None)

    def _evidence(self, resource_id: str, key: str) -> dict[str, Any]:
        resource = self.get_resource_details(resource_id)
        if resource is None:
            return {"available": False, "reason": "resource not found"}
        return deepcopy(resource.metadata.get(key, {"available": False, "reason": f"{key} unavailable"}))

    def get_cost_evidence(self, resource_id: str) -> dict[str, Any]:
        return self._evidence(resource_id, "pricing")

    def get_utilization_evidence(self, resource_id: str) -> dict[str, Any]:
        return self._evidence(resource_id, "utilization")

    def get_dependency_evidence(self, resource_id: str) -> dict[str, Any]:
        return self._evidence(resource_id, "dependencies")

    def get_activity_evidence(self, resource_id: str) -> dict[str, Any]:
        return self._evidence(resource_id, "activity")

    def get_ownership_evidence(self, resource_id: str) -> dict[str, Any]:
        return self._evidence(resource_id, "ownership")

    def build_remediation_proposal(self, resource_id: str, action: str) -> dict[str, Any]:
        resource = self.get_resource_details(resource_id)
        if resource is None:
            raise ValueError(f"Unknown {self.provider} resource: {resource_id}")
        if not resource.infrastructure_as_code_managed or not resource.terraform_address:
            return {
                "managed": False,
                "message": "Resource is not currently managed by Terraform.",
                "recommended_next_steps": ["import into Terraform", "create Jira remediation task", "request platform-owner action"],
            }
        return {
            "managed": True,
            "terraform_address": resource.terraform_address,
            "action": action,
            "provider": self.provider,
            "resource_id": resource.resource_id,
            "note": "Simulated proposal only; no provider mutation was performed.",
        }


class AWSCloudAdapter(CloudProviderAdapter):
    provider = "aws"
    display_name = "AWS"

    def __init__(self, resources: list[CloudResource]) -> None:
        self._resources = resources

    def list_resources(self) -> list[CloudResource]:
        return [item.model_copy(deep=True) for item in self._resources]


class RealAWSCloudAdapter(CloudProviderAdapter):
    """Read-only EC2, EBS, EIP, CloudWatch, STS, and best-effort pricing adapter."""

    provider = "aws"
    display_name = "AWS"
    fixture_backed = False
    _PRICING_REGION = "us-east-1"
    _PRICING_LOCATIONS = {
        "ap-south-1": "Asia Pacific (Mumbai)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "eu-west-1": "EU (Ireland)",
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-2": "US West (Oregon)",
    }

    def __init__(self, regions: list[str], lookback_days: int = 14, low_cpu_threshold: float = 10.0, session_factory=None, role_arn: str | None = None, external_id: str | None = None) -> None:
        self.regions = list(dict.fromkeys(regions))
        self.lookback_days = lookback_days
        self.low_cpu_threshold = low_cpu_threshold
        self._session_factory = session_factory
        self.role_arn = role_arn
        self.external_id = external_id
        self._assumed_session = None
        self.account_id: str | None = None
        self.collection_warnings: list[str] = []
        self._pricing_cache: dict[str, dict[str, Any]] = {}

    def _session(self):
        if self._session_factory:
            return self._session_factory()
        try:
            import boto3
            base_session = boto3.Session()
            if not self.role_arn:
                return base_session
            if self._assumed_session is not None:
                return self._assumed_session
            credentials = base_session.client("sts", region_name=self.regions[0] if self.regions else None).assume_role(
                RoleArn=self.role_arn,
                RoleSessionName="ghostbusters-readonly",
                ExternalId=self.external_id,
            )["Credentials"]
            self._assumed_session = boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
            return self._assumed_session
        except ImportError as exc:
            raise RuntimeError("boto3 is not installed; real AWS mode is unavailable.") from exc

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return str(getattr(exc, "response", {}).get("Error", {}).get("Code", exc.__class__.__name__))

    def validate(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        try:
            identity = self._session().client("sts", region_name=self.regions[0] if self.regions else None).get_caller_identity()
            self.account_id = str(identity.get("Account") or "")
            missing = []
            warnings = []
            session = self._session()
            region = self.regions[0] if self.regions else getattr(session, "region_name", None)
            if not region:
                warnings.append("No AWS region is configured.")
            else:
                try: session.client("ec2", region_name=region).describe_regions(RegionNames=[region], AllRegions=False)
                except Exception as exc: missing.append(f"ec2:DescribeRegions ({self._error_code(exc)})")
                try: session.client("cloudwatch", region_name=region).list_metrics(Namespace="AWS/EC2", RecentlyActive="PT3H")
                except Exception as exc: missing.append(f"cloudwatch:ListMetrics ({self._error_code(exc)})")
                try:
                    session.client("pricing", region_name=self._PRICING_REGION).get_products(
                        ServiceCode="AmazonEC2",
                        Filters=[{"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"}],
                        FormatVersion="aws_v1",
                        MaxResults=1,
                    )
                except Exception as exc: missing.append(f"pricing:GetProducts ({self._error_code(exc)})")
            return {"connected": True, "account_id": self.account_id, "allowed_regions": self.regions, "permission_warnings": warnings, "missing_permissions": missing, "checked_at": checked_at}
        except Exception as exc:
            return {"connected": False, "account_id": None, "allowed_regions": self.regions, "permission_warnings": [], "missing_permissions": [f"sts:GetCallerIdentity ({self._error_code(exc)})"], "checked_at": checked_at}

    def list_resources(self) -> list[CloudResource]:
        session = self._session()
        resources: list[CloudResource] = []
        for region in self.regions:
            try:
                ec2 = session.client("ec2", region_name=region)
                reservations = ec2.describe_instances().get("Reservations", [])
                for reservation in reservations:
                    for instance in reservation.get("Instances", []):
                        tags = {str(tag.get("Key")): str(tag.get("Value", "")) for tag in instance.get("Tags", [])}
                        resource_id = str(instance.get("InstanceId"))
                        state = str((instance.get("State") or {}).get("Name") or "unknown")
                        metrics = self._instance_metrics(session, region, resource_id)
                        resources.append(self._resource(resource_id, f"EC2 {resource_id}", "virtual_machine", region, tags, state, instance.get("LaunchTime"), metrics, {"instance_type": instance.get("InstanceType"), "platform_details": instance.get("PlatformDetails")}))
                for volume in ec2.describe_volumes().get("Volumes", []):
                    tags = {str(tag.get("Key")): str(tag.get("Value", "")) for tag in volume.get("Tags", [])}
                    attached = bool(volume.get("Attachments"))
                    resources.append(self._resource(str(volume.get("VolumeId")), f"EBS {volume.get('VolumeId')}", "storage_volume", region, tags, "attached" if attached else "unattached", volume.get("CreateTime"), {"available": False, "reason": "EBS utilization metrics are not available for this volume."}, {"attached": attached, "size_gib": volume.get("Size"), "volume_type": volume.get("VolumeType")}))
                for address in ec2.describe_addresses().get("Addresses", []):
                    allocation = str(address.get("AllocationId") or address.get("PublicIp") or "unknown")
                    associated = bool(address.get("AssociationId") or address.get("InstanceId") or address.get("NetworkInterfaceId"))
                    resources.append(self._resource(allocation, f"Elastic IP {address.get('PublicIp', allocation)}", "public_ip", region, {}, "associated" if associated else "unassociated", None, {"available": False, "reason": "Elastic IP has no utilization metric."}, {"associated": associated, "public_ip": address.get("PublicIp")}))
            except Exception as exc:
                self.collection_warnings.append(f"{region}: {self._error_code(exc)}")
        return resources

    def _instance_metrics(self, session, region: str, instance_id: str) -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - __import__("datetime").timedelta(days=self.lookback_days)
        try:
            result = session.client("cloudwatch", region_name=region).get_metric_statistics(Namespace="AWS/EC2", MetricName="CPUUtilization", Dimensions=[{"Name": "InstanceId", "Value": instance_id}], StartTime=start, EndTime=end, Period=3600, Statistics=["Average", "Maximum"])
            datapoints = result.get("Datapoints", [])
            if not datapoints: return {"available": False, "reason": "No CloudWatch CPUUtilization datapoints were returned.", "metric": "CPUUtilization", "lookback_days": self.lookback_days}
            return {"available": True, "metric": "CPUUtilization", "average_cpu_pct": sum(float(item.get("Average", 0)) for item in datapoints) / len(datapoints), "peak_cpu_pct": max(float(item.get("Maximum", 0)) for item in datapoints), "datapoints": len(datapoints), "lookback_days": self.lookback_days, "source": "AWS CloudWatch"}
        except Exception as exc:
            return {"available": False, "reason": f"CloudWatch metrics unavailable: {self._error_code(exc)}", "metric": "CPUUtilization", "lookback_days": self.lookback_days}

    @staticmethod
    def _unavailable_pricing(reason: str) -> dict[str, Any]:
        return {"available": False, "reason": reason, "source": "AWS Pricing API", "source_mode": "unavailable"}

    def _pricing_location(self, region: str) -> str | None:
        return self._PRICING_LOCATIONS.get(region)

    @staticmethod
    def _on_demand_rate(product: dict[str, Any], expected_unit: str) -> float | None:
        terms = (product.get("terms") or {}).get("OnDemand") or {}
        for term in terms.values():
            for dimension in (term.get("priceDimensions") or {}).values():
                if str(dimension.get("unit") or "") != expected_unit:
                    continue
                amount = (dimension.get("pricePerUnit") or {}).get("USD")
                try:
                    return float(amount)
                except (TypeError, ValueError):
                    continue
        return None

    def _lookup_price(self, cache_key: str, filters: list[dict[str, str]], expected_unit: str) -> tuple[float | None, dict[str, Any]]:
        cached = self._pricing_cache.get(cache_key)
        if cached is not None:
            return cached.get("rate"), dict(cached.get("metadata") or {})
        try:
            response = self._session().client("pricing", region_name=self._PRICING_REGION).get_products(
                ServiceCode="AmazonEC2", Filters=filters, FormatVersion="aws_v1", MaxResults=20,
            )
            products = []
            for item in response.get("PriceList") or []:
                products.append(json.loads(item) if isinstance(item, str) else item)
            rates = []
            for product in products:
                rate = self._on_demand_rate(product, expected_unit)
                if rate is not None:
                    rates.append((str((product.get("product") or {}).get("sku") or ""), rate))
            distinct_rates = {rate for _, rate in rates}
            if len(distinct_rates) != 1:
                result = (None, {"reason": "AWS Pricing returned no single exact on-demand rate."})
            else:
                sku, rate = sorted(rates)[0]
                result = (rate, {"sku": sku, "pricing_region": self._PRICING_REGION, "retrieved_at": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            result = (None, {"reason": f"AWS Pricing lookup unavailable: {self._error_code(exc)}"})
        self._pricing_cache[cache_key] = {"rate": result[0], "metadata": result[1]}
        return result

    def _pricing_for_resource(self, normalized_type: str, region: str, metadata: dict[str, Any]) -> dict[str, Any]:
        location = self._pricing_location(region)
        if not location:
            return self._unavailable_pricing(f"AWS Pricing location mapping is unavailable for {region}.")
        if normalized_type == "virtual_machine":
            instance_type = str(metadata.get("instance_type") or "")
            if not instance_type:
                return self._unavailable_pricing("EC2 instance type is unavailable for pricing.")
            filters = [
                {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"},
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ]
            rate, details = self._lookup_price(f"ec2:{region}:{instance_type}", filters, "Hrs")
            if rate is None:
                return self._unavailable_pricing(str(details.get("reason") or "AWS Pricing lookup did not return an exact EC2 rate."))
            return {"available": True, "source": "AWS Pricing API", "source_mode": "live", "service": "AmazonEC2", "resource_type": "EC2", "instance_type": instance_type, "rate_per_hour_usd": rate, "estimated_monthly_cost_usd": round(rate * 730, 4), "currency": "USD", "assumption": "On-demand Linux shared tenancy, 730 hours per month.", **details}
        if normalized_type == "storage_volume":
            volume_type = str(metadata.get("volume_type") or "")
            size_gib = metadata.get("size_gib")
            if not volume_type or not isinstance(size_gib, (int, float)):
                return self._unavailable_pricing("EBS volume type or size is unavailable for pricing.")
            filters = [
                {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"},
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": volume_type},
            ]
            rate, details = self._lookup_price(f"ebs:{region}:{volume_type}", filters, "GB-Mo")
            if rate is None:
                return self._unavailable_pricing(str(details.get("reason") or "AWS Pricing lookup did not return an exact EBS rate."))
            return {"available": True, "source": "AWS Pricing API", "source_mode": "live", "service": "AmazonEC2", "resource_type": "EBS", "volume_type": volume_type, "size_gib": size_gib, "rate_per_gb_month_usd": rate, "estimated_monthly_cost_usd": round(rate * float(size_gib), 4), "currency": "USD", "assumption": "Storage capacity only; provisioned IOPS and throughput charges are excluded.", **details}
        return self._unavailable_pricing(f"AWS Pricing lookup is not supported for {normalized_type}.")

    def _resource(self, resource_id, name, normalized_type, region, tags, state, created_at, utilization, metadata) -> CloudResource:
        created = created_at if isinstance(created_at, datetime) else None
        age_days = max(0, (datetime.now(timezone.utc) - created).days) if created else None
        environment = tags.get("Environment") or tags.get("environment")
        owner = tags.get("Owner") or tags.get("owner")
        pricing = self._pricing_for_resource(normalized_type, region, metadata)
        estimate = pricing.get("estimated_monthly_cost_usd") if pricing.get("available") else None
        return CloudResource(provider="aws", account_or_subscription_id=self.account_id or "unknown", region_or_location=region, resource_id=resource_id, resource_name=name, provider_resource_type=normalized_type, normalized_resource_type=normalized_type, status=state, environment=environment, owner=owner, created_at=created, age_days=age_days, tags=tags, estimated_monthly_cost=float(estimate) if estimate is not None else None, metadata={**metadata, "utilization": utilization, "source_mode": "real_aws", "collected_at": datetime.now(timezone.utc).isoformat(), "pricing": pricing})

    def get_utilization_evidence(self, resource_id: str) -> dict[str, Any]: return self._evidence(resource_id, "utilization")


class AzureCloudAdapter(CloudProviderAdapter):
    provider = "azure"
    display_name = "Azure"

    def __init__(self, resources: list[CloudResource]) -> None:
        self._resources = resources

    def list_resources(self) -> list[CloudResource]:
        return [item.model_copy(deep=True) for item in self._resources]


class GCPCloudAdapter(CloudProviderAdapter):
    provider = "gcp"
    display_name = "Google Cloud"

    def __init__(self, resources: list[CloudResource]) -> None:
        self._resources = resources

    def list_resources(self) -> list[CloudResource]:
        return [item.model_copy(deep=True) for item in self._resources]
