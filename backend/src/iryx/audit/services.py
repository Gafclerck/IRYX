"""Synchronous append-only audit trail service (Story 8.5)."""

import hashlib
import json
import math
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.audit.models import AuditEvent

_SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "authorization",
        "jwt",
        "credential",
    }
)


def _canonical_json(value: Any) -> str:
    """Serialize deterministically for hashing purposes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_audit_payload_hash(
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    details: Mapping[str, Any] | None,
) -> str:
    """Return the lowercase SHA-256 hex digest of the canonical action payload."""
    payload = {
        "action": str(action),
        "target_type": str(target_type),
        "target_id": str(target_id) if target_id is not None else None,
        "details": dict(details) if details else {},
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest().lower()


def _sanitize(value: Any) -> Any:
    """Strip secret keys recursively and produce a deterministic JSON-safe structure."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _SECRET_KEYS:
                continue
            sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, (set, frozenset)):
        items = [_sanitize(item) for item in value]
        return sorted(items, key=_canonical_json)
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if isinstance(value, Enum):
        return _sanitize(value.value)
    return str(value)


def sanitize_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strip secret-bearing keys recursively; never persist them."""
    sanitized = _sanitize(details or {})
    return sanitized if isinstance(sanitized, dict) else {}


class AuditService:
    """Synchronous append-only write into the ``audit_events`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        action: str,
        actor_id: uuid.UUID | None,
        case_id: uuid.UUID | None,
        target_type: str,
        target_id: uuid.UUID,
        details: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Add an audit event and flush it within the caller's transaction."""
        safe_details = sanitize_details(details)
        if actor_id is None:
            safe_details = {**safe_details, "actor": "system"}
        event = AuditEvent(
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload_hash=compute_audit_payload_hash(action, target_type, target_id, safe_details),
            details=safe_details,
            case_id=case_id,
            actor_id=actor_id,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def list_events(
        self,
        case_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Return the immutable audit trail of one case, oldest first."""
        return list(
            self.db.scalars(
                select(AuditEvent)
                .where(AuditEvent.case_id == case_id)
                .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
                .limit(limit)
                .offset(offset)
            )
        )

    def count_events(self, case_id: uuid.UUID) -> int:
        """Return the total number of audit events recorded for one case."""
        count = self.db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.case_id == case_id)
        )
        return int(count or 0)
