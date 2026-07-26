"""Safe redaction helpers for model-bound payloads and audit metadata."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|secret|password|credential|private_key|api_key|authorization|cookie|webhook_secret|database_url)",
    re.IGNORECASE,
)
LIKELY_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|glpat|xox[baprs])-[-_A-Za-z0-9]{12,}\b"),
    re.compile(r"\b[A-Za-z0-9_=-]{32,}\.[A-Za-z0-9_=-]{16,}\.[A-Za-z0-9_=-]{16,}\b"),
    re.compile(r"(?i)\b(?:password|secret|token|api_key)\s*=\s*['\"]?[^'\"\s]+"),
)
REDACTED = "[REDACTED]"


def is_sensitive_key(key: object) -> bool:
    return bool(SENSITIVE_KEY_PATTERN.search(str(key)))


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in LIKELY_SECRET_VALUE_PATTERNS):
            return REDACTED
        return value[:1200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [redact_value(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return redact_mapping(value)
    return str(value)[:300]


def redact_mapping(payload: dict[Any, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in payload.items():
        safe_key = str(key)
        output[safe_key] = REDACTED if is_sensitive_key(safe_key) else redact_value(value)
    return output


def redact_model_payload(payload: Any) -> Any:
    return redact_value(payload)
