"""Refusals for a relationship whose mutation takes the fields of its peers, for ``--set``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node.inline_peers import INLINE_INPUT_REASON, PEER_REFERENCE_KEYS, peers_are_inline_input

if TYPE_CHECKING:
    from infrahub_sdk.schema import MainSchemaTypesAPI


def _names_peers_by_reference(value: Any) -> bool:
    """Return whether a ``--set`` value points at existing peers instead of carrying their fields.

    ``--set`` reads a value between brackets as JSON, so a list of objects carries the fields of
    each peer. Every other shape names peers: a UUID, an HFID, a list of either, or an object
    holding one of the keys a peer is named by.
    """
    if not isinstance(value, list):
        return True
    return any(not isinstance(item, dict) or item.keys() & PEER_REFERENCE_KEYS for item in value)


def _inline_peer_relationships(data: dict[str, Any], schema: MainSchemaTypesAPI) -> list[tuple[str, Any, str]]:
    """Return the key, the value and the peer kind of every relationship whose mutation takes the peers' fields."""
    found = []
    for key, value in data.items():
        rel_schema = schema.get_relationship_or_none(key)
        if rel_schema and peers_are_inline_input(rel_schema):
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
