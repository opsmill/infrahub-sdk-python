"""Relationships whose mutation takes the fields of their peers instead of a reference to one."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schema import RelationshipSchemaAPI

# The reason both the SDK and the CLI give for refusing an edit; each adds the way out of its own.
INLINE_INPUT_REASON = "the mutation takes the fields of a {peer} and not a reference to one"

INLINE_INPUT_PEERS_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "The peers of '{name}' cannot be edited one at a time, because " + INLINE_INPUT_REASON + ". "
    "To set them, pass the complete list of '{name}' to client.create() and save the node with "
    "allow_upsert=True, or create, update or delete the {peer} node itself."
)

# Keys that name an existing peer rather than carry its fields.
PEER_REFERENCE_KEYS = frozenset({"id", "hfid", "node"})

# The relationships concerned, by peer kind.
INLINE_INPUT_RELATIONSHIPS: dict[str, frozenset[str]] = {"CoreNumberPoolRange": frozenset({"ranges"})}


def peers_are_inline_input(schema: RelationshipSchemaAPI) -> bool:
    """Return whether a mutation takes this relationship's peers as fields instead of as references."""
    return schema.name in INLINE_INPUT_RELATIONSHIPS.get(schema.peer, frozenset())
