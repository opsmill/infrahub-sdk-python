"""Enumerations shared across the Infrahub SDK."""

import enum


class InfrahubClientMode(str, enum.Enum):
    DEFAULT = "default"
    TRACKING = "tracking"
    # IDEMPOTENT = "idempotent"


class Priority(str, enum.Enum):
    """Request priority emitted as the ``X-Priority`` header.

    String-valued closed enum accepting values case-insensitively (e.g. "LOW",
    "Low" and "low" all resolve to :attr:`Priority.LOW`). Unknown values raise
    ``ValueError``, which surfaces as a ``pydantic.ValidationError`` at config load.
    """

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @classmethod
    def _missing_(cls, value: object) -> "Priority | None":
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None
