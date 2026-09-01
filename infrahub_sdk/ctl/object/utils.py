"""Shared utilities for end-user CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrahub_sdk.exceptions import NodeNotFoundError
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

    raise NodeNotFoundError(
        branch_name=branch or client.default_branch,
        node_type=kind,
        identifier={"id": [identifier]},
    )


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
