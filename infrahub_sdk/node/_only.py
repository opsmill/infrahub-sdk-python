"""Checks and field lists shared by every query that names its fields with `only`.

The helpers take schemas the caller has already looked up and do no I/O, so the async and the sync
code paths reach the same decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..exceptions import FieldNotFoundError, FieldNotLoadedError, FieldSelectionConflictError
from ..schema import GenericSchemaAPI, NodeSchemaAPI

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from ..schema import MainSchemaTypesAPI

HIERARCHY_FIELD_NAMES: tuple[str, ...] = ("parent", "children", "ancestors", "descendants")

# Every node is requested with its id and display label; "hfid" stands for the fields of the kind's HFID.
_ALWAYS_ACCEPTED_NAMES = frozenset({"id", "display_label", "hfid"})

# Like the default prefetch, only the hierarchy fields that are schema relationships get peer nodes.
_HIERARCHY_PEER_NODE_NAMES = frozenset({"parent", "children"})


@dataclass(frozen=True)
class OnlyMarker:
    """Marks a node built from a query with `only`, so reading a field it does not carry raises.

    `peer_of` is `None` for the nodes the query returned, and `"Kind.relationship"` for a peer
    returned with them.
    """

    only: tuple[str, ...]
    peer_of: str | None = None

    def not_loaded_error(self, kind: str, field: str) -> FieldNotLoadedError:
        """Build the error for reading `field` on a node of `kind` that carries this marker."""
        return FieldNotLoadedError(kind=kind, field=field, only=self.only, peer_of=self.peer_of)


@dataclass(frozen=True)
class HfidFields:
    """The fields a query needs so that a kind's human-friendly ID can be calculated.

    `attributes` are requested on the node. `relationships` maps each relationship to the peer
    attributes to request with it; an empty tuple means the relationship is requested as a reference
    only. Both keep the order of the HFID paths, without duplicates.
    """

    attributes: tuple[str, ...]
    relationships: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class KindFields:
    """The fields a query with `only` requests on one kind.

    `schema` is the schema of that kind. `relationships` and `hierarchy_fields` map each field to the peer
    attributes to request with it; an empty tuple means the field is requested as a reference only. `named`
    holds the relationships and hierarchy fields named in `only`, which are the only ones whose peers get
    their default fields with `prefetch_relationships`; the others are requested for the HFID alone.
    `hierarchy_kind` is the kind whose fields the peers of the hierarchy fields get, and is set whenever
    `hierarchy_fields` is not empty. Every field is listed in a fixed order, so the query does not depend
    on the order of `only`.
    """

    schema: MainSchemaTypesAPI
    attributes: tuple[str, ...] = ()
    relationships: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    hierarchy_fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    named: frozenset[str] = frozenset()
    hierarchy_kind: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.attributes or self.relationships or self.hierarchy_fields)


@dataclass(frozen=True)
class OnlyQueryFields:
    """Where a query with `only` requests each field.

    `only` is the list the query was built from, as given. `node` holds the fields requested on the
    queried kind. For a generic kind, `implementing_kinds` maps each implementing kind that needs fields
    the generic does not have to the fields requested in its `...on Kind` block, in the order the
    implementing schemas were given.
    """

    only: tuple[str, ...]
    node: KindFields
    implementing_kinds: Mapping[str, KindFields]


@dataclass(frozen=True)
class OnlyPeerRelationships:
    """How the nodes of one kind returned by a query with `only` are marked, and which of their peers are built.

    `marker` goes on each node. `peer_markers` maps each relationship whose peers are built as nodes, in
    the order the query requests them, to the marker of those peers. `hfid` holds the relationships
    requested for the node's HFID, whose peers the node keeps so that its HFID does not depend on the store.
    """

    marker: OnlyMarker
    peer_markers: Mapping[str, OnlyMarker]
    hfid: frozenset[str]


def check_only_conflict(
    only: Sequence[str] | None, include: Sequence[str] | None, exclude: Sequence[str] | None
) -> None:
    """Reject `only` combined with `include` or `exclude`, even when either is an empty list.

    Raises:
        FieldSelectionConflictError: `only` is not `None` and `include` or `exclude` is not `None`.
    """
    if only is not None and (include is not None or exclude is not None):
        raise FieldSelectionConflictError


def field_names(schema: MainSchemaTypesAPI) -> frozenset[str]:
    """The fields `only` can name on one kind, not counting the fields of its implementing kinds.

    These are the kind's attributes and relationships, plus the four hierarchy fields when the kind
    is a node with a hierarchy or a hierarchical generic.
    """
    names = {*schema.attribute_names, *schema.relationship_names}
    if _is_hierarchical(schema):
        names.update(HIERARCHY_FIELD_NAMES)
    return frozenset(names)


def check_only_names(
    only: Sequence[str], schema: MainSchemaTypesAPI, implementing_schemas: Iterable[MainSchemaTypesAPI] = ()
) -> None:
    """Reject the first name in `only` that is neither an identifier nor a field of the kind.

    For a generic kind, pass the schemas of the kinds that implement it: a name is accepted when the
    generic or any of those kinds has it.

    Raises:
        TypeError: `only` is a string instead of a list of names.
        FieldNotFoundError: a name is not accepted; it names that field and `schema.kind`.
    """
    if isinstance(only, str):
        raise TypeError("only must be a list of field names, not a string")
    accepted = set(field_names(schema))
    for implementing_schema in implementing_schemas:
        accepted.update(field_names(implementing_schema))
    for name in only:
        if name not in accepted and name not in _ALWAYS_ACCEPTED_NAMES:
            raise FieldNotFoundError(kind=schema.kind, field=name)


def check_only_names_on_every_kind(only: Sequence[str], schemas: Iterable[MainSchemaTypesAPI]) -> None:
    """Reject `only` unless every kind in `schemas` has every name in it.

    Raises:
        FieldNotFoundError: a name is missing on one of the kinds; it names that field and that kind.
    """
    for schema in schemas:
        check_only_names(only=only, schema=schema)


def expand_hfid(schema: MainSchemaTypesAPI) -> HfidFields:
    """The fields a query must fetch for the kind's HFID, which the SDK calculates instead of reading the server's.

    A relationship path (`location__name__value`) gives the relationship plus the peer attribute; an
    attribute path (`name__value`) gives the attribute. For a generic kind, call it per implementing kind.
    """
    attributes: list[str] = []
    relationships: dict[str, list[str]] = {}
    for path in schema.human_friendly_id or []:
        first, *rest = path.split("__")
        if first in schema.relationship_names:
            peer_attributes = relationships.setdefault(first, [])
            if rest and rest[0] not in peer_attributes:
                peer_attributes.append(rest[0])
        elif first in schema.attribute_names and first not in attributes:
            attributes.append(first)
    return HfidFields(
        attributes=tuple(attributes),
        relationships={name: tuple(peer_attributes) for name, peer_attributes in relationships.items()},
    )


def only_query_fields(
    only: Sequence[str], schema: MainSchemaTypesAPI, implementing_schemas: Iterable[MainSchemaTypesAPI] = ()
) -> OnlyQueryFields:
    """Decide which fields a query with `only` requests, and on which kind.

    `id` and `display_label` add nothing. `hfid` adds the fields of the HFID of the queried kind, or for
    a generic kind of each implementing kind; a relationship it adds carries only the peer attributes
    the HFID needs. A field the generic has is requested on the generic; any other field goes to the
    block of each implementing kind that has it (or whose HFID uses it).
    On a hierarchical kind, `parent`, `children`, `ancestors` and `descendants` are hierarchy fields.

    Raises:
        TypeError: `only` is a string instead of a list of names.
        FieldNotFoundError: a name is not a field of the kind or of any of `implementing_schemas`.
    """
    implementing_schemas = tuple(implementing_schemas)
    check_only_names(only=only, schema=schema, implementing_schemas=implementing_schemas)

    node = _KindFieldsBuilder(schema)
    blocks = {implementing.kind: _KindFieldsBuilder(implementing) for implementing in implementing_schemas}
    for name in dict.fromkeys(only):
        if name in _ALWAYS_ACCEPTED_NAMES:
            continue
        if node.has(name):
            node.add(name)
            continue
        for block in blocks.values():
            if block.has(name):
                block.add(name)

    if "hfid" in only:
        hfid_schemas = implementing_schemas if isinstance(schema, GenericSchemaAPI) else (schema,)
        for hfid_schema in hfid_schemas:
            owner = blocks.get(hfid_schema.kind, node)
            hfid = expand_hfid(hfid_schema)
            for name in hfid.attributes:
                (node if node.has(name) else owner).add(name, named=False)
            for name, peer_attributes in hfid.relationships.items():
                (node if node.has(name) else owner).add(name, peer_attributes, named=False)

    implementing_kinds = {kind: block.build() for kind, block in blocks.items()}
    return OnlyQueryFields(
        only=tuple(only),
        node=node.build(),
        implementing_kinds={kind: fields for kind, fields in implementing_kinds.items() if not fields.is_empty},
    )


def only_peer_relationships(fields: OnlyQueryFields, kind: str, prefetch_relationships: bool) -> OnlyPeerRelationships:
    """Decide how the nodes of `kind` returned by the query `fields` describes are marked, and which peers are built.

    A relationship's peers are built as nodes when they carry attributes the HFID needs, or when the
    relationship is named in `only` and the query prefetches relationships. Of the hierarchy fields, only
    `parent` and `children` qualify. A node of an implementing kind also gets the relationships of that
    kind's `...on Kind` block.
    """
    names: dict[str, None] = {}
    hfid: set[str] = set()
    for kind_fields in (fields.node, fields.implementing_kinds.get(kind)):
        if kind_fields is None:
            continue
        hierarchy_fields = {
            name: peer_attributes
            for name, peer_attributes in kind_fields.hierarchy_fields.items()
            if name in _HIERARCHY_PEER_NODE_NAMES
        }
        for name, peer_attributes in {**kind_fields.relationships, **hierarchy_fields}.items():
            if peer_attributes:
                hfid.add(name)
                names[name] = None
            elif prefetch_relationships and name in kind_fields.named:
                names[name] = None
    return OnlyPeerRelationships(
        marker=OnlyMarker(only=fields.only),
        peer_markers={name: OnlyMarker(only=fields.only, peer_of=f"{kind}.{name}") for name in names},
        hfid=frozenset(hfid),
    )


class _KindFieldsBuilder:
    def __init__(self, schema: MainSchemaTypesAPI) -> None:
        self._schema = schema
        self._names = field_names(schema)
        self._hierarchy_kind = _hierarchy_kind(schema)
        self._attributes: set[str] = set()
        self._relationships: dict[str, list[str]] = {}
        self._hierarchy_fields: dict[str, list[str]] = {}
        self._named: set[str] = set()

    def has(self, name: str) -> bool:
        return name in self._names

    def add(self, name: str, peer_attributes: Iterable[str] = (), named: bool = True) -> None:
        if self._hierarchy_kind is not None and name in HIERARCHY_FIELD_NAMES:
            requested = self._hierarchy_fields.setdefault(name, [])
        elif name in self._schema.attribute_names:
            self._attributes.add(name)
            return
        else:
            requested = self._relationships.setdefault(name, [])
        if named:
            self._named.add(name)
        for peer_attribute in peer_attributes:
            if peer_attribute not in requested:
                requested.append(peer_attribute)

    def build(self) -> KindFields:
        return KindFields(
            schema=self._schema,
            attributes=tuple(name for name in self._schema.attribute_names if name in self._attributes),
            relationships={
                name: tuple(self._relationships[name])
                for name in self._schema.relationship_names
                if name in self._relationships
            },
            hierarchy_fields={
                name: tuple(self._hierarchy_fields[name])
                for name in HIERARCHY_FIELD_NAMES
                if name in self._hierarchy_fields
            },
            named=frozenset(self._named),
            hierarchy_kind=self._hierarchy_kind if self._hierarchy_fields else None,
        )


def _hierarchy_kind(schema: MainSchemaTypesAPI) -> str | None:
    """The hierarchical generic the kind's hierarchy is defined on; a hierarchical generic is its own."""
    if isinstance(schema, NodeSchemaAPI):
        return schema.hierarchy
    if isinstance(schema, GenericSchemaAPI) and schema.hierarchical:
        return schema.kind
    return None


def _is_hierarchical(schema: MainSchemaTypesAPI) -> bool:
    return _hierarchy_kind(schema) is not None
