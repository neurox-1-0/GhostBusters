from pathlib import Path


APP_JS = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (Path(__file__).parents[1] / "static" / "index.html").read_text(encoding="utf-8")


def test_goal_start_has_bounded_creation_and_progress_requests() -> None:
    assert 'withTimeout(api("/api/goals"' in APP_JS
    assert 'api(`/api/goals/${goalId}/events`)' in APP_JS
    assert '"The investigation did not start. Retry."' in APP_JS
    assert '"Goal progress is temporarily unavailable. Retry refresh."' in APP_JS


def test_goal_start_transitions_immediately_and_normalizes_workflow_runs() -> None:
    assert "normalizeGoalResponse(await withTimeout" in APP_JS
    assert 'state.goalTab = "plan"' in APP_JS
    assert '"Goal received. Interpreting scope…"' in APP_JS
    assert '"Interpreting scope"' in APP_JS


def test_goal_start_maps_errors_and_prevents_duplicate_requests() -> None:
    for status in (401, 403, 409, 422):
        assert f"error?.status === {status}" in APP_JS
    assert "state.goalStartInFlight" in APP_JS
    assert "idempotency_key: state.goalDraft.idempotencyKey" in APP_JS
    assert 'id="goal-retry-button"' in INDEX_HTML
    assert 'on("goal-retry-button", "click", confirmGoal)' in APP_JS


def test_goal_start_handler_is_exposed_for_dynamic_frontend_tests() -> None:
    assert "confirmGoal," in APP_JS
    assert "normalizeGoalResponse," in APP_JS
