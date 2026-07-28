from dataclasses import replace

import pytest
from fastapi import Response

import app.auth as auth_module
from app.auth import set_session_cookies
from app.settings import Settings, validate_startup_settings


def production_settings(**updates) -> Settings:
    base = Settings(
        app_env="production",
        auth_required=True,
        session_cookie_secure=True,
        allow_insecure_http_demo=False,
        secret_key="x" * 48,
        database_url="postgresql://db",
        redis_url="redis://redis",
        cors_allowed_origins=("https://example.test",),
        trust_proxy_headers=True,
        demo_mode_enabled=False,
        auto_create_schema=False,
    )
    return replace(base, **updates)


def test_production_requires_secure_cookie_without_explicit_http_demo() -> None:
    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        validate_startup_settings(production_settings(session_cookie_secure=False))


def test_controlled_http_demo_allows_insecure_cookie() -> None:
    validate_startup_settings(production_settings(session_cookie_secure=False, allow_insecure_http_demo=True))


def test_cookie_flags_follow_dedicated_setting(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "settings", production_settings(session_cookie_secure=False, allow_insecure_http_demo=True))
    response = Response()
    set_session_cookies(response, "session", "csrf")
    cookie = "\n".join(value.decode() for name, value in response.raw_headers if name == b"set-cookie")
    assert "ghostbusters_session=session" in cookie
    assert "ghostbusters_csrf=csrf" in cookie
    assert "Secure" not in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    monkeypatch.setattr(auth_module, "settings", production_settings(session_cookie_secure=True))
    response = Response()
    set_session_cookies(response, "session", "csrf")
    cookie = "\n".join(value.decode() for name, value in response.raw_headers if name == b"set-cookie")
    assert cookie.count("Secure") == 2
