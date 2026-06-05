"""FastAPI endpoint to handle the DigiLocker OAuth callback redirection."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse

from app.api.deps import get_verification_service
from app.errors.exceptions import DigiLockerError
from app.models import VerificationResult
from app.schemas.callback import CallbackQueryParams
from app.schemas.verification import VerificationStatusResponse
from app.services.verification import VerificationService

__all__ = ["router"]

router = APIRouter()


@router.get(
    "",
    response_model=VerificationStatusResponse,
    summary="Handle DigiLocker OAuth redirection callback",
    description=(
        "Receives authorization code and CSRF state from DigiLocker, "
        "validates credentials, exchanges code for tokens, verifies signature, "
        "and completes the identity verification."
    ),
)
async def oauth_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    params: CallbackQueryParams = Depends(),
    verification_service: VerificationService = Depends(get_verification_service),
) -> VerificationStatusResponse | RedirectResponse:
    """OAuth 2.0 callback endpoint redirected from DigiLocker."""
    # Extract client IP address for audit log
    ip_address = request.headers.get("x-forwarded-for")
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    # Retrieve correlation ID
    correlation_id = getattr(request.state, "correlation_id", "unknown-correlation-id")

    # Pre-fetch verification_id from Redis session for browser error redirection if state exists
    verification_id = None
    if params.state:
        import json

        from app.infrastructure.redis import RedisKeyBuilder
        try:
            session_key = RedisKeyBuilder.session_key(params.state)
            session_data_str = await verification_service.redis.get(session_key)
            if session_data_str:
                session_data = json.loads(session_data_str)
                verification_id = session_data.get("verification_id")
        except Exception:
            pass

    is_browser = "text/html" in request.headers.get("accept", "")

    try:
        # Delegate validation flow to VerificationService
        verification = await verification_service.handle_callback(
            code=params.code,
            state=params.state,
            error=params.error,
            error_description=params.error_description,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
    except DigiLockerError as e:
        # Commit the transaction so that FAILED status and audit events are persisted!
        try:
            await verification_service.db_session.commit()
        except Exception:
            pass

        if is_browser:
            if verification_id:
                return RedirectResponse(
                    url=f"/ui/verification/result/{verification_id}",
                    status_code=303,
                )
            else:
                import urllib.parse
                err_msg = urllib.parse.quote(str(e))
                return RedirectResponse(
                    url=f"/ui/verification/start?error={err_msg}",
                    status_code=303,
                )

        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=e.http_status,
            content={
                "error": {
                    "code": e.error_code.value,
                    "message": e.message,
                    "retryable": e.retryable,
                    "retry_after_seconds": e.retry_after_seconds,
                    "correlation_id": correlation_id,
                }
            }
        )
    except Exception as e:
        if is_browser:
            if verification_id:
                return RedirectResponse(
                    url=f"/ui/verification/result/{verification_id}",
                    status_code=303,
                )
            else:
                import urllib.parse
                err_msg = urllib.parse.quote(str(e))
                return RedirectResponse(
                    url=f"/ui/verification/start?error={err_msg}",
                    status_code=303,
                )
        raise

    # Queue pruning task for expired PII data
    background_tasks.add_task(verification_service.prune_expired_results)

    # Fetch demographic details for response
    name, dob, gender = None, None, None
    if verification.status == "VERIFIED":
        result = await verification_service.get_verification_result(
            verification_id=verification.id,
            user_id=verification.user_id,
        )
        if isinstance(result, VerificationResult):
            name = result.name
            dob = result.dob
            gender = result.gender

    if is_browser:
        return RedirectResponse(
            url=f"/ui/verification/result/{verification.id}",
            status_code=303,
        )

    return VerificationStatusResponse(
        id=str(verification.id),
        status=verification.status,
        verified_at=verification.completed_at,
        proof_hash=verification.proof_hash,
        name=name,
        dob=dob,
        gender=gender,
    )
