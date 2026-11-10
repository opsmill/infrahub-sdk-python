"""Dependencies between kinds through their mandatory relationships.

The server refuses to delete a node while another node holds it through a mandatory relationship,
and refuses to create a node before the nodes it must hold exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..topological_sort import dependents_first, strongly_connected_components

if TYPE_CHECKING:
    from . import MainSchemaTypesAPI


@dataclass
class PeerLookup:
    """The nodes of one kind whose mandatory peers must be read to order them among themselves.

    Attributes:
        kind: The kind of the nodes.
        ids: The ids of the nodes of that kind.
        relationships: The name of each mandatory relationship to read, mapped to whether it has cardinality many.

    """

    kind: str
    ids: list[str]
    relationships: dict[str, bool]


def _mandatory_peer_kinds(schema: MainSchemaTypesAPI, schemas: Mapping[str, MainSchemaTypesAPI]) -> dict[str, set[str]]:
    """The name of each mandatory relationship of `schema`, mapped to the kinds in `schemas` its peer can be.

    A peer that is a generic matches every kind in `schemas` that inherits from it.
    """
    peer_kinds: dict[str, set[str]] = {}
    for name in schema.mandatory_relationship_names:
        peer = schema.get_relationship(name).peer
        kinds = {
            kind
            for kind, peer_schema in schemas.items()
            if peer == kind or peer in getattr(peer_schema, "inherit_from", [])
        }
        if kinds:
            peer_kinds[name] = kinds
    return peer_kinds


class DeletionOrder:
    """Orders the nodes to delete so that no node is deleted while another one still holds it.

    The server refuses to delete a node that another node holds through a mandatory relationship, so
    the node that holds it has to be deleted first. Kinds are ordered from the schema alone. Nodes of
    the same kind, or of kinds that hold each other, can only be ordered from their actual peers, which
    `peer_lookups` names and `order` takes.

    A kind missing from the schema cannot be ordered, so its nodes go last.
    """

    def __init__(self, candidates: list[tuple[str, str]], schemas: Mapping[str, MainSchemaTypesAPI]) -> None:
        self.candidates = candidates
        kinds = list(dict.fromkeys(kind for kind, _ in candidates))
        self.kinds = [kind for kind in kinds if kind in schemas]
        self.unknown_kinds = {kind for kind in kinds if kind not in schemas}

        candidate_schemas = {kind: schemas[kind] for kind in self.kinds}
        self.relationships = {
            kind: _mandatory_peer_kinds(candidate_schemas[kind], candidate_schemas) for kind in self.kinds
        }
        self.cardinality_many = {
            kind: {
                name: candidate_schemas[kind].get_relationship(name).cardinality_is_many
                for name in self.relationships[kind]
            }
            for kind in self.kinds
        }
        self.graph: dict[str, set[str]] = {kind: set().union(*self.relationships[kind].values()) for kind in self.kinds}
        self.blocks = strongly_connected_components(graph=self.graph, order=self.kinds)

    def _is_cyclic(self, block: list[str]) -> bool:
        return len(block) > 1 or block[0] in self.graph[block[0]]

    @property
    def peer_lookups(self) -> list[PeerLookup]:
        """The nodes whose mandatory peers are needed, one entry per kind. Empty in the common case."""
        lookups: list[PeerLookup] = []
        for block in self.blocks:
            if not self._is_cyclic(block):
                continue
            block_kinds = set(block)
            # Every kind in a cyclic block has at least one mandatory relationship into the block.
            for kind in block:
                relationships = {
                    name: self.cardinality_many[kind][name]
                    for name, peer_kinds in self.relationships[kind].items()
                    if peer_kinds & block_kinds
                }
                ids = [node_id for node_kind, node_id in self.candidates if node_kind == kind]
                lookups.append(PeerLookup(kind=kind, ids=ids, relationships=relationships))
        return lookups

    def order(self, node_peers: Mapping[str, set[str]] | None = None) -> list[tuple[str, str]]:
        """The candidates in the order to delete them.

        Args:
            node_peers: The mandatory peer ids of each node named by `peer_lookups`.

        """
        node_peers = node_peers or {}
        block_key = {kind: block[0] for block in self.blocks for kind in block}
        block_graph = {
            block[0]: {block_key[peer_kind] for kind in block for peer_kind in self.graph[kind]} - {block[0]}
            for block in self.blocks
        }
        block_order = dependents_first(dependencies=block_graph, order=self.kinds) or []
        blocks = {block[0]: block for block in self.blocks}

        ordered: list[tuple[str, str]] = []
        for key in block_order:
            ordered.extend(self._order_block(block=blocks[key], node_peers=node_peers))
        ordered.extend(candidate for candidate in self.candidates if candidate[0] in self.unknown_kinds)
        return ordered

    def _order_block(self, block: list[str], node_peers: Mapping[str, set[str]]) -> list[tuple[str, str]]:
        block_kinds = set(block)
        nodes = [candidate for candidate in self.candidates if candidate[0] in block_kinds]
        if not self._is_cyclic(block):
            return nodes

        node_ids = [node_id for _, node_id in nodes]
        id_set = set(node_ids)
        dependencies = {node_id: (node_peers.get(node_id, set()) & id_set) - {node_id} for node_id in node_ids}
        # Nodes whose mandatory relationships form a cycle cannot be deleted in any order. Group
        # order lets the server refuse them while the other nodes are still deleted.
        ordered_ids = dependents_first(dependencies=dependencies, order=node_ids)
        if ordered_ids is None:
            return nodes
        kind_of = {node_id: kind for kind, node_id in nodes}
        return [(kind_of[node_id], node_id) for node_id in ordered_ids]
