# DigiLocker Verification API

A production-grade FastAPI service for verifying user identity through DigiLocker's OAuth 2.0 / OpenID Connect flow with PKCE. Follows a **verify-don't-store** privacy-first approach — identity is verified and hashed, never persisted as PII.

## Architecture

- **FastAPI** with async lifespan management
- **MySQL** (aiomysql) for verification records and append-only audit trail
- **Redis** for OAuth session state, distributed locks, rate limiting, and JWKS caching
- **Pydantic Settings** for typed, validated configuration
- **structlog** for structured JSON logging with PII redaction
- **Prometheus** metrics for observability
- **OpenTelemetry** tracing support
- **Alembic** for database migrations

## Project Structure

```
app/
├── api/            # Routers, dependency injection
│   ├── deps.py     # DI: db session, redis, http client
│   └── v1/         # Versioned endpoints (health, verification, callback)
├── config.py       # Pydantic Settings (env-based)
├── errors/         # Error codes, exceptions, handlers
├── infrastructure/ # Database, Redis, HTTP client setup
├── main.py         # App factory + lifespan
├── middleware/      # Request ID, auth, rate limiting, logging
├── models/         # SQLAlchemy ORM models
├── observability/  # Logging, metrics, tracing
├── repositories/   # Data access layer
├── schemas/        # Pydantic request/response models
├── security/       # PKCE, state/nonce, hashing, JWT utils
└── services/       # Business logic (verification, OAuth, token, JWKS)

tests/
├── conftest.py     # Shared fixtures
├── unit/           # Pure logic tests
├── integration/    # Tests with real DB/Redis (testcontainers)
└── mock_provider/  # Mock DigiLocker OAuth provider

migrations/         # Alembic database migrations
docker/             # Dockerfile, docker-compose.yml
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for MySQL + Redis)

### Setup

```bash
# Clone and enter the project
cd Digi_API

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env

# Start MySQL and Redis
docker compose -f docker/docker-compose.yml up -d

# Run database migrations
alembic upgrade head

# Start the dev server
uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

### Verify

```bash
# Liveness probe
curl http://localhost:8000/health/live

# API docs
open http://localhost:8000/docs
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=html

# Lint
ruff check .

# Type check
mypy app
```

## Configuration

All configuration is via environment variables. See [`.env.example`](.env.example) for the full list.

Key variables:

| Variable | Description | Default |
|---|---|---|
| `APP__ENVIRONMENT` | `development`, `staging`, `production` | `development` |
| `APP__DB__HOST` | MySQL host | `localhost` |
| `APP__REDIS__HOST` | Redis host | `localhost` |
| `APP__SECURITY__JWT_SECRET_KEY` | JWT signing key | `CHANGE-ME-IN-PRODUCTION` |
| `APP__DIGILOCKER__CLIENT_ID` | DigiLocker API client ID | — |

> **Security**: The app will refuse to start in `production` mode with the default JWT secret key.

## License

Private — All rights reserved.
