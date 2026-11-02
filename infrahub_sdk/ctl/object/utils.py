"""Shared utilities for end-user CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrahub_sdk.exceptions import FeatureNotSupportedError, NodeNotFoundError
from infrahub_sdk.node.constants import INLINE_INPUT_REASON, _peers_are_inline_input
from infrahub_sdk.schema import NodeSchemaAPI
from infrahub_sdk.utils import is_valid_uuid

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode
    from infrahub_sdk.schema import MainSchemaTypesAPI


async def resolve_node(
    client: InfrahubClient,
    kind: str,
    identifier: str,
    schema: MainSchemaTypesAPI | None = None,
    branch: str | None = None,
) -> InfrahubNode:
    """Resolve a node by identifier, trying multiple lookup strategies.

    Lookup order:
    1. UUID — if the identifier looks like a valid UUID.
    2. Default filter — if the schema defines a ``default_filter``
       (e.g., ``name__value``), use it as a keyword filter.
    3. HFID — if the schema defines a ``human_friendly_id``, treat
       the identifier as HFID components (split on ``/`` for
       multi-component HFIDs, or as a single component).

    Args:
        client: Initialised async Infrahub client.
        kind: Infrahub schema kind.
        identifier: UUID, display name, or HFID string.
        schema: Pre-fetched schema (fetched if not provided).
        branch: Optional target branch.

    Returns:
        The resolved InfrahubNode.

    Raises:
        NodeNotFoundError: If no lookup strategy finds the node.

    """
    if schema is None:
        schema = await client.schema.get(kind=kind, branch=branch)

    # 1. UUID
    if is_valid_uuid(identifier):
        return await client.get(kind=kind, id=identifier, branch=branch)

    # 2. Default filter
    if isinstance(schema, NodeSchemaAPI) and schema.default_filter:
        filters: dict[str, Any] = {schema.default_filter: identifier}
        node = await client.get(
            kind=kind,
            branch=branch,
            raise_when_missing=False,
            **filters,
        )
        if node is not None:
            return node

    # 3. HFID (single or multi-component separated by /)
    if isinstance(schema, NodeSchemaAPI) and schema.human_friendly_id:
        hfid_parts = identifier.split("/") if "/" in identifier else [identifier]
        node = await client.get(
            kind=kind,
            hfid=hfid_parts,
            branch=branch,
            raise_when_missing=False,
        )
        if node is not None:
            return node

    raise NodeNotFoundError(node_type=kind, identifier={"id": [identifier]}, branch_name=branch)


def prepare_relationship_data(data: dict[str, Any], schema: MainSchemaTypesAPI) -> dict[str, Any]:
    """Convert relationship values in a data dict to SDK-compatible format.

    Instead of resolving relationship values to UUIDs via round-trips,
    this converts them to a format the SDK natively understands:

    - UUID strings → passed through (SDK wraps as ``{"id": uuid}``)
    - Non-UUID strings → converted to HFID list (SDK wraps as ``{"hfid": [...]}``)
    - Lists → passed through (for cardinality-many HFID arrays)
    - Dicts → passed through

    Attribute values are left unchanged.

    Args:
        data: Parsed data from ``--set`` arguments.
        schema: Schema for the kind being created/updated.

    Returns:
        A new dict with relationship values in SDK-compatible format.

    """
    rel_names = schema.relationship_names
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key not in rel_names:
            result[key] = value
            continue
        result[key] = _to_relationship_value(value)
    return result


def _to_relationship_value(value: Any) -> Any:
    """Convert a user-provided value to SDK-compatible relationship format.

    Args:
        value: The raw value from the CLI (string, list, or dict).

    Returns:
        A value suitable for passing to the SDK's node constructor.

    """
    if isinstance(value, (dict, list)):
        return value
    str_value = str(value)
    if is_valid_uuid(str_value):
        return str_value
    # Treat as HFID — split on / for multi-component HFIDs
    return str_value.split("/") if "/" in str_value else [str_value]


def _names_peers_by_reference(value: Any) -> bool:
    """Return whether a ``--set`` value points at existing peers instead of carrying their fields.

    ``--set`` reads a value between brackets as JSON, so a list of objects carries the fields of
    each peer. Every other shape names peers: a UUID, an HFID, or a list of either.
    """
    return not isinstance(value, list) or any(not isinstance(item, dict) for item in value)


def _inline_peer_relationships(data: dict[str, Any], schema: MainSchemaTypesAPI) -> list[tuple[str, Any, str]]:
    """Return the key, the value and the peer kind of every relationship whose mutation takes the peers' fields."""
    found = []
    for key, value in data.items():
        rel_schema = schema.get_relationship_or_none(key)
        if rel_schema and _peers_are_inline_input(rel_schema):
            found.append((key, value, rel_schema.peer))
    return found


def raise_if_set_names_inline_peers_by_reference(data: dict[str, Any], schema: MainSchemaTypesAPI) -> None:
    """Refuse a reference to a peer whose fields the mutation takes, before the node is created.

    The fields themselves are what the mutation takes, so a list of objects goes through.

    Args:
        data: Parsed data from ``--set`` arguments.
        schema: Schema for the kind being created.

    Raises:
        FeatureNotSupportedError: If such a relationship is given a reference.

    """
    for key, value, peer in _inline_peer_relationships(data, schema):
        if _names_peers_by_reference(value):
            raise FeatureNotSupportedError(
                f"'{key}' cannot be set with --set to a reference, because "
                f"{INLINE_INPUT_REASON.format(peer=peer)}. Pass the fields of every {peer} instead, "
                f"as a JSON list of objects."
            )


def raise_if_set_edits_inline_peers(data: dict[str, Any], schema: MainSchemaTypesAPI) -> None:
    """Refuse every value for a relationship whose mutation takes the peers' fields, before any change is applied.

    An update sends the peers the node was fetched with, so a value given here never reaches Infrahub,
    whether it names the peers or carries their fields.

    Args:
        data: Parsed data from ``--set`` arguments.
        schema: Schema for the kind being updated.

    Raises:
        FeatureNotSupportedError: If a key names such a relationship.

    """
    for key, _value, peer in _inline_peer_relationships(data, schema):
        raise FeatureNotSupportedError(
            f"'{key}' cannot be changed with --set, because {INLINE_INPUT_REASON.format(peer=peer)}. "
            f"To set the complete list, run infrahubctl object create with it, which upserts the node. "
            f"To add, change or delete one, run infrahubctl object create, update or delete on the "
            f"{peer} node itself."
        )
