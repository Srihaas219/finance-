"""Append-only audit helper. Callers add the returned event within their own transaction."""
from __future__ import annotations

from ..core.ids import new_id
from ..models.audit_event import AuditEvent


def build_event(
    event_type: str,
    *,
    entity_type: str,
    entity_id: str | None = None,
    actor_id: str | None = None,
    actor_role: str = "system",
    loan_id: str | None = None,
    payload: dict | None = None,
    source_file_id: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=new_id(),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        actor_role=actor_role,
        loan_id=loan_id,
        payload=payload,
        source_file_id=source_file_id,
    )
