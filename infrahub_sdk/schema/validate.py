"""Offline validation of a schema payload against the generated write models.

This module depends only on pydantic and the generated write models, so a caller
can validate a schema payload with just the SDK installed (no server, no backend).
The write models omit fields the user may not set (read-level, internal) and set
``extra="forbid"``, so submitting a non-settable or unknown field is rejected with a
field-level message, and constrained fields set outside their allowed set are rejected
naming the field and the invalid value.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from .generated.write import InfrahubSchemaWrite


class SchemaValidationErrorDetail(BaseModel):
    """A single field-level validation problem in a schema payload."""

    field: str = Field(..., description="Dotted path to the offending field, e.g. 'nodes[0].attributes[1].kind'")
    message: str = Field(..., description="Human-readable, field-level error message")


class SchemaValidationResult(BaseModel):
    """The verdict of validating a schema payload against the write contract."""

    valid: bool = Field(..., description="True when the payload satisfies the write contract")
    errors: list[SchemaValidationErrorDetail] = Field(
        default_factory=list, description="One entry per field-level problem; empty when valid"
    )

    @property
    def messages(self) -> list[str]:
        return [error.message for error in self.errors]

    def raise_for_status(self) -> None:
        """Raise when the payload is invalid, joining every field-level message.

        Raises:
            ValueError: When the result is invalid; the message joins every field-level error.

        """
        if not self.valid:
            raise ValueError("; ".join(self.messages))


def _format_error_location(loc: tuple[Any, ...], prefix: str = "") -> str:
    """Render a dotted field path from a pydantic error location, optionally under a base prefix.

    Integer elements index into the preceding segment (``attributes`` + ``1`` becomes
    ``attributes[1]``); everything else is appended as a new dotted segment. A ``prefix`` is used
    when the location is relative to an item validated on its own (e.g. an extension attribute).
    """
    parts = [prefix] if prefix else []
    for element in loc:
        if isinstance(element, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{element}]"
            else:
                parts.append(f"[{element}]")
        else:
            parts.append(str(element))
    return ".".join(parts)


def _collect_validation_errors(
    exc: PydanticValidationError, errors: list[SchemaValidationErrorDetail], prefix: str = ""
) -> None:
    """Append a field-level detail for every problem in a pydantic validation error."""
    for error in exc.errors():
        location = _format_error_location(loc=error["loc"], prefix=prefix)
        message = f"{location}: {error['msg']}"
        if error["type"] != "missing" and "input" in error:
            message += f" (received: {error['input']!r})"
        errors.append(SchemaValidationErrorDetail(field=location, message=message))


def validate_schema(schema: dict[str, Any], *, raise_on_error: bool = False) -> SchemaValidationResult:
    """Validate a single schema-root payload against the generated write contract.

    Args:
        schema: A schema-root mapping, e.g. ``{"version": "1.0", "nodes": [...], "generics": [...]}``.
        raise_on_error: When True, raise ``ValueError`` instead of returning an invalid result.

    Returns:
        A :class:`SchemaValidationResult` with a field-level message for every field that is not
        settable (read-level, internal, or unknown) and for every constrained field set outside
        its allowed set. The whole root -- nodes, generics and the attributes/relationships nested
        under ``extensions.nodes`` -- is validated against the write document model in one pass.

    Raises:
        ValueError: When ``raise_on_error`` is True and the payload is invalid.

    """
    errors: list[SchemaValidationErrorDetail] = []

    try:
        InfrahubSchemaWrite.model_validate(schema)
    except PydanticValidationError as exc:
        _collect_validation_errors(exc=exc, errors=errors)

    result = SchemaValidationResult(valid=not errors, errors=errors)
    if raise_on_error:
        result.raise_for_status()
    return result
