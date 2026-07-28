"""Apply ordered GhostBusters migrations without mutating schema at app startup."""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "db" / "migrations"
SCHEMA = ROOT / "db" / "schema.sql"


def migrate(database_url: str, fresh_local: bool = False) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.stem in applied:
                continue
            if migration.stem == "001_baseline" and fresh_local:
                exists = connection.execute("SELECT to_regclass('public.organizations')").fetchone()[0]
                if exists is None:
                    connection.execute(SCHEMA.read_text(encoding="utf-8"))
            else:
                sql = migration.read_text(encoding="utf-8")
                if sql.strip():
                    connection.execute(sql)
            connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (migration.stem,))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--fresh-local", action="store_true", help="Apply db/schema.sql only when the target database has no organizations table.")
    args = parser.parse_args()
    migrate(args.database_url, args.fresh_local)
