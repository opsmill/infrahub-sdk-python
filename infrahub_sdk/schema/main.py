from __future__ import annotations

from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Self

from .generated.enums import (
    AllowOverrideType,
    AttributeKind,
    BranchSupportType,
    ComputedAttributeKind,
    RelationshipCardinality,
    RelationshipDeleteBehavior,
    RelationshipDirection,
    RelationshipKind,
    SchemaAttributeDisplay,
    SchemaState,
)
from .generated.read import (
    AttributeSchemaBaseRead,
    ComputedAttributeRead,  # noqa: F401  (re-exported here to resolve the inherited forward reference)
    GenericSchemaRead,
    NodeSchemaRead,
    ProfileSchemaRead,
    RelationshipSchemaRead,
    TemplateSchemaRead,
)
from .generated.write import (
    AttributeSchemaBaseWrite,
    ComputedAttributeWrite,  # noqa: F401  (re-exported here to resolve the inherited forward reference)
    GenericSchemaWrite,
    NodeSchemaWrite,
    RelationshipSchemaWrite,
)

if TYPE_CHECKING:
    from ..node import InfrahubNode, InfrahubNodeSync

    InfrahubNodeTypes = InfrahubNode | InfrahubNodeSync

# The enum classes and the generated write/read data models now live in the generated modules.
# ``main.py`` keeps the public names stable by re-exporting the enums and by pairing the generated
# data models with the hand-written behavior mixins below. The historical import paths
# (``from infrahub_sdk.schema.main import AttributeKind, NodeSchema, ...``) keep working.
__all__ = [
    "AllowOverrideType",
    "AttributeKind",
    "AttributeSchema",
    "AttributeSchemaAPI",
    "BranchSchema",
    "BranchSupportType",
    "ComputedAttributeKind",
    "GenericSchema",
    "GenericSchemaAPI",
    "NodeExtensionSchema",
    "NodeSchema",
    "NodeSchemaAPI",
    "ProfileSchemaAPI",
    "RelationshipCardinality",
    "RelationshipDeleteBehavior",
    "RelationshipDirection",
    "RelationshipKind",
    "RelationshipSchema",
    "RelationshipSchemaAPI",
    "SchemaAttributeDisplay",
    "SchemaRoot",
    "SchemaRootAPI",
    "SchemaState",
    "TemplateSchemaAPI",
]


# ---------------------------------------------------------------------------
# Behavior mixins
#
# These carry the hand-written helper methods that the generated data models do not provide.
# They are plain (non-pydantic) classes: they declare no fields, so pydantic never treats them as
# model bases. The ``TYPE_CHECKING`` annotations only inform the type checker which fields the
# concrete model they are mixed into is guaranteed to expose.
# ---------------------------------------------------------------------------


class _SchemaKindMixin:
    """``kind`` and capability flags shared by node/generic/profile/template schemas."""

    if TYPE_CHECKING:
        name: str
        namespace: str
        inherit_from: list[str]

    @property
    def kind(self) -> str:
        return self.namespace + self.name

    @property
    def supports_artifact_definition(self) -> bool:
        """Returns True if this schema represents CoreArtifactDefinition. Only meaningful for NodeSchemaAPI."""
        return self.kind == "CoreArtifactDefinition"

    @property
    def supports_artifacts(self) -> bool:
        """Return True if this schema supports artifact operations via CoreArtifactTarget inheritance.

        Only NodeSchemaAPI overrides this; all other schema types return False by design because
        artifact capability is tied to node inheritance, not profiles, templates, or generics.
        """
        return False

    @property
    def supports_file_object(self) -> bool:
        """Return True if this schema supports file object operations via CoreFileObject inheritance.

        Only NodeSchemaAPI overrides this; all other schema types return False by design because
        file object capability is tied to node inheritance, not profiles, templates, or generics.
        """
        return False

    @property
    def supports_hierarchy(self) -> bool:
        """Returns True if this schema participates in a hierarchy. Only NodeSchemaAPI overrides this."""
        return False

    @property
    def hierarchical_relationship_schemas(self) -> list[RelationshipSchemaAPI]:
        """Return pseudo-schemas for parent/children/ancestors/descendants if hierarchy is set.

        Only NodeSchemaAPI overrides this; all other schema types return an empty list.
        """
        return []


class _CardinalityMixin:
    """Cardinality helpers for the relationship read model."""

    if TYPE_CHECKING:
        cardinality: RelationshipCardinality

    @property
    def cardinality_is_one(self) -> bool:
        return self.cardinality == RelationshipCardinality.ONE

    @property
    def cardinality_is_many(self) -> bool:
        return self.cardinality == RelationshipCardinality.MANY


class _SchemaAttrRelMixin:
    """The attribute/relationship lookup helpers used across the SDK, backend and ``infrahubctl``."""

    if TYPE_CHECKING:
        attributes: list[AttributeSchemaAPI]
        relationships: list[RelationshipSchemaAPI]

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


# ---------------------------------------------------------------------------
# Write models (user-facing construction entry points)
# ---------------------------------------------------------------------------


