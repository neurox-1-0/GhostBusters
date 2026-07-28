from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import CloudHuntScheduleRequest
from app.settings import Settings
from core.cloud_hunt_scheduler import CloudHuntScheduler, ScheduleStore, next_occurrence


def _settings(tmp_path: Path) -> Settings:
    return Settings(cloud_hunt_schedule_config_path=tmp_path / "schedules.json")


def test_daily_weekly_monthly_recurrence_and_timezone(tmp_path):
    store = ScheduleStore(_settings(tmp_path))
    org = uuid4(); now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    daily = store.create(CloudHuntScheduleRequest(name="daily", recurrence="daily", hour=9, timezone="Asia/Colombo"), org, None, "System", now)
    assert daily.next_run > now
    weekly = store.create(CloudHuntScheduleRequest(name="weekly", recurrence="weekly", weekday=0, hour=10, timezone="UTC"), org, None, "System", now)
    assert weekly.next_run.weekday() == 0
    monthly = store.create(CloudHuntScheduleRequest(name="monthly", recurrence="monthly", day_of_month=1, hour=2), org, None, "System", now)
    assert monthly.next_run.month == 8


def test_claim_prevents_duplicate_and_restart_recovers(tmp_path):
    configuration = _settings(tmp_path); store = ScheduleStore(configuration); org = uuid4()
    schedule = store.create(CloudHuntScheduleRequest(name="locked"), org, None, "System", datetime(2026, 1, 1, tzinfo=timezone.utc))
    due = schedule.next_run
    assert store.claim(schedule.id, "same-key", due, org) is not None
    assert store.claim(schedule.id, "same-key", due, org) is None
    recovered = ScheduleStore(configuration).get(schedule.id, org)
    assert recovered.active_run_id is not None


def test_scheduler_links_run_and_advances_schedule(tmp_path):
    class FakeService:
        def start_hunt(self, request, organization_id, user_id, display_name, registry_override=None, schedule_id=None, schedule_name=None):
            return type("Hunt", (), {"id": uuid4(), "schedule_id": schedule_id, "schedule_name": schedule_name})()

    store = ScheduleStore(_settings(tmp_path)); org = uuid4(); schedule = store.create(CloudHuntScheduleRequest(name="nightly"), org, None, "System", datetime(2026, 1, 1, tzinfo=timezone.utc))
    hunt = CloudHuntScheduler(FakeService(), store).trigger(schedule, schedule.next_run)
    assert hunt.schedule_id == schedule.id and hunt.schedule_name == "nightly"
    assert store.get(schedule.id, org).last_success is not None
