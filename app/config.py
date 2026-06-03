"""Application configuration via Pydantic Settings.

All settings are loaded from environment variables with sensible defaults
for local development.  Each nested model uses its own ``env_prefix`` so
that, for example, ``DB_HOST`` maps to ``Settings.db.host``.

Usage::

    from app.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from typing import Self

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings

__all__ = ["Settings", "get_settings"]


# ---------------------------------------------------------------------------
# Nested settings models
# ---------------------------------------------------------------------------


class DatabaseSettings(BaseModel):
    """PostgreSQL connection parameters."""

    host: str = "localhost"
    port: int = 5432
    user: str = "digilocker"
    password: str = "digilocker"
    name: str = "digilocker_dev"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10

    @property
    def async_url(self) -> str:
        """Build an async PostgreSQL DSN (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseModel):
    """Redis connection parameters."""

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    max_connections: int = 10

    @property
    def url(self) -> str:
        """Build a ``redis://`` connection string."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class DigiLockerSettings(BaseModel):
    """DigiLocker API provider credentials and endpoints."""

    client_id: str = ""
    client_secret: str = ""
    base_url: str = "https://api.digitallocker.gov.in"
    redirect_uri: str = "http://localhost:8000/api/v1/callback"
    hmac_key: str = ""


class SecuritySettings(BaseModel):
    """JWT / authentication settings."""

    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    allowed_origins: list[str] = ["http://localhost:3000"]


class RateLimitSettings(BaseModel):
    """Rate-limiting thresholds (sliding window)."""

    user_max: int = 5
    user_window_seconds: int = 3600
    ip_max: int = 100
    ip_window_seconds: int = 60


class OAuthSessionSettings(BaseModel):
    """TTLs for OAuth flow artefacts stored in Redis."""

    session_ttl_seconds: int = 600
    active_lock_ttl_seconds: int = 900
    result_ttl_seconds: int = 300


class ObservabilitySettings(BaseModel):
    """Logging, tracing and metrics knobs."""

    log_level: str = "INFO"
    log_json: bool = False
    otlp_endpoint: str = ""
    enable_metrics: bool = False


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Top-level application settings.

    Compose every sub-section as a nested model so that each concern is
    individually addressable while the whole configuration stays in one
    validated object.
    """

    app_name: str = "digilocker-verification-api"
    environment: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    digilocker: DigiLockerSettings = DigiLockerSettings()
    security: SecuritySettings = SecuritySettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    oauth_session: OAuthSessionSettings = OAuthSessionSettings()
    observability: ObservabilitySettings = ObservabilitySettings()

    model_config = {
        "env_prefix": "APP_",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
    }

    # -- Validators ----------------------------------------------------------

    @model_validator(mode="after")
    def _reject_mock_keys_in_production(self) -> Self:
        """Prevent the default JWT secret from leaking into production."""
        if (
            self.environment == "production"
            and self.security.jwt_secret_key == "CHANGE-ME-IN-PRODUCTION"
        ):
            raise ValueError(
                "A real JWT secret key must be set when ENVIRONMENT=production. "
                "Do not use the default development placeholder."
            )
        return self


# ---------------------------------------------------------------------------
# Cached accessor
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Call this from dependency-injection or startup code rather than
    constructing ``Settings()`` directly so that environment variables are
    parsed only once per process.
    """
    return Settings()
