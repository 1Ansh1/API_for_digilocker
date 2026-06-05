"""Unit tests for the template UI routes and HTML rendering."""

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import status

from app.api.deps import get_verification_service
from app.main import create_app
from app.models.verification import Verification, VerificationStatus
from app.services.verification import VerificationService


@pytest.mark.asyncio
async def test_ui_home_endpoint() -> None:
    """Verify that the home page renders and returns 200 OK with HTML content."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    assert "DigiLocker Identity Verification" in response.text
    assert "Start Verification Demo" in response.text


@pytest.mark.asyncio
async def test_ui_verification_start_endpoint() -> None:
    """Verify that the start page renders and returns 200 OK."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ui/verification/start")

    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    assert "Initiate Identity Verification" in response.text
    assert 'name="user_id"' in response.text


@pytest.mark.asyncio
async def test_ui_initiate_success() -> None:
    """Verify that form submission initiates verification and redirects to Auth URL."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.initiate_verification = AsyncMock(
        return_value=("mocked-uuid-12345", "http://mock-identity-provider/auth")
    )
    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/ui/verification/initiate",
            data={
                "user_id": "test-user",
                "redirect_uri": "http://localhost:8000/api/v1/callback",
            },
        )

    # Must be 303 Redirect to authorization URL
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "http://mock-identity-provider/auth"
    mock_service.initiate_verification.assert_called_once()


@pytest.mark.asyncio
async def test_ui_initiate_failure_shows_error() -> None:
    """Verify that initiation failure renders start page with error message."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.initiate_verification = AsyncMock(
        side_effect=ValueError("Simulated rate limit / validation error")
    )
    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/ui/verification/initiate",
            data={
                "user_id": "test-user",
                "redirect_uri": "http://localhost:8000/api/v1/callback",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert "Simulated rate limit / validation error" in response.text


@pytest.mark.asyncio
async def test_ui_architecture_endpoint() -> None:
    """Verify that the architecture page renders and returns 200 OK."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ui/architecture")

    assert response.status_code == status.HTTP_200_OK
    assert "Architecture & Sequence Flow" in response.text
    assert "[Browser]" in response.text


@pytest.mark.asyncio
async def test_ui_mock_provider_endpoint() -> None:
    """Verify that the mock provider consent page renders and returns 200 OK."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/mock-provider/public/oauth2/1/authorize?state=mystate&nonce=mynonce"
        )

    assert response.status_code == status.HTTP_200_OK
    assert "DigiLocker Mock Identity Provider" in response.text
    assert "mystate" in response.text
    assert "mynonce" in response.text
    assert "SUCCESS_CODE" in response.text


@pytest.mark.asyncio
async def test_api_callback_redirects_for_browser() -> None:
    """Verify that a callback request with Accept: text/html redirects to the HTML result page."""
    app = create_app()
    mock_service = AsyncMock(spec=VerificationService)
    v_id = uuid.uuid4()
    mock_verification = Verification(
        id=v_id,
        user_id="user-123",
        status=VerificationStatus.VERIFIED,
    )
    mock_service.handle_callback = AsyncMock(return_value=mock_verification)
    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Browser request with Accept: text/html
        response = await client.get(
            "/api/v1/callback?code=SUCCESS_CODE&state=mystate",
            headers={"accept": "text/html,application/xhtml+xml"}
        )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == f"/ui/verification/result/{v_id}"


@pytest.mark.asyncio
async def test_api_callback_returns_json_for_api_client() -> None:
    """Verify that a callback request with application/json returns standard JSON."""
    app = create_app()
    mock_service = AsyncMock(spec=VerificationService)
    v_id = uuid.uuid4()
    mock_verification = Verification(
        id=v_id,
        user_id="user-123",
        status=VerificationStatus.VERIFIED,
    )
    mock_service.handle_callback = AsyncMock(return_value=mock_verification)
    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # API request with Accept: application/json
        response = await client.get(
            "/api/v1/callback?code=SUCCESS_CODE&state=mystate",
            headers={"accept": "application/json"}
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(v_id)
    assert data["status"] == "VERIFIED"
