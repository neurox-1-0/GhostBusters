from unittest.mock import Mock
from uuid import uuid4

import app.main as main_module


def test_callback_logs_sanitized_stage_and_preserves_error_redirect(monkeypatch) -> None:
    state = main_module.github_app_state.create(str(uuid4()), str(uuid4()))

    class FailingClient:
        def installation(self):
            return {"account": {"login": "acme", "type": "Organization"}}

        def api_client(self):
            return self

        def list_installation_repositories(self):
            raise RuntimeError("provider failure")

    logger = Mock()
    monkeypatch.setattr(main_module, "GitHubAppClient", lambda installation_id: FailingClient())
    monkeypatch.setattr(main_module, "logger", logger)

    response = main_module.github_callback(state, installation_id=42, setup_action="install")

    assert response.status_code == 303
    assert response.headers["location"] == "/?github=error&reason=connection_failed"
    logger.exception.assert_called_once()
    fields = logger.exception.call_args.kwargs["extra"]
    assert fields == {
        "stage": "list_repositories",
        "installation_id": 42,
        "setup_action": "install",
        "exception_class": "RuntimeError",
        "organization_id": fields["organization_id"],
    }
