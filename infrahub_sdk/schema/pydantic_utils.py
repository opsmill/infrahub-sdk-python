from __future__ import annotations

import re
import typing
from dataclasses import dataclass
from types import UnionType
from typing import TYPE_CHECKING, Any, Callable, ForwardRef, Literal, TypeVar, Union

from pydantic import BaseModel
from pydantic import ConfigDict as BaseConfig
from pydantic._internal._model_construction import ModelMetaclass  # noqa: PLC2701
from pydantic._internal._repr import Representation  # noqa: PLC2701
from pydantic.fields import FieldInfo as PydanticFieldInfo
from pydantic.fields import PydanticUndefined as Undefined
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

_T = TypeVar("_T")

KIND_MAPPING: dict[type, AttributeKind] = {
    int: AttributeKind.NUMBER,
    float: AttributeKind.NUMBER,
    str: AttributeKind.TEXT,
    bool: AttributeKind.BOOLEAN,
}

NAMESPACE_REGEX = r"^[A-Z][a-z0-9]+$"
NODE_KIND_REGEX = r"^[A-Z][a-zA-Z0-9]+$"


def __dataclass_transform__(
    *,
    eq_default: bool = True,
    order_default: bool = False,
    kw_only_default: bool = False,
    field_descriptors: tuple[Union[type, Callable[..., Any]], ...] = (()),
) -> Callable[[_T], _T]:
    return lambda a: a


class InfrahubConfig(BaseConfig, total=False):
    generic: bool = False
    name: str | None = None
    namespace: str | None = None
    display_labels: list[str] | None = None
    description: str | None = None
    state: SchemaState = SchemaState.PRESENT
    label: str | None = None
    include_in_menu: bool | None = None
    menu_placement: str | None = None


class AttributeInfo(PydanticFieldInfo):
    def __init__(self, default: Any = Undefined, **kwargs: Any) -> None:
        unique = kwargs.pop("unique", False)
        label = kwargs.pop("label", None)
        kind = kwargs.pop("kind", None)
        regex = kwargs.pop("regex", None)
        branch = kwargs.pop("branch", None)
        super().__init__(default=default, **kwargs)
        self.unique = unique
        self.label = label
        self.kind = kind
        self.regex = regex
        self.branch = branch


class RelationshipInfo(Representation):
    def __init__(
        self,
        *,
        alias: str | None = None,
        kind: RelationshipKind | None = None,
        peer: str | None = None,
        description: str | None = None,
        identifier: str | None = None,
        branch: BranchSupportType | None = None,
        optional: bool = False,
    ) -> None:
        self.alias = alias
        self.kind = kind
        self.identifier = identifier
        self.branch = branch
        self.description = description
        self.peer = peer
        self.optional = optional


def Relationship(
    *,
    alias: str | None = None,
    kind: RelationshipKind | None = None,
    identifier: str | None = None,
    branch: BranchSupportType | None = None,
    peer: str | None = None,
    description: str | None = None,
    optional: bool = False,
) -> Any:
    relationship_info = RelationshipInfo(
        alias=alias,
        kind=kind,
        identifier=identifier,
        branch=branch,
        peer=peer,
        description=description,
        optional=optional,
    )
    return relationship_info


def Attribute(
    default: Any = Undefined,
    *,
    alias: str | None = None,
    description: str | None = None,
    state: SchemaState = SchemaState.PRESENT,
    kind: AttributeKind | None = None,
    label: str | None = None,
    unique: bool = False,
    branch: BranchSupportType | None = None,
    regex: str | None = None,
    pattern: str | None = None,
) -> Any:
    current_schema_extra = {}
    field_info = AttributeInfo(
        default,
        alias=alias,
        description=description,
        state=state,
        kind=kind,
        label=label,
        unique=unique,
        branch=branch,
        regex=regex,
        pattern=pattern,
        **current_schema_extra,
    )
    return field_info


