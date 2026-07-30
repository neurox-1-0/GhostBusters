from uuid import uuid4

from app.models import StartRunRequest
from core.conftest_policy import ConftestPolicyEvaluator
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


def test_connected_goal_with_sufficient_evidence_abstains_without_fabricating_a_recommendation() -> None:
    service = WorkflowService(store=InMemoryRunStore())
    organization_id = uuid4()
    run, _ = service.start_connected_goal(
        StartRunRequest(goal="Inspect verified evidence.", scenario_name="safe", idempotency_key="connected-goal-4"),
        organization_id,
        connected_sources=["AWS"],
    )

    updated = service.execute_connected_evidence(run.id, organization_id, {"AWS": lambda current: {
        "evidence": [{"source": "AWS", "source_id": "123", "resource_id": "i-1", "status": "verified", "summary": "Verified inventory, utilization, pricing, and mapping.", "provenance": {}, "collected_at": current.updated_at}],
        "missing_evidence": [],
    }})

    assert updated.status.value == "abstained"
    assert updated.missing_evidence == []
    assert "No infrastructure change was proposed" in str(updated.stop_reason)
    assessment = next(item for item in updated.plan_revisions if item.get("kind") == "agent_assessment")
    assert assessment["provider"] == "deterministic safety summary"
    assert "No infrastructure change was proposed" in assessment["summary"]


def test_incremental_connected_collection_preserves_history_until_finalized() -> None:
    service = WorkflowService(store=InMemoryRunStore())
    organization_id = uuid4()
    run, _ = service.start_connected_goal(
        StartRunRequest(goal="Collect evidence one source at a time.", scenario_name="safe", idempotency_key="connected-goal-5"),
        organization_id,
        connected_sources=["GitHub", "AWS"],
    )

    first = service.execute_connected_evidence(
        run.id,
        organization_id,
        {"GitHub": lambda current: {"evidence": [], "missing_evidence": ["AWS utilization"]}},
        tools=["GitHub"],
        finalize=False,
        selection_reasons={"GitHub": "The agent selected repository context first."},
    )

    assert first.status.value == "investigating"
    assert first.tool_attempts[-1]["selected_because"] == "The agent selected repository context first."
    assert first.missing_evidence == ["AWS utilization"]

    final = service.execute_connected_evidence(first.id, organization_id, {}, tools=[], finalize=True)
    assert final.status.value == "needs_more_evidence"
    assert final.missing_evidence == ["AWS utilization"]


def test_connected_goal_with_complete_live_evidence_reaches_human_approval() -> None:
    service = WorkflowService(
        store=InMemoryRunStore(),
        policy_evaluator=ConftestPolicyEvaluator(enabled=False, minimum_confidence=0.7),
    )
    organization_id = uuid4()
    run, _ = service.start_connected_goal(
        StartRunRequest(goal="Reduce non-production AWS spending by 15% with approval.", scenario_name="safe", idempotency_key="connected-goal-rightsize"),
        organization_id,
        connected_sources=["AWS"],
    )
    now = run.updated_at
    updated = service.execute_connected_evidence(run.id, organization_id, {"AWS": lambda current: {
        "missing_evidence": [],
        "evidence": [{
            "source": "AWS", "source_id": "123", "resource_id": "i-demo", "status": "verified",
            "summary": "Mapped non-production EC2 evidence collected.", "collected_at": now,
            "resource_type": "virtual_machine", "environment": "non-production",
            "instance_type": "t3.micro", "proposed_instance_type": "t3.nano",
            "utilization": {"available": True, "average_cpu_pct": 4.0, "peak_cpu_pct": 18.0, "lookback_days": 14},
            "pricing": {"available": True, "source_mode": "live", "source": "AWS Pricing API", "currency": "USD", "estimated_monthly_cost_usd": 8.0, "assumption": "On-demand Linux shared tenancy."},
            "proposed_pricing": {"available": True, "source_mode": "live", "source": "AWS Pricing API", "currency": "USD", "estimated_monthly_cost_usd": 4.0},
            "resource_tags": {"Environment": "non-production", "Owner": "demo-team", "GhostBustersRepository": "acme/demo", "GhostBustersTerraformAddress": "aws_instance.demo"},
            "terraform_mapping": {"available": True, "repository": "acme/demo", "terraform_address": "aws_instance.demo"},
            "provenance": {"region": "ap-south-1"},
        }],
    }})

    assert updated.status.value == "pending_human_review", updated.stop_reason
    assert updated.decision_record is not None
    assert updated.decision_record.preferred_action == "downsize"
    assert updated.decision_record.policy_result.requires_human_approval is True
    assert any(event.event_type == "human_review_required" for event in updated.audit_events)
    assert any(item.get("kind") == "agent_assessment" for item in updated.plan_revisions)


def test_connected_goal_approval_prepares_proposal_without_creating_pr() -> None:
    service = WorkflowService(store=InMemoryRunStore(), policy_evaluator=ConftestPolicyEvaluator(enabled=False, minimum_confidence=0.7))
    organization_id = uuid4()
    run, _ = service.start_connected_goal(
        StartRunRequest(goal="Reduce non-production AWS spending.", scenario_name="safe", idempotency_key="connected-goal-approval"),
        organization_id,
        connected_sources=["AWS"],
    )
    now = run.updated_at
    approved_candidate = service.execute_connected_evidence(run.id, organization_id, {"AWS": lambda current: {
        "missing_evidence": [],
        "evidence": [{
            "source": "AWS", "source_id": "123", "resource_id": "i-demo", "status": "verified", "summary": "Evidence collected.", "collected_at": now,
            "resource_type": "virtual_machine", "environment": "non-production", "instance_type": "t3.micro", "proposed_instance_type": "t3.nano",
            "utilization": {"average_cpu_pct": 4.0, "peak_cpu_pct": 18.0},
            "pricing": {"available": True, "source_mode": "live", "source": "AWS Pricing API", "currency": "USD", "estimated_monthly_cost_usd": 8.0},
            "proposed_pricing": {"available": True, "source_mode": "live", "source": "AWS Pricing API", "currency": "USD", "estimated_monthly_cost_usd": 4.0},
            "resource_tags": {"Environment": "non-production", "Owner": "demo-team"},
            "terraform_mapping": {"available": True, "repository": "acme/demo", "terraform_address": "aws_instance.demo"}, "provenance": {"region": "ap-south-1"},
        }],
    }})
    from app.models import HumanReviewRequest
    result, _ = service.review_run(
        approved_candidate.id,
        HumanReviewRequest(action="approve", reviewer="owner", comment="Approved for proposal", expected_version=approved_candidate.version, idempotency_key="approval-proposal"),
        organization_id,
        expected_version=approved_candidate.version,
    )

    assert result.status.value == "remediation_proposal_prepared"
    assert result.mock_pr is None
    assert result.real_pr is None
    assert any(event.event_type == "remediation_proposal_prepared" for event in result.audit_events)
