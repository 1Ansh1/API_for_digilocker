"""DigiLocker OAuth callback schemas."""

from pydantic import BaseModel


class CallbackQueryParams(BaseModel):
    """Query parameters received on the DigiLocker OAuth callback."""

    code: str | None = None
    state: str
    error: str | None = None
    error_description: str | None = None

