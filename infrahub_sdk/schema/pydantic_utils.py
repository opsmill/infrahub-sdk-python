from __future__ import annotations

import typing
from dataclasses import dataclass
from types import UnionType
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo, PydanticUndefined

from infrahub_sdk.schema.main import AttributeSchema, NodeSchema, RelationshipSchema, SchemaRoot

from .main import AttributeKind, BranchSupportType, SchemaState

KIND_MAPPING: dict[type, AttributeKind] = {
    int: AttributeKind.NUMBER,
    float: AttributeKind.NUMBER,
    str: AttributeKind.TEXT,
    bool: AttributeKind.BOOLEAN,
}


@dataclass
class InfrahubAttributeParam:
    state: SchemaState = SchemaState.PRESENT
    kind: AttributeKind | None = None
    label: str | None = None
    unique: bool = False
    branch: BranchSupportType | None = None


@dataclass
class InfrahubRelationshipParam:
    identifier: str | None = None
    branch: BranchSupportType | None = None


@dataclass
class InfrahubFieldInfo:
    name: str
    types: list[type]
    optional: bool
    default: Any

    @property
    def primary_type(self) -> type:
        if len(self.types) == 0:
            raise ValueError("No types found")
        if self.is_list:
            return typing.get_args(self.types[0])[0]

        return self.types[0]

    @property
    def is_attribute(self) -> bool:
        return self.primary_type in KIND_MAPPING

    @property
    def is_relationship(self) -> bool:
        return issubclass(self.primary_type, BaseModel)

    @property
    def is_list(self) -> bool:
        return typing.get_origin(self.types[0]) is list

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "primary_type": self.primary_type,
            "optional": self.optional,
            "default": self.default,
            "is_attribute": self.is_attribute,
            "is_relationship": self.is_relationship,
            "is_list": self.is_list,
        }


def analyze_field(field_name: str, field: FieldInfo) -> InfrahubFieldInfo:
    clean_types = []
    if isinstance(field.annotation, UnionType) or (
        hasattr(field.annotation, "_name") and field.annotation._name == "Optional"  # type: ignore[union-attr]
    ):
        clean_types = [t for t in field.annotation.__args__ if t is not type(None)]  # type: ignore[union-attr]
    else:
        clean_types.append(field.annotation)

    return InfrahubFieldInfo(
        name=field.alias or field_name,
        types=clean_types,
        optional=not field.is_required(),
        default=field.default if field.default is not PydanticUndefined else None,
    )


def get_attribute_kind(field: FieldInfo) -> AttributeKind:
    if field.annotation in KIND_MAPPING:
        return KIND_MAPPING[field.annotation]

    if isinstance(field.annotation, UnionType) or (
        hasattr(field.annotation, "_name") and field.annotation._name == "Optional"  # type: ignore[union-attr]
    ):
        valid_types = [t for t in field.annotation.__args__ if t is not type(None)]  # type: ignore[union-attr]
        if len(valid_types) == 1 and valid_types[0] in KIND_MAPPING:
            return KIND_MAPPING[valid_types[0]]

    raise ValueError(f"Unknown field type: {field.annotation}")


def field_to_attribute(field_name: str, field_info: InfrahubFieldInfo, field: FieldInfo) -> AttributeSchema:  # noqa: ARG001
    field_param = InfrahubAttributeParam()
    field_params = [metadata for metadata in field.metadata if isinstance(metadata, InfrahubAttributeParam)]
    if len(field_params) == 1:
        field_param = field_params[0]

    return AttributeSchema(
        name=field_name,
        label=field_param.label,
        description=field.description,
        kind=field_param.kind or get_attribute_kind(field),
        optional=not field.is_required(),
        unique=field_param.unique,
        branch=field_param.branch,
    )


def field_to_relationship(
    field_name: str,
    field_info: InfrahubFieldInfo,
    field: FieldInfo,
    namespace: str = "Testing",
) -> RelationshipSchema:
    field_param = InfrahubRelationshipParam()
    field_params = [metadata for metadata in field.metadata if isinstance(metadata, InfrahubRelationshipParam)]
    if len(field_params) == 1:
        field_param = field_params[0]

    return RelationshipSchema(
        name=field_name,
        description=field.description,
        peer=f"{namespace}{field_info.primary_type.__name__}",
        identifier=field_param.identifier,
        cardinality="many" if field_info.is_list else "one",
        optional=field_info.optional,
        branch=field_param.branch,
    )


def from_pydantic(models: list[type[BaseModel]], namespace: str = "Testing") -> SchemaRoot:
    schema = SchemaRoot(version="1.0")

    for model in models:
        node = NodeSchema(
            name=model.__name__,
            namespace=namespace,
        )

        for field_name, field in model.model_fields.items():
            field_info = analyze_field(field_name, field)

            if field_info.is_attribute:
                node.attributes.append(field_to_attribute(field_name, field_info, field))
            elif field_info.is_relationship:
                node.relationships.append(field_to_relationship(field_name, field_info, field, namespace))

        schema.nodes.append(node)

    return schema
