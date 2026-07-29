"""Small deterministic helpers for interpreting evidence."""

from __future__ import annotations

from typing import Any

from app.models import EvidenceItem


VERIFIED_PRICING_MODES = {"live", "verified_cached"}
REQUIRED_PRICING_FIELDS = ("source", "region", "resource_type", "pricing_model", "checked_at", "assumptions", "currency")


def item_by_source(evidence: list[EvidenceItem], source: str) -> EvidenceItem | None:
    return next((item for item in evidence if item.source == source), None)


def value_for(evidence: list[EvidenceItem], source: str) -> dict[str, Any]:
    item = item_by_source(evidence, source)
    if item is None or not isinstance(item.value, dict):
        return {}
    return item.value


def source_unavailable(evidence: list[EvidenceItem], source: str) -> bool:
    item = item_by_source(evidence, source)
    return item is None or item.freshness_status == "unavailable"


def verified_pricing_item(evidence: list[EvidenceItem]) -> EvidenceItem | None:
    item = item_by_source(evidence, "pricing")
    if item is None or item.freshness_status == "unavailable" or item.source_mode not in VERIFIED_PRICING_MODES:
        return None
    if not isinstance(item.value, dict):
        return None
    if any(item.value.get(field) in (None, "", []) and item.metadata.get(field) in (None, "", []) for field in REQUIRED_PRICING_FIELDS):
        return None
    if not isinstance(item.value.get("current_monthly_cost"), int | float) or not isinstance(item.value.get("proposed_monthly_cost"), int | float):
        return None
    return item


def verified_pricing_values(evidence: list[EvidenceItem]) -> tuple[float | None, float | None]:
    item = verified_pricing_item(evidence)
    if item is None:
        return None, None
    return float(item.value["current_monthly_cost"]), float(item.value["proposed_monthly_cost"])


def utilization_values(evidence: list[EvidenceItem]) -> tuple[float | None, float | None]:
    utilization = value_for(evidence, "utilization")
    avg = utilization.get("average_cpu_pct")
    peak = utilization.get("peak_cpu_pct")
    return (
        float(avg) if isinstance(avg, int | float) else None,
        float(peak) if isinstance(peak, int | float) else None,
    )


def pricing_values(evidence: list[EvidenceItem]) -> tuple[float | None, float | None]:
    pricing = value_for(evidence, "pricing")
    current = pricing.get("current_monthly_cost")
    proposed = pricing.get("proposed_monthly_cost")
    return (
        float(current) if isinstance(current, int | float) else None,
        float(proposed) if isinstance(proposed, int | float) else None,
    )


def active_dependencies(evidence: list[EvidenceItem]) -> bool:
    dependencies = value_for(evidence, "dependencies")
    return bool(dependencies.get("has_active_dependencies"))


def jira_status(evidence: list[EvidenceItem]) -> str | None:
    jira = value_for(evidence, "jira")
    status = jira.get("status")
    return str(status).lower() if status is not None else None


def recent_git_activity(evidence: list[EvidenceItem], days_threshold: int = 7) -> bool:
    git = value_for(evidence, "git_activity")
    commit_count = git.get("recent_commit_count")
    days = git.get("days_since_last_commit")
    if isinstance(commit_count, int | float) and commit_count > 0:
        return True
    return isinstance(days, int | float) and days <= days_threshold


def monthly_savings(evidence: list[EvidenceItem]) -> float:
    current, proposed = pricing_values(evidence)
    if current is None or proposed is None:
        return 0.0
    return current - proposed
