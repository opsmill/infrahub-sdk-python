"""Project a schema payload onto the user-facing write contract.

``infrahubctl``/SDK callers routinely build a load payload from a schema they read back (which
carries server-computed and read-only fields) or from a full model dump. The ``/api/schema/load``
endpoint only accepts user-settable fields and rejects anything else, so the client drops the
read-only/internal fields before sending. The projection is driven by the generated write models,
so it stays correct as the contract evolves and it resolves per-kind discriminated unions (the
attribute and computed-attribute variants) to keep only the fields valid for each kind.
"""

from __future__ import annotations

import functools
import types
import typing
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from .generated.write import InfrahubSchemaWrite

_UNION_ORIGINS = {typing.Union, types.UnionType}
_SEQUENCE_ORIGINS = {list, tuple}


def normalize_schema_for_load(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` containing only fields accepted by the write contract."""
    if not isinstance(schema, dict):
        return schema
    return _project_model(schema, InfrahubSchemaWrite)


@functools.cache
def _resolved_hints(model: type[BaseModel]) -> dict[str, Any]:
    # ``model_fields[...].annotation`` leaves module-level Annotated aliases (the discriminated
    # unions) as unresolved forward references; ``get_type_hints`` resolves them with the metadata.
    return typing.get_type_hints(model, include_extras=True)


def _project_model(data: Any, model: type[BaseModel]) -> Any:
    if not isinstance(data, dict):
        return data
    hints = _resolved_hints(model)
    projected: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        key = name if name in data else (info.alias if info.alias in data else None)
        if key is None:
            continue
        projected[key] = _project_value(data[key], hints.get(name, info.annotation), info.discriminator)
    return projected


def _project_value(value: Any, annotation: Any, discriminator: str | None = None) -> Any:
    # Annotated[...] (used for the discriminated unions): unwrap to the base + its discriminator.
    if hasattr(annotation, "__metadata__"):
        nested = next(
            (m.discriminator for m in annotation.__metadata__ if isinstance(m, FieldInfo) and m.discriminator),
            None,
        )
        return _project_value(value, annotation.__origin__, nested or discriminator)

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin in _UNION_ORIGINS:
        members = [a for a in args if a is not type(None)]
        if discriminator and isinstance(value, dict):
            member = _pick_variant(members, discriminator, value)
            if member is not None:
                return _project_model(value, member)
        return _project_value(value, members[0]) if len(members) == 1 else value

    if origin in _SEQUENCE_ORIGINS and args and isinstance(value, list):
        return [_project_value(item, args[0]) for item in value]

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _project_model(value, annotation)

    return value


def _pick_variant(members: list[Any], discriminator: str, value: dict[str, Any]) -> type[BaseModel] | None:
    target = str(getattr(value.get(discriminator), "value", value.get(discriminator)))
    for member in members:
        if not (isinstance(member, type) and issubclass(member, BaseModel)):
            continue
        field = member.model_fields.get(discriminator)
        if field is not None and target in {str(getattr(a, "value", a)) for a in typing.get_args(field.annotation)}:
            return member
    return None
