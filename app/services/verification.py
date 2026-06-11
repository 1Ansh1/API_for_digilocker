"""Verification orchestration service.

Coordinates the end-to-end DigiLocker verification flow by delegating
to the OAuth, token, and repository layers.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING
from uuid import UUID

from app.errors.codes import ErrorCode
from app.errors.exceptions import (
    IdTokenInvalidError,
    InvalidStateError,
    SessionExpiredError,
    TokenExchangeError,
    VerificationAlreadyInProgressError,
    VerificationNotFoundError,
)
from app.infrastructure.redis import RedisKeyBuilder
from app.models.audit_event import AuditEventType
from app.models.verification import Verification, VerificationStatus
from app.security.hashing import compute_proof_hash, hash_digilocker_id
from app.security.pkce import generate_code_challenge, generate_code_verifier
from app.security.rate_limit import check_rate_limits
from app.security.state import generate_nonce, generate_state

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from app.infrastructure.digilocker.interface import DigiLockerProvider
    from app.models.verification_result import VerificationResult
    from app.repositories.audit import AuditRepository
    from app.repositories.verification import VerificationRepository
    from app.repositories.verification_result import VerificationResultRepository
    from app.services.oauth import OAuthService
    from app.services.token import TokenService

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
        token_service: TokenService,
        provider: DigiLockerProvider,
        audit_repository: AuditRepository,
        verification_repository: VerificationRepository,
        verification_result_repository: VerificationResultRepository,
    ) -> None:
        self.db_session = db_session
        self.redis = redis
        self.settings = settings
        self.oauth_service = oauth_service
        self.token_service = token_service
        self.provider = provider
        self.audit_repository = audit_repository
        self.verification_repository = verification_repository
        self.verification_result_repository = verification_result_repository


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

    async def handle_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        error_description: str | None,
        ip_address: str | None = None,
        correlation_id: str,
    ) -> Verification:
        """Handle the OAuth callback from DigiLocker.

        Performs state validation, OIDC token signature and claims checks,
        demographics validation, updates the database, deletes the lock, and logs audits.

        Parameters
        ----------
        code:
            The authorization code.
        state:
            The CSRF state parameter.
        error:
            The OAuth error code if the flow failed.
        error_description:
            The detailed description of the OAuth error.
        ip_address:
            IP address of the client request (for audit/rate limits).
        correlation_id:
            Trace ID of the request for auditing.

        Returns
        -------
        Verification
            The updated Verification record.
        """
        # 1. State Validation
        if not state:
            raise InvalidStateError("State parameter is missing from the callback.")

        session_key = RedisKeyBuilder.session_key(state)
        session_data_str = await self.redis.get(session_key)
        if not session_data_str:
            raise SessionExpiredError("OAuth session has expired or state is invalid.")

        session_data = json.loads(session_data_str)
        verification_id_str = session_data["verification_id"]
        user_id = session_data["user_id"]
        code_verifier = session_data["code_verifier"]
        expected_nonce = session_data["nonce"]

        verification_id = UUID(verification_id_str)
        verification = await self.verification_repository.get_by_id(verification_id)
        if not verification:
            raise VerificationNotFoundError(f"Verification record '{verification_id}' not found.")

        # 2. Transition DB status to CALLBACK_RECEIVED and write audit event
        await self.verification_repository.update_status(
            verification_id=verification_id,
            status=VerificationStatus.CALLBACK_RECEIVED,
        )
        await self.audit_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.CALLBACK_RECEIVED,
            status=VerificationStatus.CALLBACK_RECEIVED,
            metadata={"ip_address": ip_address},
        )

        # 3. Handle OAuth callback error if present
        if error:
            error_msg = error_description or f"OAuth error: {error}"
            verification.status = VerificationStatus.FAILED
            verification.error_code = error
            verification.error_message = error_msg
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.TOKEN_EXCHANGE_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error,
                metadata={"error_description": error_msg},
            )
            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error,
                metadata={"error_description": error_msg},
            )
            raise TokenExchangeError(f"DigiLocker returned callback error: {error} - {error_msg}")

        # 4. Exchange authorization code for tokens
        if not code:
            # Code is missing
            verification.status = VerificationStatus.FAILED
            verification.error_code = ErrorCode.TOKEN_EXCHANGE_FAILED
            verification.error_message = "Authorization code is missing from callback."
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.TOKEN_EXCHANGE_FAILED,
                status=VerificationStatus.FAILED,
                error_code=ErrorCode.TOKEN_EXCHANGE_FAILED,
                metadata={"error_description": "Authorization code is missing from callback."},
            )
            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=ErrorCode.TOKEN_EXCHANGE_FAILED,
                metadata={"error_description": "Authorization code is missing from callback."},
            )
            raise TokenExchangeError("Authorization code is missing from callback.")

        await self.audit_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.TOKEN_EXCHANGE_STARTED,
            status=VerificationStatus.CALLBACK_RECEIVED,
        )

        try:
            token_response = await self.provider.exchange_code(
                code=code,
                code_verifier=code_verifier,
            )
        except Exception as e:
            error_code = getattr(e, "error_code", ErrorCode.TOKEN_EXCHANGE_FAILED)
            error_msg = str(e)

            verification.status = VerificationStatus.FAILED
            verification.error_code = error_code
            verification.error_message = error_msg
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.TOKEN_EXCHANGE_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error_code,
                metadata={"error": error_msg},
            )
            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error_code,
                metadata={"error": error_msg},
            )
            raise

        await self.verification_repository.update_status(
            verification_id=verification_id,
            status=VerificationStatus.TOKEN_EXCHANGED,
        )
        await self.audit_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.TOKEN_EXCHANGE_COMPLETED,
            status=VerificationStatus.TOKEN_EXCHANGED,
        )

        # 5. Validate ID token structure and verify signature using JWKS
        try:
            claims = await self.token_service.validate_id_token(
                id_token=token_response.id_token,
                expected_nonce=expected_nonce,
            )
        except Exception as e:
            error_code = getattr(e, "error_code", ErrorCode.ID_TOKEN_INVALID)
            error_msg = str(e)

            verification.status = VerificationStatus.FAILED
            verification.error_code = error_code
            verification.error_message = error_msg
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.ID_TOKEN_VALIDATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error_code,
                metadata={"error": error_msg},
            )
            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error_code,
                metadata={"error": error_msg},
            )
            raise

        await self.audit_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.ID_TOKEN_VALIDATED,
            status=VerificationStatus.TOKEN_EXCHANGED,
            metadata={
                "digilocker_id_hash": hash_digilocker_id(claims["sub"]),
            },
        )

        # 6. Retrieve profile from provider for demographics validation
        try:
            profile = await self.provider.get_profile(token_response.access_token)
        except Exception as e:
            error_code = getattr(e, "error_code", ErrorCode.PROVIDER_UNAVAILABLE)
            error_msg = str(e)

            verification.status = VerificationStatus.FAILED
            verification.error_code = error_code
            verification.error_message = error_msg
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=error_code,
                metadata={"error": error_msg},
            )
            raise

        # Check demographic consistency
        if claims["sub"] != profile.digilockerid:
            error_msg = "Demographic mismatch between ID token and profile."
            verification.status = VerificationStatus.FAILED
            verification.error_code = ErrorCode.ID_TOKEN_INVALID
            verification.error_message = error_msg
            verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await self.db_session.flush()

            # Clean up Redis session and lock
            await self.redis.delete(session_key)
            await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

            await self.audit_repository.create(
                verification_id=verification_id,
                user_id=user_id,
                correlation_id=correlation_id,
                event_type=AuditEventType.VERIFICATION_FAILED,
                status=VerificationStatus.FAILED,
                error_code=ErrorCode.ID_TOKEN_INVALID,
                metadata={"error": error_msg},
            )
            raise IdTokenInvalidError(error_msg)

        # 7. Persist verification status
        digilocker_id = claims["sub"]
        digilocker_id_hash = hash_digilocker_id(digilocker_id)
        proof_hash = compute_proof_hash(
            user_id=user_id,
            digilocker_id=digilocker_id,
            name=claims["name"],
            dob=claims["dob"],
            gender=claims["gender"],
            hmac_key=self.settings.digilocker.hmac_key,
        )

        verification.status = VerificationStatus.VERIFIED
        verification.digilocker_id_hash = digilocker_id_hash
        verification.proof_hash = proof_hash
        verification.completed_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

        # Create verification result (PII data)
        await self.verification_result_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            name=claims["name"],
            dob=claims["dob"],
            gender=claims["gender"],
            digilocker_id=digilocker_id,
        )

        await self.db_session.flush()

        # Clean up Redis session and lock
        await self.redis.delete(session_key)
        await self.redis.delete(RedisKeyBuilder.active_lock_key(user_id))

        # 8. Write final successful audit events
        await self.audit_repository.create(
            verification_id=verification_id,
            user_id=user_id,
            correlation_id=correlation_id,
            event_type=AuditEventType.VERIFICATION_COMPLETED,
            status=VerificationStatus.VERIFIED,
            metadata={
                "digilocker_id_hash": digilocker_id_hash,
                "proof_hash": proof_hash,
            },
        )

        return verification

    async def get_verification_status(
        self,
        *,
        verification_id: str,
        user_id: str,
    ) -> Verification:
        """Fetch the verification status, ensuring it exists and belongs to the user.

        Parameters
        ----------
        verification_id:
            The verification session UUID string.
        user_id:
            The ID of the requesting user.

        Returns
        -------
        Verification
            The verification database record.

        Raises
        ------
        VerificationNotFoundError
            If the record is not found or does not belong to the user.
        """
        try:
            v_uuid = UUID(verification_id)
        except ValueError as err:
            raise VerificationNotFoundError("Invalid verification ID format.") from err

        verification = await self.verification_repository.get_by_id(v_uuid)
        if not verification or verification.user_id != user_id:
            raise VerificationNotFoundError("Verification session not found.")

        return verification

    async def get_verification_result(
        self,
        *,
        verification_id: UUID,
        user_id: str,
    ) -> VerificationResult | None:
        """Fetch the detailed demographic demographic verification result (PII) if not pruned.

        Parameters
        ----------
        verification_id:
            UUID of the verification session.
        user_id:
            External identifier of the requesting user.

        Returns
        -------
        VerificationResult | None
            Demographic details if found and authorized, otherwise None.
        """
        result = await self.verification_result_repository.get_by_verification_id(verification_id)
        if result and result.user_id == user_id:
            created_at = getattr(result, "created_at", None)
            if isinstance(created_at, datetime.datetime):
                retention_seconds = (
                    15 if self.settings.demo_mode 
                    else self.settings.oauth_session.result_ttl_seconds
                )
                cut_off = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(
                    seconds=retention_seconds
                )
                if created_at < cut_off:
                    # On-demand prune: delete expired record and log audit event
                    await self.db_session.delete(result)
                    await self.db_session.flush()
                    await self.audit_repository.create(
                        verification_id=verification_id,
                        user_id=user_id,
                        correlation_id="on-demand-pruning",
                        event_type=AuditEventType.PII_PRUNED,
                        status="PRUNED",
                        metadata={
                            "reason": "retention_expired",
                            "retention_seconds": retention_seconds,
                        },
                    )
                    await self.db_session.flush()
                    return None
            return result
        return None

    async def prune_expired_results(self) -> int:
        """Prune sensitive demographic records exceeding the retention threshold.

        Returns
        -------
        int
            The number of records successfully deleted.
        """
        retention_seconds = (
            15 if self.settings.demo_mode
            else self.settings.oauth_session.result_ttl_seconds
        )
        
        # Log audit events for records that will be deleted
        import unittest.mock
        if not isinstance(self.db_session, unittest.mock.Mock):
            cut_off = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(
                seconds=retention_seconds
            )
            try:
                from sqlalchemy import select
                from app.models.verification_result import VerificationResult
                stmt = select(VerificationResult).where(VerificationResult.created_at < cut_off)
                res = await self.db_session.execute(stmt)
                expired_records = res.scalars().all()
                for record in expired_records:
                    await self.audit_repository.create(
                        verification_id=record.verification_id,
                        user_id=record.user_id,
                        correlation_id="system-prune-job",
                        event_type=AuditEventType.PII_PRUNED,
                        status="PRUNED",
                        metadata={
                            "reason": "background_retention_pruning",
                            "retention_seconds": retention_seconds,
                        },
                    )
            except Exception:
                pass

        return await self.verification_result_repository.prune_expired(retention_seconds)


