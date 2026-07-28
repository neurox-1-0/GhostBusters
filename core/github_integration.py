"""Organization-scoped GitHub context configuration; no token material is persisted."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID

from app.models import GitHubIntegrationConfig, GitHubIntegrationConfigRequest
from app.settings import Settings, settings
from core.postgres_json_store import PostgresJsonStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GitHubIntegrationStore:
    def __init__(self, configuration: Settings = settings) -> None:
        self.path = Path(configuration.github_integration_config_path)
        self.database = PostgresJsonStore(configuration.database_url, "github_integration") if configuration.database_url else None
        self._configs: dict[UUID, GitHubIntegrationConfig] = {}
        self._lock = RLock()
        self._load()

    def get(self, organization_id: UUID) -> GitHubIntegrationConfig:
        with self._lock:
            current = self._configs.get(organization_id)
            if current is None:
                now = utc_now()
                current = GitHubIntegrationConfig(organization_id=organization_id, created_at=now, updated_at=now)
                self._configs[organization_id] = current
            return current.model_copy(deep=True)

    def update(self, organization_id: UUID, request: GitHubIntegrationConfigRequest) -> GitHubIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            values = request.model_dump(exclude_none=True)
            if "allowed_repositories" in values:
                values["allowed_repositories"] = sorted({item.strip().lower() for item in values["allowed_repositories"] if item.strip()})
            updated = current.model_copy(update={**values, "updated_at": utc_now()})
            self._configs[organization_id] = updated
            self._persist()
            return updated.model_copy(deep=True)

    def mark_validation(self, organization_id: UUID, success: bool, failure: str | None = None) -> GitHubIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            updated = current.model_copy(update={"last_validated": utc_now(), "updated_at": utc_now(), "last_failure_summary": None if success else (failure or "GitHub validation failed safely.")})
            self._configs[organization_id] = updated
            self._persist()
            return updated.model_copy(deep=True)

    def mark_collection(self, organization_id: UUID, success: bool, failure: str | None = None) -> GitHubIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            updated = current.model_copy(update={"last_successful_collection": utc_now() if success else current.last_successful_collection, "updated_at": utc_now(), "last_failure_summary": None if success else (failure or "GitHub collection failed safely.")})
            self._configs[organization_id] = updated
            self._persist()
            return updated.model_copy(deep=True)

    def reset(self) -> None:
        self._configs.clear()
        if self.database: self.database.delete_all()
        else:
            try: self.path.unlink(missing_ok=True)
            except OSError: pass

    def _load(self) -> None:
        if self.database:
            for key, value in self.database.load().items():
                try: self._configs[key] = GitHubIntegrationConfig.model_validate(value)
                except Exception: continue
            return
        try: payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return
        for key, value in payload.items():
            try: self._configs[UUID(key)] = GitHubIntegrationConfig.model_validate(value)
            except Exception: continue

    def _persist(self) -> None:
        if self.database:
            self.database.replace({key: value.model_dump(mode="json") for key, value in self._configs.items()})
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps({str(key): value.model_dump(mode="json") for key, value in self._configs.items()}), encoding="utf-8")
            temp.replace(self.path)
        except OSError: pass


github_integration_store = GitHubIntegrationStore()
