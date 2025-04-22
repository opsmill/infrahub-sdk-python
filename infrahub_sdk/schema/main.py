from __future__ import annotations

import warnings
from collections.abc import MutableMapping
from enum import Enum
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Self

if TYPE_CHECKING:
    from ..node import InfrahubNode, InfrahubNodeSync

    InfrahubNodeTypes = Union[InfrahubNode, InfrahubNodeSync]


class RelationshipCardinality(str, Enum):
    ONE = "one"
    MANY = "many"


class BranchSupportType(str, Enum):
    AWARE = "aware"
    AGNOSTIC = "agnostic"
    LOCAL = "local"


class RelationshipKind(str, Enum):
    GENERIC = "Generic"
    ATTRIBUTE = "Attribute"
    COMPONENT = "Component"
    PARENT = "Parent"
    GROUP = "Group"
    HIERARCHY = "Hierarchy"
    PROFILE = "Profile"
    TEMPLATE = "Template"


class RelationshipDirection(str, Enum):
    BIDIR = "bidirectional"
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class AttributeKind(str, Enum):
    ID = "ID"
    TEXT = "Text"
    STRING = "String"  # deprecated
    TEXTAREA = "TextArea"
    DATETIME = "DateTime"
    NUMBER = "Number"
    DROPDOWN = "Dropdown"
    EMAIL = "Email"
    PASSWORD = "Password"  # noqa: S105
    HASHEDPASSWORD = "HashedPassword"
    URL = "URL"
    FILE = "File"
    MAC_ADDRESS = "MacAddress"
    COLOR = "Color"
    BANDWIDTH = "Bandwidth"
    IPHOST = "IPHost"
    IPNETWORK = "IPNetwork"
    BOOLEAN = "Boolean"
    CHECKBOX = "Checkbox"
    LIST = "List"
    JSON = "JSON"
    ANY = "Any"

    def __getattr__(self, name: str) -> Any:
        if name == "STRING":
            warnings.warn(
                f"{name} is deprecated and will be removed in future versions.",
                DeprecationWarning,
                stacklevel=2,
            )
        return super().__getattribute__(name)


