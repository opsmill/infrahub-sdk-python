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

from .generated.write import GeneratedGenericSchema, GeneratedNodeSchema

# Maps each collection in a schema-root payload to the write model its items must satisfy.
_WRITE_MODELS_BY_COLLECTION: dict[str, type[BaseModel]] = {
    "nodes": GeneratedNodeSchema,
    "generics": GeneratedGenericSchema,
}


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


def _format_error_location(collection: str, index: int, loc: tuple[Any, ...]) -> str:
    parts = [f"{collection}[{index}]"]
    for element in loc:
        if isinstance(element, int):
            parts[-1] = f"{parts[-1]}[{element}]"
        else:
            parts.append(str(element))
    return ".".join(parts)


def validate_schema(schema: dict[str, Any], *, raise_on_error: bool = False) -> SchemaValidationResult:
    """Validate a single schema-root payload against the generated write models.

    Args:
        schema: A schema-root mapping, e.g. ``{"version": "1.0", "nodes": [...], "generics": [...]}``.
        raise_on_error: When True, raise ``ValueError`` instead of returning an invalid result.

    Returns:
        A :class:`SchemaValidationResult` with a field-level message for every field that is not
        settable (read-level, internal, or unknown) and for every constrained field set outside
        its allowed set.

    Raises:
        ValueError: When ``raise_on_error`` is True and the payload is invalid.

    """
    errors: list[SchemaValidationErrorDetail] = []
    for collection, model in _WRITE_MODELS_BY_COLLECTION.items():
        items = schema.get(collection)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                model.model_validate(item)
            except PydanticValidationError as exc:
                for error in exc.errors():
                    location = _format_error_location(collection=collection, index=index, loc=error["loc"])
                    message = f"{location}: {error['msg']}"
                    if error["type"] != "missing" and "input" in error:
                        message += f" (received: {error['input']!r})"
                    errors.append(SchemaValidationErrorDetail(field=location, message=message))

    result = SchemaValidationResult(valid=not errors, errors=errors)
    if raise_on_error:
        result.raise_for_status()
    return result
