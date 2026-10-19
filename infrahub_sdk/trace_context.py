from __future__ import annotations


def trace_context_headers() -> dict[str, str]:
    """Return the W3C trace context headers of the active span, or no header when OpenTelemetry is not installed."""
    try:
        from opentelemetry import propagate  # noqa: PLC0415
    except ImportError:
        return {}

    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier
