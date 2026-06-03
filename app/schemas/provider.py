"""Schemas for the DigiLocker provider integrations."""

from pydantic import BaseModel, Field


class DigiLockerTokenResponse(BaseModel):
    """Token response from DigiLocker OAuth token exchange.

    Contains the access token, ID token, and token lifetime details.
    """

    access_token: str = Field(..., description="Access token to call user APIs")
    id_token: str = Field(..., description="OIDC ID token (JWT) containing demographic data")
    expires_in: int = Field(..., description="Token lifespan in seconds")
    token_type: str = Field("Bearer", description="OAuth token type")
    scope: str | None = Field(None, description="Authorized scopes")


class DigiLockerProfile(BaseModel):
    """User profile and demographic data retrieved from DigiLocker.

    This maps directly to the profile properties that are used by the system
    to verify a user's identity.
    """

    digilockerid: str = Field(..., description="Unique DigiLocker ID of the user")
    name: str = Field(..., description="User's full name as registered in DigiLocker")
    dob: str = Field(..., description="Date of birth in DD-MM-YYYY or YYYY-MM-DD format")
    gender: str = Field(..., description="Gender (M/F/T)")
    eaadhaar: str | None = Field(
        None,
        description="Aadhaar linking status/metadata or masked Aadhaar number",
    )

