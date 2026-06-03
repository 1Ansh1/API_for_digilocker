"""Verification ORM model and status enum."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class VerificationStatus(StrEnum):
    """Possible states of a DigiLocker verification flow."""

    INITIATED = "INITIATED"
    REDIRECTED = "REDIRECTED"
    CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
    TOKEN_EXCHANGED = "TOKEN_EXCHANGED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class Verification(TimestampMixin, Base):
    """Tracks a single DigiLocker identity-verification lifecycle."""

    __tablename__ = "verifications"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=VerificationStatus.INITIATED,
    )
    initiated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    digilocker_id_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    proof_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="verification",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_verifications_user_id_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Verification id={self.id} user_id={self.user_id} status={self.status}>"


# Resolve forward reference
from app.models.audit_event import AuditEvent  # noqa: E402, F811
