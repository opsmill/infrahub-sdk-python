"""Checks and field lists shared by every query that names its fields with `only`.

The helpers take schemas the caller has already looked up and do no I/O, so the async and the sync
code paths reach the same decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..exceptions import FieldNotFoundError, FieldNotLoadedError, FieldSelectionConflictError
from ..schema import GenericSchemaAPI, NodeSchemaAPI

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from ..schema import MainSchemaTypesAPI

HIERARCHY_FIELD_NAMES: tuple[str, ...] = ("parent", "children", "ancestors", "descendants")

# Every node is requested with its id and display label; "hfid" requests the HFID the server stores.
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
class KindFields:
    """The fields a query with `only` requests on one kind.

    `schema` is the schema of that kind. `hierarchy_kind` is the kind of the peers of the hierarchy fields,
    and is set whenever `hierarchy_fields` is not empty. Every field is listed in a fixed order, so the query
    does not depend on the order of `only`.
    """

    schema: MainSchemaTypesAPI
    attributes: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    hierarchy_fields: tuple[str, ...] = ()
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
    implementing schemas were given. `hfid` is true when the queried node requests the HFID the server
    stores.
    """

    only: tuple[str, ...]
    node: KindFields
    implementing_kinds: Mapping[str, KindFields]
    hfid: bool


@dataclass(frozen=True)
class OnlyPeerRelationships:
    """How the nodes of one kind returned by a query with `only` are marked, and which of their peers are built.

    `marker` goes on each node. `peer_markers` maps each relationship whose peers are built as nodes, in
    the order the query requests them, to the marker of those peers.
    """

    marker: OnlyMarker
    peer_markers: Mapping[str, OnlyMarker]


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


def only_query_fields(
    only: Sequence[str], schema: MainSchemaTypesAPI, implementing_schemas: Iterable[MainSchemaTypesAPI] = ()
) -> OnlyQueryFields:
    """Decide which fields a query with `only` requests, and on which kind.

    `id` and `display_label` add nothing. `hfid` requests the HFID the server stores on the queried node, when
    the kind, or for a generic kind the generic or one of `implementing_schemas`, has an HFID. A field the
    generic has is requested on the generic; any other field goes to the block of each implementing kind
    that has it. On a hierarchical kind, `parent`, `children`, `ancestors` and `descendants` are hierarchy
    fields.

    Raises:
        TypeError: `only` is a string instead of a list of names.
        FieldNotFoundError: a name is not a field of the kind or of any of `implementing_schemas`.
    """
    implementing_schemas = tuple(implementing_schemas)
    check_only_names(only=only, schema=schema, implementing_schemas=implementing_schemas)

    names = [name for name in dict.fromkeys(only) if name not in _ALWAYS_ACCEPTED_NAMES]
    node_names = field_names(schema)
    implementing_kinds: dict[str, KindFields] = {}
    for implementing_schema in implementing_schemas:
        block_names = field_names(implementing_schema)
        kind_fields = _kind_fields(
            implementing_schema, {name for name in names if name not in node_names and name in block_names}
        )
        if not kind_fields.is_empty:
            implementing_kinds[implementing_schema.kind] = kind_fields

    return OnlyQueryFields(
        only=tuple(only),
        node=_kind_fields(schema, {name for name in names if name in node_names}),
        implementing_kinds=implementing_kinds,
        hfid="hfid" in only and any(hfid_schema.human_friendly_id for hfid_schema in (schema, *implementing_schemas)),
    )


def only_peer_relationships(fields: OnlyQueryFields, kind: str, prefetch_relationships: bool) -> OnlyPeerRelationships:
    """Decide how the nodes of `kind` returned by the query `fields` describes are marked, and which peers are built.

    With `prefetch_relationships`, the peers of each named relationship are built as nodes; of the hierarchy
    fields, only `parent` and `children` qualify. A node of an implementing kind also gets the relationships
    of that kind's `...on Kind` block.
    """
    names: dict[str, None] = {}
    if prefetch_relationships:
        for kind_fields in (fields.node, fields.implementing_kinds.get(kind)):
            if kind_fields is None:
                continue
            for name in kind_fields.relationships:
                names[name] = None
            for name in kind_fields.hierarchy_fields:
                if name in _HIERARCHY_PEER_NODE_NAMES:
                    names[name] = None
    return OnlyPeerRelationships(
        marker=OnlyMarker(only=fields.only),
        peer_markers={name: OnlyMarker(only=fields.only, peer_of=f"{kind}.{name}") for name in names},
    )


def _kind_fields(schema: MainSchemaTypesAPI, names: set[str]) -> KindFields:
    hierarchy_kind = _hierarchy_kind(schema)
    hierarchy_names = names.intersection(HIERARCHY_FIELD_NAMES) if hierarchy_kind is not None else set()
    hierarchy_fields = tuple(name for name in HIERARCHY_FIELD_NAMES if name in hierarchy_names)
    return KindFields(
        schema=schema,
        attributes=tuple(name for name in schema.attribute_names if name in names and name not in hierarchy_names),
        relationships=tuple(
            name for name in schema.relationship_names if name in names and name not in hierarchy_names
        ),
        hierarchy_fields=hierarchy_fields,
        hierarchy_kind=hierarchy_kind if hierarchy_fields else None,
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
