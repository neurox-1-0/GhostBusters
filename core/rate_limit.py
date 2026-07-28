"""Small Redis-first rate limiter with an explicit local development fallback."""

from __future__ import annotations

import time
from threading import RLock
from uuid import UUID

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.settings import settings


class RateLimiter:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
        self.local: dict[str, tuple[int, float]] = {}
        self.lock = RLock()

    def check(self, request: Request, bucket: str, user_id: UUID | None = None, limit: int = 30, window_seconds: int = 60, organization_id: UUID | None = None) -> None:
        ip = request.client.host if request.client else "unknown"
        scope = f"org:{organization_id}:" if organization_id else ""
        identity = f"{scope}user:{user_id}" if user_id else f"{scope}ip:{ip}"
        key = f"ghostbusters:rate:{bucket}:{identity}"
        if self.redis is not None:
            try:
                count = int(self.redis.incr(key))
                if count == 1: self.redis.expire(key, window_seconds)
                if count > limit: self._raise(bucket, window_seconds)
                return
            except RedisError:
                if settings.app_env == "production":
                    raise HTTPException(status_code=503, detail={"code": "rate_limiter_unavailable", "message": "Rate limiting dependency is unavailable."})
        now = time.monotonic()
        with self.lock:
            count, started = self.local.get(key, (0, now))
            if now - started >= window_seconds: count, started = 0, now
            count += 1; self.local[key] = (count, started)
            if count > limit: self._raise(bucket, max(1, int(window_seconds - (now - started))))

    @staticmethod
    def _raise(bucket: str, retry_after: int) -> None:
        raise HTTPException(status_code=429, headers={"Retry-After": str(retry_after)}, detail={"code": "rate_limited", "message": f"Too many {bucket} requests. Try again later."})


rate_limiter = RateLimiter()
