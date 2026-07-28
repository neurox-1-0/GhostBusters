"""Organization-scoped, non-secret AWS connection configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID

from app.models import AWSIntegrationConfig, AWSIntegrationConfigRequest
from app.settings import Settings, settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AWSIntegrationStore:
    def __init__(self, configuration: Settings = settings) -> None:
        self.path = configuration.aws_integration_config_path
        self._configs: dict[UUID, AWSIntegrationConfig] = {}
        self._lock = RLock()
        self._load()

    def get(self, organization_id: UUID) -> AWSIntegrationConfig:
        with self._lock:
            config = self._configs.get(organization_id)
            if config is None:
                now = utc_now()
                config = AWSIntegrationConfig(organization_id=organization_id, regions=[], created_at=now, updated_at=now)
                self._configs[organization_id] = config
            return config.model_copy(deep=True)

    def update(self, organization_id: UUID, request: AWSIntegrationConfigRequest) -> AWSIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            values = request.model_dump(exclude_none=True)
            if "regions" in values:
                values["regions"] = sorted(set(values["regions"]))
            updated = current.model_copy(update={**values, "updated_at": utc_now()})
            self._configs[organization_id] = updated
            self._persist()
            return updated.model_copy(deep=True)

    def mark_collection(self, organization_id: UUID, success: bool, summary: str | None = None) -> AWSIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            update = {"updated_at": utc_now(), "last_successful_collection": utc_now() if success else current.last_successful_collection, "last_failure_summary": None if success else (summary or "AWS collection failed safely.")}
            self._configs[organization_id] = current.model_copy(update=update)
            self._persist()
            return self._configs[organization_id].model_copy(deep=True)

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, value in payload.items():
            try:
                self._configs[UUID(key)] = AWSIntegrationConfig.model_validate(value)
            except Exception:
                continue

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({str(key): value.model_dump(mode="json") for key, value in self._configs.items()}), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass


aws_integration_store = AWSIntegrationStore()
