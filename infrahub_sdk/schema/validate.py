"""Offline validation of a schema payload against the generated write models.

This module depends only on pydantic and the generated write models, so a caller
can validate a schema payload with just the SDK installed (no server, no backend).
The write models omit fields the user may not set (read-level, internal) and set
``extra="ignore"``, so those values never reach the server. Whether an omitted field is
reported depends on what it is: a read-only field -- one the read API returns -- is reported
as a warning so a payload read back from Infrahub still loads, while any other extra field is
an error, because the only ways to get one are a typo and a field that no longer exists.
Constrained fields set outside their allowed set are also rejected naming the field and the
invalid value, as are missing required fields and unknown enum members.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from .generated.contract import READ_ONLY_FIELDS
from .generated.write import InfrahubSchemaWrite

# Payload containers whose items carry the identity used to report a finding. The warning shape
# consumers render is named (kind, field) rather than positional, so the walk tracks the owning
# kind and element alongside the dotted path.
_KIND_CONTAINERS = frozenset({"nodes", "generics"})
_ELEMENT_CONTAINERS = frozenset({"attributes", "relationships"})


class SchemaValidationErrorDetail(BaseModel):
    """A single field-level validation problem in a schema payload."""

    field: str = Field(..., description="Dotted path to the offending field, e.g. 'nodes[0].attributes[1].kind'")
    message: str = Field(..., description="Human-readable, field-level error message")


class SchemaValidationWarningDetail(BaseModel):
    """A read-only field set in a schema payload: accepted, but the submitted value is dropped."""

    field: str = Field(..., description="Dotted path to the offending field, e.g. 'nodes[0].attributes[1].inherited'")
    name: str = Field(..., description="Name of the read-only field, e.g. 'inherited'")
    kind: str | None = Field(default=None, description="Kind of the schema node carrying the field, when resolvable")
    element: str | None = Field(
        default=None, description="Name of the attribute or relationship carrying the field, when applicable"
    )
    message: str = Field(..., description="Human-readable, field-level warning message")


class SchemaValidationResult(BaseModel):
    """The verdict of validating a schema payload against the write contract."""

    valid: bool = Field(..., description="True when the payload satisfies the write contract")
    errors: list[SchemaValidationErrorDetail] = Field(
        default_factory=list, description="One entry per field-level problem; empty when valid"
    )
    warnings: list[SchemaValidationWarningDetail] = Field(
        default_factory=list, description="One entry per read-only field set in the payload"
    )

    @property
    def messages(self) -> list[str]:
        return [error.message for error in self.errors]

    @property
    def warning_messages(self) -> list[str]:
        return [warning.message for warning in self.warnings]

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


def _read_only_fields(model: type[BaseModel]) -> frozenset[str]:
    """Read-only field names declared for a model, including those it inherits."""
    names: set[str] = set()
    for klass in model.__mro__:
        names |= READ_ONLY_FIELDS.get(klass.__name__, frozenset())
    return frozenset(names)


def _descend_context(
    container: str, item: dict[str, Any], kind: str | None, element: str | None
) -> tuple[str | None, str | None]:
    """Resolve the owning kind and element for an item of a payload container."""
    if container in _KIND_CONTAINERS:
        namespace, name = item.get("namespace"), item.get("name")
        # An extension addresses an existing node by kind; a new node is namespace + name.
        resolved = f"{namespace}{name}" if namespace and name else item.get("kind")
        return (resolved if isinstance(resolved, str) else None), None
    if container in _ELEMENT_CONTAINERS:
        name = item.get("name")
        return kind, name if isinstance(name, str) else None
    return kind, element


def _collect_extra_fields(
    payload: dict[str, Any],
    instance: BaseModel,
    errors: list[SchemaValidationErrorDetail],
    warnings: list[SchemaValidationWarningDetail],
    path: str = "",
    kind: str | None = None,
    element: str | None = None,
) -> None:
    """Report every payload key the write contract does not declare, walking the validated model.

    The validated instance resolves the model that applies at each location -- including which
    member of a discriminated union an attribute matched -- so the raw payload can be compared
    against the fields that location actually accepts.
    """
    model = type(instance)
    fields = model.model_fields
    read_only = _read_only_fields(model)

    for key in sorted(set(payload) - set(fields)):
        location = f"{path}.{key}" if path else key
        if key in read_only:
            warnings.append(
                SchemaValidationWarningDetail(
                    field=location,
                    name=key,
                    kind=kind,
                    element=element,
                    message=f"{location}: Read-only field, the submitted value is ignored (received: {payload[key]!r})",
                )
            )
        else:
            errors.append(
                SchemaValidationErrorDetail(
                    field=location,
                    message=f"{location}: Unknown field, it is not part of the schema (received: {payload[key]!r})",
                )
            )

    for name in fields:
        if name not in payload:
            continue
        raw, value = payload[name], getattr(instance, name)
        child_path = f"{path}.{name}" if path else name
        if isinstance(value, list) and isinstance(raw, list):
            for index, (raw_item, item) in enumerate(zip(raw, value, strict=False)):
                if not isinstance(item, BaseModel) or not isinstance(raw_item, dict):
                    continue
                item_kind, item_element = _descend_context(container=name, item=raw_item, kind=kind, element=element)
                _collect_extra_fields(
                    payload=raw_item,
                    instance=item,
                    errors=errors,
                    warnings=warnings,
                    path=f"{child_path}[{index}]",
                    kind=item_kind,
                    element=item_element,
                )
        elif isinstance(value, BaseModel) and isinstance(raw, dict):
            _collect_extra_fields(
                payload=raw,
                instance=value,
                errors=errors,
                warnings=warnings,
                path=child_path,
                kind=kind,
                element=element,
            )


def validate_schema(schema: dict[str, Any], *, raise_on_error: bool = False) -> SchemaValidationResult:
    """Validate a single schema-root payload against the generated write contract.

    Args:
        schema: A schema-root mapping, e.g. ``{"version": "1.0", "nodes": [...], "generics": [...]}``.
        raise_on_error: When True, raise ``ValueError`` instead of returning an invalid result.

    Returns:
        A :class:`SchemaValidationResult` with a field-level message for every constrained field set
        outside its allowed set, every missing required field, and every extra field the contract
        does not declare, plus a warning for every read-only field the payload sets. The whole root
        -- nodes, generics and the attributes/relationships nested under ``extensions.nodes`` -- is
        validated against the write document model in one pass.

        Extra fields are reported only once the payload validates against the write models, since
        the validated instance is what resolves the contract applying at each location. A payload
        rejected for another reason therefore reports that reason first.

    Raises:
        ValueError: When ``raise_on_error`` is True and the payload is invalid.

    """
    errors: list[SchemaValidationErrorDetail] = []
    warnings: list[SchemaValidationWarningDetail] = []

    try:
        validated = InfrahubSchemaWrite.model_validate(schema)
    except PydanticValidationError as exc:
        _collect_validation_errors(exc=exc, errors=errors)
    else:
        _collect_extra_fields(payload=schema, instance=validated, errors=errors, warnings=warnings)

    result = SchemaValidationResult(valid=not errors, errors=errors, warnings=warnings)
    if raise_on_error:
        result.raise_for_status()
    return result
