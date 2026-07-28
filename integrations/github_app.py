"""GitHub App state signing and short-lived installation authentication."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from redis import Redis
from redis.exceptions import RedisError

from app.settings import Settings, settings
from integrations.github_client import GitHubAPIError, GitHubClient


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class GitHubAppState:
    def __init__(self) -> None:
        self._used: set[str] = set(); self._lock = RLock(); self._redis = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None

    def create(self, organization_id: str, user_id: str, configuration: Settings = settings) -> str:
        nonce = secrets.token_urlsafe(24); expires = int(time.time()) + configuration.github_app_state_ttl_seconds
        payload = {"organization_id": organization_id, "user_id": user_id, "nonce": nonce, "expires": expires}
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = hmac.new((configuration.secret_key or "development-state-key").encode(), body.encode(), hashlib.sha256).digest()
        return f"{body}.{_b64(signature)}"

    def consume(self, state: str, configuration: Settings = settings) -> dict[str, Any]:
        try: body, encoded_signature = state.split(".", 1)
        except ValueError as exc: raise ValueError("Invalid GitHub connection state.") from exc
        expected = _b64(hmac.new((configuration.secret_key or "development-state-key").encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, encoded_signature): raise ValueError("Invalid GitHub connection state.")
        try: payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        except (ValueError, json.JSONDecodeError) as exc: raise ValueError("Invalid GitHub connection state.") from exc
        nonce = str(payload.get("nonce") or "")
        with self._lock:
            if not nonce or nonce in self._used: raise ValueError("GitHub connection state was already used.")
            if int(payload.get("expires") or 0) < int(time.time()): raise ValueError("GitHub connection state expired.")
            if self._redis is not None:
                try:
                    if not self._redis.set(f"ghostbusters:github-state:{nonce}", "1", nx=True, ex=configuration.github_app_state_ttl_seconds): raise ValueError("GitHub connection state was already used.")
                except RedisError as exc: raise ValueError("GitHub connection state store is unavailable.") from exc
            self._used.add(nonce)
        return payload


github_app_state = GitHubAppState()


def private_key(configuration: Settings = settings):
    value = configuration.github_app_private_key
    if not value and configuration.github_app_private_key_path:
        value = Path(configuration.github_app_private_key_path).read_text(encoding="utf-8")
    if not value: raise GitHubAPIError("configuration", "GitHub App private key is unavailable.")
    try: return serialization.load_pem_private_key(value.replace("\\n", "\n").encode(), password=None)
    except Exception as exc: raise GitHubAPIError("configuration", "GitHub App private key is invalid.") from exc


def app_jwt(configuration: Settings = settings) -> str:
    now = int(time.time()); header = _b64(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": configuration.github_app_id}, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode(); key = private_key(configuration)
    signature = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64(signature)}"


class GitHubAppClient:
    def __init__(self, installation_id: int, configuration: Settings = settings, client: httpx.Client | None = None) -> None:
        self.installation_id = installation_id; self.configuration = configuration; self._client = client or httpx.Client(base_url=configuration.github_api_base_url.rstrip("/"), timeout=configuration.github_request_timeout_seconds)
        self._token: str | None = None; self._token_expires = 0

    def installation_token(self) -> str:
        if self._token and self._token_expires > int(time.time()) + 30: return self._token
        response = self._client.post(f"/app/installations/{self.installation_id}/access_tokens", headers={"Authorization": f"Bearer {app_jwt(self.configuration)}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        if response.status_code >= 400: raise GitHubAPIError("authentication", "GitHub installation authentication failed safely.")
        payload = response.json(); token = payload.get("token")
        if not token: raise GitHubAPIError("authentication", "GitHub installation token was not returned.")
        self._token = str(token); self._token_expires = int(time.time()) + min(self.configuration.github_app_installation_token_ttl_seconds, 540); return self._token

    def api_client(self) -> GitHubClient:
        return GitHubClient(self.installation_token(), self.configuration.github_api_base_url, self.configuration.github_request_timeout_seconds, self._client)

    def installation(self) -> dict[str, Any]:
        response = self._client.get(f"/app/installations/{self.installation_id}", headers={"Authorization": f"Bearer {app_jwt(self.configuration)}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        if response.status_code >= 400: raise GitHubAPIError("authentication", "GitHub installation could not be resolved safely.")
        return response.json()
