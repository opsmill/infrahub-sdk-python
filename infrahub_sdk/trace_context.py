from __future__ import annotations

import logging
from functools import cache

LOGGER = logging.getLogger("infrahub_sdk")


def trace_context_headers() -> dict[str, str]:
    """Return the W3C trace context headers of the active span, or no header when OpenTelemetry is not installed."""
    try:
        from opentelemetry import propagate  # noqa: PLC0415
    except ImportError:
        return {}
    except ValueError as exc:
        # OpenTelemetry validates OTEL_PROPAGATORS on import, and a value set for another tool must not fail requests.
        _warn_invalid_propagators(str(exc))
        return {}

    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


@cache
def _warn_invalid_propagators(reason: str) -> None:
    LOGGER.warning("Not sending the trace context: OpenTelemetry could not load its propagators (%s)", reason)
