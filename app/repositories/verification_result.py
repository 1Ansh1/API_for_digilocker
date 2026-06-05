"""Data access layer for verification results."""

import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.verification_result import VerificationResult


class VerificationResultRepository:
    """Data access layer for sensitive verification results.

    Handles CRUD operations and data-retention pruning for the
    ``verification_results`` table.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        verification_id: UUID,
        user_id: str,
        name: str,
        dob: str,
        gender: str,
        digilocker_id: str,
    ) -> VerificationResult:
        """Persist a new verification result (PII data).

        Args:
            verification_id: UUID of the parent verification session.
            user_id: External identifier of the user.
            name: The verified user's name.
            dob: The verified user's date of birth.
            gender: The verified user's gender.
            digilocker_id: The verified user's unique DigiLocker ID.

        Returns:
            The created VerificationResult instance.
        """
        result = VerificationResult(
            verification_id=verification_id,
            user_id=user_id,
            name=name,
            dob=dob,
            gender=gender,
            digilocker_id=digilocker_id,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def get_by_verification_id(self, verification_id: UUID) -> VerificationResult | None:
        """Fetch the verification result details for a specific session.

        Args:
            verification_id: UUID of the verification session.

        Returns:
            The VerificationResult if found, otherwise ``None``.
        """
        stmt = select(VerificationResult).where(
            VerificationResult.verification_id == verification_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def prune_expired(self, retention_seconds: int) -> int:
        """Prune verification results older than the retention threshold.

        Args:
            retention_seconds: Cut-off age in seconds for record pruning.

        Returns:
            Number of rows deleted.
        """
        cut_off = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(
            seconds=retention_seconds
        )
        stmt = delete(VerificationResult).where(VerificationResult.created_at < cut_off)
        result = await self._session.execute(stmt)
        return cast(int, getattr(result, "rowcount", 0))
