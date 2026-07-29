"""Stateless, signed AWS CloudFormation onboarding state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID


class AWSOnboardingState:
    def __init__(self, secret: str | None, ttl_seconds: int) -> None:
        self.secret = (secret or "").encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def _signature(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode("ascii"), hashlib.sha256).hexdigest()

    def external_id(self, organization_id: UUID) -> str:
        return hmac.new(self.secret, f"aws-role:{organization_id}".encode("utf-8"), hashlib.sha256).hexdigest()

    def create(self, organization_id: UUID, user_id: UUID | None) -> tuple[str, str]:
        if not self.secret:
            raise ValueError("AWS onboarding requires a configured application secret.")
        correlation_id = secrets.token_urlsafe(12)
        body = {
            "organization_id": str(organization_id),
            "user_id": str(user_id) if user_id else None,
            "correlation_id": correlation_id,
            "expires_at": int(time.time()) + self.ttl_seconds,
        }
        payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
        return f"{payload}.{self._signature(payload)}", correlation_id

    def consume(self, state: str) -> dict[str, object]:
        try:
            payload, signature = state.split(".", 1)
            if not hmac.compare_digest(signature, self._signature(payload)):
                raise ValueError("invalid signature")
            decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            result = json.loads(decoded.decode("utf-8"))
            if int(result["expires_at"]) < time.time():
                raise ValueError("expired state")
            UUID(str(result["organization_id"]))
            return result
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid onboarding state") from exc
