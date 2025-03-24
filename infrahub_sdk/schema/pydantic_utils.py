from __future__ import annotations

import re
import typing
from dataclasses import dataclass
from types import UnionType
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo, PydanticUndefined
from typing_extensions import Self

from .main import (
    AttributeKind,
    AttributeSchema,
    BranchSupportType,
    GenericSchema,
    NodeSchema,
    RelationshipKind,
    RelationshipSchema,
    SchemaRoot,
    SchemaState,
)

if TYPE_CHECKING:
    from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

KIND_MAPPING: dict[type, AttributeKind] = {
    int: AttributeKind.NUMBER,
    float: AttributeKind.NUMBER,
    str: AttributeKind.TEXT,
    bool: AttributeKind.BOOLEAN,
}

NAMESPACE_REGEX = r"^[A-Z][a-z0-9]+$"
NODE_KIND_REGEX = r"^[A-Z][a-zA-Z0-9]+$"


class SchemaModel(BaseModel):
    id: str | None = Field(default=None, description="The ID of the node")

    @classmethod
    def get_kind(cls) -> str:
        return get_kind(cls)

    @classmethod
    def from_node(cls, node: InfrahubNode | InfrahubNodeSync) -> Self:
        data = {}
        for field_name, field in cls.model_fields.items():
            field_info = analyze_field(field_name, field)
            if field_name == "id":
                data[field_name] = node.id
            elif field_info.is_attribute:
                attr = getattr(node, field_name)
                data[field_name] = attr.value

            # elif field_info.is_relationship:
            #     rel = getattr(node, field_name)
            #     data[field_name] = rel.value

        return cls(**data)


class NodeModel(SchemaModel):
    pass


class GenericModel(SchemaModel):
    pass


@dataclass
class InfrahubAttributeParam:
    state: SchemaState = SchemaState.PRESENT
    kind: AttributeKind | None = None
    label: str | None = None
    unique: bool = False
    branch: BranchSupportType | None = None


@dataclass
class InfrahubRelationshipParam:
    kind: RelationshipKind | None = None
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

        # if isinstance(self.primary_type, ForwardRef):
        #     raise TypeError("Forward References are not supported yet, please ensure the models are defined in the right order")

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
        # breakpoint()
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


def field_to_attribute(field_name: str, field_info: InfrahubFieldInfo, field: FieldInfo) -> AttributeSchema:
    field_param = InfrahubAttributeParam()
    field_params = [metadata for metadata in field.metadata if isinstance(metadata, InfrahubAttributeParam)]
    if len(field_params) == 1:
        field_param = field_params[0]

    pattern = field._attributes_set.get("pattern", None)
    max_length = field._attributes_set.get("max_length", None)
    min_length = field._attributes_set.get("min_length", None)

    return AttributeSchema(
        name=field_name,
        label=field_param.label,
        description=field.description,
        kind=field_param.kind or get_attribute_kind(field),
        optional=not field.is_required(),
        unique=field_param.unique,
        branch=field_param.branch,
        default_value=field_info.default,
        regex=str(pattern) if pattern else None,
        max_length=int(str(max_length)) if max_length else None,
        min_length=int(str(min_length)) if min_length else None,
    )


def field_to_relationship(
    field_name: str,
    field_info: InfrahubFieldInfo,
    field: FieldInfo,
) -> RelationshipSchema:
    field_param = InfrahubRelationshipParam()
    field_params = [metadata for metadata in field.metadata if isinstance(metadata, InfrahubRelationshipParam)]
    if len(field_params) == 1:
        field_param = field_params[0]

    return RelationshipSchema(
        name=field_name,
        description=field.description,
        peer=get_kind(field_info.primary_type),
        identifier=field_param.identifier,
        cardinality="many" if field_info.is_list else "one",
        optional=field_info.optional,
        branch=field_param.branch,
    )


def extract_validate_generic(model: type[BaseModel]) -> list[str]:
    return [get_kind(ancestor) for ancestor in model.__bases__ if issubclass(ancestor, GenericModel)]


def validate_kind(kind: str) -> tuple[str, str]:
    # First, handle transition from a lowercase to uppercase
    name_with_spaces = re.sub(r"([a-z])([A-Z])", r"\1 \2", kind)

    # Then, handle consecutive uppercase letters followed by a lowercase
    # (e.g., "HTTPRequest" -> "HTTP Request")
    name_with_spaces = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", name_with_spaces)

    name_parts = name_with_spaces.split(" ")

    if len(name_parts) == 1:
        raise ValueError(f"Invalid kind: {kind}, must contain a Namespace and a Name")
    kind_namespace = name_parts[0]
    kind_name = "".join(name_parts[1:])

    if not kind_namespace[0].isupper():
        raise ValueError(f"Invalid namespace: {kind_namespace}, must start with an uppercase letter")

    return kind_namespace, kind_name


def is_generic(model: type[BaseModel]) -> bool:
    return GenericModel in model.__bases__


