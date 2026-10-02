"""Field selection of SDK-generated node queries: the recorded selection, ``only`` validation and selection rules."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ..exceptions import SelectionConflictError, SelectionFieldNotFoundError
from ..schema import GenericSchemaAPI, RelationshipCardinality, RelationshipKind

if TYPE_CHECKING:
    from ..schema import MainSchemaTypesAPI, RelationshipSchemaAPI

IDENTITY_FLOOR_NAMES = frozenset({"id", "hfid", "display_label"})
HIERARCHICAL_FIELD_NAMES = ("parent", "children", "ancestors", "descendants")

_ALWAYS_SELECTED_MANY_KINDS = frozenset({RelationshipKind.ATTRIBUTE, RelationshipKind.PARENT})

# Keys of a peer edge or its node that carry no field value: the peer's identity and the edge's own data.
_PEER_ENVELOPE_KEYS = frozenset(
    {"id", "hfid", "display_label", "__typename", "kind", "node_metadata", "properties", "relationship_metadata"}
)


def _as_tuple(names: Iterable[str] | None) -> tuple[str, ...] | None:
    return None if names is None else tuple(names)


@dataclass(frozen=True)
class Selection:
    """The selection of the SDK-generated query that produced a node.

    ``strict`` is ``True`` when the selection came from ``only``, directly or through a parent query.
    ``peer_of`` names the ``<Kind>.<relationship>`` a peer node was built from, and ``peer_floor`` marks
    a peer that only carries the identity floor.
    """

    only: tuple[str, ...] | None = None
    include: tuple[str, ...] | None = None
    exclude: tuple[str, ...] | None = None
    strict: bool = False
    peer_of: str | None = None
    peer_floor: bool = False

    @classmethod
    def from_args(
        cls,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        only: Iterable[str] | None = None,
    ) -> Selection:
        """Return the selection of a query built from these ``include``, ``exclude`` and ``only`` arguments.

        The selection is strict when ``only`` is given, even as an empty list.
        """
        return cls(
            only=_as_tuple(only),
            include=_as_tuple(include),
            exclude=_as_tuple(exclude),
            strict=only is not None,
        )

    @staticmethod
    def for_peer(parent: Selection, parent_kind: str, rel_name: str, peer_floor: bool = False) -> Selection:
        """Return the selection of a peer built from the ``rel_name`` relationship of a ``parent_kind`` node.

        The peer keeps the arguments and strictness of ``parent``. Set ``peer_floor`` when the peer data carries
        only the identity floor.
        """
        return replace(parent, peer_of=f"{parent_kind}.{rel_name}", peer_floor=peer_floor)

    def describe(self) -> str:
        """Return the label used in messages, such as ``only=['name']`` or ``default selection``."""
        if self.only is not None:
            label = f"only={list(self.only)!r}"
        else:
            parts = []
            if self.include is not None:
                parts.append(f"include={list(self.include)!r}")
            if self.exclude is not None:
                parts.append(f"exclude={list(self.exclude)!r}")
            label = ", ".join(parts) or "default selection"

        if self.peer_of is not None:
            return f"peer of {self.peer_of}, fetched with {label}"
        return label


def carries_identity_only(peer_data: Mapping[str, Any]) -> bool:
    """Return whether a peer edge, or the ``node`` inside it, carries no field beyond the peer's identity."""
    keys = set(peer_data) - {"node"}
    node_data = peer_data.get("node")
    if isinstance(node_data, Mapping):
        keys.update(node_data)
    return keys <= _PEER_ENVELOPE_KEYS


def check_selection_conflict(
    include: Collection[str] | None, exclude: Collection[str] | None, only: Collection[str] | None
) -> None:
    """Reject ``only`` combined with ``include`` or ``exclude``, even when those lists are empty.

    Raises:
        SelectionConflictError: If ``only`` is given together with ``include`` or ``exclude``.

    """
    if only is None:
        return
    conflicting = [name for name, value in (("include", include), ("exclude", exclude)) if value is not None]
    if conflicting:
        raise SelectionConflictError(parameters=["only", *conflicting])


def _field_names(schema: MainSchemaTypesAPI) -> set[str]:
    names = set(schema.attribute_names) | set(schema.relationship_names)
    if schema.supports_hierarchy:
        names.update(HIERARCHICAL_FIELD_NAMES)
    return names


