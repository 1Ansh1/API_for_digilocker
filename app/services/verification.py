"""Verification orchestration service.

Coordinates the end-to-end DigiLocker verification flow by delegating
to the OAuth, token, and repository layers.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.errors.exceptions import VerificationAlreadyInProgressError
from app.infrastructure.redis import RedisKeyBuilder
from app.models.audit_event import AuditEventType
from app.models.verification import VerificationStatus
from app.security.pkce import generate_code_challenge, generate_code_verifier
from app.security.rate_limit import check_rate_limits
from app.security.state import generate_nonce, generate_state

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from app.repositories.audit import AuditRepository
    from app.repositories.verification import VerificationRepository
    from app.services.oauth import OAuthService

__all__ = ["VerificationService"]


class VerificationService:
    """Orchestrates the DigiLocker verification flow.

    Responsibilities:
        - Initiate a new verification (create record, build auth URL)
        - Handle the OAuth callback (exchange code, validate token)
        - Expose verification status to callers
    """

    def __init__(
        self,
        *,
        db_session: AsyncSession,
        redis: Redis,
        settings: Settings,
        oauth_service: OAuthService,
        audit_repository: AuditRepository,
        verification_repository: VerificationRepository,
    ) -> None:
        self.db_session = db_session
        self.redis = redis
        self.settings = settings
        self.oauth_service = oauth_service
        self.audit_repository = audit_repository
        self.verification_repository = verification_repository

    async def initiate_verification(
        self,
        *,
        user_id: str,
        client_redirect_uri: str,
        ip_address: str | None = None,
        correlation_id: str,
    ) -> tuple[str, str]:
        """Initiate a new DigiLocker identity verification.

        Performs rate limiting checks, locks concurrent flows, saves session in Redis,
        logs appropriate audits, and builds the auth URL.

        Parameters
        ----------
        user_id:
            External identifier of the user initiating verification.
        client_redirect_uri:
            URL to redirect the user to after the verification flow completes.
        ip_address:
            IP address of the client request (for rate limiting).
        correlation_id:
            Trace ID of the request for auditing.

        Returns
        -------
        tuple[str, str]
            Tuple containing: (verification_id_str, authorization_url)
        """
        # 1. Enforce rate limits (IP & User) via sliding window
        await check_rate_limits(
            redis=self.redis,
            settings=self.settings,
            user_id=user_id,
            ip_address=ip_address,
        )

        # 2. Prevent concurrent verification flows for the same user
        lock_key = RedisKeyBuilder.active_lock_key(user_id)
        existing_lock = await self.redis.get(lock_key)
        if existing_lock:
            raise VerificationAlreadyInProgressError(
                f"A verification flow is already active for user: {user_id}"
            )

        # 3. Create Verification record in database (default status is INITIATED)
        verification = await self.verification_repository.create(user_id)
        verification_id_str = str(verification.id)

        # 4. Acquire the lock by setting the active lock key in Redis
        await self.redis.set(
            lock_key,
            verification_id_str,
            ex=self.settings.oauth_session.active_lock_ttl_seconds,
        )

        # 5. Generate authorization credentials
        state = generate_state()
        nonce = generate_nonce()
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # 6. Store OAuth session in Redis keyed by state
        session_key = RedisKeyBuilder.session_key(state)
        session_payload = {
            "verification_id": verification_id_str,
            "user_id": user_id,
            "code_verifier": code_verifier,
            "nonce": nonce,
            "redirect_uri": client_redirect_uri,
        }
        await self.redis.set(
            session_key,
            json.dumps(session_payload),
            ex=self.settings.oauth_session.session_ttl_seconds,
        )

        # 7. Write VERIFICATION_INITIATED audit event
        await self.audit_repository.create(
            verification_id=verification.id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.VERIFICATION_INITIATED,
            status=VerificationStatus.INITIATED,
            metadata={
                "client_redirect_uri": client_redirect_uri,
                "state": state,  # Storing generated state/nonce/challenge (no verifier)
                "nonce": nonce,
                "code_challenge": code_challenge,
            },
        )

        # 8. Construct provider authorization redirect URL
        authorization_url = self.oauth_service.build_authorization_url(
            state=state,
            code_challenge=code_challenge,
            nonce=nonce,
        )

        # 9. Transition DB status to REDIRECTED and write USER_REDIRECTED audit event
        await self.verification_repository.update_status(
            verification_id=verification.id,
            status=VerificationStatus.REDIRECTED,
        )
        await self.audit_repository.create(
            verification_id=verification.id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.USER_REDIRECTED,
            status=VerificationStatus.REDIRECTED,
            metadata={
                "authorization_url": authorization_url,
            },
        )

        return verification_id_str, authorization_url

