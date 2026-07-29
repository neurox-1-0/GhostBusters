from pathlib import Path


APP_JS = Path("static/app.js").read_text(encoding="utf-8")


def test_successful_pr_list_clears_stale_auth_message() -> None:
    assert 'state.currentUser?.authenticated && $("ui-message")?.textContent === "Authentication required."' in APP_JS
    assert 'setMessage("ui-message", "");' in APP_JS


def test_auxiliary_401_is_local_and_has_retry_without_replacing_loaded_page() -> None:
    assert 'const target = state.activeMode === "simple" ? "pr-auxiliary-message" : "cloud-hunt-message";' in APP_JS
    assert '"Approval metadata unavailable."' in APP_JS
    assert 'id="pr-auxiliary-retry-button"' in Path("static/index.html").read_text(encoding="utf-8")
    assert 'on("pr-auxiliary-retry-button", "click", loadReviewQueue);' in APP_JS


def test_main_pr_list_401_keeps_authentication_required_flow() -> None:
    assert 'if (error?.status === 401)' in APP_JS
    assert 'openAuthModal("signin");' in APP_JS
    assert 'setMessage("ui-message", "Authentication required.");' in APP_JS


def test_member_auxiliary_failure_does_not_write_page_auth_message() -> None:
    members_loader = APP_JS[APP_JS.index("async function loadMembers"):APP_JS.index("async function loadPRReviews")]
    assert 'setMessage("members-message", message);' in members_loader
    assert 'setMessage("ui-message"' not in members_loader
