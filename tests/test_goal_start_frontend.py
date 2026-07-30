from pathlib import Path


APP_JS = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (Path(__file__).parents[1] / "static" / "index.html").read_text(encoding="utf-8")


def test_goal_start_has_bounded_creation_and_progress_requests() -> None:
    assert 'withTimeout(api("/api/goals"' in APP_JS
    assert 'api(`/api/goals/${goalId}/events`)' in APP_JS
    assert '"The investigation did not start. Retry."' in APP_JS
    assert '"Live updates temporarily unavailable. Showing last known state."' in APP_JS


def test_goal_start_transitions_immediately_and_normalizes_workflow_runs() -> None:
    assert "normalizeGoalResponse(await withTimeout" in APP_JS
    assert 'state.goalTab = "plan"' in APP_JS
    assert '"Goal received. Interpreting scope…"' in APP_JS
    assert '"Interpreting scope"' in APP_JS


def test_goal_start_maps_errors_and_prevents_duplicate_requests() -> None:
    for status in (401, 403, 409, 422, 429):
        assert f"error?.status === {status}" in APP_JS
    assert "state.goalStartInFlight" in APP_JS
    assert "state.goalValidationInFlight" in APP_JS
    assert 'withButtonState("goal-start-button", "Groq is reviewing the goal..."' in APP_JS
    assert "idempotency_key: state.goalDraft.idempotencyKey" in APP_JS
    assert 'id="goal-retry-button"' in INDEX_HTML
    assert 'on("goal-retry-button", "click", retryGoalAction)' in APP_JS
    assert "goalPollFailures" in APP_JS
    assert "beginGoalPolling" in APP_JS


def test_clarification_revalidation_keeps_a_visible_next_action() -> None:
    assert '$("goal-clarification-panel").hidden = true;' in APP_JS
    assert 'if (validation.status !== "accepted") { $("goal-clarification-reason").textContent' in APP_JS
    assert '$("goal-interpretation-panel").hidden = false;' in APP_JS
    assert '$("goal-confirm-button").focus?.();' in APP_JS


def test_goal_start_handler_is_exposed_for_dynamic_frontend_tests() -> None:
    assert "confirmGoal," in APP_JS
    assert "normalizeGoalResponse," in APP_JS


def test_evidence_paused_goal_has_a_truthful_retry_state() -> None:
    assert '"goal-retry-evidence-button"' in APP_JS
    assert 'run.status !== "needs_more_evidence"' in APP_JS
    assert '"Live updates temporarily unavailable. Showing last known state."' in APP_JS
    assert "missing_evidence" in APP_JS


def test_goal_repository_scope_uses_persistent_checkbox_selection() -> None:
    assert 'class="goal-repository-checkboxes"' in INDEX_HTML
    assert 'input.type = "checkbox"' in APP_JS
    assert "goalSelectedRepositories" in APP_JS
    assert "Choose the repositories GhostOps may inspect." in APP_JS


def test_abstained_goal_is_not_rendered_as_a_running_policy_step() -> None:
    assert 'if (run.status === "abstained")' in APP_JS
    assert 'run.status === "abstained" ? "No recommendation"' in APP_JS
    assert "const roadmapStates = goalRoadmapStates(run, state.goalEvents);" in APP_JS


def test_live_plan_surfaces_a_safe_groq_fallback_reason() -> None:
    assert "Groq could not complete this decision" in APP_JS
    assert "decision.error_category" in APP_JS


def test_current_step_uses_a_human_readable_presentation() -> None:
    assert "function goalStepPresentation" in APP_JS
    assert 'title: "Reviewed AWS resource evidence"' in APP_JS
    assert 'title: "Reviewed Terraform repository context"' in APP_JS
    assert "const presentation = goalStepPresentation(latest, run);" in APP_JS
