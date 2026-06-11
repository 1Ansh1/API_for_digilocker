"""UI Routes and Page Handlers for Jinja2 templates.

Renders Home, Start, Result, Audit Timeline, Metrics Dashboard,
and the Mock Identity Provider login/consent simulation page.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from prometheus_client import REGISTRY
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_verification_service
from app.config import get_settings
from app.models.verification import Verification, VerificationStatus
from app.models.verification_result import VerificationResult
from app.services.verification import VerificationService

logger = logging.getLogger(__name__)

__all__ = ["ui_router"]

# Mount templates directory
templates = Jinja2Templates(directory="app/templates")

ui_router = APIRouter(tags=["UI"])


@ui_router.get("/", response_class=HTMLResponse)
async def ui_home(request: Request) -> HTMLResponse:
    """Render the Home/Landing page."""
    return templates.TemplateResponse(
        request,
        "home.html",
        context={"active_page": "home"},
    )


@ui_router.get("/ui/verification/start", response_class=HTMLResponse)
async def ui_verification_start(request: Request) -> HTMLResponse:
    """Render the Verification initiation form."""
    return templates.TemplateResponse(
        request,
        "start.html",
        context={"active_page": "start"},
    )


@ui_router.post("/ui/verification/initiate", response_model=None)
async def ui_initiate_verification(
    request: Request,
    user_id: str = Form(...),
    redirect_uri: str = Form(...),
    verification_service: VerificationService = Depends(get_verification_service),
) -> RedirectResponse | HTMLResponse:
    """Initiate a verification session and redirect the user to DigiLocker authorization URL."""
    # Extract request IP address
    ip_address = request.headers.get("x-forwarded-for")
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    # Correlation ID
    correlation_id = getattr(request.state, "correlation_id", "ui-correlation-id")

    try:
        verification_id, authorization_url = await verification_service.initiate_verification(
            user_id=user_id,
            client_redirect_uri=redirect_uri,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
        logger.info(
            "UI verification initiated: user_id=%s, verification_id=%s, url=%s",
            user_id,
            verification_id,
            authorization_url,
        )

        # Determine if base_url needs override for local testing.
        # If settings APP_DIGILOCKER__BASE_URL points to our local app,
        # build_authorization_url will automatically construct the local mock url.
        return RedirectResponse(url=authorization_url, status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        logger.exception("Failed to initiate verification via UI form")
        # Render page with error message
        return templates.TemplateResponse(
            request,
            "start.html",
            context={
                "active_page": "start",
                "error_message": str(e),
            },
        )


@ui_router.get("/ui/verification/result/{verification_id}", response_class=HTMLResponse)
async def ui_verification_result(
    request: Request,
    verification_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Render the verification status and details report page."""
    try:
        v_uuid = UUID(verification_id)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "start.html",
            context={
                "active_page": "start",
                "error_message": f"Invalid verification ID format: '{verification_id}'",
            },
        )

    # Fetch verification
    stmt = select(Verification).where(Verification.id == v_uuid)
    res = await db.execute(stmt)
    verification = res.scalar_one_or_none()

    if not verification:
        return templates.TemplateResponse(
            request,
            "start.html",
            context={
                "active_page": "start",
                "error_message": f"Verification session '{verification_id}' not found.",
            },
        )

    # Fetch result (demographics / PII)
    result_stmt = select(VerificationResult).where(VerificationResult.verification_id == v_uuid)
    result_res = await db.execute(result_stmt)
    result = result_res.scalar_one_or_none()

    retained_until = None
    settings = get_settings()
    if result:
        import datetime
        retention_seconds = 15 if settings.demo_mode else settings.oauth_session.result_ttl_seconds
        retained_until = result.created_at + datetime.timedelta(seconds=retention_seconds)

    return templates.TemplateResponse(
        request,
        "result.html",
        context={
            "active_page": "start",
            "verification": verification,
            "result": result,
            "demo_mode": settings.demo_mode,
            "retained_until": retained_until,
        },
    )


