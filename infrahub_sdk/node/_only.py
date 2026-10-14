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

# Every node is requested with its id and display label; "hfid" stands for the fields of the kind's HFID.
_ALWAYS_ACCEPTED_NAMES = frozenset({"id", "display_label", "hfid"})


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
        FieldNotFoundError: a name is not accepted; it names that field and `schema.kind`.
    """
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
    """The fields named by the kind's own `human_friendly_id` paths, read the way the HFID is calculated.

    A path whose first part is a relationship (`location`, `location__name`, `location__name__value`)
    gives that relationship, with the peer attribute when the path has one. A path whose first part
    is an attribute (`name`, `name__value`) gives that attribute. Any other path gives nothing. For a
    generic kind, call it once per implementing kind, since each of them may define its own HFID.
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


def _is_hierarchical(schema: MainSchemaTypesAPI) -> bool:
    if isinstance(schema, NodeSchemaAPI):
        return schema.hierarchy is not None
    if isinstance(schema, GenericSchemaAPI):
        return schema.hierarchical
    return False
