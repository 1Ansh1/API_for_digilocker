"""OpenTelemetry tracing setup for DigiLocker Verification API.

Provides a :func:`setup_tracing` bootstrap that configures a
:class:`TracerProvider` with either a console exporter (development) or an
OTLP/gRPC exporter (production).

FastAPI auto-instrumentation is left as a commented-out placeholder so it
can be enabled once the application wiring is finalised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = ["setup_tracing"]


def setup_tracing(settings: Settings) -> trace.Tracer:
    """Initialise OpenTelemetry tracing and return a :class:`Tracer`.

    Parameters
    ----------
    settings:
        Application configuration.  The following attributes are inspected:

        * ``debug`` – when ``True`` spans are printed to the console; when
          ``False`` they are exported via OTLP/gRPC.
        * ``otlp_endpoint`` – gRPC endpoint for the OTLP exporter
          (default ``http://localhost:4317``).
        * ``app_name`` – used as the ``service.name`` resource attribute.

    Returns
    -------
    opentelemetry.trace.Tracer
        A tracer bound to the configured provider.
    """
    app_name = getattr(settings, "app_name", "digilocker-verification-api")
    resource = Resource.create({"service.name": app_name})

    provider = TracerProvider(resource=resource)

    if settings.debug:
        exporter = ConsoleSpanExporter()
    else:
        # Use OTLP exporter for production environments.
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        otlp_endpoint = getattr(
            settings, "otlp_endpoint", "http://localhost:4317"
        )
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # ------------------------------------------------------------------
    # FastAPI auto-instrumentation
    # Enable once the FastAPI app instance is available in the lifespan:
    #
    #   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    #   FastAPIInstrumentor.instrument_app(app)
    # ------------------------------------------------------------------

    return trace.get_tracer(app_name)
