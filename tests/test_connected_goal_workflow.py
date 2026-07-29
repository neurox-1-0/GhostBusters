from uuid import uuid4

from app.models import StartRunRequest
from core.run_store import InMemoryRunStore
from core.workflow_service import WorkflowService


def test_connected_goal_is_persisted_without_fixture_fallback() -> None:
    service = WorkflowService(store=InMemoryRunStore())
    organization_id = uuid4()

    run, created = service.start_connected_goal(
        StartRunRequest(
            goal="Reduce unnecessary production cloud spending without affecting reliability.",
            scenario_name="safe",
            idempotency_key="connected-goal-1",
            scope="Production AWS",
        ),
        organization_id,
        connected_sources=["GitHub", "AWS"],
    )

    assert created is True
    assert run.organization_id == organization_id
    assert run.source_type == "autonomous_goal"
    assert run.execution_mode == "connected_read_only"
    assert run.data_source_mode == "Connected evidence"
    assert run.status == "investigating"
    assert run.evidence_summaries == []
    assert run.stop_reason is None
    assert [event.event_type for event in run.audit_events] == [
        "run_created",
        "goal_received",
        "investigation_plan_created",
        "evidence_collection_started",
    ]
    assert service.get_run(run.id, organization_id).id == run.id


def test_connected_goal_idempotency_and_organization_isolation() -> None:
    service = WorkflowService(store=InMemoryRunStore())
    organization_id = uuid4()
    request = StartRunRequest(goal="Review connected evidence safely.", scenario_name="safe", idempotency_key="connected-goal-2")

    first, created = service.start_connected_goal(request, organization_id)
    replay, replay_created = service.start_connected_goal(request, organization_id)

    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert service.list_runs(uuid4()) == []


def test_connected_goal_executes_selected_collector_and_records_evidence() -> None:
    service = WorkflowService(store=InMemoryRunStore())
    organization_id = uuid4()
    run, _ = service.start_connected_goal(
        StartRunRequest(goal="Inspect connected GitHub evidence safely.", scenario_name="safe", idempotency_key="connected-goal-3"),
        organization_id,
        connected_sources=["GitHub"],
    )

    def github_collector(current):
        return {
            "github_context": {"repository": "acme/infra", "source_mode": "real_github"},
            "evidence": [{"source": "GitHub", "source_id": "acme/infra", "resource_id": "acme/infra", "status": "verified", "summary": "Repository metadata collected.", "provenance": {"organization_id": str(organization_id)}, "limitations": ["No runtime utilization."], "collected_at": current.updated_at}],
            "missing_evidence": ["AWS utilization", "Verified pricing"],
        }

    updated = service.execute_connected_evidence(run.id, organization_id, {"GitHub": github_collector})

    assert updated.github_context["repository"] == "acme/infra"
    assert updated.tool_attempts[-1]["tool_name"] == "GitHub"
    assert updated.tool_attempts[-1]["status"] == "completed"
    assert updated.evidence_summaries[0]["source"] == "GitHub"
    assert updated.status == "needs_more_evidence"
    assert updated.missing_evidence == ["AWS utilization", "Verified pricing"]
    assert any(event.event_type == "github_evidence_recorded" for event in updated.audit_events)
