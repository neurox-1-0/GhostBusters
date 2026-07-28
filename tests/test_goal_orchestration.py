from fastapi.testclient import TestClient

from app.main import app


def test_goals_expose_structured_journey_and_retain_state() -> None:
    client = TestClient(app)
    client.post("/api/reset")
    first = client.post("/api/goals", json={"goal": "Reduce cost", "scenario_name": "safe", "scope": "AWS production"})
    assert first.status_code == 201
    run = first.json()
    assert run["data_source_mode"] == "Fixture-backed"
    assert run["scope"] == "AWS production"
    events = client.get(f"/api/goals/{run['id']}/events").json()
    assert events
    assert [event["sequence_number"] for event in events] == sorted(event["sequence_number"] for event in events)
    assert all(event["correlation_id"] == run["correlation_id"] for event in events)
    assert any(event["event_type"] == "goal_received" for event in events)
    assert any(event["event_type"] in {"goal_completed", "human_review_required", "failed_safely"} for event in events)
    since = client.get(f"/api/goals/{run['id']}/events?since_sequence=1").json()
    assert all(event["sequence_number"] > 1 for event in since)
    assert client.get("/api/goals").status_code == 200


def test_different_goal_paths_and_safe_cancel() -> None:
    client = TestClient(app)
    client.post("/api/reset")
    cost = client.post("/api/goals", json={"goal": "Optimize monthly cost", "scenario_name": "safe"}).json()
    dependency = client.post("/api/goals", json={"goal": "Explain dependency risk", "scenario_name": "dependency"}).json()
    assert cost["id"] != dependency["id"]
    assert cost["selected_tools"] != dependency["selected_tools"] or cost["skipped_tools"] != dependency["skipped_tools"]
    canceled = client.post(f"/api/goals/{cost['id']}/cancel", json={})
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    events = client.get(f"/api/goals/{cost['id']}/events").json()
    assert events[-1]["event_type"] == "failed_safely"
    assert "No Terraform apply" in events[-1]["decision_impact"]
