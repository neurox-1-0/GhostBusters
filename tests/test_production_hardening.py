from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.main import app
from app.settings import settings, validate_startup_settings
from core.cloud_hunt_scheduler import DistributedScheduleLease
from core.rate_limit import RateLimiter


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1234), "scheme": "http", "query_string": b"", "server": ("test", 80)})


def test_legacy_reset_route_is_removed_and_demo_reset_is_present():
    paths = {(route.path, tuple(getattr(route, "methods", None) or ())) for route in app.routes}
    assert not any(path == "/api/reset" for path, _ in paths)
    assert any(path == "/api/demo/reset" and "POST" in methods for path, methods in paths)


def test_production_settings_fail_closed():
    production = replace(
        settings,
        app_env="production",
        auth_required=False,
        secret_key=None,
        database_url=None,
        redis_url=None,
        cors_allowed_origins=(),
        trust_proxy_headers=False,
        demo_mode_enabled=True,
        auto_create_schema=True,
    )
    with pytest.raises(RuntimeError, match="Production configuration validation failed"):
        validate_startup_settings(production)


def test_rate_limiter_returns_structured_429():
    limiter = RateLimiter()
    limiter.check(request(), "focused", UUID("00000000-0000-0000-0000-000000000001"), limit=1, window_seconds=60)
    with pytest.raises(HTTPException) as error:
        limiter.check(request(), "focused", UUID("00000000-0000-0000-0000-000000000001"), limit=1, window_seconds=60)
    assert error.value.status_code == 429
    assert error.value.detail["code"] == "rate_limited"


class FakeRedis:
    def __init__(self): self.values = {}
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values: return False
        self.values[key] = value; return True
    def eval(self, *_args): self.values.clear(); return 1


def test_schedule_lease_is_atomic_and_releasable():
    redis = FakeRedis()
    schedule = type("Schedule", (), {"organization_id": UUID("00000000-0000-0000-0000-000000000001"), "id": UUID("00000000-0000-0000-0000-000000000002")})()
    first = DistributedScheduleLease(redis, schedule, 30)
    second = DistributedScheduleLease(redis, schedule, 30)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True


def test_migration_runner_and_hardening_migration_exist():
    assert Path("scripts/migrate.py").exists()
    assert Path("db/migrations/001_baseline.sql").exists()
    migration = Path("db/migrations/002_activity_and_scheduler_hardening.sql").read_text(encoding="utf-8")
    assert "scheduler_locks" in migration
    assert "activity_events" in migration
