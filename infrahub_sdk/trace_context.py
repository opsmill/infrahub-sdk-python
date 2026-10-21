from __future__ import annotations

import logging
import re
from functools import cache
from importlib.metadata import PackageNotFoundError, version

LOGGER = logging.getLogger("infrahub_sdk")

MINIMUM_OPENTELEMETRY_API = (1, 33)


def trace_context_headers() -> dict[str, str]:
    """Return the W3C trace context headers of the active span, or no header when a supported OpenTelemetry is not installed."""
    if not _supported_opentelemetry_is_installed():
        return {}

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
def _supported_opentelemetry_is_installed() -> bool:
    # Older releases can raise unexpected errors on import, so they are never imported; the lookup is cached
    # because reading package metadata costs far more than the rest of the request headers.
    try:
        installed = version("opentelemetry-api")
    except PackageNotFoundError:
        return False

    release = re.match(r"(\d+)\.(\d+)", installed)
    if release is None or (int(release[1]), int(release[2])) < MINIMUM_OPENTELEMETRY_API:
        LOGGER.warning(
            "Not sending the trace context: opentelemetry-api %s is installed, %s or later is required",
            installed,
            ".".join(str(part) for part in MINIMUM_OPENTELEMETRY_API),
        )
        return False
    return True


@cache
def _warn_invalid_propagators(reason: str) -> None:
    LOGGER.warning("Not sending the trace context: OpenTelemetry could not load its propagators (%s)", reason)
