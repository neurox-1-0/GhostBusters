from __future__ import annotations

from core.redaction import REDACTED, redact_model_payload


def test_secrets_are_redacted_from_model_payloads() -> None:
    payload = {
        "GITHUB_TOKEN": "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "nested": {
            "database_url": "postgresql://user:pass@example/db",
            "terraform": 'password = "super-secret-value"',
            "safe": "resource id",
        },
    }

    redacted = redact_model_payload(payload)

    assert redacted["GITHUB_TOKEN"] == REDACTED
    assert redacted["nested"]["database_url"] == REDACTED
    assert redacted["nested"]["terraform"] == REDACTED
    assert redacted["nested"]["safe"] == "resource id"
    assert "super-secret-value" not in str(redacted)