class AttributeSchema(AttributeSchemaBaseWrite):
    """Thin, constructible attribute model kept for backward compatibility.

    ``AttributeSchemaWrite`` (from the generated module) is a non-constructible discriminated union.
    This class keeps ``AttributeSchema(name=..., kind=AttributeKind.TEXT, ...)`` working by exposing
    the shared write base plus a permissive ``parameters``/``choices``. ``extra="forbid"`` from the
    base is relaxed here so the historical construction keyword arguments keep working.
    """

    model_config = ConfigDict(use_enum_values=True)

    choices: list[dict[str, Any]] | None = None
    parameters: dict[str, Any] | None = None


class RelationshipSchema(RelationshipSchemaWrite):
    """Constructible relationship write model (kept as a distinct public name)."""


class NodeSchema(NodeSchemaWrite, _SchemaKindMixin):
    # ``attributes`` accepts the constructible ``AttributeSchema`` (the generated discriminated union
    # cannot be built from an ``AttributeSchema`` instance); dumping still validates server-side.
    # ``relationships`` keeps the historical constructible ``RelationshipSchema`` item type.
    attributes: list[AttributeSchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)

    def convert_api(self) -> NodeSchemaAPI:
        return NodeSchemaAPI(**self.model_dump())


class GenericSchema(GenericSchemaWrite, _SchemaKindMixin):
    attributes: list[AttributeSchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)

    def convert_api(self) -> GenericSchemaAPI:
        return GenericSchemaAPI(**self.model_dump())


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


# ---------------------------------------------------------------------------
# Read models (``*API``) -- concrete subclasses so ``isinstance`` keeps working
# ---------------------------------------------------------------------------


class AttributeSchemaAPI(AttributeSchemaBaseRead):
    """Thin, constructible read-side attribute model kept for backward compatibility.

    ``AttributeSchemaRead`` (from the generated module) is a non-constructible discriminated union.
    This class keeps ``AttributeSchemaAPI(name=..., kind=..., ...)`` working and is used as the item
    type on the read schema models. It exposes the shared read base plus a permissive
    ``parameters``/``choices``. No code performs ``isinstance`` on it.
    """

    model_config = ConfigDict(use_enum_values=True)

    choices: list[dict[str, Any]] | None = None
    parameters: dict[str, Any] | None = None


class RelationshipSchemaAPI(RelationshipSchemaRead, _CardinalityMixin):
    pass


class NodeSchemaAPI(NodeSchemaRead, _SchemaAttrRelMixin, _SchemaKindMixin):
    hash: str | None = None
    # Narrow the attribute/relationship item types to the API variants so the behavior helpers
    # (``cardinality_is_*``, ``inherited`` filtering, ...) are available on the returned items.
    attributes: list[AttributeSchemaAPI] = Field(default_factory=list)
    relationships: list[RelationshipSchemaAPI] = Field(default_factory=list)

    @property
    def supports_artifacts(self) -> bool:
        return "CoreArtifactTarget" in self.inherit_from

    @property
    def supports_file_object(self) -> bool:
        return "CoreFileObject" in self.inherit_from

    @property
    def supports_hierarchy(self) -> bool:
        return self.hierarchy is not None

    @property
    def hierarchical_relationship_schemas(self) -> list[RelationshipSchemaAPI]:
        if self.hierarchy is None:
            return []
        return [
            RelationshipSchemaAPI(
                name="parent",
                peer=self.hierarchy,
                kind=RelationshipKind.HIERARCHY,
                cardinality=RelationshipCardinality.ONE,
                optional=True,
            ),
            RelationshipSchemaAPI(
                name="children",
                peer=self.hierarchy,
                kind=RelationshipKind.HIERARCHY,
                cardinality=RelationshipCardinality.MANY,
                optional=True,
            ),
            RelationshipSchemaAPI(
                name="ancestors",
                peer=self.hierarchy,
                cardinality=RelationshipCardinality.MANY,
                read_only=True,
                optional=True,
            ),
            RelationshipSchemaAPI(
                name="descendants",
                peer=self.hierarchy,
                cardinality=RelationshipCardinality.MANY,
                read_only=True,
                optional=True,
            ),
        ]


class GenericSchemaAPI(GenericSchemaRead, _SchemaAttrRelMixin, _SchemaKindMixin):
    """A Generic can be either an Interface or a Union depending if there are some Attributes or Relationships defined."""

    hash: str | None = None
    attributes: list[AttributeSchemaAPI] = Field(default_factory=list)
    relationships: list[RelationshipSchemaAPI] = Field(default_factory=list)


class ProfileSchemaAPI(ProfileSchemaRead, _SchemaAttrRelMixin, _SchemaKindMixin):
    attributes: list[AttributeSchemaAPI] = Field(default_factory=list)
    relationships: list[RelationshipSchemaAPI] = Field(default_factory=list)


class TemplateSchemaAPI(TemplateSchemaRead, _SchemaAttrRelMixin, _SchemaKindMixin):
    attributes: list[AttributeSchemaAPI] = Field(default_factory=list)
    relationships: list[RelationshipSchemaAPI] = Field(default_factory=list)


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
        """Convert an API response from /api/schema into a BranchSchema object."""
        return cls.from_schema_root_api(data=SchemaRootAPI(**data))

    @classmethod
    def from_schema_root_api(cls, data: SchemaRootAPI) -> Self:
        """Convert a SchemaRootAPI object to a BranchSchema object."""
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
