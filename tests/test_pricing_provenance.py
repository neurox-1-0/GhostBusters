from dataclasses import replace
from datetime import datetime, timezone
import re

import pytest

from app.models import EvidenceItem, TerraformResourceChange
from app.settings import Settings, validate_startup_settings
from core.evidence_utils import verified_pricing_item
from integrations.registry import UnavailablePricingTool


def resource() -> TerraformResourceChange:
    return TerraformResourceChange(address="aws_instance.app", resource_type="aws_instance", actions=["update"], before={}, after={}, destructive=False)


def test_unavailable_pricing_tool_is_explicit_and_never_returns_zero() -> None:
    item = UnavailablePricingTool().collect(None, resource())[0]
    assert item.source_mode == "unavailable"
    assert item.value is None
    assert item.metadata["reason"] == "Live pricing evidence was not available for this change."


def test_production_rejects_mock_pricing_provider() -> None:
    config = replace(
        Settings(),
        app_env="production",
        auth_required=True,
        session_cookie_secure=True,
        secret_key="x" * 40,
        database_url="postgresql://db",
        redis_url="redis://redis",
        cors_allowed_origins=("https://example.test",),
        trust_proxy_headers=True,
        auto_create_schema=False,
        pricing_provider="mock",
    )
    with pytest.raises(RuntimeError, match="Mock or fixture pricing providers"):
        validate_startup_settings(config)


def test_pricing_provenance_requires_live_source_fields() -> None:
    item = EvidenceItem(source="pricing", tool_name="pricing", claim="cost", value={"current_monthly_cost": 140, "proposed_monthly_cost": 70, "currency": "USD"}, resource_id="aws_instance.app", collected_at=datetime.now(timezone.utc), freshness_status="fresh", reliability=1.0, source_mode="live")
    assert verified_pricing_item([item]) is None


def test_typo_was_not_reintroduced() -> None:
    from pathlib import Path

    files = [path for root in (Path("app"), Path("core"), Path("integrations")) for path in root.rglob("*.py")]
    assert not re.search(r"current_monthly_cos(?!t)", "\n".join(path.read_text(encoding="utf-8") for path in files))


def test_frontend_has_fail_closed_pricing_copy_and_provenance_gate() -> None:
    script = open("static/app.js", encoding="utf-8").read()
    assert "Cost estimate unavailable" in script
    assert "Live pricing evidence was not available for this change." in script
    assert 'item.source_mode !== "live" && item.source_mode !== "verified_cached"' in script
