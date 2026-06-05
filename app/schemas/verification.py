"""Verification request and response schemas."""

from datetime import datetime

from pydantic import BaseModel


class VerificationInitiateRequest(BaseModel):
    """Request body to start a new DigiLocker verification flow."""

    redirect_uri: str


class VerificationInitiateResponse(BaseModel):
    """Response returned after initiating a verification flow."""

    verification_id: str
    authorization_url: str


class VerificationStatusResponse(BaseModel):
    """Response containing the current status of a verification."""

    id: str
    status: str
    verified_at: datetime | None = None
    proof_hash: str | None = None
    name: str | None = None
    dob: str | None = None
    gender: str | None = None