@__dataclass_transform__(kw_only_default=True, field_descriptors=(Attribute, AttributeInfo))
class InfrahubMetaclass(ModelMetaclass):
    __infrahub_relationships__: dict[str, RelationshipInfo]
    model_config: InfrahubConfig
    model_fields: dict[str, AttributeInfo]

    def __new__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        class_dict: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        relationships: dict[str, RelationshipInfo] = {}
        dict_for_pydantic = {}
        original_annotations: dict[str, Any] = class_dict.get("__annotations__", {})
        pydantic_annotations = {}
        relationship_annotations = {}
        for k, v in class_dict.items():
            if isinstance(v, RelationshipInfo):
                relationships[k] = v
            else:
                dict_for_pydantic[k] = v
        for k, v in original_annotations.items():
            if k in relationships:
                relationship_annotations[k] = v
            else:
                pydantic_annotations[k] = v
        dict_used = {
            **dict_for_pydantic,
            "__infrahub_relationships__": relationships,
            "__annotations__": pydantic_annotations,
        }
        # Duplicate logic from Pydantic to filter config kwargs because if they are
        # passed directly including the registry Pydantic will pass them over to the
        # superclass causing an error
        allowed_config_kwargs: set[str] = {
            key
            for key in dir(BaseConfig)
            if not (key.startswith("__") and key.endswith("__"))  # skip dunder methods and attributes
        }
        config_kwargs = {key: kwargs[key] for key in kwargs.keys() & allowed_config_kwargs}
        new_cls = super().__new__(cls, name, bases, dict_used, **config_kwargs)
        new_cls.__annotations__ = {
            **relationship_annotations,
            **pydantic_annotations,
            **new_cls.__annotations__,
        }

        # def get_config(name: str) -> Any:
        #     config_class_value = new_cls.model_config.get(name, Undefined)
        #     if config_class_value is not Undefined:
        #         return config_class_value
        #     kwarg_value = kwargs.get(name, Undefined)
        #     if kwarg_value is not Undefined:
        #         return kwarg_value
        #     return Undefined

        # new_cls.model_config["generic"] = get_config("generic")

        return new_cls


class SchemaModel(BaseModel, metaclass=InfrahubMetaclass):
    id: str | None = Attribute(default=None, description="The ID of the node")

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
class InfrahubFieldInfo:
    name: str
    types: list[type]
    optional: bool
    default: Any
    field_kind: Literal["attribute", "relationship"] | None = None

    @property
    def primary_type(self) -> type:
        if not self.types:
            raise ValueError("No types found")

        # if isinstance(self.primary_type, ForwardRef):
        #     raise TypeError("Forward References are not supported yet, please ensure the models are defined in the right order")

        if self.is_list:
            return typing.get_args(self.types[0])[0]

        return self.types[0]

    @property
    def is_attribute(self) -> bool:
        if self.field_kind == "attribute":
            return True
        return self.primary_type in KIND_MAPPING

    @property
    def is_relationship(self) -> bool:
        if self.field_kind == "relationship":
            return True
        if isinstance(self.primary_type, ForwardRef):
            return True
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


def analyze_field(field_name: str, field: AttributeInfo | RelationshipInfo | PydanticFieldInfo) -> InfrahubFieldInfo:
    if isinstance(field, RelationshipInfo):
        return InfrahubFieldInfo(
            name=field.alias or field_name,
            types=[field.peer] if field.peer else [],
            optional=field.optional,
            field_kind="relationship",
            default=None,
        )

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
        default=field.default if field.default is not Undefined else None,
    )


def get_attribute_kind(field: AttributeInfo | PydanticFieldInfo) -> AttributeKind:
    if isinstance(field, AttributeInfo) and field.kind:
        return field.kind

    if field.annotation in KIND_MAPPING:
        return KIND_MAPPING[field.annotation]

    if isinstance(field.annotation, UnionType) or (
        hasattr(field.annotation, "_name") and field.annotation._name == "Optional"  # type: ignore[union-attr]
    ):
        valid_types = [t for t in field.annotation.__args__ if t is not type(None)]  # type: ignore[union-attr]
        if len(valid_types) == 1 and valid_types[0] in KIND_MAPPING:
            return KIND_MAPPING[valid_types[0]]

    raise ValueError(f"Unknown field type: {field.annotation}")


def field_to_attribute(
    field_name: str, field_info: InfrahubFieldInfo, field: AttributeInfo | PydanticFieldInfo
) -> AttributeSchema:
    pattern = field._attributes_set.get("pattern", None)
    max_length = field._attributes_set.get("max_length", None)
    min_length = field._attributes_set.get("min_length", None)

    if isinstance(field, AttributeInfo):
        return AttributeSchema(
            name=field_name,
            label=field.label,
            description=field.description,
            kind=get_attribute_kind(field),
            optional=field_info.optional,  # not field.is_required(),
            unique=field.unique,
            branch=field.branch,
            default_value=field_info.default,
            regex=str(pattern) if pattern else None,
            max_length=int(str(max_length)) if max_length else None,
            min_length=int(str(min_length)) if min_length else None,
        )

    return AttributeSchema(
        name=field_name,
        # label=field.label,
        description=field.description,
        kind=get_attribute_kind(field),
        optional=not field.is_required(),
        # unique=field.unique,
        # branch=field.branch,
        default_value=field_info.default,
        regex=str(pattern) if pattern else None,
        max_length=int(str(max_length)) if max_length else None,
        min_length=int(str(min_length)) if min_length else None,
    )