def get_kind(model: type[BaseModel]) -> str:
    node_schema: NodeSchema | None = model.model_config.get("node_schema") or None  # type: ignore[assignment]
    generic_schema: GenericSchema | None = model.model_config.get("generic_schema") or None  # type: ignore[assignment]

    if is_generic(model) and generic_schema:
        return generic_schema.kind
    if node_schema:
        return node_schema.kind
    namespace, name = validate_kind(model.__name__)
    return f"{namespace}{name}"


def get_generics(model: type[BaseModel]) -> list[type[GenericModel]]:
    return [ancestor for ancestor in model.__bases__ if issubclass(ancestor, GenericModel)]


def _add_fields(
    node: NodeSchema | GenericSchema, model: type[BaseModel], inherited_fields: dict[str, dict[str, Any]] | None = None
) -> None:
    for field_name, field in model.model_fields.items():
        if (
            inherited_fields
            and field_name in inherited_fields
            and field._attributes_set == inherited_fields[field_name]
        ):
            continue

        if field_name == "id":
            continue

        field_info = analyze_field(field_name, field)

        if field_info.is_attribute:
            node.attributes.append(field_to_attribute(field_name, field_info, field))
        elif field_info.is_relationship:
            node.relationships.append(field_to_relationship(field_name, field_info, field))


def model_to_node(model: type[BaseModel]) -> NodeSchema | GenericSchema:
    # ------------------------------------------------------------
    # GenericSchema
    # ------------------------------------------------------------
    if GenericModel in model.__bases__:
        generic_schema: GenericSchema | None = model.model_config.get("generic_schema") or None  # type: ignore[assignment]

        if not generic_schema:
            namespace, name = validate_kind(model.__name__)

        generic = GenericSchema(
            name=generic_schema.name if generic_schema else name,
            namespace=generic_schema.namespace if generic_schema else namespace,
            display_labels=generic_schema.display_labels if generic_schema else None,
            description=generic_schema.description if generic_schema else None,
            state=generic_schema.state if generic_schema else SchemaState.PRESENT,
            label=generic_schema.label if generic_schema else None,
            include_in_menu=generic_schema.include_in_menu if generic_schema else None,
            menu_placement=generic_schema.menu_placement if generic_schema else None,
            documentation=generic_schema.documentation if generic_schema else None,
            order_by=generic_schema.order_by if generic_schema else None,
            # parent=schema.parent if schema else None,
            # children=schema.children if schema else None,
            icon=generic_schema.icon if generic_schema else None,
            # generate_profile=schema.generate_profile if schema else None,
            # branch=schema.branch if schema else None,
            # default_filter=schema.default_filter if schema else None,
        )
        _add_fields(node=generic, model=model)
        return generic

    # ------------------------------------------------------------
    # NodeSchema
    # ------------------------------------------------------------
    node_schema: NodeSchema | None = model.model_config.get("node_schema") or None  # type: ignore[assignment]

    if not node_schema:
        namespace, name = validate_kind(model.__name__)

    generics = get_generics(model)

    # list all inherited fields with a hash for each to track if they are identical on the node
    inherited_fields = {
        field_name: field._attributes_set for generic in generics for field_name, field in generic.model_fields.items()
    }

    node = NodeSchema(
        name=node_schema.name if node_schema else name,
        namespace=node_schema.namespace if node_schema else namespace,
        display_labels=node_schema.display_labels if node_schema else None,
        description=node_schema.description if node_schema else None,
        state=node_schema.state if node_schema else SchemaState.PRESENT,
        label=node_schema.label if node_schema else None,
        include_in_menu=node_schema.include_in_menu if node_schema else None,
        menu_placement=node_schema.menu_placement if node_schema else None,
        documentation=node_schema.documentation if node_schema else None,
        order_by=node_schema.order_by if node_schema else None,
        inherit_from=[get_kind(generic) for generic in generics],
        parent=node_schema.parent if node_schema else None,
        children=node_schema.children if node_schema else None,
        icon=node_schema.icon if node_schema else None,
        generate_profile=node_schema.generate_profile if node_schema else None,
        branch=node_schema.branch if node_schema else None,
        # default_filter=schema.default_filter if schema else None,
    )

    _add_fields(node=node, model=model, inherited_fields=inherited_fields)
    return node


def from_pydantic(models: list[type[BaseModel]]) -> SchemaRoot:
    schema = SchemaRoot(version="1.0")

    for model in models:
        node = model_to_node(model=model)

        if isinstance(node, NodeSchema):
            schema.nodes.append(node)
        elif isinstance(node, GenericSchema):
            schema.generics.append(node)

    return schema


# class NodeSchema(BaseModel):
#     name: str| None = None
#     namespace: str| None = None
#     display_labels: list[str] | None = None

# class NodeMetaclass(ModelMetaclass):
#     model_config: NodeConfig
#     # model_schema: NodeSchema
#     __config__: type[NodeConfig]
#     # __schema__: NodeSchema
