from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_frontend_exposes_actual_planning_mode_and_ai_boundary_copy() -> None:
    root = client.get("/").text
    script = client.get("/static/app.js").text
    assert "Deterministic Safety Policy" in root
    assert "AI-assisted planning" in script
    assert "Mock AI planning was used for demonstration only." in script
    assert "AI planning was unavailable" in script
    assert "Prepared fixtures are backing this demo case." in script
    assert "[object Object]" not in root + script
