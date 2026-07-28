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
            if request.expected_version is not None and request.expected_version != current.version:
                raise ValueError("GitHub integration settings are stale. Refresh and try again.")
            values = request.model_dump(exclude_none=True)
            values.pop("expected_version", None)
            if "allowed_repositories" in values:
                values["allowed_repositories"] = sorted({item.strip().lower() for item in values["allowed_repositories"] if item.strip()})
            updated = current.model_copy(update={**values, "updated_at": utc_now(), "version": current.version + 1})
            self._configs[organization_id] = updated
            self._persist()
            return updated.model_copy(deep=True)

    def find_by_installation(self, installation_id: int) -> tuple[UUID, GitHubIntegrationConfig] | None:
        with self._lock:
            for organization_id, config in self._configs.items():
                if config.installation_id == installation_id:
                    return organization_id, config.model_copy(deep=True)
        return None

    def disconnect(self, organization_id: UUID, expected_version: int | None = None) -> GitHubIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            if expected_version is not None and expected_version != current.version:
                raise ValueError("GitHub integration settings are stale. Refresh and try again.")
            updated = current.model_copy(update={"enabled": False, "installation_identity": None, "installation_id": None, "account_login": None, "account_type": None, "connected_repositories": [], "allowed_repositories": [], "updated_at": utc_now(), "version": current.version + 1, "last_failure_summary": "GitHub installation disconnected; historical records retained."})
            self._configs[organization_id] = updated; self._persist(); return updated.model_copy(deep=True)

    def update_installation(self, organization_id: UUID, *, installation_id: int | None, account_login: str | None, account_type: str | None, repositories: list[dict[str, object]], repository_selection: str = "selected", enabled: bool = True) -> GitHubIntegrationConfig:
        with self._lock:
            current = self.get(organization_id)
            safe_repositories = [{key: repo.get(key) for key in ("full_name", "private", "archived", "default_branch", "installation_access") if key in repo} for repo in repositories]
            updated = current.model_copy(update={"enabled": enabled, "installation_id": installation_id, "installation_identity": str(installation_id) if installation_id else None, "account_login": account_login, "account_type": account_type, "repository_selection": repository_selection if repository_selection in {"all", "selected"} else "selected", "connected_repositories": safe_repositories, "allowed_repositories": [str(repo.get("full_name")).lower() for repo in safe_repositories if repo.get("full_name")], "last_validated": utc_now(), "last_failure_summary": None, "updated_at": utc_now(), "version": current.version + 1})
            self._configs[organization_id] = updated; self._persist(); return updated.model_copy(deep=True)

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
