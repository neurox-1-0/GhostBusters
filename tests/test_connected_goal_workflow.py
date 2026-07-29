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
    assert run.status == "needs_more_evidence"
    assert run.evidence_summaries == []
    assert "will not fabricate" in (run.stop_reason or "")
    assert [event.event_type for event in run.audit_events] == [
        "run_created",
        "goal_received",
        "investigation_plan_created",
        "evidence_collection_pending",
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