def validate_only(
    only: Iterable[str],
    schema: MainSchemaTypesAPI,
    implementing_schemas: Sequence[MainSchemaTypesAPI],
    fragment: bool,
    kind: str,
) -> None:
    """Check that every name in ``only`` resolves to a field of ``schema``.

    For a generic schema, a name that only the implementing kinds define is accepted when ``fragment`` is set.

    Raises:
        SelectionFieldNotFoundError: If a name resolves nowhere, or only on implementing kinds without ``fragment``.

    """
    valid_names = _field_names(schema) | IDENTITY_FLOOR_NAMES
    is_generic = isinstance(schema, GenericSchemaAPI)

    for name in only:
        if name in valid_names:
            continue
        implementing_kinds = (
            [implementing.kind for implementing in implementing_schemas if name in _field_names(implementing)]
            if is_generic
            else []
        )
        if not implementing_kinds:
            raise SelectionFieldNotFoundError(kind=kind, field=name)
        if not fragment:
            raise SelectionFieldNotFoundError(kind=kind, field=name, implementing_kinds=implementing_kinds)


def requests_identity_only(names: Iterable[str]) -> bool:
    """Return whether ``names``, as a peer query's ``only``, requests nothing beyond the identity a reference holds."""
    return set(names) <= IDENTITY_FLOOR_NAMES


def peer_kind_only(only: Iterable[str], peer_schema: MainSchemaTypesAPI) -> list[str]:
    """Return the names in ``only`` that ``peer_schema`` defines, identity floor names included."""
    valid_names = _field_names(peer_schema) | IDENTITY_FLOOR_NAMES
    return [name for name in only if name in valid_names]


def implementing_kind_only(
    only: Iterable[str], generic_schema: MainSchemaTypesAPI, implementing_schema: MainSchemaTypesAPI
) -> list[str]:
    """Return the names in ``only`` to request in an implementing kind's fragment of a generic query.

    These are the names ``implementing_schema`` defines, inherited fields included, that ``generic_schema`` does not.
    """
    generic_names = _field_names(generic_schema)
    implementing_names = _field_names(implementing_schema)
    return [name for name in only if name not in generic_names and name in implementing_names]


def is_attribute_selected(
    name: str,
    include: Collection[str] | None,  # noqa: ARG001  # kept so every selection helper takes the same arguments
    exclude: Collection[str] | None,
    only: Collection[str] | None,
) -> bool:
    """Return whether the query selects the attribute ``name``.

    With ``only``, the attribute must be named in it. Otherwise every attribute is selected unless ``exclude`` names
    it.
    """
    if only is not None:
        return name in only
    return not (exclude and name in exclude)


def is_relationship_selected(
    rel_schema: RelationshipSchemaAPI,
    include: Collection[str] | None,
    exclude: Collection[str] | None,
    only: Collection[str] | None,
) -> bool:
    """Return whether the query selects the relationship described by ``rel_schema``.

    With ``only``, the relationship must be named in it. Otherwise it is selected unless ``exclude`` names it, and a
    relationship of cardinality many that isn't of kind Attribute or Parent must also be named in ``include``.
    """
    name = rel_schema.name
    if only is not None:
        return name in only
    if exclude and name in exclude:
        return False
    if rel_schema.cardinality == RelationshipCardinality.MANY and rel_schema.kind not in _ALWAYS_SELECTED_MANY_KINDS:
        return bool(include and name in include)
    return True


def should_expand_peer(
    rel_name: str, include: Collection[str] | None, only: Collection[str] | None, prefetch_relationships: bool
) -> bool:
    """Return whether the query requests the fields of the peers of ``rel_name``, not just their identity.

    It does with ``prefetch_relationships``, or without ``only`` when ``include`` names the relationship.
    """
    if prefetch_relationships:
        return True
    return only is None and include is not None and rel_name in include


def is_hierarchical_selected(
    name: str,
    include: Collection[str] | None,
    exclude: Collection[str] | None,
    only: Collection[str] | None,
    prefetch_relationships: bool,
) -> bool:
    """Return whether the query selects the hierarchical field ``name`` (``parent``, ``children``, ...).

    With ``only``, the field must be named in it. Otherwise it is selected when ``prefetch_relationships`` is set or
    ``include`` names it, unless ``exclude`` names it.
    """
    if only is not None:
        return name in only
    if exclude and name in exclude:
        return False
    return prefetch_relationships or (include is not None and name in include)
