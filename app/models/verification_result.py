"""VerificationResult ORM model for storing sensitive verified demographics."""

from datetime import datetime
import uuid
from uuid import UUID

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class VerificationResult(Base):
    """Stores sensitive verified demographic details (PII) with strict retention."""

    __tablename__ = "verification_results"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    verification_id: Mapped[UUID] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    dob: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    gender: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    digilocker_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    # Relationship back to the session
    verification: Mapped["Verification"] = relationship(
        "Verification",
        back_populates="verification_result",
    )

    def __repr__(self) -> str:
        return f"<VerificationResult id={self.id} verification_id={self.verification_id}>"


# Resolve forward reference
from app.models.verification import Verification  # noqa: E402
