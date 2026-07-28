"""Audit event helpers for workflow runs."""

from __future__ import annotations

from typing import Any

from app.models import AuditEvent, WorkflowRun
from integrations.base import utc_now


def append_audit_event(
    run: WorkflowRun,
    *,
    event_type: str,
    actor: str,
    summary: str,
    details: dict[str, Any] | None = None,
    goal_id=None,
    stage: str | None = None,
    status: str | None = None,
    label: str | None = None,
    tool: str | None = None,
    reason: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    decision_impact: str | None = None,
    attempt_number: int | None = None,
    correlation_id: str | None = None,
) -> WorkflowRun:
    next_sequence = len(run.audit_events) + 1
    run.audit_events.append(
        AuditEvent(
            sequence_number=next_sequence,
            timestamp=utc_now(),
            event_type=event_type,
            actor=actor,  # type: ignore[arg-type]
            summary=summary,
            details=details or {},
            goal_id=goal_id or run.id,
            stage=stage or event_type,
            status=status or "completed",
            label=label or summary,
            tool=tool,
            reason=reason,
            input_summary=input_summary,
            output_summary=output_summary,
            decision_impact=decision_impact,
            attempt_number=attempt_number,
            correlation_id=correlation_id or run.correlation_id,
        )
    )
    run.updated_at = utc_now()
    return run
