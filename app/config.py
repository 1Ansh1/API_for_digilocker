"""Application configuration via Pydantic Settings.

All settings are loaded from environment variables with sensible defaults
for local development.  Each nested model uses its own ``env_prefix`` so
that, for example, ``DB_HOST`` maps to ``Settings.db.host``.

Usage::

    from app.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from dotenv import load_dotenv
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env relative to the config file path
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

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
    demo_mode: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    digilocker: DigiLockerSettings = DigiLockerSettings()
    security: SecuritySettings = SecuritySettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    oauth_session: OAuthSessionSettings = OAuthSessionSettings()
    observability: ObservabilitySettings = ObservabilitySettings()

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Validators ----------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _load_flat_env_variables(cls, data: Any) -> Any:
        import os
        if not isinstance(data, dict):
            data = {}
        
        def set_nested(section: str, field: str, env_vars: list[str], val_type=str):
            if section in data and isinstance(data[section], dict) and field in data[section]:
                return
            for var in env_vars:
                if val := os.environ.get(var):
                    if section not in data:
                        data[section] = {}
                    elif not isinstance(data[section], dict):
                        data[section] = data[section].model_dump() if hasattr(data[section], "model_dump") else dict(data[section])
                    
                    if val_type == int:
                        data[section][field] = int(val)
                    elif val_type == bool:
                        data[section][field] = val.lower() in ("true", "1", "yes")
                    else:
                        data[section][field] = val
                    break

        set_nested("db", "host", ["APP_DB__HOST", "POSTGRES_HOST"])
        set_nested("db", "port", ["APP_DB__PORT", "POSTGRES_PORT"], int)
        set_nested("db", "user", ["APP_DB__USER", "POSTGRES_USER"])
        set_nested("db", "password", ["APP_DB__PASSWORD", "POSTGRES_PASSWORD"])
        set_nested("db", "name", ["APP_DB__NAME", "POSTGRES_DB"])

        set_nested("redis", "host", ["APP_REDIS__HOST", "REDIS_HOST"])
        set_nested("redis", "port", ["APP_REDIS__PORT", "REDIS_PORT"], int)
        set_nested("redis", "password", ["APP_REDIS__PASSWORD", "REDIS_PASSWORD"])
        set_nested("redis", "db", ["APP_REDIS__DB", "REDIS_DB"], int)

        set_nested("digilocker", "client_id", ["APP_DIGILOCKER__CLIENT_ID", "DIGILOCKER_CLIENT_ID"])
        set_nested("digilocker", "client_secret", ["APP_DIGILOCKER__CLIENT_SECRET", "DIGILOCKER_CLIENT_SECRET"])
        set_nested("digilocker", "base_url", ["APP_DIGILOCKER__BASE_URL"])
        set_nested("digilocker", "redirect_uri", ["APP_DIGILOCKER__REDIRECT_URI", "DIGILOCKER_REDIRECT_URI"])

        set_nested("security", "jwt_secret_key", ["APP_SECURITY__JWT_SECRET_KEY", "JWT_SECRET_KEY"])
        set_nested("security", "jwt_algorithm", ["APP_SECURITY__JWT_ALGORITHM", "JWT_ALGORITHM"])

        set_nested("rate_limit", "user_max", ["APP_RATE_LIMIT__USER_MAX", "RATE_LIMIT_USER_MAX"], int)
        set_nested("rate_limit", "user_window_seconds", ["APP_RATE_LIMIT__USER_WINDOW_SECONDS", "RATE_LIMIT_USER_WINDOW_SECONDS"], int)
        set_nested("rate_limit", "ip_max", ["APP_RATE_LIMIT__IP_MAX", "RATE_LIMIT_IP_MAX"], int)
        set_nested("rate_limit", "ip_window_seconds", ["APP_RATE_LIMIT__IP_WINDOW_SECONDS", "RATE_LIMIT_IP_WINDOW_SECONDS"], int)

        set_nested("oauth_session", "session_ttl_seconds", ["APP_OAUTH_SESSION__SESSION_TTL_SECONDS", "OAUTH_SESSION_TTL_SECONDS"], int)
        set_nested("oauth_session", "active_lock_ttl_seconds", ["APP_OAUTH_SESSION__ACTIVE_LOCK_TTL_SECONDS", "ACTIVE_LOCK_TTL_SECONDS"], int)
        set_nested("oauth_session", "result_ttl_seconds", ["APP_OAUTH_SESSION__RESULT_TTL_SECONDS", "RESULT_TTL_SECONDS"], int)

        set_nested("observability", "log_level", ["APP_OBSERVABILITY__LOG_LEVEL", "LOG_LEVEL"])
        set_nested("observability", "enable_metrics", ["APP_OBSERVABILITY__ENABLE_METRICS", "METRICS_ENABLED"], bool)

        if "environment" not in data and (env_val := os.environ.get("ENVIRONMENT")):
            data["environment"] = env_val
        if "debug" not in data and (debug_val := os.environ.get("DEBUG")):
            data["debug"] = debug_val.lower() in ("true", "1", "yes")
        if "demo_mode" not in data and (demo_val := os.environ.get("APP_DEMO_MODE") or os.environ.get("DEMO_MODE")):
            data["demo_mode"] = demo_val.lower() in ("true", "1", "yes")

        return data

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
