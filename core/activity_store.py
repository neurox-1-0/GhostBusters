"""Authoritative PostgreSQL activity persistence for configured deployments."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from core.redaction import redact_mapping


class PostgresActivityStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def append(self, event: dict[str, object], connection=None) -> None:
        metadata = redact_mapping(dict(event.get("metadata") or event.get("details") or {}))
        if connection is not None:
            connection.execute(
                """INSERT INTO activity_events
                (event_id, organization_id, actor_user_id, event_type, created_at,
                 details, actor_type, actor_display_name, actor_role_snapshot, category,
                 action, target_type, target_id, target_display_name, result, summary,
                 metadata, correlation_id, related_case_id, related_run_id)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb, %s, %s, %s)""",
                (
                    event["id"], event["organization_id"], event.get("actor_user_id"), event.get("event_type"),
                    event["created_at"], json.dumps(redact_mapping(dict(event.get("details") or {}))),
                    event.get("actor_type"), event.get("actor_display_name"), event.get("actor_role_snapshot"),
                    event.get("category"), event.get("action"), event.get("target_type"), event.get("target_id"),
                    event.get("target_display_name"), event.get("result"), event.get("summary"), json.dumps(metadata),
                    event.get("correlation_id"), event.get("related_case_id"), event.get("related_run_id"),
                ),
            )
            return
        with psycopg.connect(self.database_url) as connection:
            self.append(event, connection=connection)

    def list(self, organization_id: UUID) -> list[dict[str, object]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute("SELECT * FROM activity_events WHERE organization_id = %s ORDER BY created_at", (organization_id,)).fetchall()
        return [self._normalize(row) for row in rows]

    def get(self, organization_id: UUID, event_id: UUID) -> dict[str, object] | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute("SELECT * FROM activity_events WHERE organization_id = %s AND event_id = %s", (organization_id, event_id)).fetchone()
        return self._normalize(row) if row else None

    @staticmethod
    def _normalize(row: dict[str, object]) -> dict[str, object]:
        event = dict(row)
        event["id"] = event.pop("event_id", event.get("id"))
        if isinstance(event.get("metadata"), str): event["metadata"] = json.loads(event["metadata"])
        return event
