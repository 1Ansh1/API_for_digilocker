"""Append-only data access layer for audit events."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent, AuditEventType


class AuditRepository:
    """Append-only data access layer for audit events.

    Audit events are immutable once written; only ``create`` is exposed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        verification_id: UUID,
        user_id: str,
        correlation_id: str,
        event_type: AuditEventType,
        status: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append a new audit event.

        Args:
            verification_id: FK to the parent verification record.
            user_id: External identifier of the acting user.
            correlation_id: Request correlation / trace ID.
            event_type: Category of the audited action.
            status: Optional status snapshot at the time of the event.
            error_code: Optional error code if the event records a failure.
            metadata: Optional JSON-serialisable context data.

        Returns:
            The persisted AuditEvent instance.
        """
        event = AuditEvent(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=event_type,
            status=status,
            error_code=error_code,
            metadata_=metadata or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event
