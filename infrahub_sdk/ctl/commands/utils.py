"""Shared utilities for end-user CLI commands."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from infrahub_sdk.exceptions import NodeNotFoundError, SchemaNotFoundError
from infrahub_sdk.schema import NodeSchemaAPI
from infrahub_sdk.utils import is_valid_uuid

logger = logging.getLogger(__name__)

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

    # Nothing found — raise with a helpful error via the standard path
    return await client.get(kind=kind, id=identifier, branch=branch)


async def resolve_relationship_values(
    client: InfrahubClient,
    data: dict[str, Any],
    schema: MainSchemaTypesAPI,
    branch: str | None = None,
) -> dict[str, Any]:
    """Resolve relationship string values in a data dict to node IDs.

    For each key that is a relationship name in the schema, attempts to
    look up the target node by the string value (using the relationship's
    peer kind). The value is replaced with ``{"id": "<uuid>"}`` so the
    SDK can create/update the node correctly.

    Attribute values are passed through unchanged.

    Args:
        client: Initialised async Infrahub client.
        data: Parsed data from ``--set`` arguments.
        schema: Schema for the kind being created/updated.
        branch: Optional target branch.

    Returns:
        A new dict with relationship values resolved to ID references.
    """
    resolved: dict[str, Any] = {}

    for key, value in data.items():
        if key not in schema.relationship_names:
            resolved[key] = value
            continue

        # Already a dict (e.g. {"id": "uuid"}) — pass through
        if isinstance(value, dict):
            resolved[key] = value
            continue

        str_value = str(value)
        rel_schema = schema.get_relationship(key)
        peer_kind = rel_schema.peer

        # Try to resolve the string value as a node identifier.
        # Only fall back to generic peer search on lookup-miss errors;
        # re-raise auth, network, and other unexpected errors.
        try:
            peer_node = await resolve_node(client, peer_kind, str_value, branch=branch)
            resolved[key] = {"id": peer_node.id}
        except (NodeNotFoundError, SchemaNotFoundError, ValueError, IndexError):
            node = await _search_generic_peer(client, str_value, branch=branch)
            if node is not None:
                resolved[key] = {"id": node.id}
            else:
                resolved[key] = value

    return resolved


async def _search_generic_peer(
    client: InfrahubClient,
    identifier: str,
    branch: str | None = None,
) -> InfrahubNode | None:
    """Search across all node schemas for a node matching the identifier.

    Used as a fallback when the relationship peer is a generic type
    and the direct lookup fails.

    Args:
        client: Initialised async Infrahub client.
        identifier: Display name or HFID to search for.
        branch: Optional target branch.

    Returns:
        The matched node, or None if not found.
    """
    all_schemas = await client.schema.all(branch=branch)
    hfid_parts = identifier.split("/") if "/" in identifier else [identifier]

    for schema in all_schemas.values():
        if not isinstance(schema, NodeSchemaAPI):
            continue

        # Try default_filter first
        if schema.default_filter:
            try:
                filters: dict[str, Any] = {schema.default_filter: identifier}
                node = await client.get(  # type: ignore[arg-type]
                    kind=schema.kind,
                    branch=branch,
                    raise_when_missing=False,
                    **filters,
                )
                if node is not None:
                    return node
            except Exception:
                logger.debug("Failed default_filter for %r via %s", identifier, schema.kind)

        # Try HFID
        if schema.human_friendly_id:
            try:
                node = await client.get(
                    kind=schema.kind,
                    hfid=hfid_parts,
                    branch=branch,
                    raise_when_missing=False,
                )
                if node is not None:
                    return node
            except Exception:
                logger.debug("Failed HFID for %r via %s", identifier, schema.kind)

    return None
