"""AuditEvent ORM model and event type enum."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditEventType(StrEnum):
    """All auditable event types in the verification flow."""

    VERIFICATION_INITIATED = "VERIFICATION_INITIATED"
    USER_REDIRECTED = "USER_REDIRECTED"
    CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
    TOKEN_EXCHANGE_STARTED = "TOKEN_EXCHANGE_STARTED"
    TOKEN_EXCHANGE_COMPLETED = "TOKEN_EXCHANGE_COMPLETED"
    TOKEN_EXCHANGE_FAILED = "TOKEN_EXCHANGE_FAILED"
    ID_TOKEN_VALIDATED = "ID_TOKEN_VALIDATED"
    ID_TOKEN_VALIDATION_FAILED = "ID_TOKEN_VALIDATION_FAILED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_EXPIRED = "VERIFICATION_EXPIRED"


class AuditEvent(Base):
    """Append-only audit log entry tied to a verification flow."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    verification_id: Mapped[UUID] = mapped_column(
        ForeignKey("verifications.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    # Relationships
    verification: Mapped["Verification"] = relationship(
        "Verification",
        back_populates="audit_events",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} type={self.event_type} "
            f"verification_id={self.verification_id}>"
        )


# Resolve forward reference
from app.models.verification import Verification  # noqa: E402, F811
