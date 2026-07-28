from pathlib import Path


SCRIPT = Path("static/app.js").read_text(encoding="utf-8")


def test_disconnected_connect_button_is_bound_to_github_connect_route() -> None:
    assert 'document.getElementById("github-connect-button")' in SCRIPT
    assert 'window.location.assign("/api/integrations/github/connect")' in SCRIPT
    assert 'githubConnectButton.textContent = "Connecting…"' in SCRIPT


def test_connect_button_binding_is_idempotent_and_render_safe() -> None:
    assert 'githubConnectButton.dataset.githubConnectBound === "true"' in SCRIPT
    assert SCRIPT.count("bindGitHubConnectButton();") >= 2
    assert 'githubConnectButton.textContent = "Connect GitHub"' in SCRIPT
    assert 'setMessage("github-message"' in SCRIPT