@ui_router.get("/ui/audit-timeline", response_class=HTMLResponse)
async def ui_audit_timeline(
    request: Request,
    verification_id: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Render the audit timeline registry list or a single session's details timeline."""
    if verification_id:
        try:
            v_uuid = UUID(verification_id)
            stmt = select(Verification).where(Verification.id == v_uuid)
            res = await db.execute(stmt)
            selected_verification = res.scalar_one_or_none()
        except ValueError:
            selected_verification = None

        return templates.TemplateResponse(
            request,
            "timeline.html",
            context={
                "active_page": "timeline",
                "selected_verification": selected_verification,
            },
        )

    # List recent verifications
    stmt = select(Verification).order_by(Verification.initiated_at.desc()).limit(20)
    res = await db.execute(stmt)
    verifications = res.scalars().all()

    return templates.TemplateResponse(
        request,
        "timeline.html",
        context={
            "active_page": "timeline",
            "verifications": verifications,
        },
    )


@ui_router.get("/ui/dashboard", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Render the Metrics Dashboard with aggregated DB states and Prometheus values."""
    # Compute DB Aggregates
    total_attempts = await db.scalar(select(func.count(Verification.id))) or 0
    success_count = await db.scalar(
        select(func.count(Verification.id)).where(
            Verification.status == VerificationStatus.VERIFIED
        )
    ) or 0
    failure_count = await db.scalar(
        select(func.count(Verification.id)).where(Verification.status == VerificationStatus.FAILED)
    ) or 0
    active_count = await db.scalar(
        select(func.count(Verification.id)).where(
            Verification.status.notin_([VerificationStatus.VERIFIED, VerificationStatus.FAILED])
        )
    ) or 0

    success_rate = (success_count / total_attempts * 100) if total_attempts > 0 else 0.0

    # Top errors
    stmt = (
        select(Verification.error_code, func.count(Verification.id))
        .where(Verification.status == VerificationStatus.FAILED)
        .group_by(Verification.error_code)
    )
    res = await db.execute(stmt)
    errors_distribution = {row[0] or "UNKNOWN": row[1] for row in res.all()}

    # Fetch Prometheus telemetry from memory registry
    rate_limit_hits = 0
    jwks_hits = 0
    jwks_misses = 0
    active_sessions = 0
    for m in REGISTRY.collect():
        if m.name == "digilocker_rate_limit_hits_total":
            rate_limit_hits = int(sum(sample.value for sample in m.samples))
        elif m.name == "digilocker_jwks_cache_hits_total":
            jwks_hits = int(sum(sample.value for sample in m.samples))
        elif m.name == "digilocker_jwks_cache_misses_total":
            jwks_misses = int(sum(sample.value for sample in m.samples))
        elif m.name == "digilocker_active_sessions":
            active_sessions = int(sum(sample.value for sample in m.samples))

    metrics_context = {
        "total_attempts": total_attempts,
        "success_count": success_count,
        "failure_count": failure_count,
        "active_count": active_count,
        "success_rate": success_rate,
        "errors_distribution": errors_distribution,
        "rate_limit_hits": rate_limit_hits,
        "jwks_hits": jwks_hits,
        "jwks_misses": jwks_misses,
        "active_sessions": active_sessions,
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={
            "active_page": "dashboard",
            "metrics": metrics_context,
        },
    )


@ui_router.get("/ui/architecture", response_class=HTMLResponse)
async def ui_architecture(request: Request) -> HTMLResponse:
    """Render the Architecture diagram page."""
    return templates.TemplateResponse(
        request,
        "architecture.html",
        context={"active_page": "architecture"},
    )


@ui_router.get("/mock-provider/public/oauth2/1/authorize", response_class=HTMLResponse)
async def ui_mock_provider_authorize(
    request: Request,
    response_type: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    state: str | None = None,
    nonce: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> HTMLResponse:
    """Render the simulated DigiLocker login & user consent screen.

    Redirects the user back to the redirect_uri callback endpoint with simulated codes.
    """
    settings = get_settings()
    # Fallback to config redirect URI if not provided
    callback_target = redirect_uri or settings.digilocker.redirect_uri

    return templates.TemplateResponse(
        request,
        "mock_provider.html",
        context={
            "active_page": "",  # No active page highlight for IdP screen
            "state": state,
            "nonce": nonce,
            "client_id": client_id,
            "redirect_uri": callback_target,
        },
    )
