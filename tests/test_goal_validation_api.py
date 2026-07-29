from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_goal_validation_accepts_supported_safe_goal() -> None:
    response = client.post("/api/goals/validate", json={
        "goal": "Reduce non-production cloud waste while protecting production workloads.",
        "scope": "Non-production AWS",
        "require_approval": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "run_cloud_hunt" in body["suggested_capabilities"]
    assert "Human approval required" in body["constraints"]


def test_goal_validation_rejects_unsafe_or_unrelated_input() -> None:
    unsafe = client.post("/api/goals/validate", json={"goal": "Delete all AWS servers", "scope": "Production AWS"})
    unrelated = client.post("/api/goals/validate", json={"goal": "Plan a birthday party", "scope": "Home"})

    assert unsafe.status_code == 200
    assert unsafe.json()["status"] == "rejected"
    assert unrelated.status_code == 200
    assert unrelated.json()["status"] == "rejected"