def field_to_relationship(
    field_name: str,
    field_info: InfrahubFieldInfo,
    field: RelationshipInfo | PydanticFieldInfo,
) -> RelationshipSchema:
    if isinstance(field, RelationshipInfo):
        return RelationshipSchema(
            name=field_name,
            description=field.description,
            peer=field.peer or get_kind(field_info.primary_type),
            identifier=field.identifier,
            cardinality="many" if field_info.is_list else "one",
            optional=field_info.optional,
            branch=field.branch,
        )

    return RelationshipSchema(
        name=field_name,
        description=field.description,
        peer=get_kind(field_info.primary_type),
        cardinality="many" if field_info.is_list else "one",
        optional=field_info.optional,
    )


def extract_validate_generic(model: type[BaseModel]) -> list[str]:
    return [get_kind(ancestor) for ancestor in model.__bases__ if issubclass(ancestor, GenericModel)]


def validate_kind(kind: str) -> tuple[str, str]:
    """Validate the kind of a model.

    TODO Move the function to the main module
    """

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


def get_kind(model: type[BaseModel] | ForwardRef) -> str:
    """Get the kind of a model.

    If the model name and namespace are set in model_config, return the full kind.
    If the model namespace is set in model_config, use the name of the class as name.
    If the model has no name or namespace, extract both from the name of the class.
    """

    model_class: type[BaseModel]

    if isinstance(model, type) and issubclass(model, BaseModel):
        model_class = model
    elif isinstance(model, ForwardRef):
        return model.__forward_arg__
    else:
        raise ValueError(f"Expected BaseModel class, got {model}")

    name = model_class.model_config.get("name", None)
    namespace = model_class.model_config.get("namespace", None)
    class_name = model_class.__name__

    if name and namespace:
        return f"{namespace}{name}"
    if namespace and not name and not class_name.startswith(namespace):
        return f"{namespace}{class_name}"

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

    kind = get_kind(model)
    namespace, name = validate_kind(kind)

    if GenericModel in model.__bases__:
        generic = GenericSchema(
            name=name,
            namespace=namespace,
            display_labels=model.model_config.get("display_labels", None),
            description=model.model_config.get("description", None),
            state=model.model_config.get("state", SchemaState.PRESENT),
            label=model.model_config.get("label", None),
            # include_in_menu=generic_schema.include_in_menu if generic_schema else None,
            # menu_placement=generic_schema.menu_placement if generic_schema else None,
            # documentation=generic_schema.documentation if generic_schema else None,
            # order_by=generic_schema.order_by if generic_schema else None,
            # parent=schema.parent if schema else None,
            # children=schema.children if schema else None,
            # icon=generic_schema.icon if generic_schema else None,
            # generate_profile=schema.generate_profile if schema else None,
            # branch=schema.branch if schema else None,
            # default_filter=schema.default_filter if schema else None,
        )
        _add_fields(node=generic, model=model)
        return generic

    # ------------------------------------------------------------
    # NodeSchema
    # ------------------------------------------------------------
    generics = get_generics(model)

    # list all inherited fields with a hash for each to track if they are identical on the node
    inherited_fields = {
        field_name: field._attributes_set for generic in generics for field_name, field in generic.model_fields.items()
    }

    node = NodeSchema(
        name=name,
        namespace=namespace,
        display_labels=model.model_config.get("display_labels", None),
        description=model.model_config.get("description", None),
        state=model.model_config.get("state", SchemaState.PRESENT),
        label=model.model_config.get("label", None),
        # include_in_menu=node_schema.include_in_menu if node_schema else None,
        # menu_placement=node_schema.menu_placement if node_schema else None,
        # documentation=node_schema.documentation if node_schema else None,
        # order_by=node_schema.order_by if node_schema else None,
        inherit_from=[get_kind(generic) for generic in generics],
        # parent=node_schema.parent if node_schema else None,
        # children=node_schema.children if node_schema else None,
        # icon=node_schema.icon if node_schema else None,
        # generate_profile=node_schema.generate_profile if node_schema else None,
        # branch=node_schema.branch if node_schema else None,
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
