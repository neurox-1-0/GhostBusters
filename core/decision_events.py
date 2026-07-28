"""Append-only human decision event ledger and idempotency helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
import psycopg
from psycopg.rows import dict_row

from app.auth import Principal, utc_now
from app.settings import settings


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    id: UUID
    organization_id: UUID
    case_id: UUID
    case_type: str
    actor_snapshot: dict[str, Any]
    action: str
    reason: str | None
    previous_state: dict[str, Any]
    resulting_state: dict[str, Any]
    related_event_id: UUID | None
    correlation_id: str
    idempotency_key: str
    request_fingerprint: str
    response_snapshot: dict[str, Any]
    created_at: Any


class DecisionEventStore:
    """In-memory append-only event store used by the API and tests."""

    def __init__(self) -> None:
        self._events: list[DecisionEvent] = []
        self._idempotency: dict[tuple[UUID, str], DecisionEvent] = {}
        self._lock = RLock()
        self.database_url = settings.database_url

    def reset(self) -> None:
        if self.database_url:
            with psycopg.connect(self.database_url) as connection:
                connection.execute("DELETE FROM human_decision_events")
            return
        with self._lock:
            self._events.clear()
            self._idempotency.clear()

    def replay(self, organization_id: UUID, key: str, fingerprint: str) -> dict[str, Any] | None:
        if self.database_url:
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                existing = connection.execute("SELECT request_fingerprint, response_snapshot FROM human_decision_events WHERE organization_id=%s AND idempotency_key=%s", (organization_id, key)).fetchone()
            if existing is None: return None
            if existing["request_fingerprint"] != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for a different request.")
            response = dict(existing["response_snapshot"]); response["idempotent_replay"] = True; return response
        with self._lock:
            existing = self._idempotency.get((organization_id, key))
            if existing is None:
                return None
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for a different request.")
            response = dict(existing.response_snapshot)
            response["idempotent_replay"] = True
            return response

    def append(
        self,
        *,
        organization_id: UUID,
        case_id: UUID,
        case_type: str,
        principal: Principal,
        action: str,
        reason: str | None,
        previous_state: dict[str, Any],
        resulting_state: dict[str, Any],
        related_event_id: UUID | None,
        correlation_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_snapshot: dict[str, Any],
    ) -> DecisionEvent:
        with self._lock:
            key = (organization_id, idempotency_key)
            if key in self._idempotency:
                existing = self._idempotency[key]
                if existing.request_fingerprint != request_fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency key was already used for a different request.")
                return existing
            event = DecisionEvent(
                id=uuid4(),
                organization_id=organization_id,
                case_id=case_id,
                case_type=case_type,
                actor_snapshot=actor_snapshot(principal),
                action=action,
                reason=reason,
                previous_state=previous_state,
                resulting_state=resulting_state,
                related_event_id=related_event_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                response_snapshot=dict(response_snapshot),
                created_at=utc_now(),
            )
            self._events.append(event)
            self._idempotency[key] = event
            if self.database_url:
                with psycopg.connect(self.database_url) as connection:
                    connection.execute("""INSERT INTO human_decision_events
                        (id, organization_id, case_id, case_type, actor_snapshot, action, reason,
                         previous_state, resulting_state, related_event_id, correlation_id,
                         idempotency_key, request_fingerprint, response_snapshot, created_at)
                        VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s)""",
                        (event.id, event.organization_id, event.case_id, event.case_type,
                         json.dumps(event.actor_snapshot), event.action, event.reason,
                         json.dumps(event.previous_state), json.dumps(event.resulting_state),
                         event.related_event_id, event.correlation_id, event.idempotency_key,
                         event.request_fingerprint, json.dumps(event.response_snapshot), event.created_at))
            return event

    def list(self, organization_id: UUID | None = None, case_id: UUID | None = None) -> list[DecisionEvent]:
        if self.database_url:
            query = "SELECT * FROM human_decision_events WHERE TRUE"
            params: list[Any] = []
            if organization_id is not None: query += " AND organization_id=%s"; params.append(organization_id)
            if case_id is not None: query += " AND case_id=%s"; params.append(case_id)
            query += " ORDER BY created_at"
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                rows = connection.execute(query, params).fetchall()
            return [self._from_row(row) for row in rows]
        with self._lock:
            return [
                event
                for event in self._events
                if (organization_id is None or event.organization_id == organization_id)
                and (case_id is None or event.case_id == case_id)
            ]

    def latest_for_case(self, organization_id: UUID, case_id: UUID, action: str | None = None) -> DecisionEvent | None:
        if self.database_url:
            matches = self.list(organization_id, case_id)
            if action is not None: matches = [event for event in matches if event.action == action]
            return matches[-1] if matches else None
        with self._lock:
            matches = [
                event
                for event in self._events
                if event.organization_id == organization_id and event.case_id == case_id and (action is None or event.action == action)
            ]
            return matches[-1] if matches else None

    @staticmethod
    def _from_row(row: dict[str, Any]) -> DecisionEvent:
        return DecisionEvent(id=row["id"], organization_id=row["organization_id"], case_id=row["case_id"], case_type=row["case_type"], actor_snapshot=row["actor_snapshot"], action=row["action"], reason=row["reason"], previous_state=row["previous_state"], resulting_state=row["resulting_state"], related_event_id=row["related_event_id"], correlation_id=row["correlation_id"], idempotency_key=row["idempotency_key"], request_fingerprint=row["request_fingerprint"], response_snapshot=row["response_snapshot"], created_at=row["created_at"])


def actor_snapshot(principal: Principal) -> dict[str, Any]:
    return {
        "user_id": str(principal.user.id) if principal.user else None,
        "email": principal.user.email if principal.user else None,
        "display_name": principal.reviewer_name,
        "membership_id": str(principal.membership.id),
        "membership_role": principal.membership.role.value,
        "organization_id": str(principal.organization_id),
        "permissions": sorted(principal.permissions),
        "authenticated": principal.authenticated,
    }


def normalized_fingerprint(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


decision_event_store = DecisionEventStore()
