from __future__ import annotations

from .constants import HFID_STR_SEPARATOR
from .node import InfrahubNode, InfrahubNodeBase, InfrahubNodeSync
from .related_node import RelatedNode, RelatedNodeBase, RelatedNodeSync
from .relationship import RelationshipManager, RelationshipManagerBase, RelationshipManagerSync

__all__ = [
    "InfrahubNode",
    "InfrahubNodeBase",
    "InfrahubNodeSync",
    "RelatedNode",
    "RelatedNodeBase",
    "RelatedNodeSync",
    "RelationshipManager",
    "RelationshipManagerBase",
    "RelationshipManagerSync",
]


def parse_human_friendly_id(hfid: str | list[str]) -> tuple[str | None, list[str]]:
    """Parse a human friendly ID into a kind and an identifier."""
    if isinstance(hfid, str):
        hfid_parts = hfid.split(HFID_STR_SEPARATOR)
        if len(hfid_parts) == 1:
            return None, hfid_parts
        return hfid_parts[0], hfid_parts[1:]
    if isinstance(hfid, list):
        return None, hfid
    raise ValueError(f"Invalid human friendly ID: {hfid}")
