"""Async HTTP client lifecycle management.

Wraps :mod:`httpx` with sensible timeout and connection-pool defaults for
outbound calls to the DigiLocker API and other external services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.config import Settings


__all__ = ["create_http_client", "close_http_client"]


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """Build a pre-configured :class:`httpx.AsyncClient`.

    Parameters
    ----------
    settings:
        Application configuration.  The ``app_name`` attribute (if present)
        is included in the ``User-Agent`` header.

    Returns
    -------
    httpx.AsyncClient
        A client instance with timeouts, connection limits, and default
        headers already set.  The caller is responsible for closing the
        client (see :func:`close_http_client`).
    """
    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    limits = httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
    )

    app_name = getattr(settings, "app_name", "DigiLockerVerificationAPI")

    default_headers = {
        "User-Agent": f"{app_name}/1.0",
        "Accept": "application/json",
    }

    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=default_headers,
    )


async def close_http_client(client: httpx.AsyncClient) -> None:
    """Gracefully close *client* and release pooled connections.

    Parameters
    ----------
    client:
        The HTTP client to shut down.
    """
    await client.aclose()