class SchemaState(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"


class AllowOverrideType(str, Enum):
    NONE = "none"
    ANY = "any"


class RelationshipDeleteBehavior(str, Enum):
    NO_ACTION = "no-action"
    CASCADE = "cascade"


class AttributeSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str | None = None
    state: SchemaState = SchemaState.PRESENT
    name: str
    kind: AttributeKind
    label: str | None = None
    description: str | None = None
    default_value: Any | None = None
    unique: bool = False
    branch: BranchSupportType | None = None
    optional: bool = False
    choices: list[dict[str, Any]] | None = None
    enum: list[str | int] | None = None
    max_length: int | None = None
    min_length: int | None = None
    regex: str | None = None
    order_weight: int | None = None


class AttributeSchemaAPI(AttributeSchema):
    model_config = ConfigDict(use_enum_values=True)

    inherited: bool = False
    read_only: bool = False
    allow_override: AllowOverrideType = AllowOverrideType.ANY


class RelationshipSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str | None = None
    state: SchemaState = SchemaState.PRESENT
    name: str
    peer: str
    kind: RelationshipKind = RelationshipKind.GENERIC
    label: str | None = None
    description: str | None = None
    identifier: str | None = None
    min_count: int | None = None
    max_count: int | None = None
    direction: RelationshipDirection = RelationshipDirection.BIDIR
    on_delete: RelationshipDeleteBehavior | None = None
    cardinality: str = "many"
    branch: BranchSupportType | None = None
    optional: bool = True
    order_weight: int | None = None


class RelationshipSchemaAPI(RelationshipSchema):
    model_config = ConfigDict(use_enum_values=True)

    inherited: bool = False
    read_only: bool = False
    hierarchical: str | None = None
    allow_override: AllowOverrideType = AllowOverrideType.ANY


class BaseSchemaAttrRel(BaseModel):
    attributes: list[AttributeSchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)


class BaseSchemaAttrRelAPI(BaseModel):
    attributes: list[AttributeSchemaAPI] = Field(default_factory=list)
    relationships: list[RelationshipSchemaAPI] = Field(default_factory=list)

    def get_field(self, name: str, raise_on_error: bool = True) -> AttributeSchemaAPI | RelationshipSchemaAPI | None:
        if attribute_field := self.get_attribute_or_none(name=name):
            return attribute_field

        if relationship_field := self.get_relationship_or_none(name=name):
            return relationship_field

        if not raise_on_error:
            return None

        raise ValueError(f"Unable to find the field {name}")

    def get_attribute(self, name: str) -> AttributeSchemaAPI:
        for item in self.attributes:
            if item.name == name:
                return item
        raise ValueError(f"Unable to find the attribute {name}")

    def get_attribute_or_none(self, name: str) -> AttributeSchemaAPI | None:
        for item in self.attributes:
            if item.name == name:
                return item
        return None

    def get_relationship(self, name: str) -> RelationshipSchemaAPI:
        for item in self.relationships:
            if item.name == name:
                return item
        raise ValueError(f"Unable to find the relationship {name}")

    def get_relationship_or_none(self, name: str) -> RelationshipSchemaAPI | None:
        for item in self.relationships:
            if item.name == name:
                return item
        return None

    def get_relationship_by_identifier(self, id: str, raise_on_error: bool = True) -> RelationshipSchemaAPI | None:
        for item in self.relationships:
            if item.identifier == id:
                return item

        if not raise_on_error:
            return None

        raise ValueError(f"Unable to find the relationship {id}")

    def get_matching_relationship(
        self, id: str, direction: RelationshipDirection = RelationshipDirection.BIDIR
    ) -> RelationshipSchemaAPI:
        valid_direction = RelationshipDirection.BIDIR
        if direction == RelationshipDirection.INBOUND:
            valid_direction = RelationshipDirection.OUTBOUND
        elif direction == RelationshipDirection.OUTBOUND:
            valid_direction = RelationshipDirection.INBOUND
        for item in self.relationships:
            if item.identifier == id and item.direction == valid_direction:
                return item
        raise ValueError(f"Unable to find the relationship {id} / ({valid_direction.value})")

    @property
    def attribute_names(self) -> list[str]:
        return [item.name for item in self.attributes]

    @property
    def relationship_names(self) -> list[str]:
        return [item.name for item in self.relationships]

    @property
    def mandatory_input_names(self) -> list[str]:
        return self.mandatory_attribute_names + self.mandatory_relationship_names

    @property
    def mandatory_attribute_names(self) -> list[str]:
        return [
            item.name
            for item in self.attributes
            if (not item.optional and item.default_value is None) and not item.read_only
        ]

    @property
    def mandatory_relationship_names(self) -> list[str]:
        return [item.name for item in self.relationships if not item.optional]

    @property
    def local_attributes(self) -> list[AttributeSchemaAPI]:
        return [item for item in self.attributes if not item.inherited]

    @property
    def local_relationships(self) -> list[RelationshipSchemaAPI]:
        return [item for item in self.relationships if not item.inherited]

    @property
    def unique_attributes(self) -> list[AttributeSchemaAPI]:
        return [item for item in self.attributes if item.unique]


class BaseSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str | None = None
    state: SchemaState = SchemaState.PRESENT
    name: str
    label: str | None = None
    namespace: str
    description: str | None = None
    include_in_menu: bool | None = None
    menu_placement: str | None = None
    display_labels: list[str] | None = None
    human_friendly_id: list[str] | None = None
    icon: str | None = None
    uniqueness_constraints: list[list[str]] | None = None
    documentation: str | None = None
    order_by: list[str] | None = None

    @property
    def kind(self) -> str:
        return self.namespace + self.name


class GenericSchema(BaseSchema, BaseSchemaAttrRel):
    def convert_api(self) -> GenericSchemaAPI:
        return GenericSchemaAPI(**self.model_dump())


class GenericSchemaAPI(BaseSchema, BaseSchemaAttrRelAPI):
    """A Generic can be either an Interface or a Union depending if there are some Attributes or Relationships defined."""

    hash: str | None = None
    used_by: list[str] = Field(default_factory=list)


class BaseNodeSchema(BaseSchema):
    model_config = ConfigDict(use_enum_values=True)

    inherit_from: list[str] = Field(default_factory=list)
    branch: BranchSupportType | None = None
    default_filter: str | None = None
    generate_profile: bool | None = None
    generate_template: bool | None = None
    parent: str | None = None
    children: str | None = None


class NodeSchema(BaseNodeSchema, BaseSchemaAttrRel):
    def convert_api(self) -> NodeSchemaAPI:
        return NodeSchemaAPI(**self.model_dump())


class NodeSchemaAPI(BaseNodeSchema, BaseSchemaAttrRelAPI):
    hash: str | None = None
    hierarchy: str | None = None


class ProfileSchemaAPI(BaseSchema, BaseSchemaAttrRelAPI):
    inherit_from: list[str] = Field(default_factory=list)


class TemplateSchemaAPI(BaseSchema, BaseSchemaAttrRelAPI):
    inherit_from: list[str] = Field(default_factory=list)


class NodeExtensionSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str | None = None
    kind: str
    description: str | None = None
    label: str | None = None
    inherit_from: list[str] = Field(default_factory=list)
    branch: BranchSupportType | None = None
    default_filter: str | None = None
    attributes: list[AttributeSchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)


class SchemaRoot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    version: str
    generics: list[GenericSchema] = Field(default_factory=list)
    nodes: list[NodeSchema] = Field(default_factory=list)
    node_extensions: list[NodeExtensionSchema] = Field(default_factory=list)

    def to_schema_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_defaults=True)


class SchemaRootAPI(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    main: str | None = None
    generics: list[GenericSchemaAPI] = Field(default_factory=list)
    nodes: list[NodeSchemaAPI] = Field(default_factory=list)
    profiles: list[ProfileSchemaAPI] = Field(default_factory=list)
    templates: list[TemplateSchemaAPI] = Field(default_factory=list)


class BranchSchema(BaseModel):
    hash: str = Field(...)
    nodes: MutableMapping[str, GenericSchemaAPI | NodeSchemaAPI | ProfileSchemaAPI | TemplateSchemaAPI] = Field(
        default_factory=dict
    )

    @classmethod
    def from_api_response(cls, data: MutableMapping[str, Any]) -> Self:
        """
        Convert an API response from /api/schema into a BranchSchema object.
        """
        return cls.from_schema_root_api(data=SchemaRootAPI(**data))

    @classmethod
    def from_schema_root_api(cls, data: SchemaRootAPI) -> Self:
        """
        Convert a SchemaRootAPI object to a BranchSchema object.
        """
        nodes: MutableMapping[str, GenericSchemaAPI | NodeSchemaAPI | ProfileSchemaAPI | TemplateSchemaAPI] = {}
        for node in data.nodes:
            nodes[node.kind] = node

        for generic in data.generics:
            nodes[generic.kind] = generic

        for profile in data.profiles:
            nodes[profile.kind] = profile

        for template in data.templates:
            nodes[template.kind] = template

        schema_hash = data.main or ""

        return cls(hash=schema_hash, nodes=nodes)
