from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from core.webhook_dedup import NoopWebhookDeduplicator


client = TestClient(app)


def setup_function() -> None:
    main_module.webhook_deduplicator = NoopWebhookDeduplicator()
    client.post("/api/demo/reset", json={"confirm": True})


def test_product_help_question_works_without_case_id() -> None:
    response = client.post("/api/assistant/ask", json={"question": "What is Cloud Hunt?", "context": "product_help"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_type"] == "product_help"
    assert "Cloud Hunt" in payload["answer"]
    assert payload["fallback_used"] is True


def test_case_question_requires_case_id() -> None:
    response = client.post("/api/assistant/ask", json={"question": "Why was this recommendation made?", "context": "pr_review"})

    assert response.status_code == 422


def test_case_question_returns_grounded_evidence_and_no_secrets() -> None:
    run = client.post("/api/runs", json={"goal": "reduce cost", "scenario_name": "safe"}).json()
    response = client.post(
        "/api/assistant/ask",
        json={"question": "Why was this recommendation made?", "context": "pr_review", "case_id": run["id"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_type"] == "explanation"
    assert payload["evidence_sources"]
    assert "GITHUB_TOKEN" not in str(payload)
    assert "[object Object]" not in str(payload)


def test_action_request_is_read_only() -> None:
    run = client.post("/api/runs", json={"goal": "reduce cost", "scenario_name": "safe"}).json()
    response = client.post(
        "/api/assistant/ask",
        json={"question": "Please approve this case", "context": "pr_review", "case_id": run["id"]},
    )

    assert response.status_code == 200
    assert response.json()["answer_type"] == "action_not_allowed"
    assert client.get(f"/api/runs/{run['id']}").json()["status"] == "pending_human_review"


def test_invalid_case_id_returns_not_found() -> None:
    response = client.post(
        "/api/assistant/ask",
        json={"question": "What evidence was used?", "context": "pr_review", "case_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
