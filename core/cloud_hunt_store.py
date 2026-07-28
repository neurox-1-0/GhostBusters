"""Small PostgreSQL persistence boundary for Cloud Hunt records."""

from __future__ import annotations

import json
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.models import DEFAULT_DEVELOPMENT_ORGANIZATION_ID, CloudHuntRun, ReviewCase


class CloudHuntPersistence(Protocol):
    def save_hunt(self, hunt: CloudHuntRun) -> None: ...
    def save_case(self, case: ReviewCase) -> None: ...
    def list_hunts(self, organization_id: UUID | None = None) -> list[CloudHuntRun]: ...
    def list_cases(self, organization_id: UUID | None = None) -> list[ReviewCase]: ...
    def clear(self) -> None: ...
    def clear_organization_fixture_data(self, organization_id: UUID) -> None: ...


class PostgresCloudHuntPersistence:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.ensure_schema()

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS cloud_hunts (id UUID PRIMARY KEY, organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001', created_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL);
                CREATE TABLE IF NOT EXISTS cloud_review_cases (id UUID PRIMARY KEY, organization_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001', updated_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL);
                CREATE INDEX IF NOT EXISTS cloud_review_cases_status_idx ON cloud_review_cases ((payload->>'status'));
                CREATE INDEX IF NOT EXISTS cloud_hunts_org_idx ON cloud_hunts(organization_id, created_at);
                CREATE INDEX IF NOT EXISTS cloud_hunts_status_idx ON cloud_hunts ((payload->>'status'));
                CREATE INDEX IF NOT EXISTS cloud_hunts_provider_idx ON cloud_hunts ((payload->>'provider_scope'));
                CREATE INDEX IF NOT EXISTS cloud_hunts_started_by_idx ON cloud_hunts ((payload->>'started_by_user_id'), created_at);
                CREATE INDEX IF NOT EXISTS cloud_review_cases_org_idx ON cloud_review_cases(organization_id, updated_at);
            """)

    def save_hunt(self, hunt: CloudHuntRun) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO cloud_hunts (id, organization_id, created_at, payload) VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload", (hunt.id, hunt.organization_id, hunt.started_at, json.dumps(hunt.model_dump(mode="json"))))

    def save_case(self, case: ReviewCase) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO cloud_review_cases (id, organization_id, updated_at, payload) VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (id) DO UPDATE SET updated_at = EXCLUDED.updated_at, payload = EXCLUDED.payload", (case.id, case.organization_id, case.updated_at, json.dumps(case.model_dump(mode="json"))))

    def list_hunts(self, organization_id: UUID | None = None) -> list[CloudHuntRun]:
        scope = organization_id or DEFAULT_DEVELOPMENT_ORGANIZATION_ID
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM cloud_hunts WHERE organization_id = %s ORDER BY created_at", (scope,)).fetchall()
        return [CloudHuntRun.model_validate(row["payload"]) for row in rows]

    def list_cases(self, organization_id: UUID | None = None) -> list[ReviewCase]:
        scope = organization_id or DEFAULT_DEVELOPMENT_ORGANIZATION_ID
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM cloud_review_cases WHERE organization_id = %s ORDER BY updated_at", (scope,)).fetchall()
        return [ReviewCase.model_validate(row["payload"]) for row in rows]

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("TRUNCATE cloud_review_cases, cloud_hunts")

    def clear_organization_fixture_data(self, organization_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM cloud_review_cases WHERE organization_id = %s AND payload->>'data_source_mode' = 'Fixture-backed'", (organization_id,))
            connection.execute("DELETE FROM cloud_hunts WHERE organization_id = %s AND payload->>'data_source_mode' = 'Fixture-backed'", (organization_id,))
