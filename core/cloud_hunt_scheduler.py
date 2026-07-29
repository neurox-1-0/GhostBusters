"""Safe organization-scoped Cloud Hunt scheduling and due-run coordination."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from redis import Redis
from redis.exceptions import RedisError

from app.models import CloudHuntRequest, CloudHuntSchedule, CloudHuntScheduleRequest
from app.settings import Settings, settings
from core.cloud_hunt_service import CloudHuntConflictError, CloudHuntService
from core.postgres_json_store import PostgresJsonStore
from core.aws_integration import aws_integration_store
from core.aws_onboarding import AWSOnboardingState
from integrations.cloud_adapters import RealAWSCloudAdapter
from integrations.cloud_registry import CloudProviderRegistry

def utc_now() -> datetime: return datetime.now(timezone.utc)

def _zone(name: str) -> ZoneInfo:
    try: return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc: raise ValueError("Unknown timezone.") from exc

def next_occurrence(schedule: CloudHuntSchedule, after: datetime) -> datetime:
    local = after.astimezone(_zone(schedule.timezone)).replace(second=0, microsecond=0)
    candidate = local.replace(hour=schedule.hour, minute=schedule.minute)
    if schedule.recurrence == "daily":
        if candidate <= local: candidate += timedelta(days=1)
    elif schedule.recurrence == "weekly":
        weekday = schedule.weekday if schedule.weekday is not None else local.weekday()
        days = (weekday - local.weekday()) % 7
        candidate = candidate + timedelta(days=days)
        if candidate <= local: candidate += timedelta(days=7)
    else:
        day = schedule.day_of_month or 1
        candidate = candidate.replace(day=day)
        if candidate <= local:
            month = candidate.month + 1
            year = candidate.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            candidate = candidate.replace(year=year, month=month, day=day)
    return candidate.astimezone(timezone.utc)

class ScheduleStore:
    def __init__(self, configuration: Settings = settings) -> None:
        self.path = Path(configuration.cloud_hunt_schedule_config_path)
        self.redis = Redis.from_url(configuration.redis_url, decode_responses=True) if configuration.redis_url else None
        self.database = PostgresJsonStore(configuration.database_url, "cloud_hunt_schedule") if configuration.database_url else None
        self.redis_key = "ghostbusters:cloud-hunt-schedules"
        self._items: dict[UUID, CloudHuntSchedule] = {}
        self._lock = RLock()
        self._load()

    def list(self, organization_id: UUID) -> list[CloudHuntSchedule]:
        with self._lock: return [item.model_copy(deep=True) for item in self._items.values() if item.organization_id == organization_id]
    def get(self, schedule_id: UUID, organization_id: UUID) -> CloudHuntSchedule:
        with self._lock:
            item = self._items.get(schedule_id)
            if item is None or item.organization_id != organization_id: raise KeyError("Schedule not found.")
            return item.model_copy(deep=True)
    def create(self, request: CloudHuntScheduleRequest, organization_id: UUID, user_id: UUID | None, display_name: str | None, now: datetime | None = None) -> CloudHuntSchedule:
        now = now or utc_now()
        values = request.model_dump(exclude={"expected_version"})
        schedule = CloudHuntSchedule(id=uuid4(), organization_id=organization_id, **values, next_run=now, created_by_user_id=user_id, created_by_display_name=display_name, created_at=now, updated_at=now)
        schedule.next_run = next_occurrence(schedule, now - timedelta(minutes=1))
        with self._lock: self._items[schedule.id] = schedule; self._persist()
        return schedule.model_copy(deep=True)
    def update(self, schedule_id: UUID, request: CloudHuntScheduleRequest, organization_id: UUID, now: datetime | None = None) -> CloudHuntSchedule:
        now = now or utc_now()
        with self._lock:
            current = self.get(schedule_id, organization_id)
            if request.expected_version is not None and request.expected_version != current.version: raise ValueError("Schedule version is stale. Refresh and try again.")
            if current.active_run_id: raise ValueError("Active schedule runs cannot be edited.")
            values = request.model_dump(exclude={"expected_version"})
            updated = current.model_copy(update={**values, "next_run": next_occurrence(current.model_copy(update=values), now - timedelta(minutes=1)), "updated_at": now, "version": current.version + 1})
            self._items[schedule_id] = updated; self._persist(); return updated.model_copy(deep=True)
    def toggle(self, schedule_id: UUID, enabled: bool, organization_id: UUID, expected_version: int | None = None) -> CloudHuntSchedule:
        with self._lock:
            current = self.get(schedule_id, organization_id)
            if expected_version is not None and expected_version != current.version: raise ValueError("Schedule version is stale. Refresh and try again.")
            updated = current.model_copy(update={"enabled": enabled, "updated_at": utc_now(), "version": current.version + 1})
            self._items[schedule_id] = updated; self._persist(); return updated.model_copy(deep=True)
    def claim(self, schedule_id: UUID, trigger_key: str, now: datetime, organization_id: UUID, force: bool = False) -> CloudHuntSchedule | None:
        with self._lock:
            current = self.get(schedule_id, organization_id)
            if not current.enabled or current.active_run_id or current.last_trigger_key == trigger_key or (current.next_run > now and not force): return None
            claimed = current.model_copy(update={"active_run_id": uuid4(), "last_trigger_key": trigger_key, "last_run": now, "updated_at": now, "version": current.version + 1})
            self._items[schedule_id] = claimed; self._persist(); return claimed.model_copy(deep=True)
    def finish(self, schedule_id: UUID, organization_id: UUID, success: bool, message: str | None, now: datetime) -> CloudHuntSchedule:
        with self._lock:
            current = self.get(schedule_id, organization_id)
            updated = current.model_copy(update={"active_run_id": None, "last_success": now if success else current.last_success, "last_failure": None if success else message, "next_run": next_occurrence(current, now), "updated_at": now, "version": current.version + 1})
            self._items[schedule_id] = updated; self._persist(); return updated.model_copy(deep=True)
    def delete(self, schedule_id: UUID, organization_id: UUID) -> None:
        with self._lock:
            current = self.get(schedule_id, organization_id)
            if current.active_run_id: raise ValueError("Active schedule runs cannot be deleted.")
            del self._items[schedule_id]; self._persist()
    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            if self.database: self.database.delete_all()
            else:
                try: self.path.unlink(missing_ok=True)
                except OSError: pass
            if self.redis is not None and not self.database:
                try: self.redis.delete(self.redis_key)
                except RedisError: pass
    def _load(self) -> None:
        if self.database:
            for key, value in self.database.load().items():
                try: self._items[key] = CloudHuntSchedule.model_validate(value)
                except Exception: continue
            return
        try:
            if self.redis is not None:
                payload = self.redis.hgetall(self.redis_key)
                for key, value in payload.items():
                    try: self._items[UUID(key)] = CloudHuntSchedule.model_validate(json.loads(value))
                    except Exception: continue
                return
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RedisError): return
        for key, value in payload.items():
            try: self._items[UUID(key)] = CloudHuntSchedule.model_validate(value)
            except Exception: continue
    def _persist(self) -> None:
        if self.database:
            self.database.replace({key: value.model_dump(mode="json") for key, value in self._items.items()})
            return
        try:
            if self.redis is not None:
                self.redis.delete(self.redis_key)
                if self._items:
                    self.redis.hset(self.redis_key, mapping={str(k): json.dumps(v.model_dump(mode="json")) for k, v in self._items.items()})
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps({str(k): v.model_dump(mode="json") for k, v in self._items.items()}), encoding="utf-8"); temp.replace(self.path)
        except OSError: pass

class CloudHuntScheduler:
    def __init__(self, service: CloudHuntService, store: ScheduleStore = None) -> None:
        self.service, self.store, self._lock = service, store or ScheduleStore(), RLock()
    def trigger(self, schedule: CloudHuntSchedule, now: datetime | None = None, force: bool = False):
        now = now or utc_now(); key = f"schedule:{schedule.id}:{schedule.next_run.isoformat()}" if not force else f"manual:{schedule.id}:{uuid4()}"
        lease = DistributedScheduleLease(self.store.redis, schedule, settings.scheduler_lock_ttl_seconds)
        if not lease.acquire(): return None
        claimed = self.store.claim(schedule.id, key, now, schedule.organization_id, force=force)
        if claimed is None:
            lease.release()
            return None
        try:
            request = CloudHuntRequest(provider_scope=claimed.provider_scope, inventory_source=claimed.inventory_source, trigger_source="scheduled_cloud_hunt")
            registry_override = None
            if claimed.inventory_source == "real_aws":
                config = aws_integration_store.get(claimed.organization_id)
                if not config.enabled or config.connection_status != "connected" or not config.role_arn:
                    raise CloudHuntConflictError("A verified AWS account connection is required for real AWS mode; scheduled hunt did not use fixtures.")
                regions = config.regions or list(settings.aws_allowed_regions)
                adapter = RealAWSCloudAdapter(
                    regions,
                    config.cloudwatch_lookback_days,
                    config.low_cpu_threshold,
                    role_arn=config.role_arn,
                    external_id=AWSOnboardingState(settings.secret_key, settings.aws_onboarding_state_ttl_seconds).external_id(config.organization_id),
                )
                if not adapter.validate()["connected"]: raise CloudHuntConflictError("AWS validation failed safely; scheduled hunt did not use fixtures.")
                registry_override = CloudProviderRegistry([adapter])
            hunt = self.service.start_hunt(request, claimed.organization_id, None, "System", registry_override, schedule_id=claimed.id, schedule_name=claimed.name)
            self.store.finish(claimed.id, claimed.organization_id, True, None, utc_now())
            return hunt
        except Exception as exc:
            self.store.finish(claimed.id, claimed.organization_id, False, "Scheduled Cloud Hunt failed safely.", utc_now())
            return None
        finally:
            lease.release()
    def run_due(self, organization_id: UUID, now: datetime | None = None) -> list:
        now = now or utc_now(); results = []
        for schedule in self.store.list(organization_id):
            if schedule.enabled and schedule.next_run <= now:
                hunt = self.trigger(schedule, now)
                if hunt is not None: results.append(hunt)
        return results


class DistributedScheduleLease:
    """Redis lease guarding one organization/schedule across workers."""
    def __init__(self, redis: Redis | None, schedule: CloudHuntSchedule, ttl_seconds: int) -> None:
        self.redis = redis
        self.key = f"ghostbusters:cloud-hunt-lock:{schedule.organization_id}:{schedule.id}"
        self.token = str(uuid4())
        self.ttl_seconds = ttl_seconds

    def acquire(self) -> bool:
        if self.redis is None:
            return True
        try: return bool(self.redis.set(self.key, self.token, nx=True, ex=self.ttl_seconds))
        except RedisError: return False

    def release(self) -> None:
        if self.redis is None: return
        try:
            self.redis.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, self.key, self.token)
        except RedisError: return

schedule_store = ScheduleStore()
