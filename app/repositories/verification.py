"""Data access layer for verification records."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.verification import Verification, VerificationStatus


class VerificationRepository:
    """Data access layer for verification records.

    Provides CRUD operations for the ``verifications`` table using
    async SQLAlchemy sessions.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str) -> Verification:
        """Persist a new verification record.

        Args:
            user_id: External identifier of the user initiating verification.

        Returns:
            The newly created Verification instance.
        """
        verification = Verification(user_id=user_id)
        self._session.add(verification)
        await self._session.flush()
        return verification

    async def get_by_id(self, verification_id: UUID) -> Verification | None:
        """Fetch a verification by its primary key.

        Args:
            verification_id: UUID of the verification record.

        Returns:
            The Verification if found, otherwise ``None``.
        """
        return await self._session.get(Verification, verification_id)

    async def update_status(
        self,
        verification_id: UUID,
        status: VerificationStatus,
    ) -> Verification | None:
        """Transition a verification to a new status.

        Args:
            verification_id: UUID of the verification record.
            status: Target status to transition to.

        Returns:
            The updated Verification if found, otherwise ``None``.
        """
        verification = await self.get_by_id(verification_id)
        if verification is None:
            return None
        verification.status = status
        await self._session.flush()
        return verification
