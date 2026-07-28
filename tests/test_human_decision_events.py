from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import auth_store, session_store
from app.main import app
from app.models import CloudHuntRequest, ReviewCaseActionRequest
from core.cloud_hunt_service import CloudHuntService
from core.decision_events import decision_event_store


def setup_function() -> None:
    auth_store.reset()
    decision_event_store.reset()
    if hasattr(session_store, "sessions"):
        session_store.sessions.clear()


def register() -> tuple[TestClient, dict]:
    client = TestClient(app)
    profile = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "display_name": "Owner One",
            "password": "correct horse battery staple",
            "organization_name": "Owner Org",
            "timezone": "UTC",
        },
    ).json()
    client.post("/api/reset")
    return client, profile


def start_safe_run(client: TestClient, csrf: str) -> dict:
    response = client.post(
        "/api/runs",
        headers={"X-CSRF-Token": csrf},
        json={"goal": "reduce cost", "scenario_name": "safe"},
    )
    assert response.status_code == 201
    return response.json()


def decide(client: TestClient, csrf: str, run: dict, payload: dict):
    body = {"expected_version": run["version"], "idempotency_key": payload.pop("idempotency_key", f"{payload['action']}-key"), **payload}
    return client.post(f"/api/runs/{run['id']}/review", headers={"X-CSRF-Token": csrf}, json=body)


def test_decision_event_uses_authenticated_actor_and_is_append_only() -> None:
    client, profile = register()
    run = start_safe_run(client, profile["csrf_token"])

    response = decide(client, profile["csrf_token"], run, {"action": "reject", "reviewer": "spoofed", "comment": "not safe enough"})

    assert response.status_code == 200
    event = decision_event_store.list()[0]
    assert event.actor_snapshot["display_name"] == "Owner One"
    assert event.actor_snapshot["email"] == "owner@example.com"
    assert event.action == "reject"
    assert event.previous_state["status"] == "pending_human_review"
    assert event.resulting_state["status"] == "rejected"
    assert event.response_snapshot["correlation_id"] == response.json()["correlation_id"]
    assert len(decision_event_store.list()) == 1


def test_idempotent_retry_and_conflict_do_not_duplicate_side_effects() -> None:
    client, profile = register()
    run = start_safe_run(client, profile["csrf_token"])
    payload = {"action": "approve", "comment": "approved", "idempotency_key": "same-key"}

    first = decide(client, profile["csrf_token"], run, dict(payload))
    second = decide(client, profile["csrf_token"], run, dict(payload))
    conflict = decide(client, profile["csrf_token"], run, {"action": "approve", "comment": "different", "idempotency_key": "same-key"})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert first.json()["decision_event_id"] == second.json()["decision_event_id"]
    assert conflict.status_code == 409
    assert len(decision_event_store.list()) == 1


def test_stale_expected_version_returns_409_and_creates_no_event() -> None:
    client, profile = register()
    run = start_safe_run(client, profile["csrf_token"])
    first = decide(client, profile["csrf_token"], run, {"action": "reject", "comment": "no", "idempotency_key": "reject"})
    assert first.status_code == 200

    stale = decide(client, profile["csrf_token"], run, {"action": "request_evidence", "requested_sources": ["jira"], "idempotency_key": "stale"})

    assert stale.status_code == 409
    assert len(decision_event_store.list()) == 1


def test_revoke_is_distinct_from_reject_and_reopen_records_related_event() -> None:
    client, profile = register()
    run = start_safe_run(client, profile["csrf_token"])
    approved = decide(client, profile["csrf_token"], run, {"action": "approve", "comment": "approved", "idempotency_key": "approve"}).json()

    revoked = client.post(
        f"/api/runs/{run['id']}/review",
        headers={"X-CSRF-Token": profile["csrf_token"]},
        json={"action": "revoke_approval", "comment": "approval withdrawn", "expected_version": approved["version"], "idempotency_key": "revoke"},
    )
    reopened = client.post(
        f"/api/runs/{run['id']}/review",
        headers={"X-CSRF-Token": profile["csrf_token"]},
        json={"action": "reopen_case", "comment": "review again", "expected_version": revoked.json()["version"], "idempotency_key": "reopen"},
    )

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "approval_revoked"
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    events = decision_event_store.list()
    assert [event.action for event in events] == ["approve", "revoke_approval", "reopen_case"]
    assert events[1].related_event_id == events[0].id


def test_cloud_hunt_mapped_and_unmapped_approval_outcomes_are_truthful() -> None:
    service = CloudHuntService()
    service.start_hunt(CloudHuntRequest())
    mapped = next(case for case in service.list_cases() if case.terraform_address and not service._is_protected(case.candidate))
    unmapped = next(case for case in service.list_cases() if not case.terraform_address and not service._is_protected(case.candidate))

    mapped_result = service.act_on_case(mapped.id, ReviewCaseActionRequest(action="approve", reviewer="r"))
    unmapped_result = service.act_on_case(unmapped.id, ReviewCaseActionRequest(action="approve", reviewer="r"))

    assert mapped_result.status == "remediation_pr_created"
    assert mapped_result.simulated_pr is not None
    assert unmapped_result.status == "remediation_proposal_prepared"
    assert "not currently managed by Terraform" in unmapped_result.simulated_pr.terraform_patch_preview


def test_audit_and_activity_share_correlation_id() -> None:
    client, profile = register()
    run = start_safe_run(client, profile["csrf_token"])
    response = decide(client, profile["csrf_token"], run, {"action": "reject", "comment": "no", "idempotency_key": "corr"})
    body = response.json()

    stored = client.get(f"/api/runs/{run['id']}").json()
    assert any(event["details"].get("correlation_id") == body["correlation_id"] for event in stored["audit_events"])
    assert any(event["details"].get("correlation_id") == body["correlation_id"] for event in auth_store.activity_events)
