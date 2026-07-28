"""Small durable JSONB stores for tenant-scoped configuration snapshots.

These stores are deliberately boring: PostgreSQL is authoritative whenever a
database URL is configured, while file snapshots remain a local/demo fallback.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class PostgresJsonStore:
    def __init__(self, database_url: str, kind: str) -> None:
        self.database_url = database_url
        self.kind = kind

    def load(self) -> dict[UUID, dict[str, Any]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT organization_id, payload FROM tenant_state WHERE kind = %s",
                (self.kind,),
            ).fetchall()
        return {UUID(str(row["organization_id"])): row["payload"] for row in rows}

    def put(self, organization_id: UUID, payload: dict[str, Any]) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """INSERT INTO tenant_state (kind, organization_id, payload, updated_at)
                   VALUES (%s, %s, %s::jsonb, NOW())
                   ON CONFLICT (kind, organization_id) DO UPDATE
                   SET payload = EXCLUDED.payload, updated_at = NOW()""",
                (self.kind, organization_id, json.dumps(payload, default=str)),
            )

    def replace(self, values: dict[UUID, dict[str, Any]]) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("DELETE FROM tenant_state WHERE kind = %s", (self.kind,))
            for organization_id, payload in values.items():
                connection.execute(
                    "INSERT INTO tenant_state (kind, organization_id, payload) VALUES (%s, %s, %s::jsonb)",
                    (self.kind, organization_id, json.dumps(payload, default=str)),
                )

    def delete_all(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("DELETE FROM tenant_state WHERE kind = %s", (self.kind,))
